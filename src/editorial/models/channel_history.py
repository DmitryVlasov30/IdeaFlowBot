from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.editorial.db.base import BaseIdMixin, EditorialBase, TimestampMixin


class ChannelHistoryMessage(EditorialBase, BaseIdMixin, TimestampMixin):
    __tablename__ = "channel_history_messages"
    __table_args__ = (
        UniqueConstraint("channel_id", "source_chat_id", "source_message_id"),
    )

    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True)
    source_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    source_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    content_type: Mapped[str] = mapped_column(String(32), nullable=False, default="text")
    raw_text: Mapped[str | None] = mapped_column(Text)
    normalized_text: Mapped[str | None] = mapped_column(Text, index=True)
    text_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    original_published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    imported_by: Mapped[int | None] = mapped_column(BigInteger)
    matched_paste_id: Mapped[int | None] = mapped_column(
        ForeignKey("paste_library.id", ondelete="SET NULL"),
        index=True,
    )
    match_kind: Mapped[str | None] = mapped_column(String(16))
    match_score: Mapped[float | None] = mapped_column(Float)
