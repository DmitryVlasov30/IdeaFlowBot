from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped
from src.core_database.models.base import Base
from typing import Optional


class DelayedPost(Base):
    __tablename__ = 'delayed_posts'

    bot_id: Mapped[int]
    time_seconds: Mapped[int]
    message_id: Mapped[int]
    sender_id: Mapped[int]

    __table_args__ = (
        UniqueConstraint('bot_id', 'time_seconds', 'message_id'),
    )

