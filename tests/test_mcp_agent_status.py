from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.editorial.models.enums import ContentItemStatus, ReviewDecision, SubmissionStatus
from src.editorial.services.legacy_moderation_sync import LegacyModerationSyncService
from src.editorial.services.telegram_actions import TelegramEditorialActions


class _SessionContext:
    def __init__(self, session) -> None:
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


def test_agent_approval_markup_matches_admin_status_with_cancel() -> None:
    markup = LegacyModerationSyncService._build_panel_status_markup(
        state="approved",
        user_id=1001,
        username="suggest_sender",
        first_name="Sender",
        moderator_label="agent",
        allow_cancel=True,
    ).to_dict()

    assert markup["inline_keyboard"] == [
        [
            {
                "text": "👤 @suggest_sender",
                "callback_data": "add_info;1001",
            }
        ],
        [
            {
                "text": "✅ agent (одобрено в слот)",
                "callback_data": "agent_info",
            }
        ],
        [
            {
                "text": "↩️ Отменить слот",
                "callback_data": "cancel_approve_to_slot;1001",
            }
        ],
    ]


def test_agent_rejection_markup_matches_admin_status_with_cancel() -> None:
    markup = LegacyModerationSyncService._build_panel_status_markup(
        state="rejected",
        user_id=1001,
        username="suggest_sender",
        first_name="Sender",
        moderator_label="agent",
        allow_cancel=True,
    ).to_dict()

    assert markup["inline_keyboard"] == [
        [
            {
                "text": "👤 @suggest_sender",
                "callback_data": "add_info;1001",
            }
        ],
        [
            {
                "text": "❌ agent (отклонено)",
                "callback_data": "agent_info",
            }
        ],
        [
            {
                "text": "↩️ Отменить отклонение",
                "callback_data": "cancel_reject;1001",
            }
        ],
    ]


def test_agent_advertising_markup_identifies_agent_and_author() -> None:
    markup = LegacyModerationSyncService._build_panel_status_markup(
        state="advertising",
        user_id=1001,
        username="suggest_sender",
        first_name="Sender",
        moderator_label="agent",
    ).to_dict()

    assert markup["inline_keyboard"] == [
        [
            {
                "text": "👤 @suggest_sender",
                "callback_data": "add_info;1001",
            }
        ],
        [
            {
                "text": "💵 agent (реклама отправлена)",
                "callback_data": "agent_info",
            }
        ],
    ]


@pytest.mark.asyncio
async def test_agent_sync_methods_request_agent_markup() -> None:
    service = LegacyModerationSyncService(
        legacy_reader=SimpleNamespace(),
        importer=SimpleNamespace(),
        moderation=SimpleNamespace(),
    )
    service._sync_panel_review_markup = AsyncMock(side_effect=[2, 3, 4])

    approved_count = await service.mark_panel_submission_agent_approved(10)
    rejected_count = await service.mark_panel_submission_agent_rejected(11)
    advertising_count = await service.mark_panel_submission_agent_advertising(12)

    assert approved_count == 2
    assert rejected_count == 3
    assert advertising_count == 4
    assert service._sync_panel_review_markup.await_args_list[0].args == (10,)
    assert service._sync_panel_review_markup.await_args_list[0].kwargs == {
        "state": "approved",
        "moderator_label": "agent",
        "allow_cancel": True,
    }
    assert service._sync_panel_review_markup.await_args_list[1].args == (11,)
    assert service._sync_panel_review_markup.await_args_list[1].kwargs == {
        "state": "rejected",
        "moderator_label": "agent",
        "allow_cancel": True,
    }
    assert service._sync_panel_review_markup.await_args_list[2].args == (12,)
    assert service._sync_panel_review_markup.await_args_list[2].kwargs == {
        "state": "advertising",
        "moderator_label": "agent",
    }


@pytest.mark.asyncio
async def test_panel_advertising_sends_reply_and_sets_terminal_status(monkeypatch) -> None:
    submission = SimpleNamespace(id=12)
    session = SimpleNamespace(commit=AsyncMock())
    monkeypatch.setattr(
        "src.editorial.services.telegram_actions.session_factory",
        lambda: _SessionContext(session),
    )
    actions = object.__new__(TelegramEditorialActions)
    actions.send_submission_advertising_reply_v2 = AsyncMock()
    actions.moderation = SimpleNamespace(
        set_submission_status=AsyncMock(return_value=submission),
    )
    actions.moderation_cases = SimpleNamespace(void_submission_case=AsyncMock())

    result = await actions.advertise_submission(12, reviewer_id=9001)

    assert result is submission
    actions.send_submission_advertising_reply_v2.assert_awaited_once_with(12)
    status_kwargs = actions.moderation.set_submission_status.await_args.kwargs
    assert status_kwargs["submission_id"] == 12
    assert status_kwargs["status"] == SubmissionStatus.ADVERTISING
    assert status_kwargs["commit"] is False
    actions.moderation_cases.void_submission_case.assert_awaited_once_with(
        session,
        submission_id=12,
        moderator_id=9001,
        source="panel",
        action="advertise_submission",
    )
    session.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_admin_can_cancel_agent_approval_into_hold(monkeypatch) -> None:
    execution_result = SimpleNamespace(
        scalars=lambda: SimpleNamespace(all=lambda: []),
    )
    session = SimpleNamespace(
        scalar=AsyncMock(return_value=None),
        execute=AsyncMock(return_value=execution_result),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )
    monkeypatch.setattr(
        "src.editorial.services.legacy_moderation_sync.session_factory",
        lambda: _SessionContext(session),
    )

    row = SimpleNamespace(id=55)
    submission = SimpleNamespace(
        id=101,
        status=SubmissionStatus.CONTENT_CREATED,
        reviewed_at=None,
        moderator_note="Codex MCP: подходит правилам",
    )
    content_item = SimpleNamespace(
        id=77,
        status=ContentItemStatus.APPROVED,
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
        review_content_item=AsyncMock(return_value=content_item),
    )
    service = LegacyModerationSyncService(
        legacy_reader=reader,
        importer=importer,
        moderation=moderation,
    )
    service._get_latest_content_item = AsyncMock(return_value=content_item)
    service.moderation_cases = SimpleNamespace(void_submission_case=AsyncMock())

    result = await service.cancel_review_message_approval(
        channel_tg_id=-1007,
        review_chat_id=-100123,
        review_message_id=4321,
        reviewer_id=987654321,
    )

    assert result is content_item
    assert submission.status == SubmissionStatus.HOLD
    assert submission.reviewed_at is not None
    assert submission.moderator_note == "Legacy slot approval cancelled"
    review_kwargs = moderation.review_content_item.await_args.kwargs
    assert review_kwargs["decision"] == ReviewDecision.HOLD
    assert review_kwargs["moderation_action"] == "cancel_approve_to_slot"
    service.moderation_cases.void_submission_case.assert_awaited_once_with(
        session,
        submission_id=submission.id,
        moderator_id=987654321,
        source="legacy",
        action="cancel_approve_to_slot",
    )
    session.commit.assert_awaited_once()
