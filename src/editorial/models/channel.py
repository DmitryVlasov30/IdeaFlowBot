from __future__ import annotations

from datetime import date, datetime, time

from sqlalchemy import BigInteger, Boolean, Date, DateTime, ForeignKey, Integer, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.editorial.db.base import BaseIdMixin, EditorialBase, TimestampMixin
from src.editorial.models.enums import ContentFamily


class Channel(EditorialBase, BaseIdMixin, TimestampMixin):
    __tablename__ = "channels"

    tg_channel_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    short_code: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    content_family: Mapped[str] = mapped_column(
        String(32),
        default=ContentFamily.OVERHEARD.value,
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow", nullable=False)
    min_gap_minutes: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    slot_jitter_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    auto_slots_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    auto_slots_plan_time: Mapped[time] = mapped_column(Time, default=time(hour=23, minute=30), nullable=False)
    auto_slots_window_start: Mapped[time] = mapped_column(Time, default=time(hour=10, minute=0), nullable=False)
    auto_slots_window_end: Mapped[time] = mapped_column(Time, default=time(hour=22, minute=0), nullable=False)
    auto_slots_replace_manual: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_slots_last_planned_for: Mapped[date | None] = mapped_column(Date)
    subscriber_count: Mapped[int | None] = mapped_column(Integer)
    subscriber_count_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    settings_profile_id: Mapped[int | None] = mapped_column(
        ForeignKey("channel_setting_profiles.id", ondelete="SET NULL"),
        index=True,
    )
    settings_profile_auto_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    settings_profile_applied_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    min_slots_per_day: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_posts_per_day: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    max_generated_per_day: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_paste_per_day: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    same_tag_cooldown_hours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    same_template_cooldown_hours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    same_paste_cooldown_days: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    min_ready_queue: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    prefer_real_ratio: Mapped[int] = mapped_column(Integer, default=70, nullable=False)
    allow_generated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_pastes: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    slots = relationship("ChannelSlot", back_populates="channel", cascade="all, delete-orphan")
    settings_profile = relationship("ChannelSettingProfile")


class ChannelSettingProfile(EditorialBase, BaseIdMixin, TimestampMixin):
    __tablename__ = "channel_setting_profiles"
    __table_args__ = (
        UniqueConstraint("slug"),
    )

    slug: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False, index=True)
    min_subscribers: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    max_subscribers: Mapped[int | None] = mapped_column(Integer, index=True)

    timezone: Mapped[str | None] = mapped_column(String(64))
    min_gap_minutes: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    slot_jitter_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    auto_slots_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    auto_slots_plan_time: Mapped[time] = mapped_column(Time, default=time(hour=23, minute=30), nullable=False)
    auto_slots_window_start: Mapped[time] = mapped_column(Time, default=time(hour=10, minute=0), nullable=False)
    auto_slots_window_end: Mapped[time] = mapped_column(Time, default=time(hour=22, minute=0), nullable=False)
    auto_slots_replace_manual: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    min_slots_per_day: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_posts_per_day: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    max_generated_per_day: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_paste_per_day: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    same_tag_cooldown_hours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    same_template_cooldown_hours: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    same_paste_cooldown_days: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    min_ready_queue: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    prefer_real_ratio: Mapped[int] = mapped_column(Integer, default=70, nullable=False)
    allow_generated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_pastes: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ChannelSubscriberSnapshot(EditorialBase, BaseIdMixin):
    __tablename__ = "channel_subscriber_snapshots"

    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True)
    subscriber_count: Mapped[int] = mapped_column(Integer, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)


class ChannelSlot(EditorialBase, BaseIdMixin):
    __tablename__ = "channel_slots"
    __table_args__ = (
        UniqueConstraint("channel_id", "weekday", "slot_time"),
    )

    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    slot_time: Mapped[time] = mapped_column(Time, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_auto_managed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    channel = relationship("Channel", back_populates="slots")

