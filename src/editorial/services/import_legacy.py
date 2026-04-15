from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.editorial.config import settings
from src.editorial.models.channel import Channel
from src.editorial.models.submission import Submission
from src.editorial.services.legacy_source import LegacyCollectorReader, LegacySenderRow
from src.editorial.utils.text import (
    clean_text,
    compute_text_hash,
    detect_language_code,
    detect_tags,
    normalize_text,
)


SLUG_RE = re.compile(r"[^a-z0-9_]+")


@dataclass(slots=True)
class ImportLegacyResult:
    scanned: int = 0
    imported: int = 0
    skipped_duplicates: int = 0
    channels_created: int = 0
    last_legacy_id: int = 0


class LegacyImporter:
    def __init__(self, legacy_reader: LegacyCollectorReader | None = None):
        self.legacy_reader = legacy_reader or LegacyCollectorReader()

    @staticmethod
    def _build_media_fingerprint(row: LegacySenderRow) -> str:
        message_ref = row.media_group_id or str(row.message_id or row.id)
        return f"telegram media {row.content_type or 'unknown'} {row.channel_id} {row.chat_id or 0} {message_ref}"

    async def sync_channels(self, session: AsyncSession) -> int:
        created = 0
        bindings = await self.legacy_reader.fetch_all_bot_bindings()
        if not bindings:
            return created

        existing_map = {
            item.tg_channel_id: item
            for item in (
                await session.execute(select(Channel).where(Channel.tg_channel_id.in_([b.channel_id for b in bindings])))
            ).scalars()
        }

        for binding in bindings:
            if binding.channel_id in existing_map:
                channel = existing_map[binding.channel_id]
                if not channel.title:
                    channel.title = binding.bot_username
                continue

            short_code_base = binding.bot_username.replace("@", "").lower()
            short_code_base = SLUG_RE.sub("_", short_code_base).strip("_") or f"channel_{abs(binding.channel_id)}"
            short_code = short_code_base
            suffix = 1
            while await session.scalar(select(func.count()).select_from(Channel).where(Channel.short_code == short_code)):
                suffix += 1
                short_code = f"{short_code_base}_{suffix}"

            session.add(
                Channel(
                    tg_channel_id=binding.channel_id,
                    title=binding.bot_username,
                    short_code=short_code,
                    timezone=settings.default_timezone,
                )
            )
            created += 1

        await session.flush()
        return created

    async def import_new(self, session: AsyncSession, limit: int | None = None) -> ImportLegacyResult:
        result = ImportLegacyResult()
        result.channels_created = await self.sync_channels(session)

        last_id = await session.scalar(
            select(func.max(Submission.legacy_row_id)).where(Submission.legacy_source == "sender_info")
        )
        rows = await self.legacy_reader.fetch_sender_rows(
            after_id=last_id or 0,
            limit=limit or settings.legacy_import_batch_size,
        )

        if not rows:
            await session.commit()
            return result

        channels = {
            item.tg_channel_id: item.id
            for item in (await session.execute(select(Channel))).scalars()
        }

        for row in rows:
            result.scanned += 1
            result.last_legacy_id = row.id

            if row.id is None or row.channel_id not in channels:
                logger.warning("Skipping legacy row {} because channel {} is unknown", row.id, row.channel_id)
                continue

            exists = await session.scalar(
                select(func.count())
                .select_from(Submission)
                .where(
                    Submission.legacy_source == "sender_info",
                    Submission.legacy_row_id == row.id,
                )
            )
            if exists:
                result.skipped_duplicates += 1
                continue

            raw_text = row.text_post or ""
            cleaned_text = clean_text(raw_text)
            normalized_text = normalize_text(cleaned_text)
            text_hash = compute_text_hash(cleaned_text)
            if not normalized_text:
                normalized_text = self._build_media_fingerprint(row)
            if text_hash is None:
                text_hash = compute_text_hash(normalized_text) or ""
            created_at = datetime.fromtimestamp(row.timestamp, tz=timezone.utc)

            submission = Submission(
                legacy_source="sender_info",
                legacy_row_id=row.id,
                channel_id=channels[row.channel_id],
                source_user_id=row.user_id,
                source_message_id=row.message_id,
                source_chat_id=row.chat_id,
                content_type=(row.content_type or "text"),
                media_group_id=row.media_group_id or None,
                bot_username=row.bot_username,
                username=row.username or None,
                first_name=row.first_name or None,
                raw_text=raw_text or None,
                cleaned_text=cleaned_text or None,
                normalized_text=normalized_text or None,
                text_hash=text_hash,
                detected_tags=detect_tags(cleaned_text),
                language_code=detect_language_code(cleaned_text),
                is_candidate_for_generation=len(cleaned_text) >= settings.minimum_submission_length,
                is_candidate_for_paste=len(cleaned_text) >= settings.minimum_submission_length,
                created_at=created_at,
            )
            session.add(submission)
            result.imported += 1

        await session.commit()
        return result
