from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import case, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.editorial.config import settings
from src.editorial.models.channel import Channel, ChannelSlot
from src.editorial.models.content import ContentItem
from src.editorial.models.enums import ContentItemStatus, ContentSourceType, PublicationStatus
from src.editorial.models.paste import PasteLibrary
from src.editorial.models.publication import PublicationLog
from src.editorial.services.paste_service import PasteService
from src.editorial.utils.text import similarity_score


@dataclass(slots=True)
class SchedulerRunResult:
    channels_checked: int = 0
    slots_checked: int = 0
    scheduled_items: int = 0


class SchedulerService:
    def __init__(self, paste_service: PasteService | None = None):
        self.paste_service = paste_service or PasteService()

    async def run(
        self,
        session: AsyncSession,
        now: datetime | None = None,
    ) -> SchedulerRunResult:
        now = now or datetime.now(timezone.utc)
        result = SchedulerRunResult()
        channels = list((await session.execute(select(Channel).where(Channel.is_active.is_(True)))).scalars().all())

        for channel in channels:
            result.channels_checked += 1
            for slot_dt in await self._get_due_slots(session, channel, now):
                result.slots_checked += 1
                if await self._slot_already_used(session, channel.id, slot_dt):
                    continue
                if not await self._channel_can_publish(session, channel, slot_dt):
                    continue

                candidate = await self._pick_candidate(session, channel, slot_dt)
                if candidate is None:
                    continue

                candidate.status = ContentItemStatus.SCHEDULED
                candidate.scheduled_for = slot_dt
                session.add(
                    PublicationLog(
                        content_item_id=candidate.id,
                        channel_id=channel.id,
                        scheduled_for=slot_dt,
                        publish_status=PublicationStatus.SCHEDULED,
                        created_at=now,
                    )
                )
                result.scheduled_items += 1

        await session.commit()
        return result

    async def _get_due_slots(
        self,
        session: AsyncSession,
        channel: Channel,
        now: datetime,
    ) -> list[datetime]:
        local_now = now.astimezone(ZoneInfo(channel.timezone))
        slots = list(
            (
                await session.execute(
                    select(ChannelSlot)
                    .where(
                        ChannelSlot.channel_id == channel.id,
                        ChannelSlot.is_active.is_(True),
                        ChannelSlot.weekday == local_now.weekday(),
                    )
                    .order_by(ChannelSlot.slot_time.asc())
                )
            ).scalars().all()
        )

        due_slots: list[datetime] = []
        for slot in slots:
            slot_local = datetime.combine(local_now.date(), slot.slot_time, tzinfo=ZoneInfo(channel.timezone))
            if slot_local > local_now:
                continue
            if local_now - slot_local > timedelta(minutes=settings.scheduler_window_minutes):
                continue
            due_slots.append(slot_local.astimezone(timezone.utc))
        return due_slots

    async def _slot_already_used(
        self,
        session: AsyncSession,
        channel_id: int,
        slot_dt: datetime,
    ) -> bool:
        count = await session.scalar(
            select(func.count())
            .select_from(PublicationLog)
            .where(
                PublicationLog.channel_id == channel_id,
                PublicationLog.scheduled_for == slot_dt,
                PublicationLog.publish_status.in_([PublicationStatus.SCHEDULED, PublicationStatus.SENT]),
            )
        )
        return bool(count)

    async def _channel_can_publish(
        self,
        session: AsyncSession,
        channel: Channel,
        slot_dt: datetime,
    ) -> bool:
        day_start_utc, day_end_utc = self._channel_day_bounds(channel.timezone, slot_dt)

        total_for_day = await session.scalar(
            select(func.count())
            .select_from(PublicationLog)
            .where(
                PublicationLog.channel_id == channel.id,
                PublicationLog.scheduled_for >= day_start_utc,
                PublicationLog.scheduled_for < day_end_utc,
                PublicationLog.publish_status.in_([PublicationStatus.SCHEDULED, PublicationStatus.SENT]),
            )
        )
        if (total_for_day or 0) >= channel.max_posts_per_day:
            return False

        latest_publication = await session.scalar(
            select(PublicationLog)
            .where(
                PublicationLog.channel_id == channel.id,
                PublicationLog.publish_status.in_([PublicationStatus.SCHEDULED, PublicationStatus.SENT]),
            )
            .order_by(desc(PublicationLog.scheduled_for))
            .limit(1)
        )
        if latest_publication and latest_publication.scheduled_for >= slot_dt - timedelta(minutes=channel.min_gap_minutes):
            return False
        return True

    async def _pick_candidate(
        self,
        session: AsyncSession,
        channel: Channel,
        slot_dt: datetime,
    ) -> ContentItem | None:
        candidate = await self._pick_existing_candidate(session, channel, slot_dt, include_generated=False)
        if candidate is not None:
            return candidate

        candidate = await self._pick_library_paste_candidate(session, channel, slot_dt)
        if candidate is not None:
            return candidate

        return await self._pick_existing_candidate(session, channel, slot_dt, include_generated=True)

    async def _pick_existing_candidate(
        self,
        session: AsyncSession,
        channel: Channel,
        slot_dt: datetime,
        include_generated: bool,
    ) -> ContentItem | None:
        priority_case = case(
            (ContentItem.source_type == ContentSourceType.SUBMISSION, 0),
            (ContentItem.source_type == ContentSourceType.EDITORIAL, 1),
            (ContentItem.source_type == ContentSourceType.PASTE, 2),
            (ContentItem.source_type == ContentSourceType.GENERATED, 3),
            else_=99,
        )
        stmt = (
            select(ContentItem)
            .where(
                ContentItem.channel_id == channel.id,
                ContentItem.status == ContentItemStatus.APPROVED,
                (ContentItem.publish_after.is_(None) | (ContentItem.publish_after <= slot_dt)),
                (ContentItem.expires_at.is_(None) | (ContentItem.expires_at > slot_dt)),
            )
            .order_by(priority_case.asc(), ContentItem.priority.asc(), ContentItem.created_at.asc())
            .limit(50)
        )
        if include_generated:
            stmt = stmt.where(ContentItem.source_type == ContentSourceType.GENERATED)
        else:
            stmt = stmt.where(ContentItem.source_type != ContentSourceType.GENERATED)

        candidates = list(((await session.execute(stmt)).scalars().all()))

        for candidate in candidates:
            if not await self._passes_limits(session, channel, candidate, slot_dt):
                continue
            if await self._is_duplicate_for_channel(session, channel.id, candidate):
                continue
            return candidate
        return None

    async def _pick_library_paste_candidate(
        self,
        session: AsyncSession,
        channel: Channel,
        slot_dt: datetime,
    ) -> ContentItem | None:
        if not channel.allow_pastes:
            return None

        for paste in await self.paste_service.list_available_for_channel(session, channel.id, limit=20):
            draft_candidate = ContentItem(
                channel_id=channel.id,
                source_type=ContentSourceType.PASTE,
                origin_paste_id=paste.id,
                body_text=paste.body_text,
                normalized_text=paste.normalized_text,
                text_hash=paste.text_hash,
                primary_tag=paste.primary_tag,
                tags=paste.tags,
                template_key="paste_library",
                tone_key="community",
                review_required=False,
                status=ContentItemStatus.APPROVED,
            )
            if not await self._passes_limits(session, channel, draft_candidate, slot_dt):
                continue
            if await self._is_duplicate_for_channel(session, channel.id, draft_candidate):
                continue
            return await self.paste_service.create_content_item_from_paste(
                session=session,
                paste_id=paste.id,
                channel_id=channel.id,
                status=ContentItemStatus.APPROVED,
                review_required=False,
            )
        return None

    async def _passes_limits(
        self,
        session: AsyncSession,
        channel: Channel,
        candidate: ContentItem,
        slot_dt: datetime,
    ) -> bool:
        if candidate.source_type == ContentSourceType.GENERATED and not channel.allow_generated:
            return False
        if candidate.source_type == ContentSourceType.PASTE and not channel.allow_pastes:
            return False

        day_start_utc, day_end_utc = self._channel_day_bounds(channel.timezone, slot_dt)
        if candidate.source_type == ContentSourceType.GENERATED:
            generated_today = await session.scalar(
                select(func.count())
                .select_from(PublicationLog)
                .join(ContentItem, ContentItem.id == PublicationLog.content_item_id)
                .where(
                    PublicationLog.channel_id == channel.id,
                    PublicationLog.scheduled_for >= day_start_utc,
                    PublicationLog.scheduled_for < day_end_utc,
                    PublicationLog.publish_status.in_([PublicationStatus.SCHEDULED, PublicationStatus.SENT]),
                    ContentItem.source_type == ContentSourceType.GENERATED,
                )
            )
            if (generated_today or 0) >= channel.max_generated_per_day:
                return False
        if candidate.source_type == ContentSourceType.PASTE:
            paste_today = await session.scalar(
                select(func.count())
                .select_from(PublicationLog)
                .join(ContentItem, ContentItem.id == PublicationLog.content_item_id)
                .where(
                    PublicationLog.channel_id == channel.id,
                    PublicationLog.scheduled_for >= day_start_utc,
                    PublicationLog.scheduled_for < day_end_utc,
                    PublicationLog.publish_status.in_([PublicationStatus.SCHEDULED, PublicationStatus.SENT]),
                    ContentItem.source_type == ContentSourceType.PASTE,
                )
            )
            if (paste_today or 0) >= channel.max_paste_per_day:
                return False
            if candidate.origin_paste_id is not None:
                paste = await session.get(PasteLibrary, candidate.origin_paste_id)
                if paste and await self.paste_service._is_paste_in_cooldown(session, paste, channel.id):
                    return False
                latest_same_paste = await session.scalar(
                    select(PublicationLog)
                    .join(ContentItem, ContentItem.id == PublicationLog.content_item_id)
                    .where(
                        PublicationLog.channel_id == channel.id,
                        PublicationLog.publish_status.in_([PublicationStatus.SCHEDULED, PublicationStatus.SENT]),
                        ContentItem.origin_paste_id == candidate.origin_paste_id,
                    )
                    .order_by(desc(PublicationLog.scheduled_for))
                    .limit(1)
                )
                if (
                    latest_same_paste
                    and latest_same_paste.scheduled_for
                    and latest_same_paste.scheduled_for >= slot_dt - timedelta(days=channel.same_paste_cooldown_days)
                ):
                    return False

        if candidate.primary_tag and channel.same_tag_cooldown_hours > 0:
            latest_same_tag = await session.scalar(
                select(PublicationLog)
                .join(ContentItem, ContentItem.id == PublicationLog.content_item_id)
                .where(
                    PublicationLog.channel_id == channel.id,
                    PublicationLog.publish_status == PublicationStatus.SENT,
                    ContentItem.primary_tag == candidate.primary_tag,
                )
                .order_by(desc(PublicationLog.published_at))
                .limit(1)
            )
            if latest_same_tag and latest_same_tag.published_at and latest_same_tag.published_at >= slot_dt - timedelta(hours=channel.same_tag_cooldown_hours):
                return False

        if candidate.template_key and channel.same_template_cooldown_hours > 0:
            latest_same_template = await session.scalar(
                select(PublicationLog)
                .join(ContentItem, ContentItem.id == PublicationLog.content_item_id)
                .where(
                    PublicationLog.channel_id == channel.id,
                    PublicationLog.publish_status == PublicationStatus.SENT,
                    ContentItem.template_key == candidate.template_key,
                )
                .order_by(desc(PublicationLog.published_at))
                .limit(1)
            )
            if latest_same_template and latest_same_template.published_at and latest_same_template.published_at >= slot_dt - timedelta(hours=channel.same_template_cooldown_hours):
                return False

        return True

    async def _is_duplicate_for_channel(
        self,
        session: AsyncSession,
        channel_id: int,
        candidate: ContentItem,
    ) -> bool:
        exact_match_count = await session.scalar(
            select(func.count())
            .select_from(ContentItem)
            .join(PublicationLog, PublicationLog.content_item_id == ContentItem.id)
            .where(
                PublicationLog.channel_id == channel_id,
                PublicationLog.publish_status == PublicationStatus.SENT,
                ContentItem.text_hash == candidate.text_hash,
            )
        )
        if exact_match_count:
            return True

        recent_items = list(
            (
                await session.execute(
                    select(ContentItem)
                    .join(PublicationLog, PublicationLog.content_item_id == ContentItem.id)
                    .where(
                        PublicationLog.channel_id == channel_id,
                        PublicationLog.publish_status == PublicationStatus.SENT,
                    )
                    .order_by(desc(PublicationLog.published_at))
                    .limit(25)
                )
            ).scalars().all()
        )
        for recent in recent_items:
            if similarity_score(candidate.normalized_text, recent.normalized_text) >= settings.similarity_threshold:
                return True
        return False

    def _channel_day_bounds(self, timezone_name: str, dt_utc: datetime) -> tuple[datetime, datetime]:
        tz = ZoneInfo(timezone_name)
        local_dt = dt_utc.astimezone(tz)
        local_start = datetime.combine(local_dt.date(), time.min, tzinfo=tz)
        local_end = datetime.combine(local_dt.date() + timedelta(days=1), time.min, tzinfo=tz)
        return local_start.astimezone(timezone.utc), local_end.astimezone(timezone.utc)
