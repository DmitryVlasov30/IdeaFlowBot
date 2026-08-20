from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.editorial.models.enums import ContentItemStatus, PasteStatus
from src.editorial.models.paste import PasteLibrary
from src.editorial.services.paste_service import (
    PasteAvailabilityContext,
    PasteService,
    _combine_last_use,
)


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


def _paste(
    paste_id: int,
    *,
    tags: list[str] | None = None,
    primary_tag: str | None = None,
    global_cooldown_days: int = 0,
    per_channel_cooldown_days: int = 120,
    allow_all_channels: bool = True,
) -> PasteLibrary:
    paste = PasteLibrary(
        title=f"paste-{paste_id}",
        body_text=f"body-{paste_id}",
        normalized_text=f"body-{paste_id}",
        text_hash=f"hash-{paste_id}",
        tags=tags or [],
        primary_tag=primary_tag,
        status=PasteStatus.ACTIVE,
        global_cooldown_days=global_cooldown_days,
        per_channel_cooldown_days=per_channel_cooldown_days,
        allow_all_channels=allow_all_channels,
        min_channel_activity_score=0,
    )
    paste.id = paste_id
    return paste


def test_context_preserves_per_channel_and_global_cooldowns() -> None:
    now = datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)
    per_channel = _paste(1)
    global_paste = _paste(2, global_cooldown_days=1)
    context = PasteAvailabilityContext(
        reference_now=now,
        channel_ids=frozenset({10, 20}),
        pastes=[per_channel, global_paste],
        last_used_by_channel={(1, 10): now - timedelta(days=1)},
        last_used_global={2: now - timedelta(hours=2)},
    )

    assert context.available_for_channel(10) == []
    assert context.available_for_channel(20) == [per_channel]


def test_context_applies_tag_and_explicit_channel_rules() -> None:
    now = datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)
    allowed = _paste(1, tags=["community"])
    excluded = _paste(2, tags=["community", "blocked"])
    explicit = _paste(3, tags=["community"], allow_all_channels=False)
    context = PasteAvailabilityContext(
        reference_now=now,
        channel_ids=frozenset({10}),
        pastes=[allowed, excluded, explicit],
        explicitly_allowed_pairs={(3, 10)},
        global_included={"community"},
        channel_excluded={10: {"blocked"}},
    )

    assert context.available_for_channel(10) == [allowed, explicit]


def test_record_reservation_updates_same_run_eligibility() -> None:
    now = datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)
    per_channel = _paste(1)
    global_paste = _paste(2, global_cooldown_days=1)
    context = PasteAvailabilityContext(
        reference_now=now,
        channel_ids=frozenset({10, 20}),
        pastes=[per_channel, global_paste],
    )

    context.record_reservation(1, 10, now + timedelta(minutes=5))
    assert per_channel not in context.available_for_channel(10)
    assert per_channel in context.available_for_channel(20)

    context.record_reservation(2, 10, now + timedelta(minutes=5))
    assert global_paste not in context.available_for_channel(10)
    assert global_paste not in context.available_for_channel(20)


def test_zero_channel_cooldown_still_blocks_future_reservation() -> None:
    now = datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)
    paste = _paste(1, per_channel_cooldown_days=0)
    context = PasteAvailabilityContext(
        reference_now=now,
        channel_ids=frozenset({10}),
        pastes=[paste],
        last_reserved_by_channel={(1, 10): now + timedelta(minutes=5)},
    )

    assert context.available_for_channel(10) == []


def test_combined_last_use_keeps_legacy_history_semantics() -> None:
    now = datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc)
    published = now - timedelta(days=10)
    history = now - timedelta(days=1)
    usage = now - timedelta(days=5)

    assert _combine_last_use(None, published, history) == published
    assert _combine_last_use(usage, published, history) == history


@pytest.mark.asyncio
async def test_list_available_uses_supplied_context_without_queries() -> None:
    paste = _paste(1)
    context = PasteAvailabilityContext(
        reference_now=datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc),
        channel_ids=frozenset({10}),
        pastes=[paste],
    )
    session = SimpleNamespace(execute=AsyncMock(side_effect=AssertionError("unexpected query")))

    result = await PasteService().list_available_for_channel(
        session,
        10,
        availability_context=context,
    )

    assert result == [paste]
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_context_build_uses_fixed_number_of_bulk_queries() -> None:
    pastes = [_paste(1), _paste(2)]
    session = SimpleNamespace(
        execute=AsyncMock(
            side_effect=[
                _Rows(pastes),
                _Rows([]),  # Explicit channel rules.
                _Rows([]),  # Global tag rules.
                _Rows([]),  # Channel tag rules.
                _Rows([]),  # Paste usage maxima.
                _Rows([]),  # Published-at maxima.
                _Rows([]),  # Imported channel history maxima.
                _Rows([]),  # Scheduled/sent reservation maxima.
            ]
        )
    )

    context = await PasteService().build_availability_context(
        session,
        channel_ids=[10, 20],
        now=datetime(2026, 8, 20, 9, 0, tzinfo=timezone.utc),
    )

    assert context.pastes == pastes
    assert session.execute.await_count == 8


@pytest.mark.asyncio
async def test_scheduler_can_create_paste_item_without_internal_commit() -> None:
    paste = _paste(1, tags=["community"], primary_tag="community")
    session = SimpleNamespace(
        get=AsyncMock(return_value=paste),
        add=Mock(),
        flush=AsyncMock(),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )
    tag_service = SimpleNamespace(
        refresh_paste_tag_cache=AsyncMock(),
        pick_primary_tag=AsyncMock(return_value="community"),
    )
    service = PasteService(tag_service=tag_service)

    item = await service.create_content_item_from_paste(
        session,
        paste_id=1,
        channel_id=10,
        status=ContentItemStatus.APPROVED,
        review_required=False,
        commit=False,
    )

    assert item.origin_paste_id == 1
    session.flush.assert_awaited()
    session.commit.assert_not_awaited()
    session.refresh.assert_not_awaited()
