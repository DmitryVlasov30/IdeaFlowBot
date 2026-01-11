from sqlalchemy.orm import Mapped, mapped_column
from src.core_database.models.base import Base


class ServiceMessage(Base):
    __tablename__ = "service_message"

    bot_id: Mapped[int] = mapped_column(unique=True)
    hello_message: Mapped[str]
    ban_user_message: Mapped[str]
