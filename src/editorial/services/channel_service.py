from __future__ import annotations

from calendar import monthrange
from datetime import datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.editorial.models.ad_blackout import ChannelAdBlackout
from src.editorial.models.channel import Channel, ChannelSlot


class ChannelService:
    EDITABLE_SETTINGS_ORDER = [
        "title",
        "short_code",
        "is_active",
        "timezone",
        "min_gap_minutes",
        "slot_jitter_minutes",
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
        "slot_jitter_minutes": "int",
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

    async def list_channels(self, session: AsyncSession, include_inactive: bool = False) -> list[Channel]:
        stmt = select(Channel).order_by(Channel.id.asc())
        if not include_inactive:
            stmt = stmt.where(Channel.is_active.is_(True))
        return list((await session.execute(stmt)).scalars().all())

    async def get_channel(self, session: AsyncSession, channel_id: int) -> Channel | None:
        return await session.get(Channel, channel_id)

    async def set_channel_active_by_tg_id(
        self,
        session: AsyncSession,
        tg_channel_id: int,
        is_active: bool,
        title: str | None = None,
        short_code: str | None = None,
    ) -> Channel | None:
        channel = await session.scalar(
            select(Channel).where(Channel.tg_channel_id == tg_channel_id).limit(1)
        )
        if channel is None:
            return None

        channel.is_active = is_active
        if title:
            channel.title = title
        if short_code:
            channel.short_code = short_code
        await session.commit()
        await session.refresh(channel)
        return channel

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

    async def create_ad_blackout(
        self,
        session: AsyncSession,
        channel_id: int,
        day_of_month: int,
        start_time: str,
        end_time: str,
        created_by: int | None = None,
    ) -> ChannelAdBlackout:
        channel = await session.get(Channel, channel_id)
        if channel is None:
            raise ValueError(f"Channel {channel_id} not found")

        if day_of_month < 1 or day_of_month > 31:
            raise ValueError("День месяца должен быть числом от 1 до 31.")

        start_value = self._parse_time_value(start_time)
        end_value = self._parse_time_value(end_time)

        tz = ZoneInfo(channel.timezone)
        local_now = datetime.now(timezone.utc).astimezone(tz)
        starts_at_local, ends_at_local = self._resolve_ad_blackout_window(
            local_now=local_now,
            day_of_month=day_of_month,
            start_value=start_value,
            end_value=end_value,
        )

        blackout = ChannelAdBlackout(
            channel_id=channel_id,
            starts_at=starts_at_local.astimezone(timezone.utc),
            ends_at=ends_at_local.astimezone(timezone.utc),
            created_by=created_by,
            reason="advertising",
        )
        existing = await session.scalar(
            select(ChannelAdBlackout)
            .where(
                ChannelAdBlackout.channel_id == channel_id,
                ChannelAdBlackout.starts_at == blackout.starts_at,
                ChannelAdBlackout.ends_at == blackout.ends_at,
            )
            .limit(1)
        )
        if existing is not None:
            return existing

        session.add(blackout)
        await session.commit()
        await session.refresh(blackout)
        return blackout

    async def list_upcoming_ad_blackouts(
        self,
        session: AsyncSession,
        channel_id: int,
        limit: int = 5,
    ) -> list[ChannelAdBlackout]:
        now = datetime.now(timezone.utc)
        stmt = (
            select(ChannelAdBlackout)
            .where(
                ChannelAdBlackout.channel_id == channel_id,
                ChannelAdBlackout.ends_at > now,
            )
            .order_by(ChannelAdBlackout.starts_at.asc())
            .limit(limit)
        )
        return list((await session.execute(stmt)).scalars().all())

    async def delete_ad_blackout(
        self,
        session: AsyncSession,
        channel_id: int,
        day_of_month: int,
        start_time: str,
        end_time: str,
    ) -> ChannelAdBlackout:
        channel = await session.get(Channel, channel_id)
        if channel is None:
            raise ValueError(f"Channel {channel_id} not found")

        if day_of_month < 1 or day_of_month > 31:
            raise ValueError("День месяца должен быть числом от 1 до 31.")

        start_value = self._parse_time_value(start_time)
        end_value = self._parse_time_value(end_time)
        tz = ZoneInfo(channel.timezone)
        local_now = datetime.now(timezone.utc).astimezone(tz)
        starts_at_local, ends_at_local = self._resolve_ad_blackout_window(
            local_now=local_now,
            day_of_month=day_of_month,
            start_value=start_value,
            end_value=end_value,
        )
        starts_at = starts_at_local.astimezone(timezone.utc)
        ends_at = ends_at_local.astimezone(timezone.utc)

        blackout = await session.scalar(
            select(ChannelAdBlackout)
            .where(
                ChannelAdBlackout.channel_id == channel_id,
                ChannelAdBlackout.starts_at == starts_at,
                ChannelAdBlackout.ends_at == ends_at,
            )
            .limit(1)
        )
        if blackout is None:
            raise ValueError("Такое рекламное окно для канала не найдено.")

        await session.delete(blackout)
        await session.commit()
        return blackout

    async def is_channel_in_ad_blackout(
        self,
        session: AsyncSession,
        channel_id: int,
        when: datetime,
    ) -> bool:
        when_utc = when.astimezone(timezone.utc)
        count = await session.scalar(
            select(ChannelAdBlackout.id)
            .where(
                ChannelAdBlackout.channel_id == channel_id,
                ChannelAdBlackout.starts_at <= when_utc,
                ChannelAdBlackout.ends_at > when_utc,
            )
            .limit(1)
        )
        return count is not None

    @staticmethod
    def _parse_time_value(raw_value: str) -> time:
        try:
            return datetime.strptime(raw_value.strip(), "%H:%M").time()
        except ValueError as exc:
            raise ValueError(f"Время '{raw_value}' должно быть в формате HH:MM.") from exc

    def _resolve_ad_blackout_window(
        self,
        *,
        local_now: datetime,
        day_of_month: int,
        start_value: time,
        end_value: time,
    ) -> tuple[datetime, datetime]:
        year = local_now.year
        month = local_now.month
        for month_offset in range(13):
            candidate_year, candidate_month = self._add_months(year, month, month_offset)
            if day_of_month > monthrange(candidate_year, candidate_month)[1]:
                continue

            starts_at = datetime(
                candidate_year,
                candidate_month,
                day_of_month,
                start_value.hour,
                start_value.minute,
                tzinfo=local_now.tzinfo,
            )
            ends_at = datetime(
                candidate_year,
                candidate_month,
                day_of_month,
                end_value.hour,
                end_value.minute,
                tzinfo=local_now.tzinfo,
            )
            if ends_at <= starts_at:
                ends_at += timedelta(days=1)
            if ends_at > local_now:
                return starts_at, ends_at

        raise ValueError("Не удалось подобрать будущую дату для рекламного окна.")

    @staticmethod
    def _add_months(year: int, month: int, offset: int) -> tuple[int, int]:
        month_index = (year * 12 + (month - 1)) + offset
        return month_index // 12, month_index % 12 + 1

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
