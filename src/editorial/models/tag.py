from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.editorial.db.base import BaseIdMixin, EditorialBase, TimestampMixin
from src.editorial.models.enums import (
    ChannelPasteTagRuleMode,
    TagAssignmentSource,
    TagMatchType,
    enum_column,
)


class TagDefinition(EditorialBase, BaseIdMixin, TimestampMixin):
    __tablename__ = "tag_definitions"
    __table_args__ = (
        UniqueConstraint("slug"),
    )

    slug: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=100, nullable=False, index=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger)


class TagKeyword(EditorialBase, BaseIdMixin, TimestampMixin):
    __tablename__ = "tag_keywords"
    __table_args__ = (
        UniqueConstraint("tag_id", "keyword", "match_type"),
    )

    tag_id: Mapped[int] = mapped_column(ForeignKey("tag_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    keyword: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_keyword: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    match_type: Mapped[TagMatchType] = mapped_column(
        enum_column(TagMatchType, "tag_match_type"),
        default=TagMatchType.CONTAINS,
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)


class PasteTagAssignment(EditorialBase, BaseIdMixin):
    __tablename__ = "paste_tag_assignments"
    __table_args__ = (
        UniqueConstraint("paste_id", "tag_id", "source"),
    )

    paste_id: Mapped[int] = mapped_column(ForeignKey("paste_library.id", ondelete="CASCADE"), nullable=False, index=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tag_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    source: Mapped[TagAssignmentSource] = mapped_column(
        enum_column(TagAssignmentSource, "tag_assignment_source"),
        nullable=False,
        index=True,
    )
    created_by: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ChannelPasteTagRule(EditorialBase, BaseIdMixin, TimestampMixin):
    __tablename__ = "channel_paste_tag_rules"
    __table_args__ = (
        UniqueConstraint("channel_id", "tag_id", "mode"),
    )

    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("tag_definitions.id", ondelete="CASCADE"), nullable=False, index=True)
    mode: Mapped[ChannelPasteTagRuleMode] = mapped_column(
        enum_column(ChannelPasteTagRuleMode, "channel_paste_tag_rule_mode"),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_by: Mapped[int | None] = mapped_column(BigInteger)
