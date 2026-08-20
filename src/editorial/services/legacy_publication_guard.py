from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.editorial.db.session import session_factory
from src.editorial.models.ad_blackout import ChannelAdBlackout
from src.editorial.models.channel import Channel


class LegacyPublicationGuard:
    AUTOMATIC_AD_WINDOW_DURATION = timedelta(hours=1)

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

    async def ensure_automatic_ad_blackout_for_channel_post(
        self,
        tg_channel_id: int,
        telegram_message_id: int,
        published_at: datetime,
    ) -> ChannelAdBlackout | None:
        async with session_factory() as session:
            return await self.ensure_automatic_ad_blackout_for_channel_post_in_session(
                session=session,
                tg_channel_id=tg_channel_id,
                telegram_message_id=telegram_message_id,
                published_at=published_at,
            )

    async def ensure_automatic_ad_blackout_for_channel_post_in_session(
        self,
        session: AsyncSession,
        tg_channel_id: int,
        telegram_message_id: int,
        published_at: datetime,
    ) -> ChannelAdBlackout | None:
        channel_id = await session.scalar(
            select(Channel.id)
            .where(Channel.tg_channel_id == tg_channel_id)
            .limit(1)
        )
        if channel_id is None:
            return None

        starts_at = self._as_utc(published_at)
        ends_at = starts_at + self.AUTOMATIC_AD_WINDOW_DURATION
        existing = await session.scalar(
            select(ChannelAdBlackout)
            .where(
                ChannelAdBlackout.channel_id == channel_id,
                ChannelAdBlackout.starts_at == starts_at,
                ChannelAdBlackout.ends_at == ends_at,
            )
            .limit(1)
        )
        if existing is not None:
            return existing

        blackout = ChannelAdBlackout(
            channel_id=channel_id,
            starts_at=starts_at,
            ends_at=ends_at,
            created_by=None,
            reason=f"automatic: external link in channel post {telegram_message_id}",
        )
        session.add(blackout)
        try:
            await session.commit()
        except IntegrityError:
            await session.rollback()
            return await session.scalar(
                select(ChannelAdBlackout)
                .where(
                    ChannelAdBlackout.channel_id == channel_id,
                    ChannelAdBlackout.starts_at == starts_at,
                    ChannelAdBlackout.ends_at == ends_at,
                )
                .limit(1)
            )
        return blackout

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
