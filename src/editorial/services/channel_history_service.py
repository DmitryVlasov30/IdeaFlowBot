from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.editorial.config import settings
from src.editorial.models.channel_history import ChannelHistoryMessage
from src.editorial.models.enums import PasteStatus
from src.editorial.models.paste import PasteLibrary
from src.editorial.utils.text import compute_text_hash, normalize_text, similarity_score


@dataclass(slots=True)
class ChannelHistoryImportResult:
    saved: bool
    duplicate: bool
    matched_paste_id: int | None
    match_kind: str | None
    match_score: float | None


class ChannelHistoryService:
    async def import_message(
        self,
        session: AsyncSession,
        *,
        channel_id: int,
        source_chat_id: int,
        source_message_id: int,
        content_type: str,
        raw_text: str | None,
        original_published_at: datetime | None,
        imported_by: int | None,
    ) -> ChannelHistoryImportResult:
        existing = await session.scalar(
            select(ChannelHistoryMessage)
            .where(
                ChannelHistoryMessage.channel_id == channel_id,
                ChannelHistoryMessage.source_chat_id == source_chat_id,
                ChannelHistoryMessage.source_message_id == source_message_id,
            )
            .limit(1)
        )
        if existing is not None:
            return ChannelHistoryImportResult(
                saved=False,
                duplicate=True,
                matched_paste_id=existing.matched_paste_id,
                match_kind=existing.match_kind,
                match_score=existing.match_score,
            )

        text_value = (raw_text or "").strip() or None
        normalized = normalize_text(text_value)
        text_hash = compute_text_hash(text_value)
        matched_paste_id, match_kind, match_score = await self._match_paste(session, text_value)

        item = ChannelHistoryMessage(
            channel_id=channel_id,
            source_chat_id=source_chat_id,
            source_message_id=source_message_id,
            content_type=content_type,
            raw_text=text_value,
            normalized_text=normalized or None,
            text_hash=text_hash,
            original_published_at=original_published_at,
            imported_by=imported_by,
            matched_paste_id=matched_paste_id,
            match_kind=match_kind,
            match_score=match_score,
        )
        session.add(item)
        await session.commit()
        return ChannelHistoryImportResult(
            saved=True,
            duplicate=False,
            matched_paste_id=matched_paste_id,
            match_kind=match_kind,
            match_score=match_score,
        )

    async def _match_paste(
        self,
        session: AsyncSession,
        body_text: str | None,
    ) -> tuple[int | None, str | None, float | None]:
        clean_text = (body_text or "").strip()
        if not clean_text:
            return None, None, None

        text_hash = compute_text_hash(clean_text)
        if text_hash:
            exact_match = await session.scalar(
                select(PasteLibrary)
                .where(
                    PasteLibrary.status == PasteStatus.ACTIVE,
                    PasteLibrary.text_hash == text_hash,
                )
                .order_by(desc(PasteLibrary.updated_at))
                .limit(1)
            )
            if exact_match is not None:
                return exact_match.id, "exact", 1.0

        best_match: PasteLibrary | None = None
        best_score = 0.0
        pastes = list(
            (
                await session.execute(
                    select(PasteLibrary)
                    .where(PasteLibrary.status == PasteStatus.ACTIVE)
                    .order_by(desc(PasteLibrary.updated_at))
                )
            ).scalars().all()
        )
        for paste in pastes:
            current_score = similarity_score(clean_text, paste.body_text)
            if current_score < settings.similarity_threshold:
                continue
            if current_score > best_score:
                best_match = paste
                best_score = current_score

        if best_match is None:
            return None, None, None
        return best_match.id, "near", best_score

    @staticmethod
    def normalize_forwarded_datetime(value: datetime | int | None) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc)
        if isinstance(value, int):
            return datetime.fromtimestamp(value, tz=timezone.utc)
        return None
