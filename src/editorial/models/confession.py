from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from src.editorial.db.base import BaseIdMixin, EditorialBase, TimestampMixin


class ConfessionPublisher(EditorialBase, BaseIdMixin, TimestampMixin):
    __tablename__ = "confession_publishers"

    bot_api_token: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    bot_user_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    bot_username: Mapped[str | None] = mapped_column(String(255))
    storage_chat_id: Mapped[int | None] = mapped_column(BigInteger, index=True)
    storage_chat_title: Mapped[str | None] = mapped_column(String(255))
    bind_code: Mapped[str | None] = mapped_column(String(32), index=True)
    bind_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
