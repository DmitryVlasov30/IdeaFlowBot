from __future__ import annotations

from datetime import time

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, Time, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.editorial.db.base import BaseIdMixin, EditorialBase, TimestampMixin


class Channel(EditorialBase, BaseIdMixin, TimestampMixin):
    __tablename__ = "channels"

    tg_channel_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    short_code: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow", nullable=False)
    min_gap_minutes: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_posts_per_day: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    max_generated_per_day: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    max_paste_per_day: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    same_tag_cooldown_hours: Mapped[int] = mapped_column(Integer, default=48, nullable=False)
    same_template_cooldown_hours: Mapped[int] = mapped_column(Integer, default=72, nullable=False)
    same_paste_cooldown_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    min_ready_queue: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    prefer_real_ratio: Mapped[int] = mapped_column(Integer, default=70, nullable=False)
    allow_generated: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    allow_pastes: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    slots = relationship("ChannelSlot", back_populates="channel", cascade="all, delete-orphan")


class ChannelSlot(EditorialBase, BaseIdMixin):
    __tablename__ = "channel_slots"
    __table_args__ = (
        UniqueConstraint("channel_id", "weekday", "slot_time"),
    )

    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    slot_time: Mapped[time] = mapped_column(Time, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    channel = relationship("Channel", back_populates="slots")

