from sqlalchemy import BigInteger
from sqlalchemy.orm import Mapped, mapped_column
from src.core_database.models.base import Base


class AdminActionData(Base):
    __tablename__ = "admin_actions_data"

    message_id: Mapped[int] = mapped_column(BigInteger)
    chat_id: Mapped[int] = mapped_column(BigInteger)
    admin_id: Mapped[int] = mapped_column(BigInteger)
    timestamp: Mapped[int] = mapped_column(BigInteger)
    button: Mapped[str]


