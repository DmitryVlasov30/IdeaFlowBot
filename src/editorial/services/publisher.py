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
                telegram_message_id = await self.telegram_adapter.send_text(
                    bot_token=binding.bot_api_token,
                    channel_id=channel.tg_channel_id,
                    text=content_item.body_text,
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

