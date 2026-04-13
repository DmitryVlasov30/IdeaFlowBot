from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from src.editorial.db.base import BaseIdMixin, EditorialBase, TimestampMixin
from src.editorial.models.enums import ContentItemStatus, ContentSourceType


class ContentItem(EditorialBase, BaseIdMixin, TimestampMixin):
    __tablename__ = "content_items"

    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type: Mapped[ContentSourceType] = mapped_column(
        Enum(ContentSourceType, name="content_source_type"),
        nullable=False,
        index=True,
    )
    origin_submission_id: Mapped[int | None] = mapped_column(ForeignKey("submissions.id", ondelete="SET NULL"), index=True)
    origin_paste_id: Mapped[int | None] = mapped_column(ForeignKey("paste_library.id", ondelete="SET NULL"), index=True)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    primary_tag: Mapped[str | None] = mapped_column(String(64), index=True)
    tags: Mapped[list[str]] = mapped_column(JSONB, default=list, nullable=False)
    template_key: Mapped[str | None] = mapped_column(String(64), index=True)
    tone_key: Mapped[str | None] = mapped_column(String(64))
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    review_required: Mapped[bool] = mapped_column(default=True, nullable=False)
    status: Mapped[ContentItemStatus] = mapped_column(
        Enum(ContentItemStatus, name="content_item_status"),
        default=ContentItemStatus.PENDING_REVIEW,
        nullable=False,
        index=True,
    )
    publish_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    generation_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("generation_runs.id", ondelete="SET NULL"),
        index=True,
    )
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class ContentItemSource(EditorialBase, BaseIdMixin):
    __tablename__ = "content_item_sources"

    content_item_id: Mapped[int] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(32), default="source", nullable=False)

