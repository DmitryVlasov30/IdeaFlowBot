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


class LegacyCollectorReader:
    """Read-only bridge to the existing SQLite collector database."""

    async def fetch_sender_rows(self, after_id: int = 0, limit: int = 200) -> list[SenderData]:
        async with legacy_db_helper.engine.connect() as conn:
            result = await conn.execute(
                select(SenderData)
                .where(SenderData.id > after_id)
                .order_by(SenderData.id.asc())
                .limit(limit)
            )
            return list(result.scalars().all())

    async def fetch_all_bot_bindings(self) -> list[LegacyBotBinding]:
        async with legacy_db_helper.engine.connect() as conn:
            result = await conn.execute(select(BotsData))
            rows = result.scalars().all()
            return [
                LegacyBotBinding(
                    channel_id=row.channel_id,
                    bot_api_token=row.bot_api_token,
                    bot_username=row.bot_username,
                )
                for row in rows
            ]

    async def get_bot_binding(self, channel_id: int) -> LegacyBotBinding | None:
        async with legacy_db_helper.engine.connect() as conn:
            result = await conn.execute(
                select(BotsData).where(BotsData.channel_id == channel_id).limit(1)
            )
            row = result.scalars().first()
            if row is None:
                return None
            return LegacyBotBinding(
                channel_id=row.channel_id,
                bot_api_token=row.bot_api_token,
                bot_username=row.bot_username,
            )

