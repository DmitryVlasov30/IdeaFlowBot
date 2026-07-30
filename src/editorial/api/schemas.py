from __future__ import annotations

from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, Field

from src.editorial.models.enums import (
    ContentItemStatus,
    PasteStatus,
    ReviewDecision,
    SubmissionStatus,
)
from src.editorial.services.auto_slot_planner import AutoSlotPlannerResult
from src.editorial.services.channel_profile_service import ChannelProfileSyncResult
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
    auto_slots_enabled: bool
    auto_slots_plan_time: time
    auto_slots_window_start: time
    auto_slots_window_end: time
    auto_slots_replace_manual: bool
    subscriber_count: int | None
    subscriber_count_checked_at: datetime | None
    settings_profile_id: int | None
    settings_profile_auto_enabled: bool
    settings_profile_applied_at: datetime | None


class ChannelSettingProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    slug: str
    title: str
    is_active: bool
    priority: int
    min_subscribers: int
    max_subscribers: int | None
    timezone: str | None
    min_gap_minutes: int
    slot_jitter_minutes: int
    auto_slots_enabled: bool
    auto_slots_plan_time: time
    auto_slots_window_start: time
    auto_slots_window_end: time
    auto_slots_replace_manual: bool
    max_posts_per_day: int
    max_generated_per_day: int
    max_paste_per_day: int
    same_tag_cooldown_hours: int
    same_template_cooldown_hours: int
    same_paste_cooldown_days: int
    min_ready_queue: int
    prefer_real_ratio: int
    allow_generated: bool
    allow_pastes: bool


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


class UpsertChannelSettingProfileRequest(BaseModel):
    slug: str
    title: str | None = None
    min_subscribers: int | None = None
    max_subscribers: int | None = None
    priority: int | None = None
    is_active: bool | None = None
    settings: dict[str, str] = Field(default_factory=dict)


class ApplyChannelSettingProfileRequest(BaseModel):
    profile_slug: str
    auto_enabled: bool = False


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


class AutoSlotPlannerRunResponse(BaseModel):
    channels_checked: int
    channels_planned: int
    slots_deleted: int
    slots_created: int

    @classmethod
    def from_result(cls, result: AutoSlotPlannerResult) -> "AutoSlotPlannerRunResponse":
        return cls(
            channels_checked=result.channels_checked,
            channels_planned=result.channels_planned,
            slots_deleted=result.slots_deleted,
            slots_created=result.slots_created,
        )


class ChannelProfileSyncResponse(BaseModel):
    channels_checked: int
    subscriber_counts_updated: int
    profiles_changed: int
    skipped_manual: int
    failed: int

    @classmethod
    def from_result(cls, result: ChannelProfileSyncResult) -> "ChannelProfileSyncResponse":
        return cls(
            channels_checked=result.channels_checked,
            subscriber_counts_updated=result.subscriber_counts_updated,
            profiles_changed=result.profiles_changed,
            skipped_manual=result.skipped_manual,
            failed=result.failed,
        )


class PublisherRunResponse(BaseModel):
    attempted: int
    sent: int
    failed: int

    @classmethod
    def from_result(cls, result: PublisherRunResult) -> "PublisherRunResponse":
        return cls(**result.__dict__)
