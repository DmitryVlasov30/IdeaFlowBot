from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from src.core_database.models.base import Base


class UserData(Base):
    __tablename__ = "users"

    user_id: Mapped[int]
    bot_username: Mapped[str]
    __table_args__ = (
        UniqueConstraint('user_id', 'bot_username'),
    )


