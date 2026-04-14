from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from src.editorial.db.session import session_factory
from src.editorial.models.channel import Channel
from src.editorial.models.content import ContentItem
from src.editorial.models.enums import ContentItemStatus, PublicationStatus, ReviewDecision, SubmissionStatus
from src.editorial.models.publication import PublicationLog
from src.editorial.models.submission import Submission
from src.editorial.services.channel_service import ChannelService
from src.editorial.services.import_legacy import LegacyImporter
from src.editorial.services.moderation import ModerationService
from src.editorial.services.paste_service import PasteService
from src.editorial.services.publisher import PublisherService
from src.editorial.services.scheduler import SchedulerService


class TelegramEditorialActions:
    def __init__(self) -> None:
        self.importer = LegacyImporter()
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

    async def seed_default_slots(self, channel_id: int) -> int:
        async with session_factory() as session:
            created = await self.channel_service.seed_daily_slots(
                session=session,
                channel_id=channel_id,
                slot_times=["10:00", "15:00", "20:00"],
                weekdays=[0, 1, 2, 3, 4, 5, 6],
            )
            return len(created)

    async def list_pending_submissions(self) -> list[Submission]:
        async with session_factory() as session:
            stmt = (
                select(Submission)
                .where(Submission.status.in_([SubmissionStatus.NEW, SubmissionStatus.HOLD]))
                .order_by(Submission.created_at.asc())
                .limit(50)
            )
            return list((await session.execute(stmt)).scalars().all())

    async def get_submission(self, submission_id: int) -> Submission | None:
        async with session_factory() as session:
            return await session.get(Submission, submission_id)

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

        existing = await session.scalar(
            select(ContentItem)
            .where(ContentItem.origin_submission_id == submission_id)
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

