from sqlalchemy.orm import Mapped
from src.core_database.models.base import Base


class AdminActionData(Base):
    __tablename__ = "admin_actions_data"

    message_id: Mapped[int]
    chat_id: Mapped[int]
    admin_id: Mapped[int]
    timestamp: Mapped[int]
    button: Mapped[str]


