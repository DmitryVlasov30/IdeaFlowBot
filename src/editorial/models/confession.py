from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.editorial.db.base import BaseIdMixin, EditorialBase, TimestampMixin


class ConfessionPublisher(EditorialBase, BaseIdMixin, TimestampMixin):
    __tablename__ = "confession_publishers"

    bot_api_token: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    bot_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    bot_username: Mapped[str | None] = mapped_column(String(255))
    storage_chat_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    storage_chat_title: Mapped[str | None] = mapped_column(String(255))
    bind_code: Mapped[str | None] = mapped_column(String(32), index=True)
    bind_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger)


class ConfessionPasteCandidate(EditorialBase, BaseIdMixin, TimestampMixin):
    __tablename__ = "confession_paste_candidates"
    __table_args__ = (
        UniqueConstraint(
            "storage_chat_id",
            "storage_message_id",
            name="uq_confession_paste_candidates_storage_message",
        ),
    )

    publisher_id: Mapped[int] = mapped_column(
        ForeignKey("confession_publishers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    storage_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    storage_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    prompt_message_id: Mapped[int | None] = mapped_column(BigInteger)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False)
    body_text: Mapped[str | None] = mapped_column(Text)
    submitted_by: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(
        String(32),
        default="pending",
        server_default="pending",
        nullable=False,
        index=True,
    )
    paste_id: Mapped[int | None] = mapped_column(
        ForeignKey("paste_library.id", ondelete="SET NULL"),
        index=True,
    )
    reviewed_by: Mapped[int | None] = mapped_column(BigInteger)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
