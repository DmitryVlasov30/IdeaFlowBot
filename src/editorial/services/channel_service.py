from __future__ import annotations

from datetime import time

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.editorial.models.channel import Channel, ChannelSlot


class ChannelService:
    async def list_channels(self, session: AsyncSession) -> list[Channel]:
        return list((await session.execute(select(Channel).order_by(Channel.id.asc()))).scalars().all())

    async def seed_daily_slots(
        self,
        session: AsyncSession,
        channel_id: int,
        slot_times: list[str],
        weekdays: list[int] | None = None,
    ) -> list[ChannelSlot]:
        channel = await session.get(Channel, channel_id)
        if channel is None:
            raise ValueError(f"Channel {channel_id} not found")

        weekdays = weekdays or [0, 1, 2, 3, 4, 5, 6]
        created: list[ChannelSlot] = []
        for weekday in weekdays:
            for slot_value in slot_times:
                hour, minute = map(int, slot_value.split(":"))
                slot_time = time(hour=hour, minute=minute)
                existing = await session.scalar(
                    select(ChannelSlot).where(
                        ChannelSlot.channel_id == channel_id,
                        ChannelSlot.weekday == weekday,
                        ChannelSlot.slot_time == slot_time,
                    )
                )
                if existing:
                    continue
                slot = ChannelSlot(
                    channel_id=channel_id,
                    weekday=weekday,
                    slot_time=slot_time,
                    is_active=True,
                )
                session.add(slot)
                created.append(slot)
        await session.commit()
        return created

