from __future__ import annotations

from src.editorial.db.session import session_factory
from src.editorial.models.enums import SubmissionStatus
from src.editorial.services.import_legacy import LegacyImporter
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

            await self.moderation.set_submission_status(
                session=session,
                submission_id=submission.id,
                status=status,
                moderator_note=moderator_note,
            )
            return True
