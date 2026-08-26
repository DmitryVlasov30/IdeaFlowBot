from __future__ import annotations

from dataclasses import dataclass

from loguru import logger
from sqlalchemy import and_, exists, select
from sqlalchemy.orm import aliased
from telebot.async_telebot import AsyncTeleBot

from src.editorial.db.session import session_factory
from src.editorial.models.channel import Channel
from src.editorial.models.content import ContentItem, ContentItemSource
from src.editorial.models.enums import (
    ContentItemStatus,
    ContentSourceType,
    PublicationStatus,
    ReviewDecision,
)
from src.editorial.models.publication import PublicationLog
from src.editorial.models.review import Review
from src.editorial.models.submission import Submission
from src.editorial.services.legacy_source import LegacyCollectorReader
from src.editorial.services.moderation import ModerationService
from src.editorial.services.telegram_publisher import telegram_bot_session
from src.editorial.services.telegram_resilience import (
    is_telegram_message_not_modified,
    run_telegram_operation,
)
from src.markups import build_slot_status_markup


LEGACY_PUBLISHED_SOURCE_ROLE = "legacy_published"


@dataclass(slots=True)
class _PublicationReviewTarget:
    submission: Submission
    reviewer_id: int


class LegacyPublicationStatusService:
    def __init__(
        self,
        legacy_reader: LegacyCollectorReader | None = None,
        moderation: ModerationService | None = None,
    ) -> None:
        self.legacy_reader = legacy_reader or LegacyCollectorReader()
        self.moderation = moderation or ModerationService()

    async def mark_content_item_published(self, content_item_id: int) -> int:
        async with session_factory() as session:
            item = await session.get(ContentItem, content_item_id)
            if item is None or item.status != ContentItemStatus.PUBLISHED:
                return 0
            if item.origin_submission_id is None:
                return 0

            submission = await session.get(Submission, item.origin_submission_id)
            if submission is None:
                return 0
            channel = await session.get(Channel, submission.channel_id)
            if channel is None:
                return 0

            latest_approval = await session.scalar(
                select(Review)
                .where(
                    Review.content_item_id == item.id,
                    Review.decision.in_({ReviewDecision.APPROVE, ReviewDecision.EDIT_AND_APPROVE}),
                )
                .order_by(Review.created_at.desc(), Review.id.desc())
                .limit(1)
            )
            if latest_approval is None:
                logger.warning(
                    "Cannot mark content item {} as published in legacy chat: approving moderator is unknown",
                    content_item_id,
                )
                return 0

            related_submissions = await self.moderation.get_related_submissions(session, submission)
            target_by_submission_id = {
                int(related.id): _PublicationReviewTarget(
                    submission=related,
                    reviewer_id=int(latest_approval.reviewer_id),
                )
                for related in related_submissions
                if related.legacy_row_id is not None
            }

            duplicate_items: list[ContentItem] = []
            if submission.content_type == "text" and item.text_hash:
                duplicate_rows = (
                    await session.execute(
                        select(ContentItem, Submission)
                        .join(Submission, Submission.id == ContentItem.origin_submission_id)
                        .where(
                            ContentItem.id != item.id,
                            ContentItem.channel_id == item.channel_id,
                            ContentItem.source_type == ContentSourceType.SUBMISSION,
                            ContentItem.text_hash == item.text_hash,
                            ContentItem.status.in_(
                                {ContentItemStatus.APPROVED, ContentItemStatus.SCHEDULED}
                            ),
                            Submission.content_type == "text",
                            Submission.legacy_row_id.is_not(None),
                        )
                        .order_by(ContentItem.created_at.asc(), ContentItem.id.asc())
                    )
                ).all()
                duplicate_items = [duplicate_item for duplicate_item, _ in duplicate_rows]
                duplicate_item_ids = [int(duplicate_item.id) for duplicate_item in duplicate_items]

                duplicate_approvals: dict[int, Review] = {}
                if duplicate_item_ids:
                    approval_rows = list(
                        (
                            await session.execute(
                                select(Review)
                                .where(
                                    Review.content_item_id.in_(duplicate_item_ids),
                                    Review.decision.in_(
                                        {ReviewDecision.APPROVE, ReviewDecision.EDIT_AND_APPROVE}
                                    ),
                                )
                                .order_by(
                                    Review.content_item_id.asc(),
                                    Review.created_at.desc(),
                                    Review.id.desc(),
                                )
                            )
                        ).scalars().all()
                    )
                    for approval in approval_rows:
                        duplicate_approvals.setdefault(int(approval.content_item_id), approval)

                for duplicate_item, duplicate_submission in duplicate_rows:
                    approval = duplicate_approvals.get(int(duplicate_item.id))
                    if approval is None:
                        continue
                    target_by_submission_id[int(duplicate_submission.id)] = _PublicationReviewTarget(
                        submission=duplicate_submission,
                        reviewer_id=int(approval.reviewer_id),
                    )

                scheduled_duplicate_ids = [
                    int(duplicate_item.id)
                    for duplicate_item in duplicate_items
                    if duplicate_item.status == ContentItemStatus.SCHEDULED
                ]
                if scheduled_duplicate_ids:
                    scheduled_logs = list(
                        (
                            await session.execute(
                                select(PublicationLog).where(
                                    PublicationLog.content_item_id.in_(scheduled_duplicate_ids),
                                    PublicationLog.publish_status == PublicationStatus.SCHEDULED,
                                )
                            )
                        ).scalars().all()
                    )
                    for log_item in scheduled_logs:
                        log_item.publish_status = PublicationStatus.CANCELLED
                        log_item.error_text = (
                            f"Exact text duplicate of published content item {content_item_id}"
                        )
                    for duplicate_item in duplicate_items:
                        if duplicate_item.status == ContentItemStatus.SCHEDULED:
                            duplicate_item.status = ContentItemStatus.APPROVED
                            duplicate_item.scheduled_for = None
                    await session.commit()

            if not target_by_submission_id:
                return 0

            already_synced_ids = set(
                (
                    await session.execute(
                        select(ContentItemSource.submission_id).where(
                            ContentItemSource.submission_id.in_(target_by_submission_id),
                            ContentItemSource.role == LEGACY_PUBLISHED_SOURCE_ROLE,
                        )
                    )
                ).scalars().all()
            )
            pending_targets = {
                submission_id: target
                for submission_id, target in target_by_submission_id.items()
                if submission_id not in already_synced_ids
            }
            channel_tg_id = int(channel.tg_channel_id)

        if not pending_targets:
            return 0
        target_by_legacy_row_id = {
            int(target.submission.legacy_row_id): target
            for target in pending_targets.values()
            if target.submission.legacy_row_id is not None
        }
        legacy_rows = await self.legacy_reader.fetch_sender_rows_by_ids(list(target_by_legacy_row_id))
        review_rows = [
            row
            for row in legacy_rows
            if row.review_chat_id is not None and row.review_message_id is not None
        ]
        if not review_rows:
            return 0

        binding = await self.legacy_reader.get_bot_binding(channel_tg_id)
        if binding is None:
            return 0
        async with telegram_bot_session(binding.bot_api_token) as bot:
            identity_by_moderator_id: dict[int, tuple[str | None, str | None]] = {}
            for moderator_id in dict.fromkeys(
                target_by_legacy_row_id[row.id].reviewer_id
                for row in review_rows
                if row.id in target_by_legacy_row_id
            ):
                moderator_review_chat_ids = [
                    int(row.review_chat_id)
                    for row in review_rows
                    if row.id in target_by_legacy_row_id
                    and target_by_legacy_row_id[row.id].reviewer_id == moderator_id
                ]
                identity_by_moderator_id[moderator_id] = await self._resolve_moderator_identity(
                    bot,
                    moderator_id=moderator_id,
                    review_chat_ids=moderator_review_chat_ids,
                )

            updated_count = 0
            synced_submission_ids: set[int] = set()
            for row in review_rows:
                target = target_by_legacy_row_id.get(row.id)
                if target is None:
                    continue
                related_submission = target.submission
                sender_id = row.user_id or (
                    related_submission.source_user_id
                )
                sender_username = getattr(row, "username", None) or (
                    getattr(related_submission, "username", None)
                )
                sender_first_name = getattr(row, "first_name", None) or (
                    getattr(related_submission, "first_name", None)
                )
                moderator_id = target.reviewer_id
                moderator_username, moderator_first_name = identity_by_moderator_id.get(
                    moderator_id,
                    (None, None),
                )
                markup = build_slot_status_markup(
                    sender_id=sender_id,
                    sender_username=sender_username,
                    sender_first_name=sender_first_name,
                    moderator_id=moderator_id,
                    moderator_username=moderator_username,
                    moderator_first_name=moderator_first_name,
                    state="published",
                )
                try:
                    await run_telegram_operation(
                        bot.edit_message_reply_markup(
                            chat_id=int(row.review_chat_id),
                            message_id=int(row.review_message_id),
                            reply_markup=markup,
                        ),
                        operation="editPublishedReviewMarkup",
                    )
                    updated_count += 1
                    synced_submission_ids.add(int(related_submission.id))
                except Exception as ex:
                    if is_telegram_message_not_modified(ex):
                        updated_count += 1
                        synced_submission_ids.add(int(related_submission.id))
                        continue
                    logger.error(
                        "Failed to mark published content item {} on review message {} in chat {}: {}",
                        content_item_id,
                        row.review_message_id,
                        row.review_chat_id,
                        ex,
                    )

        if synced_submission_ids:
            async with session_factory() as session:
                existing_ids = set(
                    (
                        await session.execute(
                            select(ContentItemSource.submission_id).where(
                                ContentItemSource.submission_id.in_(synced_submission_ids),
                                ContentItemSource.role == LEGACY_PUBLISHED_SOURCE_ROLE,
                            )
                        )
                    ).scalars().all()
                )
                session.add_all(
                    [
                        ContentItemSource(
                            content_item_id=content_item_id,
                            submission_id=submission_id,
                            role=LEGACY_PUBLISHED_SOURCE_ROLE,
                        )
                        for submission_id in synced_submission_ids
                        if submission_id not in existing_ids
                    ]
                )
                await session.commit()

        return updated_count

    async def reconcile_published_review_statuses(self, limit: int = 20) -> int:
        """Retry stale legacy markups and close exact-text duplicates."""
        if limit <= 0:
            return 0

        published_item = aliased(ContentItem)
        duplicate_item = aliased(ContentItem)
        published_submission = aliased(Submission)
        duplicate_submission = aliased(Submission)
        origin_submission = aliased(Submission)

        any_sync_for_duplicate = exists(
            select(ContentItemSource.id).where(
                ContentItemSource.submission_id == duplicate_submission.id,
                ContentItemSource.role == LEGACY_PUBLISHED_SOURCE_ROLE,
            )
        )
        any_sync_for_origin = exists(
            select(ContentItemSource.id).where(
                ContentItemSource.submission_id == origin_submission.id,
                ContentItemSource.role == LEGACY_PUBLISHED_SOURCE_ROLE,
            )
        )

        async with session_factory() as session:
            duplicate_ids = list(
                (
                    await session.execute(
                        select(published_item.id)
                        .join(
                            duplicate_item,
                            and_(
                                duplicate_item.channel_id == published_item.channel_id,
                                duplicate_item.text_hash == published_item.text_hash,
                                duplicate_item.id != published_item.id,
                            ),
                        )
                        .join(
                            published_submission,
                            published_submission.id == published_item.origin_submission_id,
                        )
                        .join(
                            duplicate_submission,
                            duplicate_submission.id == duplicate_item.origin_submission_id,
                        )
                        .where(
                            published_item.status == ContentItemStatus.PUBLISHED,
                            published_item.origin_submission_id.is_not(None),
                            published_item.text_hash != "",
                            published_submission.content_type == "text",
                            duplicate_item.source_type == ContentSourceType.SUBMISSION,
                            duplicate_item.status.in_(
                                {ContentItemStatus.APPROVED, ContentItemStatus.SCHEDULED}
                            ),
                            duplicate_submission.content_type == "text",
                            duplicate_submission.legacy_row_id.is_not(None),
                            ~any_sync_for_duplicate,
                        )
                        .order_by(published_item.id.desc())
                        .distinct()
                        .limit(limit)
                    )
                ).scalars().all()
            )

            remaining = max(0, limit - len(duplicate_ids))
            origin_ids: list[int] = []
            if remaining:
                origin_ids = list(
                    (
                        await session.execute(
                            select(published_item.id)
                            .join(
                                origin_submission,
                                origin_submission.id == published_item.origin_submission_id,
                            )
                            .where(
                                published_item.status == ContentItemStatus.PUBLISHED,
                                origin_submission.legacy_row_id.is_not(None),
                                ~any_sync_for_origin,
                            )
                            .order_by(published_item.id.desc())
                            .limit(remaining)
                        )
                    ).scalars().all()
                )

        updated_count = 0
        for published_item_id in dict.fromkeys([*duplicate_ids, *origin_ids]):
            try:
                updated_count += await self.mark_content_item_published(int(published_item_id))
            except Exception as ex:
                logger.error(
                    "Failed to reconcile published content item {} with legacy moderation: {}",
                    published_item_id,
                    ex,
                )
        return updated_count

    @staticmethod
    async def _resolve_moderator_identity(
        bot: AsyncTeleBot,
        *,
        moderator_id: int,
        review_chat_ids: list[int],
    ) -> tuple[str | None, str | None]:
        for review_chat_id in dict.fromkeys(review_chat_ids):
            try:
                member = await run_telegram_operation(
                    bot.get_chat_member(review_chat_id, moderator_id),
                    operation="getModeratorChatMember",
                )
                user = getattr(member, "user", None)
                if user is not None:
                    return getattr(user, "username", None), getattr(user, "first_name", None)
            except Exception as ex:
                logger.debug(
                    "Failed to resolve moderator {} in review chat {}: {}",
                    moderator_id,
                    review_chat_id,
                    ex,
                )

        try:
            user = await run_telegram_operation(
                bot.get_chat(moderator_id),
                operation="getModeratorChat",
            )
            return getattr(user, "username", None), getattr(user, "first_name", None)
        except Exception as ex:
            logger.debug("Failed to resolve moderator {} directly: {}", moderator_id, ex)
            return None, None
