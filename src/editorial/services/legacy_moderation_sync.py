from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select

from src.editorial.db.session import session_factory
from src.editorial.models.content import ContentItem
from src.editorial.models.enums import ContentItemStatus, PublicationStatus, SubmissionStatus
from src.editorial.models.publication import PublicationLog
from src.editorial.models.submission import Submission
from src.editorial.services.import_legacy import LegacyImporter
from src.editorial.services.legacy_audit import (
    LEGACY_DELAYED_AUDIT_LOG_MARKER,
    LEGACY_DELAYED_AUDIT_TEMPLATE_KEY,
)
from src.editorial.services.legacy_source import LegacyCollectorReader
from src.editorial.services.moderation import ModerationService


class LegacyModerationSyncService:
    def __init__(
        self,
        legacy_reader: LegacyCollectorReader | None = None,
        importer: LegacyImporter | None = None,
        moderation: ModerationService | None = None,
    ) -> None:
        self.legacy_reader = legacy_reader or LegacyCollectorReader()
        self.importer = importer or LegacyImporter(self.legacy_reader)
        self.moderation = moderation or ModerationService()

    async def set_status_for_review_message(
        self,
        *,
        channel_tg_id: int,
        review_chat_id: int,
        review_message_id: int,
        status: SubmissionStatus,
        moderator_note: str | None = None,
        legacy_scheduled_for: datetime | None = None,
    ) -> bool:
        async with session_factory() as session:
            row = await self.legacy_reader.find_sender_row_by_review_message(
                channel_id=channel_tg_id,
                review_chat_id=review_chat_id,
                review_message_id=review_message_id,
            )
            if row is None:
                return False

            submission = await self.importer.ensure_submission_for_legacy_row(session, row)
            if submission is None:
                return False

            if legacy_scheduled_for is not None and status == SubmissionStatus.CONTENT_CREATED:
                await self._upsert_legacy_delayed_audit(
                    session=session,
                    submission=submission,
                    scheduled_for=legacy_scheduled_for,
                    moderator_note=moderator_note,
                )
                return True

            await self.moderation.set_submission_status(
                session=session,
                submission_id=submission.id,
                status=status,
                moderator_note=moderator_note,
            )
            if status == SubmissionStatus.REJECTED:
                await self._cancel_legacy_delayed_audit(
                    session=session,
                    submission=submission,
                )
            return True

    async def mark_legacy_delayed_published(
        self,
        *,
        channel_tg_id: int,
        review_chat_id: int,
        review_message_id: int,
        telegram_message_id: int | None = None,
    ) -> bool:
        async with session_factory() as session:
            row = await self.legacy_reader.find_sender_row_by_review_message(
                channel_id=channel_tg_id,
                review_chat_id=review_chat_id,
                review_message_id=review_message_id,
            )
            if row is None:
                return False

            submission = await self.importer.ensure_submission_for_legacy_row(session, row)
            if submission is None:
                return False

            audit_item = await self._get_legacy_delayed_audit_item(session, submission)
            if audit_item is None:
                audit_item = await self._upsert_legacy_delayed_audit(
                    session=session,
                    submission=submission,
                    scheduled_for=datetime.now(timezone.utc),
                    moderator_note="Handled in legacy moderation: delayed published",
                )

            now = datetime.now(timezone.utc)
            audit_item.status = ContentItemStatus.PUBLISHED
            if audit_item.scheduled_for is None:
                audit_item.scheduled_for = now

            log_item = await self._get_legacy_delayed_audit_log(session, audit_item.id)
            if log_item is None:
                log_item = PublicationLog(
                    content_item_id=audit_item.id,
                    channel_id=audit_item.channel_id,
                    scheduled_for=audit_item.scheduled_for or now,
                    publish_status=PublicationStatus.SENT,
                    created_at=now,
                    error_text=LEGACY_DELAYED_AUDIT_LOG_MARKER,
                )
                session.add(log_item)

            log_item.publish_status = PublicationStatus.SENT
            log_item.published_at = now
            log_item.telegram_message_id = telegram_message_id
            log_item.error_text = None

            related = await self.moderation.get_related_submissions(session, submission)
            for item in related:
                item.status = SubmissionStatus.CONTENT_CREATED
                item.reviewed_at = now
                item.moderator_note = "Handled in legacy moderation: delayed published"

            await session.commit()
            return True

    async def _upsert_legacy_delayed_audit(
        self,
        *,
        session,
        submission: Submission,
        scheduled_for: datetime,
        moderator_note: str | None,
    ) -> ContentItem:
        scheduled_for = scheduled_for.astimezone(timezone.utc)
        audit_item = await self._get_legacy_delayed_audit_item(session, submission)
        if audit_item is None:
            audit_item = await self.moderation.create_content_from_submission(
                session=session,
                submission_id=submission.id,
                channel_id=submission.channel_id,
                status=ContentItemStatus.SCHEDULED,
                review_required=False,
                template_key=LEGACY_DELAYED_AUDIT_TEMPLATE_KEY,
                tone_key="legacy_moderation",
                scheduled_for=scheduled_for,
            )

        audit_item.status = ContentItemStatus.SCHEDULED
        audit_item.scheduled_for = scheduled_for
        audit_item.review_required = False
        audit_item.template_key = LEGACY_DELAYED_AUDIT_TEMPLATE_KEY
        audit_item.tone_key = "legacy_moderation"

        log_item = await self._get_legacy_delayed_audit_log(session, audit_item.id)
        if log_item is None:
            log_item = PublicationLog(
                content_item_id=audit_item.id,
                channel_id=audit_item.channel_id,
                scheduled_for=scheduled_for,
                publish_status=PublicationStatus.SCHEDULED,
                created_at=datetime.now(timezone.utc),
                error_text=LEGACY_DELAYED_AUDIT_LOG_MARKER,
            )
            session.add(log_item)
        else:
            log_item.scheduled_for = scheduled_for
            log_item.publish_status = PublicationStatus.SCHEDULED
            log_item.published_at = None
            log_item.telegram_message_id = None
            log_item.error_text = LEGACY_DELAYED_AUDIT_LOG_MARKER

        reviewed_at = datetime.now(timezone.utc)
        related = await self.moderation.get_related_submissions(session, submission)
        for item in related:
            item.status = SubmissionStatus.CONTENT_CREATED
            item.reviewed_at = reviewed_at
            item.moderator_note = moderator_note

        await session.commit()
        await session.refresh(audit_item)
        return audit_item

    async def _cancel_legacy_delayed_audit(
        self,
        *,
        session,
        submission: Submission,
    ) -> None:
        audit_item = await self._get_legacy_delayed_audit_item(session, submission)
        if audit_item is None:
            return

        audit_item.status = ContentItemStatus.REJECTED
        audit_item.scheduled_for = None

        log_item = await self._get_legacy_delayed_audit_log(session, audit_item.id)
        if log_item is not None and log_item.publish_status == PublicationStatus.SCHEDULED:
            log_item.publish_status = PublicationStatus.CANCELLED
            log_item.error_text = "Legacy delayed publication rejected"

        await session.commit()

    async def _get_legacy_delayed_audit_item(
        self,
        session,
        submission: Submission,
    ) -> ContentItem | None:
        related = await self.moderation.get_related_submissions(session, submission)
        submission_ids = [item.id for item in related]
        return await session.scalar(
            select(ContentItem)
            .where(
                ContentItem.origin_submission_id.in_(submission_ids),
                ContentItem.template_key == LEGACY_DELAYED_AUDIT_TEMPLATE_KEY,
            )
            .order_by(ContentItem.created_at.desc())
            .limit(1)
        )

    @staticmethod
    async def _get_legacy_delayed_audit_log(session, content_item_id: int) -> PublicationLog | None:
        return await session.scalar(
            select(PublicationLog)
            .where(PublicationLog.content_item_id == content_item_id)
            .order_by(PublicationLog.created_at.desc())
            .limit(1)
        )
