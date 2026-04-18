from sqlalchemy import BigInteger, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.core_database.models.base import Base
from typing import Optional


class ChatAdmins(Base):
    __tablename__ = 'chat_admins'
    bot_id: Mapped[int] = mapped_column(BigInteger)
    chat_id: Mapped[int] = mapped_column(BigInteger)

    __table_args__ = (
        UniqueConstraint('bot_id', 'chat_id'),
    )

    def __str__(self):
        return f"{self.__class__.__name__} (bot_id={self.bot_id}, chat_id={self.chat_id})"

    def __repr__(self):
        return str(self)

