from __future__ import annotations

from loguru import logger
from sqlalchemy import select
from telebot.async_telebot import AsyncTeleBot

from src.editorial.db.session import session_factory
from src.editorial.models.channel import Channel
from src.editorial.models.content import ContentItem
from src.editorial.models.enums import ContentItemStatus, ReviewDecision
from src.editorial.models.review import Review
from src.editorial.models.submission import Submission
from src.editorial.services.legacy_source import LegacyCollectorReader
from src.editorial.services.moderation import ModerationService
from src.editorial.services.telegram_publisher import telegram_bot_session
from src.editorial.services.telegram_resilience import run_telegram_operation
from src.markups import build_slot_status_markup


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
            submission_by_legacy_row_id = {
                related.legacy_row_id: related
                for related in related_submissions
                if related.legacy_row_id is not None
            }
            moderator_id = int(latest_approval.reviewer_id)
            channel_tg_id = int(channel.tg_channel_id)

        if not submission_by_legacy_row_id:
            return 0
        legacy_rows = await self.legacy_reader.fetch_sender_rows_by_ids(list(submission_by_legacy_row_id))
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
            moderator_username, moderator_first_name = await self._resolve_moderator_identity(
                bot,
                moderator_id=moderator_id,
                review_chat_ids=[int(row.review_chat_id) for row in review_rows],
            )

            updated_count = 0
            for row in review_rows:
                related_submission = submission_by_legacy_row_id.get(row.id)
                sender_id = row.user_id or (
                    related_submission.source_user_id if related_submission is not None else None
                )
                markup = build_slot_status_markup(
                    sender_id=sender_id,
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
                except Exception as ex:
                    logger.error(
                        "Failed to mark published content item {} on review message {} in chat {}: {}",
                        content_item_id,
                        row.review_message_id,
                        row.review_chat_id,
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
