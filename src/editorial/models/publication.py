from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.editorial.db.base import BaseIdMixin, EditorialBase
from src.editorial.models.enums import PublicationStatus, enum_column


class PublicationLog(EditorialBase, BaseIdMixin):
    __tablename__ = "publication_log"

    content_item_id: Mapped[int] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True)
    scheduled_for: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    telegram_message_id: Mapped[int | None] = mapped_column(BigInteger)
    publish_status: Mapped[PublicationStatus] = mapped_column(
        enum_column(PublicationStatus, "publication_status"),
        default=PublicationStatus.SCHEDULED,
        nullable=False,
        index=True,
    )
    error_text: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
