from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.editorial.db.base import BaseIdMixin, EditorialBase
from src.editorial.models.enums import PublicationStatus, enum_column


class PublicationLog(EditorialBase, BaseIdMixin):
    __tablename__ = "publication_log"
    __table_args__ = (
        UniqueConstraint("channel_id", "slot_id", "slot_date", name="uq_publication_log_channel_slot_day"),
    )

    content_item_id: Mapped[int] = mapped_column(
        ForeignKey("content_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True)
    slot_id: Mapped[int | None] = mapped_column(ForeignKey("channel_slots.id", ondelete="SET NULL"), index=True)
    slot_date: Mapped[date | None] = mapped_column(Date, index=True)
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
