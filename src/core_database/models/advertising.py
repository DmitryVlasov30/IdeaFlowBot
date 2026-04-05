from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped
from src.core_database.models.base import Base
from typing import Optional


class Advertising(Base):
    __tablename__ = 'advertising'

    channel_id: Mapped[int]
    post_id: Mapped[int]
    time: Mapped[int]

    __table_args__ = (
        UniqueConstraint('time', 'channel_id', 'post_id'),
    )

    def __str__(self):
        return f"{self.__class__.__name__} (channel_id={self.channel_id}, post_id={self.post_id}, time={self.time})"

    def __repr__(self):
        return str(self)
