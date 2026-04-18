from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.editorial.db.base import BaseIdMixin, EditorialBase
from src.editorial.models.enums import ReviewDecision, enum_column


class Review(EditorialBase, BaseIdMixin):
    __tablename__ = "reviews"

    content_item_id: Mapped[int] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reviewer_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    decision: Mapped[ReviewDecision] = mapped_column(
        enum_column(ReviewDecision, "review_decision"),
        nullable=False,
        index=True,
    )
    review_note: Mapped[str | None] = mapped_column(Text)
    edited_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
