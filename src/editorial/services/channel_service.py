from __future__ import annotations

from datetime import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.editorial.models.channel import Channel, ChannelSlot


class ChannelService:
    EDITABLE_SETTINGS_ORDER = [
        "title",
        "short_code",
        "is_active",
        "timezone",
        "min_gap_minutes",
        "max_posts_per_day",
        "max_generated_per_day",
        "max_paste_per_day",
        "same_tag_cooldown_hours",
        "same_template_cooldown_hours",
        "same_paste_cooldown_days",
        "min_ready_queue",
        "prefer_real_ratio",
        "allow_generated",
        "allow_pastes",
    ]

    EDITABLE_SETTINGS_TYPES = {
        "title": "str",
        "short_code": "str",
        "is_active": "bool",
        "timezone": "str",
        "min_gap_minutes": "int",
        "max_posts_per_day": "int",
        "max_generated_per_day": "int",
        "max_paste_per_day": "int",
        "same_tag_cooldown_hours": "int",
        "same_template_cooldown_hours": "int",
        "same_paste_cooldown_days": "int",
        "min_ready_queue": "int",
        "prefer_real_ratio": "int",
        "allow_generated": "bool",
        "allow_pastes": "bool",
    }

    BOOL_TRUE_VALUES = {"true", "yes", "on", "да"}
    BOOL_FALSE_VALUES = {"false", "no", "off", "нет"}

    async def list_channels(self, session: AsyncSession) -> list[Channel]:
        return list((await session.execute(select(Channel).order_by(Channel.id.asc()))).scalars().all())

    async def get_channel(self, session: AsyncSession, channel_id: int) -> Channel | None:
        return await session.get(Channel, channel_id)

    async def list_channel_slots(self, session: AsyncSession, channel_id: int) -> list[ChannelSlot]:
        stmt = (
            select(ChannelSlot)
            .where(ChannelSlot.channel_id == channel_id)
            .order_by(ChannelSlot.weekday.asc(), ChannelSlot.slot_time.asc())
        )
        return list((await session.execute(stmt)).scalars().all())

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

    async def delete_slot(self, session: AsyncSession, slot_id: int) -> ChannelSlot | None:
        slot = await session.get(ChannelSlot, slot_id)
        if slot is None:
            return None
        await session.delete(slot)
        await session.commit()
        return slot

    async def delete_slots(
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
        target_times = []
        for slot_value in slot_times:
            hour, minute = map(int, slot_value.split(":"))
            target_times.append(time(hour=hour, minute=minute))

        slots = list(
            (
                await session.execute(
                    select(ChannelSlot).where(
                        ChannelSlot.channel_id == channel_id,
                        ChannelSlot.weekday.in_(weekdays),
                        ChannelSlot.slot_time.in_(target_times),
                    )
                )
            ).scalars().all()
        )

        for slot in slots:
            await session.delete(slot)
        await session.commit()
        return slots

    def editable_settings_snapshot(self, channel: Channel) -> list[tuple[str, Any]]:
        return [(field_name, getattr(channel, field_name)) for field_name in self.EDITABLE_SETTINGS_ORDER]

    def editable_settings_names(self) -> list[str]:
        return list(self.EDITABLE_SETTINGS_ORDER)

    async def update_channel_setting(
        self,
        session: AsyncSession,
        channel_id: int,
        field_name: str,
        raw_value: str,
    ) -> Channel:
        channel = await session.get(Channel, channel_id)
        if channel is None:
            raise ValueError(f"Channel {channel_id} not found")

        normalized_field = field_name.strip()
        expected_type = self.EDITABLE_SETTINGS_TYPES.get(normalized_field)
        if expected_type is None:
            allowed = ", ".join(self.EDITABLE_SETTINGS_ORDER)
            raise ValueError(f"Неизвестный параметр '{field_name}'. Доступно: {allowed}")

        parsed_value = self._parse_setting_value(
            field_name=normalized_field,
            raw_value=raw_value,
            expected_type=expected_type,
        )
        setattr(channel, normalized_field, parsed_value)
        await session.commit()
        await session.refresh(channel)
        return channel

    def _parse_setting_value(self, field_name: str, raw_value: str, expected_type: str) -> Any:
        clean_value = raw_value.strip()
        if expected_type == "bool":
            lowered = clean_value.lower()
            if lowered in self.BOOL_TRUE_VALUES:
                return True
            if lowered in self.BOOL_FALSE_VALUES:
                return False
            raise ValueError(
                f"Поле '{field_name}' булево. Используйте только true/false, yes/no, on/off или да/нет."
            )

        if expected_type == "int":
            try:
                value = int(clean_value)
            except ValueError as exc:
                raise ValueError(f"Поле '{field_name}' должно быть целым числом.") from exc
            if value < 0:
                raise ValueError(f"Поле '{field_name}' не может быть отрицательным.")
            return value

        if expected_type == "str":
            if not clean_value:
                raise ValueError(f"Поле '{field_name}' не может быть пустым.")
            return clean_value

        raise ValueError(f"Unsupported setting type '{expected_type}' for field '{field_name}'")
