from sqlalchemy import BigInteger, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.core_database.models.base import Base


class BotAdmin(Base):
    __tablename__ = "bot_admins"

    user_id: Mapped[int] = mapped_column(BigInteger)

    __table_args__ = (
        UniqueConstraint("user_id"),
    )
