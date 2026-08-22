from sqlalchemy import select

from src.core_database.models.db_helper import db_helper as legacy_db_helper
from src.core_database.models.sender_info import SenderData
from src.editorial.services.legacy_source import LegacyCollectorReader, LegacySenderRow


async def fetch_sender_media_group_rows(
    legacy_reader: LegacyCollectorReader,
    *,
    channel_id: int,
    source_chat_id: int,
    media_group_id: str,
) -> list[LegacySenderRow]:
    """Return one original incoming Telegram album in source message order."""
    async with legacy_db_helper.engine.connect() as conn:
        row_ids = list(
            (
                await conn.execute(
                    select(SenderData.id)
                    .where(
                        SenderData.channel_id == channel_id,
                        SenderData.chat_id == source_chat_id,
                        SenderData.media_group_id == media_group_id,
                    )
                    .order_by(SenderData.message_id.asc(), SenderData.id.asc())
                )
            ).scalars().all()
        )
    return await legacy_reader.fetch_sender_rows_by_ids(row_ids)
