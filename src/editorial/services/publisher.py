from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.editorial.config import settings
from src.editorial.models.channel import Channel
from src.editorial.models.content import ContentItem
from src.editorial.models.enums import ContentItemStatus, PublicationStatus
from src.editorial.models.publication import PublicationLog
from src.editorial.models.submission import Submission
from src.editorial.services.legacy_source import LegacyCollectorReader
from src.editorial.services.paste_service import PasteService
from src.editorial.services.telegram_publisher import TelegramPublisherAdapter


@dataclass(slots=True)
class PublisherRunResult:
    attempted: int = 0
    sent: int = 0
    failed: int = 0


class PublisherService:
    def __init__(
        self,
        telegram_adapter: TelegramPublisherAdapter | None = None,
        legacy_reader: LegacyCollectorReader | None = None,
        paste_service: PasteService | None = None,
    ) -> None:
        self.telegram_adapter = telegram_adapter or TelegramPublisherAdapter()
        self.legacy_reader = legacy_reader or LegacyCollectorReader()
        self.paste_service = paste_service or PasteService()

    @staticmethod
    def _submission_author_signature(submission: Submission) -> str:
        return f"@{submission.username}" if submission.username else "@None"

    def _append_author_signature(self, text: str, submission: Submission) -> str:
        if submission.is_anonymous:
            return text
        signature = self._submission_author_signature(submission)
        return f"{text}\n\n{signature}" if text else signature

    @staticmethod
    def _get_related_submission_source_text(related_rows: list[Submission]) -> str:
        for item in related_rows:
            text_value = (item.cleaned_text or item.raw_text or "").strip()
            if text_value:
                return text_value
        return ""

    async def _publish_submission_based_item(
        self,
        session: AsyncSession,
        content_item: ContentItem,
        channel: Channel,
        bot_token: str,
    ) -> int:
        if content_item.origin_submission_id is None:
            return await self.telegram_adapter.send_text(
                bot_token=bot_token,
                channel_id=channel.tg_channel_id,
                text=content_item.body_text,
            )

        submission = await session.get(Submission, content_item.origin_submission_id)
        if submission is None:
            raise ValueError(f"Submission {content_item.origin_submission_id} not found")

        related_rows = [submission]

        if submission.media_group_id:
            stmt = (
                select(Submission)
                .where(
                    Submission.channel_id == submission.channel_id,
                    Submission.media_group_id == submission.media_group_id,
                )
                .order_by(Submission.source_message_id.asc(), Submission.id.asc())
            )
            if submission.source_chat_id is not None:
                stmt = stmt.where(Submission.source_chat_id == submission.source_chat_id)
            related_rows = list(((await session.execute(stmt)).scalars().all()))
            message_ids = [
                int(item.source_message_id)
                for item in related_rows
                if item.source_message_id is not None
            ]
            if submission.source_chat_id is None or not message_ids:
                raise ValueError("Media group submission has no source chat or message ids")
            telegram_message_id = await self.telegram_adapter.copy_messages(
                bot_token=bot_token,
                channel_id=channel.tg_channel_id,
                from_chat_id=int(submission.source_chat_id),
                message_ids=message_ids,
            )
            if not submission.is_anonymous:
                await self.telegram_adapter.send_text(
                    bot_token=bot_token,
                    channel_id=channel.tg_channel_id,
                    text=self._submission_author_signature(submission),
                )
            return telegram_message_id

        if submission.content_type in {"photo", "video", "animation"}:
            if submission.source_chat_id is None or submission.source_message_id is None:
                raise ValueError("Media submission has no source chat or message id")
            source_text = self._get_related_submission_source_text(related_rows)
            caption_text = content_item.body_text.strip()
            if not source_text and caption_text.startswith("<") and caption_text.endswith(">"):
                caption_text = ""
            return await self.telegram_adapter.copy_message(
                bot_token=bot_token,
                channel_id=channel.tg_channel_id,
                from_chat_id=int(submission.source_chat_id),
                message_id=int(submission.source_message_id),
                caption=self._append_author_signature(caption_text, submission) or None,
            )

        return await self.telegram_adapter.send_text(
            bot_token=bot_token,
            channel_id=channel.tg_channel_id,
            text=self._append_author_signature(content_item.body_text, submission),
        )

    async def run(
        self,
        session: AsyncSession,
        now: datetime | None = None,
        limit: int | None = None,
    ) -> PublisherRunResult:
        now = now or datetime.now(timezone.utc)
        result = PublisherRunResult()

        scheduled_logs = list(
            (
                await session.execute(
                    select(PublicationLog)
                    .where(
                        PublicationLog.publish_status == PublicationStatus.SCHEDULED,
                        PublicationLog.scheduled_for <= now,
                    )
                    .order_by(PublicationLog.scheduled_for.asc())
                    .limit(limit or settings.publisher_batch_size)
                    # Protect against concurrent manual/background publisher runs.
                    # Once one session claims these rows, others skip them until commit.
                    .with_for_update(skip_locked=True)
                )
            ).scalars().all()
        )

        for log_item in scheduled_logs:
            result.attempted += 1
            content_item = await session.get(ContentItem, log_item.content_item_id)
            channel = await session.get(Channel, log_item.channel_id)
            if content_item is None or channel is None:
                log_item.publish_status = PublicationStatus.FAILED
                log_item.error_text = "Missing content item or channel"
                result.failed += 1
                continue

            binding = await self.legacy_reader.get_bot_binding(channel.tg_channel_id)
            if binding is None:
                log_item.publish_status = PublicationStatus.FAILED
                log_item.error_text = f"Legacy bot binding for channel {channel.tg_channel_id} not found"
                content_item.status = ContentItemStatus.APPROVED
                result.failed += 1
                continue

            try:
                telegram_message_id = await self._publish_submission_based_item(
                    session=session,
                    content_item=content_item,
                    channel=channel,
                    bot_token=binding.bot_api_token,
                )
                log_item.telegram_message_id = telegram_message_id
                log_item.publish_status = PublicationStatus.SENT
                log_item.published_at = now
                content_item.status = ContentItemStatus.PUBLISHED
                if content_item.origin_paste_id is not None:
                    await self.paste_service.register_usage(
                        session=session,
                        paste_id=content_item.origin_paste_id,
                        channel_id=channel.id,
                        content_item_id=content_item.id,
                    )
                result.sent += 1
            except Exception as ex:
                logger.exception("Failed to publish content item {}", content_item.id)
                log_item.publish_status = PublicationStatus.FAILED
                log_item.error_text = str(ex)
                content_item.status = ContentItemStatus.APPROVED
                result.failed += 1

        await session.commit()
        return result
