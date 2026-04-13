from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.editorial.models.content import ContentItem
from src.editorial.models.enums import (
    ContentItemStatus,
    ContentSourceType,
    ReviewDecision,
    SubmissionStatus,
)
from src.editorial.models.review import Review
from src.editorial.models.submission import Submission
from src.editorial.utils.text import compute_text_hash, detect_tags, normalize_text, pick_primary_tag


class ModerationService:
    async def list_submissions(
        self,
        session: AsyncSession,
        status: SubmissionStatus | None = None,
        limit: int = 50,
    ) -> list[Submission]:
        stmt = select(Submission).order_by(Submission.created_at.desc()).limit(limit)
        if status is not None:
            stmt = stmt.where(Submission.status == status)
        return list((await session.execute(stmt)).scalars().all())

    async def set_submission_status(
        self,
        session: AsyncSession,
        submission_id: int,
        status: SubmissionStatus,
        moderator_note: str | None = None,
    ) -> Submission:
        submission = await session.get(Submission, submission_id)
        if submission is None:
            raise ValueError(f"Submission {submission_id} not found")
        submission.status = status
        submission.moderator_note = moderator_note
        submission.reviewed_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(submission)
        return submission

    async def create_content_from_submission(
        self,
        session: AsyncSession,
        submission_id: int,
        channel_id: int | None = None,
        body_text: str | None = None,
        status: ContentItemStatus = ContentItemStatus.PENDING_REVIEW,
    ) -> ContentItem:
        submission = await session.get(Submission, submission_id)
        if submission is None:
            raise ValueError(f"Submission {submission_id} not found")

        content_text = (body_text or submission.cleaned_text or submission.raw_text or "").strip()
        if not content_text:
            raise ValueError("Submission has no text content to convert into a content item")

        tags = detect_tags(content_text)
        item = ContentItem(
            channel_id=channel_id or submission.channel_id,
            source_type=ContentSourceType.SUBMISSION,
            origin_submission_id=submission.id,
            body_text=content_text,
            normalized_text=normalize_text(content_text),
            text_hash=compute_text_hash(content_text) or "",
            primary_tag=pick_primary_tag(tags),
            tags=tags,
            template_key="submission_plain",
            tone_key="community",
            review_required=True,
            status=status,
        )
        session.add(item)
        submission.status = SubmissionStatus.CONTENT_CREATED
        submission.reviewed_at = datetime.now(timezone.utc)
        await session.commit()
        await session.refresh(item)
        return item

    async def list_content_items(
        self,
        session: AsyncSession,
        status: ContentItemStatus | None = None,
        limit: int = 50,
    ) -> list[ContentItem]:
        stmt = select(ContentItem).order_by(ContentItem.created_at.desc()).limit(limit)
        if status is not None:
            stmt = stmt.where(ContentItem.status == status)
        return list((await session.execute(stmt)).scalars().all())

    async def review_content_item(
        self,
        session: AsyncSession,
        content_item_id: int,
        reviewer_id: int,
        decision: ReviewDecision,
        review_note: str | None = None,
        edited_text: str | None = None,
    ) -> ContentItem:
        item = await session.get(ContentItem, content_item_id)
        if item is None:
            raise ValueError(f"Content item {content_item_id} not found")

        if decision == ReviewDecision.APPROVE:
            item.status = ContentItemStatus.APPROVED
        elif decision == ReviewDecision.REJECT:
            item.status = ContentItemStatus.REJECTED
        elif decision == ReviewDecision.HOLD:
            item.status = ContentItemStatus.HOLD
        elif decision == ReviewDecision.EDIT_AND_APPROVE:
            if not edited_text:
                raise ValueError("edited_text is required for edit_and_approve")
            tags = detect_tags(edited_text)
            item.body_text = edited_text
            item.normalized_text = normalize_text(edited_text)
            item.text_hash = compute_text_hash(edited_text) or ""
            item.tags = tags
            item.primary_tag = pick_primary_tag(tags)
            item.status = ContentItemStatus.APPROVED
        else:
            raise ValueError(f"Unsupported review decision for content items: {decision}")

        session.add(
            Review(
                content_item_id=item.id,
                reviewer_id=reviewer_id,
                decision=decision,
                review_note=review_note,
                edited_text=edited_text,
                created_at=datetime.now(timezone.utc),
            )
        )
        await session.commit()
        await session.refresh(item)
        return item

