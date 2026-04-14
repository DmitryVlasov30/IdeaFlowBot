from __future__ import annotations

from enum import StrEnum
from typing import Type

from sqlalchemy import Enum


class SubmissionStatus(StrEnum):
    NEW = "new"
    APPROVED_AS_SOURCE = "approved_as_source"
    PASTE_CANDIDATE = "paste_candidate"
    CONTENT_CREATED = "content_created"
    REJECTED = "rejected"
    HOLD = "hold"


class ContentSourceType(StrEnum):
    SUBMISSION = "submission"
    GENERATED = "generated"
    PASTE = "paste"
    EDITORIAL = "editorial"


class ContentItemStatus(StrEnum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    REJECTED = "rejected"
    HOLD = "hold"


class ReviewDecision(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    HOLD = "hold"
    EDIT_AND_APPROVE = "edit_and_approve"
    SAVE_AS_PASTE = "save_as_paste"
    APPROVE_AS_SOURCE = "approve_as_source"


class PublicationStatus(StrEnum):
    SCHEDULED = "scheduled"
    SENT = "sent"
    FAILED = "failed"
    CANCELLED = "cancelled"


class GenerationStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    DISABLED = "disabled"


class PasteStatus(StrEnum):
    DRAFT = "draft"
    ACTIVE = "active"
    ARCHIVED = "archived"


def enum_column(enum_cls: Type[StrEnum], name: str) -> Enum:
    return Enum(
        enum_cls,
        name=name,
        values_callable=lambda members: [member.value for member in members],
        validate_strings=True,
    )
