from __future__ import annotations

from fastapi import Depends, FastAPI, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from src.editorial.api.schemas import (
    ChannelResponse,
    ContentItemResponse,
    CreateContentFromSubmissionRequest,
    CreateManualPasteRequest,
    ImportLegacyResponse,
    PasteResponse,
    PublisherRunResponse,
    ReviewContentItemRequest,
    SchedulerRunResponse,
    SeedSlotsRequest,
    SubmissionResponse,
    UpdateSubmissionStatusRequest,
)
from src.editorial.config import settings
from src.editorial.db.session import get_session
from src.editorial.models.enums import ContentItemStatus, SubmissionStatus
from src.editorial.services.channel_service import ChannelService
from src.editorial.services.generation.service import GenerationService
from src.editorial.services.import_legacy import LegacyImporter
from src.editorial.services.moderation import ModerationService
from src.editorial.services.paste_service import PasteService
from src.editorial.services.publisher import PublisherService
from src.editorial.services.scheduler import SchedulerService


app = FastAPI(title="IdeaFlow Editorial API", version="0.1.0")


async def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    if settings.review_api_key and x_api_key != settings.review_api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/importer/run", response_model=ImportLegacyResponse, dependencies=[Depends(require_api_key)])
async def run_importer(session: AsyncSession = Depends(get_session)) -> ImportLegacyResponse:
    result = await LegacyImporter().import_new(session)
    return ImportLegacyResponse.from_result(result)


@app.get("/channels", response_model=list[ChannelResponse], dependencies=[Depends(require_api_key)])
async def list_channels(session: AsyncSession = Depends(get_session)) -> list[ChannelResponse]:
    items = await ChannelService().list_channels(session)
    return [ChannelResponse.model_validate(item) for item in items]


@app.post("/channels/{channel_id}/slots/seed", response_model=dict, dependencies=[Depends(require_api_key)])
async def seed_channel_slots(
    channel_id: int,
    payload: SeedSlotsRequest,
    session: AsyncSession = Depends(get_session),
) -> dict[str, int]:
    created = await ChannelService().seed_daily_slots(
        session=session,
        channel_id=channel_id,
        slot_times=payload.slot_times,
        weekdays=payload.weekdays,
    )
    return {"created_slots": len(created)}


@app.get("/submissions", response_model=list[SubmissionResponse], dependencies=[Depends(require_api_key)])
async def list_submissions(
    status: SubmissionStatus | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
) -> list[SubmissionResponse]:
    items = await ModerationService().list_submissions(session, status=status, limit=limit)
    return [SubmissionResponse.model_validate(item) for item in items]


@app.post("/submissions/{submission_id}/status", response_model=SubmissionResponse, dependencies=[Depends(require_api_key)])
async def update_submission_status(
    submission_id: int,
    payload: UpdateSubmissionStatusRequest,
    session: AsyncSession = Depends(get_session),
) -> SubmissionResponse:
    item = await ModerationService().set_submission_status(
        session=session,
        submission_id=submission_id,
        status=payload.status,
        moderator_note=payload.moderator_note,
    )
    return SubmissionResponse.model_validate(item)


@app.post("/submissions/{submission_id}/content-item", response_model=ContentItemResponse, dependencies=[Depends(require_api_key)])
async def create_content_from_submission(
    submission_id: int,
    payload: CreateContentFromSubmissionRequest,
    session: AsyncSession = Depends(get_session),
) -> ContentItemResponse:
    item = await ModerationService().create_content_from_submission(
        session=session,
        submission_id=submission_id,
        channel_id=payload.channel_id,
        body_text=payload.body_text,
    )
    return ContentItemResponse.model_validate(item)


@app.get("/content-items", response_model=list[ContentItemResponse], dependencies=[Depends(require_api_key)])
async def list_content_items(
    status: ContentItemStatus | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_session),
) -> list[ContentItemResponse]:
    items = await ModerationService().list_content_items(session, status=status, limit=limit)
    return [ContentItemResponse.model_validate(item) for item in items]


