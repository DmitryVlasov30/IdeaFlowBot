from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped

from src.core_database.models.base import Base


class BotAdmin(Base):
    __tablename__ = "bot_admins"

    user_id: Mapped[int]

    __table_args__ = (
        UniqueConstraint("user_id"),
    )

