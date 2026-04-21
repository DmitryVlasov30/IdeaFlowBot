from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import delete as sql_delete, or_, select
from telebot.async_telebot import AsyncTeleBot

from src.core_database.database import CrudBannedUser
from src.core_database.models.db_helper import db_helper as legacy_db_helper
from src.core_database.models.sender_info import SenderData
from src.editorial.db.session import session_factory
from src.editorial.models.channel import Channel
from src.editorial.models.content import ContentItem
from src.editorial.models.enums import ContentItemStatus, ContentSourceType, PasteStatus, PublicationStatus, ReviewDecision, SubmissionStatus
from src.editorial.models.moderation_subscription import ModerationChannelSubscription
from src.editorial.models.notification import NotificationSubscription
from src.editorial.models.paste import PasteLibrary
from src.editorial.models.publication import PublicationLog
from src.editorial.models.submission import Submission
from src.editorial.services.channel_history_service import ChannelHistoryImportResult, ChannelHistoryService
from src.editorial.services.channel_service import ChannelService
from src.editorial.services.generation.service import GenerationService
from src.editorial.services.import_legacy import LegacyImporter
from src.editorial.services.legacy_source import LegacyCollectorReader
from src.editorial.services.moderation import ModerationService
from src.editorial.services.paste_service import PasteService
from src.editorial.services.publisher import PublisherService
from src.editorial.services.scheduler import SchedulerService
from src.editorial.utils.text import clean_text, compute_raw_text_hash, compute_text_hash, detect_tags, normalize_text, pick_primary_tag


@dataclass(slots=True)
class SubmissionPreview:
    channel_tg_id: int
    review_chat_id: int
    review_message_ids: list[int]
    preview_file_ids: list[str]
    preview_file_sizes: list[int]
    preview_content_types: list[str]
    content_type: str
    media_group_id: str | None


@dataclass(slots=True)
class SubmissionBanResult:
    submission_id: int
    user_id: int
    username: str | None
    channel_tg_id: int
    already_banned: bool


@dataclass(slots=True)
class ManualChannelMessageResult:
    requested: int = 0
    sent: int = 0
    blocked: int = 0
    failed: int = 0
    content_item_ids: list[int] = field(default_factory=list)
    publication_log_ids: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


