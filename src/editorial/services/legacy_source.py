from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select

from src.core_database.database import ensure_legacy_schema
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
    content_type: str | None
    media_group_id: str | None
    preview_file_id: str | None
    preview_file_size: int | None
    review_chat_id: int | None
    review_message_id: int | None
    timestamp: int


class LegacyCollectorReader:
    """Read-only bridge to the existing SQLite collector database."""

    async def fetch_sender_rows(self, after_id: int = 0, limit: int = 200) -> list[LegacySenderRow]:
        await ensure_legacy_schema()
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
                    SenderData.content_type,
                    SenderData.media_group_id,
                    SenderData.preview_file_id,
                    SenderData.preview_file_size,
                    SenderData.review_chat_id,
                    SenderData.review_message_id,
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
                    content_type=row["content_type"],
                    media_group_id=row["media_group_id"],
                    preview_file_id=row["preview_file_id"],
                    preview_file_size=row["preview_file_size"],
                    review_chat_id=row["review_chat_id"],
                    review_message_id=row["review_message_id"],
                    timestamp=row["timestamp"],
                )
                for row in rows
            ]

    async def fetch_sender_rows_by_ids(self, row_ids: list[int]) -> list[LegacySenderRow]:
        if not row_ids:
            return []
        await ensure_legacy_schema()
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
                    SenderData.content_type,
                    SenderData.media_group_id,
                    SenderData.preview_file_id,
                    SenderData.preview_file_size,
                    SenderData.review_chat_id,
                    SenderData.review_message_id,
                    SenderData.timestamp,
                )
                .where(SenderData.id.in_(row_ids))
                .order_by(SenderData.message_id.asc(), SenderData.id.asc())
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
                    content_type=row["content_type"],
                    media_group_id=row["media_group_id"],
                    preview_file_id=row["preview_file_id"],
                    preview_file_size=row["preview_file_size"],
                    review_chat_id=row["review_chat_id"],
                    review_message_id=row["review_message_id"],
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
