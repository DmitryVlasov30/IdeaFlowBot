from sqlalchemy.orm import Mapped
from src.core_database.models.base import Base


class ChannelSuggest(Base):
    __tablename__ = "chat_suggest"
    bot_id: Mapped[int]
    channel_id: Mapped[int]

    def __str__(self):
        return f"{self.__class__.__name__} (bot_id={self.bot_id}, channel_id={self.channel_id})"

    def __repr__(self):
        return str(self)
