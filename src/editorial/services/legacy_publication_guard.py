from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.editorial.db.session import session_factory
from src.editorial.models.ad_blackout import ChannelAdBlackout
from src.editorial.models.channel import Channel


class LegacyPublicationGuard:
    @staticmethod
    def timestamp_in_legacy_ad_window(
        timestamp: float,
        advertising_data: Iterable[tuple[int, float]],
        shift_seconds: int,
    ) -> bool:
        return any(
            ad_timestamp <= timestamp < ad_timestamp + shift_seconds
            for _, ad_timestamp in advertising_data
        )

    @staticmethod
    def next_timestamp_after_legacy_ad_window(
        timestamp: float,
        advertising_data: Iterable[tuple[int, float]],
        shift_seconds: int,
    ) -> float | None:
        candidate = timestamp
        while True:
            next_candidate = max(
                (
                    ad_timestamp + shift_seconds
                    for _, ad_timestamp in advertising_data
                    if ad_timestamp <= candidate < ad_timestamp + shift_seconds
                ),
                default=None,
            )
            if next_candidate is None:
                return None if candidate == timestamp else candidate
            candidate = next_candidate

    async def get_blackout_for_telegram_channel(
        self,
        tg_channel_id: int,
        when: datetime,
    ) -> ChannelAdBlackout | None:
        async with session_factory() as session:
            return await self.get_blackout_for_telegram_channel_in_session(
                session=session,
                tg_channel_id=tg_channel_id,
                when=when,
            )

    async def get_blackout_for_telegram_channel_in_session(
        self,
        session: AsyncSession,
        tg_channel_id: int,
        when: datetime,
    ) -> ChannelAdBlackout | None:
        when_utc = self._as_utc(when)
        channel_id = await session.scalar(
            select(Channel.id)
            .where(Channel.tg_channel_id == tg_channel_id)
            .limit(1)
        )
        if channel_id is None:
            return None

        return await session.scalar(
            select(ChannelAdBlackout)
            .where(
                ChannelAdBlackout.channel_id == channel_id,
                ChannelAdBlackout.starts_at <= when_utc,
                ChannelAdBlackout.ends_at > when_utc,
            )
            .order_by(ChannelAdBlackout.ends_at.asc())
            .limit(1)
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
