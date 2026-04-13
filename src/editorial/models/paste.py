from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.editorial.db.base import BaseIdMixin, EditorialBase, TimestampMixin
from src.editorial.models.enums import PasteStatus


class PasteLibrary(EditorialBase, BaseIdMixin, TimestampMixin):
    __tablename__ = "paste_library"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_submission_id: Mapped[int | None] = mapped_column(ForeignKey("submissions.id", ondelete="SET NULL"), index=True)
    source_content_item_id: Mapped[int | None] = mapped_column(ForeignKey("content_items.id", ondelete="SET NULL"), index=True)
    source_channel_id: Mapped[int | None] = mapped_column(ForeignKey("channels.id", ondelete="SET NULL"), index=True)
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    primary_tag: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[PasteStatus] = mapped_column(
        Enum(PasteStatus, name="paste_status"),
        default=PasteStatus.ACTIVE,
        nullable=False,
        index=True,
    )
    global_cooldown_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    per_channel_cooldown_days: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    allow_all_channels: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    min_channel_activity_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_by: Mapped[int | None] = mapped_column(BigInteger)


class PasteUsage(EditorialBase, BaseIdMixin):
    __tablename__ = "paste_usage"

    paste_id: Mapped[int] = mapped_column(ForeignKey("paste_library.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True)
    content_item_id: Mapped[int] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PasteChannelRule(EditorialBase, BaseIdMixin):
    __tablename__ = "paste_channel_rules"
    __table_args__ = (
        UniqueConstraint("paste_id", "channel_id"),
    )

    paste_id: Mapped[int] = mapped_column(ForeignKey("paste_library.id", ondelete="CASCADE"), nullable=False, index=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True)
    is_allowed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

