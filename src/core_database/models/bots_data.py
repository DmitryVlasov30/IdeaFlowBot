from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.core_database.models.base import Base


class BotsData(Base):
    __tablename__ = "bots_data"
    bot_api_token: Mapped[str] = mapped_column(unique=True)
    bot_username: Mapped[str]
    channel_id: Mapped[int]

    __table_args__ = (
        UniqueConstraint('bot_api_token', 'bot_username', "channel_id"),
    )

    def __str__(self):
        return f"{self.__class__.__name__} (channel_id={self.channel_id})"

    def __repr__(self):
        return str(self)
