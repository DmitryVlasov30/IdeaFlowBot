from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.editorial.db.base import BaseIdMixin, EditorialBase, TimestampMixin


class ModerationChannelSubscription(EditorialBase, BaseIdMixin, TimestampMixin):
    __tablename__ = "moderation_channel_subscriptions"
    __table_args__ = (
        UniqueConstraint("channel_id", "user_id"),
    )

    channel_id: Mapped[int] = mapped_column(
        ForeignKey("channels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
