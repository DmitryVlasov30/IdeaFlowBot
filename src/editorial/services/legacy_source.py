from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from src.core_database.models.bots_data import BotsData
from src.core_database.models.db_helper import db_helper as legacy_db_helper
from src.core_database.models.sender_info import SenderData


@dataclass(slots=True)
class LegacyBotBinding:
    channel_id: int
    bot_api_token: str
    bot_username: str


@dataclass(slots=True)
class LegacySenderRow:
    id: int
    user_id: int | None
    channel_id: int
    bot_username: str
    username: str | None
    first_name: str | None
    message_id: int | None
    chat_id: int | None
    text_post: str | None
    timestamp: int


class LegacyCollectorReader:
    """Read-only bridge to the existing SQLite collector database."""

    async def fetch_sender_rows(self, after_id: int = 0, limit: int = 200) -> list[LegacySenderRow]:
        async with legacy_db_helper.engine.connect() as conn:
            result = await conn.execute(
                select(
                    SenderData.id,
                    SenderData.user_id,
                    SenderData.channel_id,
                    SenderData.bot_username,
                    SenderData.username,
                    SenderData.first_name,
                    SenderData.message_id,
                    SenderData.chat_id,
                    SenderData.text_post,
                    SenderData.timestamp,
                )
                .where(SenderData.id > after_id)
                .order_by(SenderData.id.asc())
                .limit(limit)
            )
            rows = result.mappings().all()
            return [
                LegacySenderRow(
                    id=row["id"],
                    user_id=row["user_id"],
                    channel_id=int(row["channel_id"]),
                    bot_username=row["bot_username"],
                    username=row["username"],
                    first_name=row["first_name"],
                    message_id=row["message_id"],
                    chat_id=row["chat_id"],
                    text_post=row["text_post"],
                    timestamp=row["timestamp"],
                )
                for row in rows
            ]

    async def fetch_all_bot_bindings(self) -> list[LegacyBotBinding]:
        async with legacy_db_helper.engine.connect() as conn:
            result = await conn.execute(
                select(
                    BotsData.channel_id,
                    BotsData.bot_api_token,
                    BotsData.bot_username,
                )
            )
            rows = result.mappings().all()
            return [
                LegacyBotBinding(
                    channel_id=row["channel_id"],
                    bot_api_token=row["bot_api_token"],
                    bot_username=row["bot_username"],
                )
                for row in rows
            ]

    async def get_bot_binding(self, channel_id: int) -> LegacyBotBinding | None:
        async with legacy_db_helper.engine.connect() as conn:
            result = await conn.execute(
                select(
                    BotsData.channel_id,
                    BotsData.bot_api_token,
                    BotsData.bot_username,
                ).where(BotsData.channel_id == channel_id).limit(1)
            )
            row = result.mappings().first()
            if row is None:
                return None
            return LegacyBotBinding(
                channel_id=row["channel_id"],
                bot_api_token=row["bot_api_token"],
                bot_username=row["bot_username"],
            )
