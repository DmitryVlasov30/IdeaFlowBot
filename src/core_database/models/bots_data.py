from sqlalchemy.orm import Mapped
from src.core_database.models.base import Base


class BotsData(Base):
    __tablename__ = "bots_data"
    bot_api_token: Mapped[str]
    bot_username: Mapped[str]
    channel_id: Mapped[int]

    def __str__(self):
        return f"{self.__class__.__name__} (channel_id={self.channel_id})"

    def __repr__(self):
        return str(self)