@app.post("/content-items/{content_item_id}/review", response_model=ContentItemResponse, dependencies=[Depends(require_api_key)])
async def review_content_item(
    content_item_id: int,
    payload: ReviewContentItemRequest,
    session: AsyncSession = Depends(get_session),
) -> ContentItemResponse:
    item = await ModerationService().review_content_item(
        session=session,
        content_item_id=content_item_id,
        reviewer_id=payload.reviewer_id,
        decision=payload.decision,
        review_note=payload.review_note,
        edited_text=payload.edited_text,
    )
    return ContentItemResponse.model_validate(item)


@app.post("/pastes/manual", response_model=PasteResponse, dependencies=[Depends(require_api_key)])
async def create_manual_paste(
    payload: CreateManualPasteRequest,
    session: AsyncSession = Depends(get_session),
) -> PasteResponse:
    paste = await PasteService().create_manual_paste(
        session=session,
        title=payload.title,
        body_text=payload.body_text,
        created_by=payload.created_by,
    )
    return PasteResponse.model_validate(paste)


@app.post("/pastes/from-submission/{submission_id}", response_model=PasteResponse, dependencies=[Depends(require_api_key)])
async def create_paste_from_submission(
    submission_id: int,
    created_by: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> PasteResponse:
    paste = await PasteService().create_paste_from_submission(session, submission_id, created_by)
    return PasteResponse.model_validate(paste)


@app.post("/pastes/from-content-item/{content_item_id}", response_model=PasteResponse, dependencies=[Depends(require_api_key)])
async def create_paste_from_content_item(
    content_item_id: int,
    created_by: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> PasteResponse:
    paste = await PasteService().create_paste_from_content_item(session, content_item_id, created_by)
    return PasteResponse.model_validate(paste)


@app.get("/pastes/available/{channel_id}", response_model=list[PasteResponse], dependencies=[Depends(require_api_key)])
async def list_available_pastes(
    channel_id: int,
    limit: int = 20,
    session: AsyncSession = Depends(get_session),
) -> list[PasteResponse]:
    items = await PasteService().list_available_for_channel(session, channel_id, limit)
    return [PasteResponse.model_validate(item) for item in items]


@app.post("/pastes/{paste_id}/content-item", response_model=ContentItemResponse, dependencies=[Depends(require_api_key)])
async def create_content_item_from_paste(
    paste_id: int,
    channel_id: int,
    session: AsyncSession = Depends(get_session),
) -> ContentItemResponse:
    item = await PasteService().create_content_item_from_paste(session, paste_id, channel_id)
    return ContentItemResponse.model_validate(item)


@app.post("/scheduler/run", response_model=SchedulerRunResponse, dependencies=[Depends(require_api_key)])
async def run_scheduler(session: AsyncSession = Depends(get_session)) -> SchedulerRunResponse:
    result = await SchedulerService().run(session)
    return SchedulerRunResponse.from_result(result)


@app.post("/publisher/run", response_model=PublisherRunResponse, dependencies=[Depends(require_api_key)])
async def run_publisher(session: AsyncSession = Depends(get_session)) -> PublisherRunResponse:
    result = await PublisherService().run(session)
    return PublisherRunResponse.from_result(result)


@app.post("/generation/run/{channel_id}", dependencies=[Depends(require_api_key)])
async def run_generation(
    channel_id: int,
    variant_count: int = 3,
    source_count: int = 5,
    session: AsyncSession = Depends(get_session),
) -> dict[str, int | str]:
    run = await GenerationService().generate_for_channel(
        session=session,
        channel_id=channel_id,
        variant_count=variant_count,
        source_count=source_count,
    )
    return {
        "generation_run_id": run.id,
        "status": run.status,
        "source_count": run.source_count,
        "generated_count": run.generated_count,
    }
