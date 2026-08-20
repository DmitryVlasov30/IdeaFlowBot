from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.editorial.db.base import BaseIdMixin, EditorialBase, TimestampMixin


class ModerationCase(EditorialBase, BaseIdMixin, TimestampMixin):
    __tablename__ = "moderation_cases"

    case_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    canonical_submission_id: Mapped[int | None] = mapped_column(
        ForeignKey("submissions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    channel_tg_id: Mapped[int | None] = mapped_column(BigInteger)
    source_user_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    source_username: Mapped[str | None] = mapped_column(String(255))
    source_first_name: Mapped[str | None] = mapped_column(String(255))
    source_message_id: Mapped[int | None] = mapped_column(BigInteger)
    media_group_id: Mapped[str | None] = mapped_column(String(255))
    message_text: Mapped[str] = mapped_column(Text, nullable=False, default="")

    moderator_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    decided_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    voided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class ModerationCaseEvent(EditorialBase, BaseIdMixin):
    __tablename__ = "moderation_case_events"

    case_id: Mapped[int] = mapped_column(
        ForeignKey("moderation_cases.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    moderator_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    event_type: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    decision: Mapped[str | None] = mapped_column(String(16))
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
