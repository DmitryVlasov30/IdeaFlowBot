from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.editorial.db.base import BaseIdMixin, EditorialBase, TimestampMixin


class ChannelAdBlackout(EditorialBase, BaseIdMixin, TimestampMixin):
    __tablename__ = "channel_ad_blackouts"
    __table_args__ = (
        UniqueConstraint("channel_id", "starts_at", "ends_at", name="uq_channel_ad_blackouts_window"),
    )

    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), nullable=False, index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger, index=True)
    reason: Mapped[str | None] = mapped_column(Text)
