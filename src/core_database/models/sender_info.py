from sqlalchemy import BigInteger
from sqlalchemy.orm import Mapped, mapped_column
from src.core_database.models.base import Base


class SenderData(Base):
    __tablename__ = "sender_info"

    user_id: Mapped[int] = mapped_column(BigInteger)
    channel_id: Mapped[int] = mapped_column(BigInteger)
    bot_username: Mapped[str]
    username: Mapped[str]
    first_name: Mapped[str]
    message_id: Mapped[int] = mapped_column(BigInteger)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    text_post: Mapped[str]
    content_type: Mapped[str]
    media_group_id: Mapped[str | None]
    preview_file_id: Mapped[str | None]
    preview_file_size: Mapped[int | None] = mapped_column(BigInteger)
    entities_json: Mapped[str | None]
    review_chat_id: Mapped[int | None] = mapped_column(BigInteger)
    review_message_id: Mapped[int | None] = mapped_column(BigInteger)
    timestamp: Mapped[int] = mapped_column(BigInteger)

