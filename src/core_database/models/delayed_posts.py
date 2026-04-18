from sqlalchemy import BigInteger, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.core_database.models.base import Base
from typing import Optional


class DelayedPost(Base):
    __tablename__ = 'delayed_posts'

    bot_id: Mapped[int] = mapped_column(BigInteger)
    time_seconds: Mapped[int] = mapped_column(BigInteger)
    message_id: Mapped[int] = mapped_column(BigInteger)
    sender_id: Mapped[int] = mapped_column(BigInteger)

    __table_args__ = (
        UniqueConstraint('bot_id', 'time_seconds', 'message_id'),
    )

