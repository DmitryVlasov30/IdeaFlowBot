from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.editorial.config import settings
from src.editorial.models.channel import Channel
from src.editorial.models.content import ContentItem
from src.editorial.models.enums import ContentItemStatus, PublicationStatus
from src.editorial.models.publication import PublicationLog
from src.editorial.models.submission import Submission
from src.editorial.services.legacy_source import LegacyCollectorReader, LegacySenderRow
from src.editorial.services.paste_service import PasteService
from src.editorial.services.telegram_publisher import TelegramPublisherAdapter
from src.editorial.utils.text import clean_text, normalize_text


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
    def _can_copy_submission_verbatim(
        submission: Submission,
        content_item: ContentItem,
        source_text: str,
    ) -> bool:
        if submission.source_chat_id is None or submission.source_message_id is None:
            return False
        source_text_clean = clean_text(source_text)
        body_text_clean = clean_text(content_item.body_text or "")

        if submission.content_type == "text":
            return bool(source_text_clean) and source_text_clean == body_text_clean

        if submission.content_type in {"photo", "video", "animation"}:
            if source_text_clean:
                return source_text_clean == body_text_clean
            body_text = (content_item.body_text or "").strip()
            return not body_text or (body_text.startswith("<") and body_text.endswith(">"))

        return False

    @staticmethod
    def _get_related_submission_source_text(related_rows: list[Submission]) -> str:
        for item in related_rows:
            text_value = (item.cleaned_text or item.raw_text or "").strip()
            if text_value:
                return text_value
        return ""

    async def _get_related_legacy_rows(self, related_rows: list[Submission]) -> list[LegacySenderRow]:
        legacy_row_ids = [item.legacy_row_id for item in related_rows if item.legacy_row_id is not None]
        if not legacy_row_ids:
            return []
        legacy_rows = await self.legacy_reader.fetch_sender_rows_by_ids(legacy_row_ids)
        row_map = {row.id: row for row in legacy_rows}
        return [row_map[item.legacy_row_id] for item in related_rows if item.legacy_row_id in row_map]

    @staticmethod
    def _pick_single_copy_source(
        submission: Submission,
        legacy_row: LegacySenderRow | None,
    ) -> tuple[int, int]:
        if legacy_row and legacy_row.review_chat_id is not None and legacy_row.review_message_id is not None:
            return int(legacy_row.review_chat_id), int(legacy_row.review_message_id)
        if submission.source_chat_id is None or submission.source_message_id is None:
            raise ValueError("Submission has no source chat or message id")
        return int(submission.source_chat_id), int(submission.source_message_id)

    @staticmethod
    def _parse_entities_json(legacy_row: LegacySenderRow | None) -> list[dict] | None:
        if legacy_row is None or not legacy_row.entities_json:
            return None
        try:
            entities = json.loads(legacy_row.entities_json)
        except json.JSONDecodeError:
            return None
        return entities if isinstance(entities, list) and entities else None

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
        related_legacy_rows = await self._get_related_legacy_rows(related_rows)

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
            related_legacy_rows = await self._get_related_legacy_rows(related_rows)
            review_rows = [
                row for row in related_legacy_rows
                if row.review_chat_id is not None and row.review_message_id is not None
            ]
            if len(review_rows) == len(related_rows) and len({row.review_chat_id for row in review_rows}) == 1:
                from_chat_id = int(review_rows[0].review_chat_id)
                message_ids = [int(row.review_message_id) for row in review_rows]
            else:
                message_ids = [
                    int(item.source_message_id)
                    for item in related_rows
                    if item.source_message_id is not None
                ]
                if submission.source_chat_id is None or not message_ids:
                    raise ValueError("Media group submission has no source chat or message ids")
                from_chat_id = int(submission.source_chat_id)
            telegram_message_id = await self.telegram_adapter.copy_messages(
                bot_token=bot_token,
                channel_id=channel.tg_channel_id,
                from_chat_id=from_chat_id,
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
            source_text = self._get_related_submission_source_text(related_rows)
            if self._can_copy_submission_verbatim(submission, content_item, source_text):
                from_chat_id, message_id = self._pick_single_copy_source(
                    submission=submission,
                    legacy_row=related_legacy_rows[0] if related_legacy_rows else None,
                )
                telegram_message_id = await self.telegram_adapter.copy_message(
                    bot_token=bot_token,
                    channel_id=channel.tg_channel_id,
                    from_chat_id=from_chat_id,
                    message_id=message_id,
                )
                logger.info(
                    "Published content item {} via copy_message from {}:{}",
                    content_item.id,
                    from_chat_id,
                    message_id,
                )
                if not submission.is_anonymous:
                    await self.telegram_adapter.send_text(
                        bot_token=bot_token,
                        channel_id=channel.tg_channel_id,
                        text=self._submission_author_signature(submission),
                    )
                return telegram_message_id
            caption_text = content_item.body_text.strip()
            if not source_text and caption_text.startswith("<") and caption_text.endswith(">"):
                caption_text = ""
            if submission.source_chat_id is None or submission.source_message_id is None:
                raise ValueError("Media submission has no source chat or message id")
            return await self.telegram_adapter.copy_message(
                bot_token=bot_token,
                channel_id=channel.tg_channel_id,
                from_chat_id=int(submission.source_chat_id),
                message_id=int(submission.source_message_id),
                caption=self._append_author_signature(caption_text, submission) or None,
            )

        source_text = self._get_related_submission_source_text(related_rows)
        if self._can_copy_submission_verbatim(submission, content_item, source_text):
            legacy_row = related_legacy_rows[0] if related_legacy_rows else None
            entities = self._parse_entities_json(legacy_row)
            source_text_value = (legacy_row.text_post if legacy_row and legacy_row.text_post is not None else source_text)
            from_chat_id, message_id = self._pick_single_copy_source(
                submission=submission,
                legacy_row=legacy_row,
            )
            try:
                telegram_message_id = await self.telegram_adapter.copy_message(
                    bot_token=bot_token,
                    channel_id=channel.tg_channel_id,
                    from_chat_id=from_chat_id,
                    message_id=message_id,
                )
                logger.info(
                    "Published content item {} via text copy_message from {}:{}",
                    content_item.id,
                    from_chat_id,
                    message_id,
                )
                if not submission.is_anonymous:
                    await self.telegram_adapter.send_text(
                        bot_token=bot_token,
                        channel_id=channel.tg_channel_id,
                        text=self._submission_author_signature(submission),
                    )
                return telegram_message_id
            except Exception as ex:
                logger.warning(
                    "Text copy_message failed for content item {} from {}:{}: {}",
                    content_item.id,
                    from_chat_id,
                    message_id,
                    ex,
                )
                if entities:
                    telegram_message_id = await self.telegram_adapter.send_text_with_entities(
                        bot_token=bot_token,
                        channel_id=channel.tg_channel_id,
                        text=source_text_value,
                        entities=entities,
                    )
                    logger.info(
                        "Published content item {} via send_text_with_entities fallback (entities={}, legacy_row={})",
                        content_item.id,
                        len(entities),
                        legacy_row.id if legacy_row else None,
                    )
                    if not submission.is_anonymous:
                        await self.telegram_adapter.send_text(
                            bot_token=bot_token,
                            channel_id=channel.tg_channel_id,
                            text=self._submission_author_signature(submission),
                        )
                    return telegram_message_id

        telegram_message_id = await self.telegram_adapter.send_text(
            bot_token=bot_token,
            channel_id=channel.tg_channel_id,
            text=self._append_author_signature(content_item.body_text, submission),
        )
        logger.info(
            "Published content item {} via plain send_text fallback",
            content_item.id,
        )
        return telegram_message_id

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
