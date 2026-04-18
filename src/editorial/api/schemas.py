from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict

from src.editorial.models.enums import (
    ContentItemStatus,
    PasteStatus,
    ReviewDecision,
    SubmissionStatus,
)
from src.editorial.services.import_legacy import ImportLegacyResult
from src.editorial.services.publisher import PublisherRunResult
from src.editorial.services.scheduler import SchedulerRunResult


class SubmissionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: int
    legacy_row_id: int | None
    username: str | None
    first_name: str | None
    content_type: str
    media_group_id: str | None
    cleaned_text: str | None
    detected_tags: list[str]
    status: SubmissionStatus
    created_at: datetime


class ChannelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tg_channel_id: int
    title: str | None
    short_code: str
    is_active: bool
    timezone: str


class ContentItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    channel_id: int
    source_type: str
    origin_submission_id: int | None
    origin_paste_id: int | None
    body_text: str
    primary_tag: str | None
    tags: list[str]
    status: ContentItemStatus
    scheduled_for: datetime | None
    created_at: datetime


class PasteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    body_text: str
    primary_tag: str | None
    tags: list[str]
    status: PasteStatus
    created_at: datetime


class UpdateSubmissionStatusRequest(BaseModel):
    status: SubmissionStatus
    moderator_note: str | None = None


class CreateContentFromSubmissionRequest(BaseModel):
    channel_id: int | None = None
    body_text: str | None = None


class ReviewContentItemRequest(BaseModel):
    reviewer_id: int
    decision: ReviewDecision
    review_note: str | None = None
    edited_text: str | None = None


class CreateManualPasteRequest(BaseModel):
    title: str
    body_text: str
    created_by: int | None = None


class SeedSlotsRequest(BaseModel):
    slot_times: list[str]
    weekdays: list[int] | None = None


class ImportLegacyResponse(BaseModel):
    scanned: int
    imported: int
    skipped_duplicates: int
    channels_created: int
    last_legacy_id: int

    @classmethod
    def from_result(cls, result: ImportLegacyResult) -> "ImportLegacyResponse":
        return cls(**result.__dict__)


class SchedulerRunResponse(BaseModel):
    channels_checked: int
    slots_checked: int
    scheduled_items: int

    @classmethod
    def from_result(cls, result: SchedulerRunResult) -> "SchedulerRunResponse":
        return cls(**result.__dict__)


class PublisherRunResponse(BaseModel):
    attempted: int
    sent: int
    failed: int

    @classmethod
    def from_result(cls, result: PublisherRunResult) -> "PublisherRunResponse":
        return cls(**result.__dict__)
