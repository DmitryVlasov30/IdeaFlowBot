from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.editorial.models.moderation_case import ModerationCase, ModerationCaseEvent
from src.editorial.services.moderation_case_service import ModerationCaseService


def _submission(submission_id: int = 10):
    return SimpleNamespace(
        id=submission_id,
        channel_id=3,
        source_user_id=500,
        username="author",
        first_name="Author",
        source_message_id=700,
        media_group_id=None,
        content_type="text",
        cleaned_text=None,
        raw_text="Original proposal text",
    )


def _case(*, decision: str = "approved", moderator_id: int = 100, voided_at=None):
    now = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)
    return ModerationCase(
        id=1,
        case_key="submission:10",
        canonical_submission_id=10,
        channel_id=3,
        channel_tg_id=-1003,
        source_user_id=500,
        source_username="author",
        source_first_name="Author",
        source_message_id=700,
        media_group_id=None,
        message_text="Original proposal text",
        moderator_id=moderator_id,
        decision=decision,
        source="panel",
        action="approve_submission",
        decided_at=now,
        finalized_at=now if voided_at is None else None,
        voided_at=voided_at,
    )


@pytest.mark.asyncio
async def test_replayed_decision_does_not_transfer_credit_or_add_event():
    service = ModerationCaseService()
    submission = _submission()
    existing = _case()
    service._load_submission_group = AsyncMock(return_value=(submission, [submission], submission))
    service._get_locked_case = AsyncMock(return_value=existing)
    session = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(tg_channel_id=-1003)),
        add=Mock(),
        flush=AsyncMock(),
    )

    result = await service.record_submission_decision(
        session,
        submission_id=10,
        moderator_id=999,
        decision="approved",
        source="legacy",
        action="publish_now",
    )

    assert result is existing
    assert existing.moderator_id == 100
    session.add.assert_not_called()
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_changed_final_decision_updates_same_case_and_adds_audit_event():
    service = ModerationCaseService()
    submission = _submission()
    existing = _case()
    service._load_submission_group = AsyncMock(return_value=(submission, [submission], submission))
    service._get_locked_case = AsyncMock(return_value=existing)
    session = SimpleNamespace(
        get=AsyncMock(return_value=SimpleNamespace(tg_channel_id=-1003)),
        add=Mock(),
        flush=AsyncMock(),
    )

    result = await service.record_submission_decision(
        session,
        submission_id=10,
        moderator_id=222,
        decision="rejected",
        source="panel",
        action="reject_submission",
    )

    assert result is existing
    assert existing.id == 1
    assert existing.moderator_id == 222
    assert existing.decision == "rejected"
    assert existing.voided_at is None
    event = session.add.call_args.args[0]
    assert isinstance(event, ModerationCaseEvent)
    assert event.case_id == existing.id
    assert event.moderator_id == 222
    assert event.event_type == "rejected"


@pytest.mark.asyncio
async def test_cancel_voids_case_without_creating_another_payable_row():
    service = ModerationCaseService()
    submission = _submission()
    existing = _case()
    service._load_submission_group = AsyncMock(return_value=(submission, [submission], submission))
    service._get_locked_case = AsyncMock(return_value=existing)
    session = SimpleNamespace(add=Mock(), flush=AsyncMock())

    result = await service.void_submission_case(
        session,
        submission_id=10,
        moderator_id=333,
        source="legacy",
        action="cancel_approve_to_slot",
    )

    assert result is existing
    assert existing.finalized_at is None
    assert existing.voided_at is not None
    event = session.add.call_args.args[0]
    assert isinstance(event, ModerationCaseEvent)
    assert event.event_type == "voided"
    assert event.moderator_id == 333


def test_media_group_snapshot_is_one_combined_proposal():
    first = _submission(10)
    first.media_group_id = "album-1"
    first.raw_text = ""
    second = _submission(11)
    second.media_group_id = "album-1"
    second.raw_text = "Album caption"

    snapshot = ModerationCaseService._build_snapshots([first, second])

    assert snapshot["media_group_id"] == "album-1"
    assert snapshot["message_text"] == "Album caption"
    assert snapshot["source_user_id"] == 500
