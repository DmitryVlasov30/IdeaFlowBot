from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select
from telebot.async_telebot import AsyncTeleBot

from src.editorial.db.session import session_factory
from src.editorial.models.channel import Channel
from src.editorial.models.content import ContentItem
from src.editorial.models.enums import ContentItemStatus, PasteStatus, PublicationStatus, ReviewDecision, SubmissionStatus
from src.editorial.models.paste import PasteLibrary
from src.editorial.models.publication import PublicationLog
from src.editorial.models.submission import Submission
from src.editorial.services.channel_service import ChannelService
from src.editorial.services.import_legacy import LegacyImporter
from src.editorial.services.legacy_source import LegacyCollectorReader
from src.editorial.services.moderation import ModerationService
from src.editorial.services.paste_service import PasteService
from src.editorial.services.publisher import PublisherService
from src.editorial.services.scheduler import SchedulerService


@dataclass(slots=True)
class SubmissionPreview:
    channel_tg_id: int
    review_chat_id: int
    review_message_ids: list[int]
    preview_file_ids: list[str]
    preview_file_sizes: list[int]
    preview_content_types: list[str]
    content_type: str
    media_group_id: str | None


class TelegramEditorialActions:
    def __init__(self) -> None:
        self.importer = LegacyImporter()
        self.legacy_reader = LegacyCollectorReader()
        self.moderation = ModerationService()
        self.paste_service = PasteService()
        self.channel_service = ChannelService()
        self.scheduler = SchedulerService()
        self.publisher = PublisherService()

    async def import_new(self):
        async with session_factory() as session:
            return await self.importer.import_new(session)

    async def list_channels(self) -> list[Channel]:
        async with session_factory() as session:
            return await self.channel_service.list_channels(session)

    async def get_channel(self, channel_id: int) -> Channel | None:
        async with session_factory() as session:
            return await self.channel_service.get_channel(session, channel_id)

    async def list_channel_slots(self, channel_id: int):
        async with session_factory() as session:
            return await self.channel_service.list_channel_slots(session, channel_id)

    async def seed_default_slots(self, channel_id: int) -> int:
        async with session_factory() as session:
            created = await self.channel_service.seed_daily_slots(
                session=session,
                channel_id=channel_id,
                slot_times=["10:00", "15:00", "20:00"],
                weekdays=[0, 1, 2, 3, 4, 5, 6],
            )
            return len(created)

    async def add_slots(self, channel_id: int, slot_times: Iterable[str], weekdays: Iterable[int]) -> int:
        async with session_factory() as session:
            created = await self.channel_service.seed_daily_slots(
                session=session,
                channel_id=channel_id,
                slot_times=list(slot_times),
                weekdays=list(weekdays),
            )
            return len(created)

    async def remove_slot(self, slot_id: int):
        async with session_factory() as session:
            return await self.channel_service.delete_slot(session, slot_id)

    async def remove_slots(self, channel_id: int, slot_times: Iterable[str], weekdays: Iterable[int]) -> int:
        async with session_factory() as session:
            removed = await self.channel_service.delete_slots(
                session=session,
                channel_id=channel_id,
                slot_times=list(slot_times),
                weekdays=list(weekdays),
            )
            return len(removed)

    async def list_pending_submissions(self) -> list[Submission]:
        async with session_factory() as session:
            stmt = (
                select(Submission)
                .where(Submission.status.in_([SubmissionStatus.NEW, SubmissionStatus.HOLD]))
                .order_by(Submission.created_at.asc())
                .limit(50)
            )
            items = list((await session.execute(stmt)).scalars().all())
            return self.moderation.collapse_media_groups(items)

    async def list_recent_submissions(self, limit: int | None = None) -> list[Submission]:
        async with session_factory() as session:
            items = await self.moderation.list_submissions(session=session, status=None, limit=limit)
            return self.moderation.collapse_media_groups(items)

    async def get_submission(self, submission_id: int) -> Submission | None:
        async with session_factory() as session:
            return await session.get(Submission, submission_id)

    async def set_submission_anonymous(self, submission_id: int, is_anonymous: bool) -> Submission:
        async with session_factory() as session:
            submission = await session.get(Submission, submission_id)
            if submission is None:
                raise ValueError(f"Submission {submission_id} not found")
            related = await self.moderation.get_related_submissions(session, submission)
            for item in related:
                item.is_anonymous = is_anonymous
            await session.commit()
            await session.refresh(submission)
            return submission

    async def get_submission_preview(self, submission_id: int) -> SubmissionPreview | None:
        async with session_factory() as session:
            submission = await session.get(Submission, submission_id)
            if submission is None:
                return None
            related_submissions = await self.moderation.get_related_submissions(session, submission)
            legacy_row_ids = [item.legacy_row_id for item in related_submissions if item.legacy_row_id is not None]
            legacy_rows = await self.legacy_reader.fetch_sender_rows_by_ids(legacy_row_ids)
            preview_rows = [
                row for row in legacy_rows
                if row.review_chat_id is not None and row.review_message_id is not None
            ]
            channel = await session.get(Channel, submission.channel_id)
            if not preview_rows or channel is None:
                return None
            review_chat_id = int(preview_rows[0].review_chat_id)
            review_message_ids = [int(row.review_message_id) for row in preview_rows]
            preview_file_ids = [row.preview_file_id for row in preview_rows if row.preview_file_id]
            preview_file_sizes = [int(row.preview_file_size or 0) for row in preview_rows if row.preview_file_id]
            preview_content_types = [row.content_type or "photo" for row in preview_rows if row.preview_file_id]
            return SubmissionPreview(
                channel_tg_id=int(channel.tg_channel_id),
                review_chat_id=review_chat_id,
                review_message_ids=sorted(set(review_message_ids)),
                preview_file_ids=preview_file_ids,
                preview_file_sizes=preview_file_sizes,
                preview_content_types=preview_content_types,
                content_type=submission.content_type,
                media_group_id=submission.media_group_id,
            )

    async def get_submission_primary_content_item(self, submission_id: int) -> ContentItem | None:
        priority_order = {
            ContentItemStatus.PUBLISHED: 0,
            ContentItemStatus.SCHEDULED: 1,
            ContentItemStatus.APPROVED: 2,
            ContentItemStatus.PENDING_REVIEW: 3,
            ContentItemStatus.HOLD: 4,
            ContentItemStatus.REJECTED: 5,
            ContentItemStatus.DRAFT: 6,
        }

        async with session_factory() as session:
            submission = await session.get(Submission, submission_id)
            if submission is None:
                return None
            related_submissions = await self.moderation.get_related_submissions(session, submission)
            submission_ids = [item.id for item in related_submissions]
            items = list(
                (
                    await session.execute(
                        select(ContentItem)
                        .where(ContentItem.origin_submission_id.in_(submission_ids))
                        .order_by(ContentItem.created_at.desc())
                    )
                ).scalars().all()
            )
            if not items:
                return None
            return min(
                items,
                key=lambda item: (
                    priority_order.get(item.status, 99),
                    -(item.id or 0),
                ),
            )

    async def approve_submission(self, submission_id: int, reviewer_id: int) -> ContentItem:
        async with session_factory() as session:
            item = await self._get_or_create_content_item(session, submission_id)
            if item.status != ContentItemStatus.APPROVED:
                item = await self.moderation.review_content_item(
                    session=session,
                    content_item_id=item.id,
                    reviewer_id=reviewer_id,
                    decision=ReviewDecision.APPROVE,
                    review_note="Approved in Telegram panel",
                )
            return item

    async def publish_submission_now(self, submission_id: int, reviewer_id: int) -> PublicationLog:
        async with session_factory() as session:
            item = await self._get_or_create_content_item(session, submission_id)
            if item.status != ContentItemStatus.APPROVED:
                item = await self.moderation.review_content_item(
                    session=session,
                    content_item_id=item.id,
                    reviewer_id=reviewer_id,
                    decision=ReviewDecision.APPROVE,
                    review_note="Approved and published in Telegram panel",
                )
            log_item = await self._schedule_now(session, item)
            await self.publisher.run(session, now=datetime.now(timezone.utc), limit=20)
            return log_item

    async def reject_submission(self, submission_id: int, note: str = "Rejected in Telegram panel") -> Submission:
        async with session_factory() as session:
            return await self.moderation.set_submission_status(
                session=session,
                submission_id=submission_id,
                status=SubmissionStatus.REJECTED,
                moderator_note=note,
            )

    async def hold_submission(self, submission_id: int, note: str = "Hold in Telegram panel") -> Submission:
        async with session_factory() as session:
            return await self.moderation.set_submission_status(
                session=session,
                submission_id=submission_id,
                status=SubmissionStatus.HOLD,
                moderator_note=note,
            )

    async def paste_submission(self, submission_id: int, reviewer_id: int):
        async with session_factory() as session:
            return await self.paste_service.create_paste_from_submission(
                session=session,
                submission_id=submission_id,
                created_by=reviewer_id,
            )

    async def reply_to_submission_author(self, submission_id: int, text: str) -> None:
        async with session_factory() as session:
            submission = await session.get(Submission, submission_id)
            if submission is None:
                raise ValueError(f"Submission {submission_id} not found")
            if submission.source_user_id is None:
                raise ValueError("Submission has no source user id")
            channel = await session.get(Channel, submission.channel_id)
            if channel is None:
                raise ValueError(f"Channel {submission.channel_id} not found")

        binding = await self.legacy_reader.get_bot_binding(channel.tg_channel_id)
        if binding is None:
            raise ValueError(f"Legacy bot binding for channel {channel.tg_channel_id} not found")

        bot = AsyncTeleBot(binding.bot_api_token)
        await bot.send_message(chat_id=submission.source_user_id, text=text)

    async def send_submission_advertising_reply(self, submission_id: int) -> None:
        await self.reply_to_submission_author(
            submission_id,
            "По рекламе напишите пожалуйста @ivanblk, сразу укажите, что вы хотите рекламировать",
        )

    async def list_pending_content_items(self) -> list[ContentItem]:
        async with session_factory() as session:
            stmt = (
                select(ContentItem)
                .where(ContentItem.status == ContentItemStatus.PENDING_REVIEW)
                .order_by(ContentItem.created_at.asc())
                .limit(50)
            )
            return list((await session.execute(stmt)).scalars().all())

    async def get_content_item(self, content_item_id: int) -> ContentItem | None:
        async with session_factory() as session:
            return await session.get(ContentItem, content_item_id)

    async def list_pastes(self, limit: int | None = None) -> list[PasteLibrary]:
        async with session_factory() as session:
            return await self.paste_service.list_pastes(session=session, status=None, limit=limit)

    async def get_paste(self, paste_id: int) -> PasteLibrary | None:
        async with session_factory() as session:
            return await session.get(PasteLibrary, paste_id)

    async def create_manual_paste(self, body_text: str, reviewer_id: int, title: str | None = None) -> PasteLibrary:
        clean_title = (title or body_text.strip().splitlines()[0][:60] or "Manual paste").strip()
        async with session_factory() as session:
            return await self.paste_service.create_manual_paste(
                session=session,
                title=clean_title,
                body_text=body_text.strip(),
                created_by=reviewer_id,
                status=PasteStatus.ACTIVE,
            )

    async def archive_paste(self, paste_id: int) -> PasteLibrary:
        async with session_factory() as session:
            return await self.paste_service.archive_paste(session=session, paste_id=paste_id)

    async def approve_content_item(self, content_item_id: int, reviewer_id: int) -> ContentItem:
        async with session_factory() as session:
            return await self.moderation.review_content_item(
                session=session,
                content_item_id=content_item_id,
                reviewer_id=reviewer_id,
                decision=ReviewDecision.APPROVE,
                review_note="Approved in Telegram panel",
            )

    async def publish_content_item_now(self, content_item_id: int, reviewer_id: int) -> PublicationLog:
        async with session_factory() as session:
            item = await session.get(ContentItem, content_item_id)
            if item is None:
                raise ValueError(f"Content item {content_item_id} not found")
            if item.status != ContentItemStatus.APPROVED:
                item = await self.moderation.review_content_item(
                    session=session,
                    content_item_id=item.id,
                    reviewer_id=reviewer_id,
                    decision=ReviewDecision.APPROVE,
                    review_note="Approved and published in Telegram panel",
                )
            log_item = await self._schedule_now(session, item)
            await self.publisher.run(session, now=datetime.now(timezone.utc), limit=20)
            return log_item

    async def reject_content_item(self, content_item_id: int, reviewer_id: int) -> ContentItem:
        async with session_factory() as session:
            return await self.moderation.review_content_item(
                session=session,
                content_item_id=content_item_id,
                reviewer_id=reviewer_id,
                decision=ReviewDecision.REJECT,
                review_note="Rejected in Telegram panel",
            )

    async def hold_content_item(self, content_item_id: int, reviewer_id: int) -> ContentItem:
        async with session_factory() as session:
            return await self.moderation.review_content_item(
                session=session,
                content_item_id=content_item_id,
                reviewer_id=reviewer_id,
                decision=ReviewDecision.HOLD,
                review_note="Hold in Telegram panel",
            )

    async def run_scheduler(self):
        async with session_factory() as session:
            return await self.scheduler.run(session)

    async def run_publisher(self):
        async with session_factory() as session:
            return await self.publisher.run(session)

    async def _get_or_create_content_item(self, session, submission_id: int) -> ContentItem:
        submission = await session.get(Submission, submission_id)
        if submission is None:
            raise ValueError(f"Submission {submission_id} not found")

        related_submissions = await self.moderation.get_related_submissions(session, submission)
        submission_ids = [item.id for item in related_submissions]
        existing = await session.scalar(
            select(ContentItem)
            .where(ContentItem.origin_submission_id.in_(submission_ids))
            .order_by(ContentItem.created_at.desc())
            .limit(1)
        )
        if existing is not None:
            return existing

        return await self.moderation.create_content_from_submission(
            session=session,
            submission_id=submission_id,
            channel_id=submission.channel_id,
            status=ContentItemStatus.PENDING_REVIEW,
        )

    async def _schedule_now(self, session, item: ContentItem) -> PublicationLog:
        now = datetime.now(timezone.utc)
        existing = await session.scalar(
            select(PublicationLog)
            .where(
                PublicationLog.content_item_id == item.id,
                PublicationLog.publish_status == PublicationStatus.SCHEDULED,
            )
            .limit(1)
        )
        if existing is not None:
            return existing

        item.status = ContentItemStatus.SCHEDULED
        item.scheduled_for = now
        log_item = PublicationLog(
            content_item_id=item.id,
            channel_id=item.channel_id,
            scheduled_for=now,
            publish_status=PublicationStatus.SCHEDULED,
            created_at=now,
        )
        session.add(log_item)
        await session.commit()
        await session.refresh(log_item)
        return log_item
