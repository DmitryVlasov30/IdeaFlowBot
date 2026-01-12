from sqlalchemy.orm import Mapped, mapped_column
from src.core_database.models.base import Base


class BannedUser(Base):
    __tablename__ = "banned_user"
    id_user: Mapped[int]
    id_channel: Mapped[int]
    bot_id: Mapped[int]

    def __str__(self):
        return f"{self.__class__.__name__} (id_user={self.id_user}, id_channel={self.id_channel})"

    def __repr__(self):
        return str(self)
