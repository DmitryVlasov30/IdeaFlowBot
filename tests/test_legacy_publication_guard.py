from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.editorial.models.ad_blackout import ChannelAdBlackout
from src.editorial.services.legacy_publication_guard import LegacyPublicationGuard


def test_timestamp_in_legacy_ad_window() -> None:
    advertising_data = {(10, 1_000.0)}

    assert LegacyPublicationGuard.timestamp_in_legacy_ad_window(
        1_100.0,
        advertising_data,
        shift_seconds=3_600,
    )
    assert not LegacyPublicationGuard.timestamp_in_legacy_ad_window(
        4_600.0,
        advertising_data,
        shift_seconds=3_600,
    )


def test_next_timestamp_after_legacy_ad_window_handles_overlap() -> None:
    advertising_data = {
        (10, 1_000.0),
        (11, 4_000.0),
    }

    assert LegacyPublicationGuard.next_timestamp_after_legacy_ad_window(
        1_100.0,
        advertising_data,
        shift_seconds=3_600,
    ) == 7_600.0


def test_next_timestamp_after_legacy_ad_window_returns_none_when_clear() -> None:
    advertising_data = {(10, 1_000.0)}

    assert LegacyPublicationGuard.next_timestamp_after_legacy_ad_window(
        4_600.0,
        advertising_data,
        shift_seconds=3_600,
    ) is None


@pytest.mark.asyncio
async def test_automatic_channel_post_blackout_lasts_one_hour() -> None:
    session = MagicMock()
    session.scalar = AsyncMock(side_effect=[42, None])
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    published_at = datetime(2026, 8, 20, 9, 15, tzinfo=timezone.utc)

    blackout = await LegacyPublicationGuard().ensure_automatic_ad_blackout_for_channel_post_in_session(
        session=session,
        tg_channel_id=-100123,
        telegram_message_id=777,
        published_at=published_at,
    )

    assert blackout is not None
    assert blackout.channel_id == 42
    assert blackout.starts_at == published_at
    assert blackout.ends_at == published_at + timedelta(hours=1)
    assert blackout.reason == "automatic: external link in channel post 777"
    session.add.assert_called_once_with(blackout)
    session.commit.assert_awaited_once()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_automatic_channel_post_blackout_is_idempotent() -> None:
    published_at = datetime(2026, 8, 20, 9, 15, tzinfo=timezone.utc)
    existing = ChannelAdBlackout(
        channel_id=42,
        starts_at=published_at,
        ends_at=published_at + timedelta(hours=1),
        reason="automatic: external link in channel post 777",
    )
    session = MagicMock()
    session.scalar = AsyncMock(side_effect=[42, existing])
    session.add = MagicMock()
    session.commit = AsyncMock()

    blackout = await LegacyPublicationGuard().ensure_automatic_ad_blackout_for_channel_post_in_session(
        session=session,
        tg_channel_id=-100123,
        telegram_message_id=777,
        published_at=published_at,
    )

    assert blackout is existing
    session.add.assert_not_called()
    session.commit.assert_not_awaited()
