from sqlalchemy import BigInteger, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.core_database.models.base import Base
from typing import Optional


class AnonymMessage(Base):
    __tablename__ = 'anonym_message'
    message_id: Mapped[int] = mapped_column(BigInteger)
    chat_id: Mapped[int] = mapped_column(BigInteger)

    __table_args__ = (
        UniqueConstraint('message_id', 'chat_id'),
    )

    def __str__(self):
        return f"{self.__class__.__name__} (message_id={self.message_id}, chat_id={self.chat_id})"

    def __repr__(self):
        return str(self)
