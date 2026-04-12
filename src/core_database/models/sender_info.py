from sqlalchemy.orm import Mapped
from src.core_database.models.base import Base


class SenderData(Base):
    __tablename__ = "sender_info"

    user_id: Mapped[int]
    channel_id: Mapped[str]
    bot_username: Mapped[str]
    username: Mapped[str]
    first_name: Mapped[str]
    message_id: Mapped[int]
    chat_id: Mapped[int]
    text_post: Mapped[str]
    timestamp: Mapped[int]

