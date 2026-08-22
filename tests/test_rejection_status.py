from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.editorial.models.enums import ContentItemStatus, SubmissionStatus
from src.editorial.services.legacy_moderation_sync import LegacyModerationSyncService
from src.markups import MarkupButton


class _SessionContext:
    def __init__(self, session) -> None:
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


@pytest.mark.asyncio
async def test_rejection_markup_shows_sender_moderator_and_cancel_button() -> None:
    bot = SimpleNamespace(
        get_chat=AsyncMock(
            return_value=SimpleNamespace(
                id=1001,
                username="suggest_sender",
                first_name="Sender",
            )
        ),
        edit_message_reply_markup=AsyncMock(),
    )
    call = SimpleNamespace(
        data="reject;1001",
        message=SimpleNamespace(message_id=4321, chat=SimpleNamespace(id=-100123)),
    )

    await MarkupButton(bot).reject_post(
        call,
        moderator_id=987654321,
        moderator_username="review_admin",
        moderator_first_name="Admin",
    )

    markup = bot.edit_message_reply_markup.await_args.kwargs["reply_markup"].to_dict()
    assert markup["inline_keyboard"] == [
        [
            {
                "text": "👤 @suggest_sender",
                "callback_data": "add_info;1001",
            }
        ],
        [
            {
                "text": "❌ @review_admin (отклонено)",
                "callback_data": "add_info;987654321",
            }
        ],
        [
            {
                "text": "↩️ Отменить отклонение",
                "callback_data": "cancel_reject;1001",
            }
        ],
    ]


@pytest.mark.asyncio
async def test_cancel_rejection_holds_submission_and_voids_moderation_case(monkeypatch) -> None:
    session = SimpleNamespace(commit=AsyncMock())
    monkeypatch.setattr(
        "src.editorial.services.legacy_moderation_sync.session_factory",
        lambda: _SessionContext(session),
    )

    row = SimpleNamespace(id=55)
    submission = SimpleNamespace(
        id=101,
        status=SubmissionStatus.REJECTED,
        reviewed_at=None,
        moderator_note="rejected",
    )
    audit_item = SimpleNamespace(
        status=ContentItemStatus.REJECTED,
        scheduled_for=None,
    )
    reader = SimpleNamespace(
        find_sender_row_by_review_message=AsyncMock(return_value=row),
    )
    importer = SimpleNamespace(
        ensure_submission_for_legacy_row=AsyncMock(return_value=submission),
    )
    moderation = SimpleNamespace(
        get_related_submissions=AsyncMock(return_value=[submission]),
    )
    service = LegacyModerationSyncService(
        legacy_reader=reader,
        importer=importer,
        moderation=moderation,
    )
    service.moderation_cases = SimpleNamespace(void_submission_case=AsyncMock())
    service._get_legacy_delayed_audit_item = AsyncMock(return_value=audit_item)

    restored = await service.cancel_review_message_rejection(
        channel_tg_id=-1007,
        review_chat_id=-100123,
        review_message_id=4321,
        reviewer_id=987654321,
    )

    assert restored is True
    assert submission.status == SubmissionStatus.HOLD
    assert submission.reviewed_at is not None
    assert submission.moderator_note == "Legacy rejection cancelled"
    assert audit_item.status == ContentItemStatus.HOLD
    service.moderation_cases.void_submission_case.assert_awaited_once_with(
        session,
        submission_id=submission.id,
        moderator_id=987654321,
        source="legacy",
        action="cancel_reject",
    )
    session.commit.assert_awaited_once()
