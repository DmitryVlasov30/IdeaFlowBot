from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.editorial.db.base import BaseIdMixin, EditorialBase


class McpModerationAction(EditorialBase, BaseIdMixin):
    """One idempotent moderation decision requested through MCP."""

    __tablename__ = "mcp_moderation_actions"
    __table_args__ = (UniqueConstraint("request_id"),)

    request_id: Mapped[str] = mapped_column(String(160), nullable=False)
    batch_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    requested_submission_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    submission_id: Mapped[int | None] = mapped_column(
        ForeignKey("submissions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    channel_id: Mapped[int | None] = mapped_column(
        ForeignKey("channels.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    actor_id: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    decision: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    dry_run: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    expected_status: Mapped[str] = mapped_column(String(32), nullable=False)
    previous_status: Mapped[str | None] = mapped_column(String(32))
    resulting_status: Mapped[str | None] = mapped_column(String(32))
    outcome: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    content_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("content_items.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    legacy_sync_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    warning_text: Mapped[str | None] = mapped_column(Text)
    error_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
