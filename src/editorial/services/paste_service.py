from __future__ import annotations

from datetime import datetime, timedelta, timezone
from random import SystemRandom

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.editorial.models.channel_history import ChannelHistoryMessage
from src.editorial.models.content import ContentItem
from src.editorial.models.enums import ContentItemStatus, ContentSourceType, PasteStatus, PublicationStatus, SubmissionStatus
from src.editorial.models.paste import PasteChannelRule, PasteLibrary, PasteUsage
from src.editorial.models.publication import PublicationLog
from src.editorial.models.submission import Submission
from src.editorial.utils.text import compute_text_hash, detect_tags, normalize_text, pick_primary_tag


class PasteService:
    GLOBAL_CROSS_CHANNEL_COOLDOWN_DAYS = 3

    def __init__(self) -> None:
        self._random = SystemRandom()

    async def list_pastes(
        self,
        session: AsyncSession,
        status: PasteStatus | None = None,
        limit: int | None = 50,
    ) -> list[PasteLibrary]:
        stmt = select(PasteLibrary).order_by(PasteLibrary.updated_at.desc())
        if status is not None:
            stmt = stmt.where(PasteLibrary.status == status)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list((await session.execute(stmt)).scalars().all())

    async def create_manual_paste(
        self,
        session: AsyncSession,
        title: str,
        body_text: str,
        created_by: int | None = None,
        status: PasteStatus = PasteStatus.ACTIVE,
    ) -> PasteLibrary:
        tags = detect_tags(body_text)
        paste = PasteLibrary(
            title=title,
            body_text=body_text,
            normalized_text=normalize_text(body_text),
            text_hash=compute_text_hash(body_text) or "",
            tags=tags,
            primary_tag=pick_primary_tag(tags),
            status=status,
            created_by=created_by,
        )
        session.add(paste)
        await session.commit()
        await session.refresh(paste)
        return paste

    async def create_paste_from_submission(
        self,
        session: AsyncSession,
        submission_id: int,
        created_by: int | None = None,
    ) -> PasteLibrary:
        submission = await session.get(Submission, submission_id)
        if submission is None:
            raise ValueError(f"Submission {submission_id} not found")
        body_text = (submission.cleaned_text or submission.raw_text or "").strip()
        if not body_text:
            raise ValueError("Submission has no text content for paste creation")

        paste = await self.create_manual_paste(
            session=session,
            title=f"Paste from submission {submission.id}",
            body_text=body_text,
            created_by=created_by,
        )
        paste.source_submission_id = submission.id
        paste.source_channel_id = submission.channel_id
        submission.status = SubmissionStatus.PASTE_CANDIDATE
        submission.is_candidate_for_paste = True
        submission.reviewed_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(paste)
        return paste

    async def create_paste_from_content_item(
        self,
        session: AsyncSession,
        content_item_id: int,
        created_by: int | None = None,
    ) -> PasteLibrary:
        item = await session.get(ContentItem, content_item_id)
        if item is None:
            raise ValueError(f"Content item {content_item_id} not found")

        paste = await self.create_manual_paste(
            session=session,
            title=f"Paste from content item {item.id}",
            body_text=item.body_text,
            created_by=created_by,
        )
        paste.source_content_item_id = item.id
        paste.source_channel_id = item.channel_id
        await session.commit()
        await session.refresh(paste)
        return paste

    async def create_content_item_from_paste(
        self,
        session: AsyncSession,
        paste_id: int,
        channel_id: int,
        status: ContentItemStatus = ContentItemStatus.PENDING_REVIEW,
        review_required: bool = True,
    ) -> ContentItem:
        paste = await session.get(PasteLibrary, paste_id)
        if paste is None:
            raise ValueError(f"Paste {paste_id} not found")

        tags = detect_tags(paste.body_text)
        item = ContentItem(
            channel_id=channel_id,
            source_type=ContentSourceType.PASTE,
            origin_paste_id=paste.id,
            body_text=paste.body_text,
            normalized_text=normalize_text(paste.body_text),
            text_hash=compute_text_hash(paste.body_text) or "",
            primary_tag=pick_primary_tag(tags),
            tags=tags,
            template_key="paste_library",
            tone_key="community",
            review_required=review_required,
            status=status,
        )
        session.add(item)
        await session.commit()
        await session.refresh(item)
        return item

    async def archive_paste(
        self,
        session: AsyncSession,
        paste_id: int,
    ) -> PasteLibrary:
        paste = await session.get(PasteLibrary, paste_id)
        if paste is None:
            raise ValueError(f"Paste {paste_id} not found")
        paste.status = PasteStatus.ARCHIVED
        await session.commit()
        await session.refresh(paste)
        return paste

    async def list_available_for_channel(
        self,
        session: AsyncSession,
        channel_id: int,
        limit: int = 20,
    ) -> list[PasteLibrary]:
        pastes = list(
            (
                await session.execute(
                    select(PasteLibrary)
                    .where(PasteLibrary.status == PasteStatus.ACTIVE)
                    .order_by(PasteLibrary.updated_at.desc())
                )
            ).scalars().all()
        )

        available: list[PasteLibrary] = []
        for paste in pastes:
            if not await self._is_paste_allowed_for_channel(session, paste, channel_id):
                continue
            if await self._is_paste_in_cooldown(session, paste, channel_id):
                continue
            if await self._is_paste_recently_reserved(session, paste, channel_id):
                continue
            available.append(paste)

        # Choose randomly among all pastes that already passed cooldown and
        # channel restrictions so scheduler does not always reuse the same item.
        self._random.shuffle(available)
        return available[:limit]

    async def register_usage(
        self,
        session: AsyncSession,
        paste_id: int,
        channel_id: int,
        content_item_id: int,
    ) -> PasteUsage:
        usage = PasteUsage(
            paste_id=paste_id,
            channel_id=channel_id,
            content_item_id=content_item_id,
            used_at=datetime.now(timezone.utc),
        )
        session.add(usage)
        await session.commit()
        await session.refresh(usage)
        return usage

    async def get_last_used_at(
        self,
        session: AsyncSession,
        paste_id: int,
        channel_id: int | None = None,
    ) -> datetime | None:
        usage_stmt = select(PasteUsage.used_at).where(PasteUsage.paste_id == paste_id)
        if channel_id is not None:
            usage_stmt = usage_stmt.where(PasteUsage.channel_id == channel_id)
        last_usage = await session.scalar(usage_stmt.order_by(desc(PasteUsage.used_at)).limit(1))

        publish_stmt = (
            select(PublicationLog.published_at)
            .join(ContentItem, ContentItem.id == PublicationLog.content_item_id)
            .where(
                ContentItem.origin_paste_id == paste_id,
                PublicationLog.published_at.is_not(None),
            )
        )
        if channel_id is not None:
            publish_stmt = publish_stmt.where(PublicationLog.channel_id == channel_id)
        last_publish = await session.scalar(publish_stmt.order_by(desc(PublicationLog.published_at)).limit(1))

        if last_usage is None:
            return last_publish
        if last_publish is None:
            last_combined = last_usage
        elif last_usage is None:
            last_combined = last_publish
        else:
            last_combined = max(last_usage, last_publish)

        history_timestamp_expr = func.coalesce(
            ChannelHistoryMessage.original_published_at,
            ChannelHistoryMessage.created_at,
        )
        history_stmt = select(history_timestamp_expr).where(ChannelHistoryMessage.matched_paste_id == paste_id)
        if channel_id is not None:
            history_stmt = history_stmt.where(ChannelHistoryMessage.channel_id == channel_id)
        last_history_use = await session.scalar(history_stmt.order_by(desc(history_timestamp_expr)).limit(1))

        if last_combined is None:
            return last_history_use
        if last_history_use is None:
            return last_combined
        return max(last_combined, last_history_use)

    async def _is_paste_allowed_for_channel(
        self,
        session: AsyncSession,
        paste: PasteLibrary,
        channel_id: int,
    ) -> bool:
        if paste.allow_all_channels:
            return True
        rule = await session.scalar(
            select(PasteChannelRule)
            .where(PasteChannelRule.paste_id == paste.id, PasteChannelRule.channel_id == channel_id)
        )
        return bool(rule and rule.is_allowed)

    async def _is_paste_in_cooldown(
        self,
        session: AsyncSession,
        paste: PasteLibrary,
        channel_id: int,
    ) -> bool:
        now = datetime.now(timezone.utc)
        global_cooldown_days = self._global_cooldown_days(paste)

        if global_cooldown_days > 0:
            last_global_use = await self.get_last_used_at(session, paste.id)
            if last_global_use and last_global_use >= now - timedelta(days=global_cooldown_days):
                return True

        last_channel_use = await self.get_last_used_at(session, paste.id, channel_id)
        if last_channel_use and last_channel_use >= now - timedelta(days=paste.per_channel_cooldown_days):
            return True
        return False

    async def _is_paste_recently_reserved(
        self,
        session: AsyncSession,
        paste: PasteLibrary,
        channel_id: int,
    ) -> bool:
        now = datetime.now(timezone.utc)
        global_cooldown_days = self._global_cooldown_days(paste)

        if global_cooldown_days > 0:
            latest_global_log = await session.scalar(
                select(PublicationLog)
                .join(ContentItem, ContentItem.id == PublicationLog.content_item_id)
                .where(
                    ContentItem.origin_paste_id == paste.id,
                    PublicationLog.publish_status.in_([PublicationStatus.SCHEDULED, PublicationStatus.SENT]),
                )
                .order_by(desc(PublicationLog.scheduled_for))
                .limit(1)
            )
            if (
                latest_global_log
                and latest_global_log.scheduled_for
                and latest_global_log.scheduled_for >= now - timedelta(days=global_cooldown_days)
            ):
                return True

        latest_channel_log = await session.scalar(
            select(PublicationLog)
            .join(ContentItem, ContentItem.id == PublicationLog.content_item_id)
            .where(
                ContentItem.origin_paste_id == paste.id,
                PublicationLog.channel_id == channel_id,
                PublicationLog.publish_status.in_([PublicationStatus.SCHEDULED, PublicationStatus.SENT]),
            )
            .order_by(desc(PublicationLog.scheduled_for))
            .limit(1)
        )
        if (
            latest_channel_log
            and latest_channel_log.scheduled_for
            and latest_channel_log.scheduled_for >= now - timedelta(days=paste.per_channel_cooldown_days)
        ):
            return True

        return False

    def _global_cooldown_days(self, paste: PasteLibrary) -> int:
        return max(0, min(paste.global_cooldown_days, self.GLOBAL_CROSS_CHANNEL_COOLDOWN_DAYS))