class TelegramEditorialActions:
    def __init__(self) -> None:
        self.importer = LegacyImporter()
        self.legacy_reader = LegacyCollectorReader()
        self.moderation = ModerationService()
        self.paste_service = PasteService()
        self.channel_history_service = ChannelHistoryService()
        self.channel_service = ChannelService()
        self.scheduler = SchedulerService()
        self.publisher = PublisherService()
        self.banned_users = CrudBannedUser()
        self._legacy_bot_id_cache: dict[str, int] = {}

    async def import_new(self):
        async with session_factory() as session:
            return await self.importer.import_new(session)

    async def list_channels(self) -> list[Channel]:
        async with session_factory() as session:
            return await self.channel_service.list_channels(session)

    async def get_channel(self, channel_id: int) -> Channel | None:
        async with session_factory() as session:
            return await self.channel_service.get_channel(session, channel_id)

    async def is_channel_notifications_enabled(self, channel_id: int, user_id: int) -> bool:
        async with session_factory() as session:
            subscription = await session.scalar(
                select(NotificationSubscription)
                .where(
                    NotificationSubscription.channel_id == channel_id,
                    NotificationSubscription.user_id == user_id,
                )
                .limit(1)
            )
            return subscription is not None

    async def toggle_channel_notifications(self, channel_id: int, user_id: int) -> bool:
        async with session_factory() as session:
            subscription = await session.scalar(
                select(NotificationSubscription)
                .where(
                    NotificationSubscription.channel_id == channel_id,
                    NotificationSubscription.user_id == user_id,
                )
                .limit(1)
            )
            if subscription is None:
                session.add(
                    NotificationSubscription(
                        channel_id=channel_id,
                        user_id=user_id,
                    )
                )
                await session.commit()
                return True

            await session.delete(subscription)
            await session.commit()
            return False

    async def is_channel_moderation_feed_enabled(self, channel_id: int, user_id: int) -> bool:
        async with session_factory() as session:
            subscription = await session.scalar(
                select(ModerationChannelSubscription)
                .where(
                    ModerationChannelSubscription.channel_id == channel_id,
                    ModerationChannelSubscription.user_id == user_id,
                )
                .limit(1)
            )
            return subscription is not None

    async def toggle_channel_moderation_feed(self, channel_id: int, user_id: int) -> bool:
        async with session_factory() as session:
            subscription = await session.scalar(
                select(ModerationChannelSubscription)
                .where(
                    ModerationChannelSubscription.channel_id == channel_id,
                    ModerationChannelSubscription.user_id == user_id,
                )
                .limit(1)
            )
            if subscription is None:
                session.add(
                    ModerationChannelSubscription(
                        channel_id=channel_id,
                        user_id=user_id,
                    )
                )
                await session.commit()
                return True

            await session.delete(subscription)
            await session.commit()
            return False

    async def list_user_moderation_feed_channel_ids(self, user_id: int) -> list[int]:
        async with session_factory() as session:
            return [
                int(channel_id)
                for channel_id in (
                    await session.execute(
                        select(ModerationChannelSubscription.channel_id)
                        .where(ModerationChannelSubscription.user_id == user_id)
                        .order_by(ModerationChannelSubscription.channel_id.asc())
                    )
                ).scalars().all()
            ]

    async def list_user_moderation_feed_channels(self, user_id: int) -> list[Channel]:
        async with session_factory() as session:
            stmt = (
                select(Channel)
                .join(ModerationChannelSubscription, ModerationChannelSubscription.channel_id == Channel.id)
                .where(ModerationChannelSubscription.user_id == user_id)
                .order_by(Channel.id.asc())
            )
            return list((await session.execute(stmt)).scalars().all())

    async def list_channel_notification_user_ids(self, channel_id: int) -> list[int]:
        async with session_factory() as session:
            return [
                int(user_id)
                for user_id in (
                    await session.execute(
                        select(NotificationSubscription.user_id)
                        .where(NotificationSubscription.channel_id == channel_id)
                        .order_by(NotificationSubscription.user_id.asc())
                    )
                ).scalars().all()
            ]

    async def ensure_channel_for_tg_channel_id(self, tg_channel_id: int) -> Channel:
        async with session_factory() as session:
            await self.importer.sync_channels(session)
            channel = await session.scalar(
                select(Channel).where(Channel.tg_channel_id == tg_channel_id).limit(1)
            )
            if channel is None:
                raise ValueError(f"Channel with tg id {tg_channel_id} not found")
            await session.commit()
            return channel

    async def ensure_submission_for_review_message(
        self,
        *,
        channel_tg_id: int,
        review_chat_id: int,
        review_message_id: int,
    ) -> Submission | None:
        async with session_factory() as session:
            row = await self.legacy_reader.find_sender_row_by_review_message(
                channel_id=channel_tg_id,
                review_chat_id=review_chat_id,
                review_message_id=review_message_id,
            )
            if row is None:
                return None

            submission = await self.importer.ensure_submission_for_legacy_row(session, row)
            if submission is None:
                return None

            await session.commit()
            await session.refresh(submission)
            return submission

    async def list_channel_slots(self, channel_id: int):
        async with session_factory() as session:
            return await self.channel_service.list_channel_slots(session, channel_id)

    async def seed_default_slots(self, channel_id: int) -> int:
        async with session_factory() as session:
            created = await self.channel_service.seed_daily_slots(
                session=session,
                channel_id=channel_id,
                slot_times=["10:00", "15:00", "20:00"],
                weekdays=[0, 1, 2, 3, 4, 5, 6],
            )
            return len(created)

    async def add_slots(self, channel_id: int, slot_times: Iterable[str], weekdays: Iterable[int]) -> int:
        async with session_factory() as session:
            created = await self.channel_service.seed_daily_slots(
                session=session,
                channel_id=channel_id,
                slot_times=list(slot_times),
                weekdays=list(weekdays),
            )
            return len(created)

    async def remove_slot(self, slot_id: int):
        async with session_factory() as session:
            return await self.channel_service.delete_slot(session, slot_id)

    async def remove_slots(self, channel_id: int, slot_times: Iterable[str], weekdays: Iterable[int]) -> int:
        async with session_factory() as session:
            removed = await self.channel_service.delete_slots(
                session=session,
                channel_id=channel_id,
                slot_times=list(slot_times),
                weekdays=list(weekdays),
            )
            return len(removed)

    async def create_channel_ad_blackout(
        self,
        *,
        channel_id: int,
        day_of_month: int,
        start_time: str,
        end_time: str,
        created_by: int | None = None,
    ):
        async with session_factory() as session:
            return await self.channel_service.create_ad_blackout(
                session=session,
                channel_id=channel_id,
                day_of_month=day_of_month,
                start_time=start_time,
                end_time=end_time,
                created_by=created_by,
            )

    async def list_channel_ad_blackouts(self, channel_id: int, limit: int = 5):
        async with session_factory() as session:
            return await self.channel_service.list_upcoming_ad_blackouts(
                session=session,
                channel_id=channel_id,
                limit=limit,
            )

    async def delete_channel_ad_blackout(
        self,
        *,
        channel_id: int,
        day_of_month: int,
        start_time: str,
        end_time: str,
    ):
        async with session_factory() as session:
            return await self.channel_service.delete_ad_blackout(
                session=session,
                channel_id=channel_id,
                day_of_month=day_of_month,
                start_time=start_time,
                end_time=end_time,
            )

    async def update_channel_setting(self, channel_id: int, field_name: str, raw_value: str) -> Channel:
        async with session_factory() as session:
            return await self.channel_service.update_channel_setting(
                session=session,
                channel_id=channel_id,
                field_name=field_name,
                raw_value=raw_value,
            )

    async def get_channel_settings_snapshot(self, channel_id: int) -> list[tuple[str, object]]:
        async with session_factory() as session:
            channel = await self.channel_service.get_channel(session, channel_id)
            if channel is None:
                raise ValueError(f"Channel {channel_id} not found")
            return self.channel_service.editable_settings_snapshot(channel)

    def get_editable_channel_setting_names(self) -> list[str]:
        return self.channel_service.editable_settings_names()

    async def import_channel_history_message(
        self,
        *,
        channel_id: int,
        source_chat_id: int,
        source_message_id: int,
        content_type: str,
        raw_text: str | None,
        original_published_at: datetime | None,
        imported_by: int | None,
    ) -> ChannelHistoryImportResult:
        async with session_factory() as session:
            return await self.channel_history_service.import_message(
                session=session,
                channel_id=channel_id,
                source_chat_id=source_chat_id,
                source_message_id=source_message_id,
                content_type=content_type,
                raw_text=raw_text,
                original_published_at=original_published_at,
                imported_by=imported_by,
            )

    async def list_pending_submissions(self, user_id: int | None = None) -> list[Submission]:
        async with session_factory() as session:
            stmt = (
                select(Submission)
                .where(
                    Submission.status.in_([SubmissionStatus.NEW, SubmissionStatus.HOLD]),
                    or_(Submission.source_chat_id.is_(None), Submission.source_chat_id >= 0),
                )
                .order_by(Submission.created_at.asc())
                .limit(50)
            )
            if user_id is not None:
                selected_channel_ids = [
                    int(channel_id)
                    for channel_id in (
                        await session.execute(
                            select(ModerationChannelSubscription.channel_id)
                            .where(ModerationChannelSubscription.user_id == user_id)
                            .order_by(ModerationChannelSubscription.channel_id.asc())
                        )
                    ).scalars().all()
                ]
                if selected_channel_ids:
                    stmt = stmt.where(Submission.channel_id.in_(selected_channel_ids))
            items = list((await session.execute(stmt)).scalars().all())
            return self.moderation.collapse_media_groups(items)

    async def list_recent_submissions(self, limit: int | None = None) -> list[Submission]:
        async with session_factory() as session:
            items = await self.moderation.list_submissions(session=session, status=None, limit=limit)
            return self.moderation.collapse_media_groups(items)

    async def get_submission(self, submission_id: int) -> Submission | None:
        async with session_factory() as session:
            return await session.get(Submission, submission_id)

    async def delete_submission(self, submission_id: int) -> int:
        async with session_factory() as session:
            submission = await session.get(Submission, submission_id)
            if submission is None:
                raise ValueError(f"Submission {submission_id} not found")

            related_submissions = await self.moderation.get_related_submissions(session, submission)
            legacy_row_ids = [item.legacy_row_id for item in related_submissions if item.legacy_row_id is not None]
            deleted_count = len(related_submissions)

            for item in related_submissions:
                await session.delete(item)
            await session.commit()

        if legacy_row_ids:
            async with legacy_db_helper.engine.begin() as conn:
                await conn.execute(
                    sql_delete(SenderData).where(SenderData.id.in_(legacy_row_ids))
                )

        return deleted_count

    async def set_submission_anonymous(self, submission_id: int, is_anonymous: bool) -> Submission:
        async with session_factory() as session:
            submission = await session.get(Submission, submission_id)
            if submission is None:
                raise ValueError(f"Submission {submission_id} not found")
            related = await self.moderation.get_related_submissions(session, submission)
            for item in related:
                item.is_anonymous = is_anonymous
            await session.commit()
            await session.refresh(submission)
            return submission

    async def get_submission_preview(self, submission_id: int) -> SubmissionPreview | None:
        async with session_factory() as session:
            submission = await session.get(Submission, submission_id)
            if submission is None:
                return None
            related_submissions = await self.moderation.get_related_submissions(session, submission)
            legacy_row_ids = [item.legacy_row_id for item in related_submissions if item.legacy_row_id is not None]
            legacy_rows = await self.legacy_reader.fetch_sender_rows_by_ids(legacy_row_ids)
            preview_rows = [
                row for row in legacy_rows
                if row.review_chat_id is not None and row.review_message_id is not None
            ]
            channel = await session.get(Channel, submission.channel_id)
            if not preview_rows or channel is None:
                return None
            review_chat_id = int(preview_rows[0].review_chat_id)
            review_message_ids = [int(row.review_message_id) for row in preview_rows]
            preview_file_ids = [row.preview_file_id for row in preview_rows if row.preview_file_id]
            preview_file_sizes = [int(row.preview_file_size or 0) for row in preview_rows if row.preview_file_id]
            preview_content_types = [row.content_type or "photo" for row in preview_rows if row.preview_file_id]
            return SubmissionPreview(
                channel_tg_id=int(channel.tg_channel_id),
                review_chat_id=review_chat_id,
                review_message_ids=sorted(set(review_message_ids)),
                preview_file_ids=preview_file_ids,
                preview_file_sizes=preview_file_sizes,
                preview_content_types=preview_content_types,
                content_type=submission.content_type,
                media_group_id=submission.media_group_id,
            )

    async def get_submission_primary_content_item(self, submission_id: int) -> ContentItem | None:
        priority_order = {
            ContentItemStatus.PUBLISHED: 0,
            ContentItemStatus.SCHEDULED: 1,
            ContentItemStatus.APPROVED: 2,
            ContentItemStatus.PENDING_REVIEW: 3,
            ContentItemStatus.HOLD: 4,
            ContentItemStatus.REJECTED: 5,
            ContentItemStatus.DRAFT: 6,
        }

        async with session_factory() as session:
            submission = await session.get(Submission, submission_id)
            if submission is None:
                return None
            related_submissions = await self.moderation.get_related_submissions(session, submission)
            submission_ids = [item.id for item in related_submissions]
            items = list(
                (
                    await session.execute(
                        select(ContentItem)
                        .where(ContentItem.origin_submission_id.in_(submission_ids))
                        .order_by(ContentItem.created_at.desc())
                    )
                ).scalars().all()
            )
            if not items:
                return None
            return min(
                items,
                key=lambda item: (
                    priority_order.get(item.status, 99),
                    -(item.id or 0),
                ),
            )

    async def approve_submission(self, submission_id: int, reviewer_id: int) -> ContentItem:
        async with session_factory() as session:
            item = await self._get_or_create_content_item(session, submission_id)
            if item.status != ContentItemStatus.APPROVED:
                item = await self.moderation.review_content_item(
                    session=session,
                    content_item_id=item.id,
                    reviewer_id=reviewer_id,
                    decision=ReviewDecision.APPROVE,
                    review_note="Approved in Telegram panel",
                )
            return item

    async def publish_submission_now(self, submission_id: int, reviewer_id: int) -> PublicationLog:
        async with session_factory() as session:
            submission = await session.get(Submission, submission_id)
            if submission is None:
                raise ValueError(f"Submission {submission_id} not found")
            now = datetime.now(timezone.utc)
            if await self.channel_service.is_channel_in_ad_blackout(session, submission.channel_id, now):
                raise ValueError(
                    "Сейчас для этого канала активно рекламное окно. Publish now временно заблокирован, чтобы не перебить рекламу."
                )
            item = await self._get_or_create_content_item(session, submission_id)
            if item.status != ContentItemStatus.APPROVED:
                item = await self.moderation.review_content_item(
                    session=session,
                    content_item_id=item.id,
                    reviewer_id=reviewer_id,
                    decision=ReviewDecision.APPROVE,
                    review_note="Approved and published in Telegram panel",
                )
            log_item = await self._schedule_now(session, item)
            await self.publisher.run(session, now=datetime.now(timezone.utc), limit=20)
            return log_item

    async def reject_submission(self, submission_id: int, note: str = "Rejected in Telegram panel") -> Submission:
        async with session_factory() as session:
            return await self.moderation.set_submission_status(
                session=session,
                submission_id=submission_id,
                status=SubmissionStatus.REJECTED,
                moderator_note=note,
            )

    async def hold_submission(self, submission_id: int, note: str = "Hold in Telegram panel") -> Submission:
        async with session_factory() as session:
            return await self.moderation.set_submission_status(
                session=session,
                submission_id=submission_id,
                status=SubmissionStatus.HOLD,
                moderator_note=note,
            )

    async def paste_submission(self, submission_id: int, reviewer_id: int):
        async with session_factory() as session:
            return await self.paste_service.create_paste_from_submission(
                session=session,
                submission_id=submission_id,
                created_by=reviewer_id,
            )

    async def reply_to_submission_author(self, submission_id: int, text: str) -> None:
        async with session_factory() as session:
            submission = await session.get(Submission, submission_id)
            if submission is None:
                raise ValueError(f"Submission {submission_id} not found")
            if submission.source_user_id is None:
                raise ValueError("Submission has no source user id")
            channel = await session.get(Channel, submission.channel_id)
            if channel is None:
                raise ValueError(f"Channel {submission.channel_id} not found")

        binding = await self.legacy_reader.get_bot_binding(channel.tg_channel_id)
        if binding is None:
            raise ValueError(f"Legacy bot binding for channel {channel.tg_channel_id} not found")

        bot = AsyncTeleBot(binding.bot_api_token)
        await bot.send_message(chat_id=submission.source_user_id, text=text)

    async def send_submission_advertising_reply(self, submission_id: int) -> None:
        await self.reply_to_submission_author(
            submission_id,
            "По рекламе напишите пожалуйста @ivanblk, сразу укажите, что вы хотите рекламировать",
        )

    async def ban_submission_author(
        self,
        submission_id: int,
        reviewer_id: int | None = None,
    ) -> SubmissionBanResult:
        async with session_factory() as session:
            submission = await session.get(Submission, submission_id)
            if submission is None:
                raise ValueError(f"Submission {submission_id} not found")
            if submission.source_user_id is None:
                raise ValueError("Submission has no source user id")

            channel = await session.get(Channel, submission.channel_id)
            if channel is None:
                raise ValueError(f"Channel {submission.channel_id} not found")

            await self.moderation.set_submission_status(
                session=session,
                submission_id=submission_id,
                status=SubmissionStatus.REJECTED,
                moderator_note=(
                    f"Banned in Telegram panel by {reviewer_id}"
                    if reviewer_id is not None
                    else "Banned in Telegram panel"
                ),
            )
            user_id = int(submission.source_user_id)
            username = submission.username
            tg_channel_id = int(channel.tg_channel_id)

        binding = await self.legacy_reader.get_bot_binding(tg_channel_id)
        if binding is None:
            raise ValueError(f"Legacy bot binding for channel {tg_channel_id} not found")

        already_banned = bool(
            await self.banned_users.get_banned_users(id_user=user_id, id_channel=tg_channel_id)
        )
        if not already_banned:
            bot_id = await self._get_legacy_bot_id(binding.bot_api_token)
            await self.banned_users.add_banned_user(
                {
                    "id_user": user_id,
                    "id_channel": tg_channel_id,
                    "bot_id": bot_id,
                }
            )

        return SubmissionBanResult(
            submission_id=submission_id,
            user_id=user_id,
            username=username,
            channel_tg_id=tg_channel_id,
            already_banned=already_banned,
        )

    async def list_pending_content_items(self) -> list[ContentItem]:
        async with session_factory() as session:
            stmt = (
                select(ContentItem)
                .where(ContentItem.status == ContentItemStatus.PENDING_REVIEW)
                .order_by(ContentItem.created_at.asc())
                .limit(50)
            )
            return list((await session.execute(stmt)).scalars().all())

    async def get_content_item(self, content_item_id: int) -> ContentItem | None:
        async with session_factory() as session:
            return await session.get(ContentItem, content_item_id)

    async def update_content_item_text(self, content_item_id: int, body_text: str) -> ContentItem:
        cleaned_body = clean_text(body_text)
        if not cleaned_body:
            raise ValueError("Content item text is empty")

        async with session_factory() as session:
            item = await session.get(ContentItem, content_item_id)
            if item is None:
                raise ValueError(f"Content item {content_item_id} not found")
            if item.status not in {ContentItemStatus.PENDING_REVIEW, ContentItemStatus.HOLD}:
                raise ValueError("Only pending or held content items can be edited")

            tags = detect_tags(cleaned_body)
            item.body_text = cleaned_body
            item.normalized_text = normalize_text(cleaned_body)
            item.text_hash = compute_text_hash(cleaned_body) or compute_raw_text_hash(cleaned_body) or ""
            item.tags = tags
            item.primary_tag = pick_primary_tag(tags)
            await session.commit()
            await session.refresh(item)
            return item

    async def list_pastes(self, limit: int | None = None) -> list[PasteLibrary]:
        async with session_factory() as session:
            return await self.paste_service.list_pastes(session=session, status=None, limit=limit)

    async def get_paste(self, paste_id: int) -> PasteLibrary | None:
        async with session_factory() as session:
            return await session.get(PasteLibrary, paste_id)

    async def delete_paste(self, paste_id: int) -> tuple[int, str]:
        async with session_factory() as session:
            paste = await session.get(PasteLibrary, paste_id)
            if paste is None:
                raise ValueError(f"Paste {paste_id} not found")
            paste_title = paste.title
            paste_pk = paste.id
            await session.delete(paste)
            await session.commit()
            return paste_pk, paste_title

    async def create_manual_paste(self, body_text: str, reviewer_id: int, title: str | None = None) -> PasteLibrary:
        clean_title = (title or body_text.strip().splitlines()[0][:60] or "Manual paste").strip()
        async with session_factory() as session:
            return await self.paste_service.create_manual_paste(
                session=session,
                title=clean_title,
                body_text=body_text.strip(),
                created_by=reviewer_id,
                status=PasteStatus.ACTIVE,
            )

    async def archive_paste(self, paste_id: int) -> PasteLibrary:
        async with session_factory() as session:
            return await self.paste_service.archive_paste(session=session, paste_id=paste_id)

    async def approve_content_item(self, content_item_id: int, reviewer_id: int) -> ContentItem:
        async with session_factory() as session:
            return await self.moderation.review_content_item(
                session=session,
                content_item_id=content_item_id,
                reviewer_id=reviewer_id,
                decision=ReviewDecision.APPROVE,
                review_note="Approved in Telegram panel",
            )

    async def publish_content_item_now(self, content_item_id: int, reviewer_id: int) -> PublicationLog:
        async with session_factory() as session:
            item = await session.get(ContentItem, content_item_id)
            if item is None:
                raise ValueError(f"Content item {content_item_id} not found")
            now = datetime.now(timezone.utc)
            if await self.channel_service.is_channel_in_ad_blackout(session, item.channel_id, now):
                raise ValueError(
                    "Сейчас для этого канала активно рекламное окно. Publish now временно заблокирован, чтобы не перебить рекламу."
                )
            if item.status != ContentItemStatus.APPROVED:
                item = await self.moderation.review_content_item(
                    session=session,
                    content_item_id=item.id,
                    reviewer_id=reviewer_id,
                    decision=ReviewDecision.APPROVE,
                    review_note="Approved and published in Telegram panel",
                )
            log_item = await self._schedule_now(session, item)
            await self.publisher.run(session, now=datetime.now(timezone.utc), limit=20)
            return log_item

    async def reject_content_item(self, content_item_id: int, reviewer_id: int) -> ContentItem:
        async with session_factory() as session:
            return await self.moderation.review_content_item(
                session=session,
                content_item_id=content_item_id,
                reviewer_id=reviewer_id,
                decision=ReviewDecision.REJECT,
                review_note="Rejected in Telegram panel",
            )

    async def hold_content_item(self, content_item_id: int, reviewer_id: int) -> ContentItem:
        async with session_factory() as session:
            return await self.moderation.review_content_item(
                session=session,
                content_item_id=content_item_id,
                reviewer_id=reviewer_id,
                decision=ReviewDecision.HOLD,
                review_note="Hold in Telegram panel",
            )

    async def publish_manual_message_to_channels(
        self,
        *,
        channel_ids: Iterable[int],
        moderator_id: int,
        body_text: str,
    ) -> ManualChannelMessageResult:
        cleaned_body = clean_text(body_text)
        if not cleaned_body:
            raise ValueError("Manual channel message text is empty")

        unique_channel_ids = list(dict.fromkeys(int(channel_id) for channel_id in channel_ids))
        result = ManualChannelMessageResult(requested=len(unique_channel_ids))
        if not unique_channel_ids:
            return result

        normalized_text = normalize_text(cleaned_body) or cleaned_body
        text_hash = compute_text_hash(cleaned_body) or compute_raw_text_hash(cleaned_body) or ""
        tags = detect_tags(cleaned_body)
        now = datetime.now(timezone.utc)

        async with session_factory() as session:
            for channel_id in unique_channel_ids:
                channel = await session.get(Channel, channel_id)
                if channel is None:
                    result.failed += 1
                    result.errors.append(f"Channel {channel_id} not found")
                    continue
                if not channel.is_active:
                    result.failed += 1
                    result.errors.append(f"Channel {channel_id} is inactive")
                    continue
                if await self.channel_service.is_channel_in_ad_blackout(session, channel.id, now):
                    result.blocked += 1
                    result.errors.append(f"Channel {channel_id} is in ad blackout")
                    continue

                item = ContentItem(
                    channel_id=channel.id,
                    source_type=ContentSourceType.EDITORIAL,
                    body_text=cleaned_body,
                    normalized_text=normalized_text,
                    text_hash=text_hash,
                    primary_tag=pick_primary_tag(tags),
                    tags=tags,
                    template_key="manual_panel_message",
                    tone_key=f"manual:{moderator_id}",
                    review_required=False,
                    status=ContentItemStatus.SCHEDULED,
                    scheduled_for=now,
                )
                session.add(item)
                await session.flush()

                log_item = PublicationLog(
                    content_item_id=item.id,
                    channel_id=channel.id,
                    scheduled_for=now,
                    publish_status=PublicationStatus.SCHEDULED,
                    created_at=now,
                )
                session.add(log_item)
                await session.flush()

                result.content_item_ids.append(int(item.id))
                result.publication_log_ids.append(int(log_item.id))

                binding = await self.legacy_reader.get_bot_binding(channel.tg_channel_id)
                if binding is None:
                    item.status = ContentItemStatus.HOLD
                    log_item.publish_status = PublicationStatus.FAILED
                    log_item.error_text = f"Legacy bot binding for channel {channel.tg_channel_id} not found"
                    result.failed += 1
                    result.errors.append(log_item.error_text)
                    continue

                try:
                    telegram_message_id = await self.publisher.telegram_adapter.send_text(
                        bot_token=binding.bot_api_token,
                        channel_id=channel.tg_channel_id,
                        text=cleaned_body,
                    )
                except Exception as ex:
                    item.status = ContentItemStatus.HOLD
                    log_item.publish_status = PublicationStatus.FAILED
                    log_item.error_text = str(ex)
                    result.failed += 1
                    result.errors.append(f"Channel {channel_id}: {ex}")
                    continue

                item.status = ContentItemStatus.PUBLISHED
                log_item.publish_status = PublicationStatus.SENT
                log_item.telegram_message_id = telegram_message_id
                log_item.published_at = now
                result.sent += 1

            await session.commit()

        return result

    async def run_scheduler(self):
        async with session_factory() as session:
            return await self.scheduler.run(session)

    async def run_publisher(self):
        async with session_factory() as session:
            return await self.publisher.run(session)

    async def run_generation(
        self,
        *,
        channel_id: int,
        variant_count: int = 3,
        source_count: int = 5,
    ):
        async with session_factory() as session:
            channel = await session.get(Channel, channel_id)
            if channel is None:
                raise ValueError(f"Channel {channel_id} not found")
            return await GenerationService().generate_for_channel(
                session=session,
                channel_id=channel_id,
                variant_count=variant_count,
                source_count=source_count,
            )

    async def _get_or_create_content_item(self, session, submission_id: int) -> ContentItem:
        submission = await session.get(Submission, submission_id)
        if submission is None:
            raise ValueError(f"Submission {submission_id} not found")

        related_submissions = await self.moderation.get_related_submissions(session, submission)
        submission_ids = [item.id for item in related_submissions]
        existing = await session.scalar(
            select(ContentItem)
            .where(ContentItem.origin_submission_id.in_(submission_ids))
            .order_by(ContentItem.created_at.desc())
            .limit(1)
        )
        if existing is not None:
            return existing

        return await self.moderation.create_content_from_submission(
            session=session,
            submission_id=submission_id,
            channel_id=submission.channel_id,
            status=ContentItemStatus.PENDING_REVIEW,
        )

    async def _schedule_now(self, session, item: ContentItem) -> PublicationLog:
        now = datetime.now(timezone.utc)
        if await self.channel_service.is_channel_in_ad_blackout(session, item.channel_id, now):
            raise ValueError(
                "Сейчас для этого канала активно рекламное окно. Publish now временно заблокирован, чтобы не перебить рекламу."
            )
        existing = await session.scalar(
            select(PublicationLog)
            .where(
                PublicationLog.content_item_id == item.id,
                PublicationLog.publish_status == PublicationStatus.SCHEDULED,
            )
            .limit(1)
        )
        if existing is not None:
            return existing

        item.status = ContentItemStatus.SCHEDULED
        item.scheduled_for = now
        log_item = PublicationLog(
            content_item_id=item.id,
            channel_id=item.channel_id,
            scheduled_for=now,
            publish_status=PublicationStatus.SCHEDULED,
            created_at=now,
        )
        session.add(log_item)
        await session.commit()
        await session.refresh(log_item)
        return log_item

    async def _get_legacy_bot_id(self, bot_api_token: str) -> int:
        cached_id = self._legacy_bot_id_cache.get(bot_api_token)
        if cached_id is not None:
            return cached_id

        bot = AsyncTeleBot(bot_api_token)
        try:
            bot_info = await bot.get_me()
            self._legacy_bot_id_cache[bot_api_token] = bot_info.id
            return bot_info.id
        finally:
            close_session = getattr(bot, "close_session", None)
            if close_session is not None:
                await close_session()
