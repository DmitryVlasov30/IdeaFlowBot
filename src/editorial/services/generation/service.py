from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.editorial.config import settings
from src.editorial.models.content import ContentItem, ContentItemSource
from src.editorial.models.enums import (
    ContentItemStatus,
    ContentSourceType,
    GenerationStatus,
    SubmissionStatus,
)
from src.editorial.models.generation import GenerationRun
from src.editorial.models.submission import Submission
from src.editorial.services.generation.providers import (
    BaseGenerationProvider,
    OpenRouterGenerationProvider,
    StubGenerationProvider,
)
from src.editorial.utils.text import compute_text_hash, detect_tags, normalize_text, pick_primary_tag


class GenerationService:
    def __init__(self, provider: BaseGenerationProvider | None = None):
        self.provider = provider or self._resolve_provider()

    def _resolve_provider(self) -> BaseGenerationProvider:
        if settings.generation_default_provider == "openrouter":
            return OpenRouterGenerationProvider()
        return StubGenerationProvider()

    async def generate_for_channel(
        self,
        session: AsyncSession,
        channel_id: int,
        variant_count: int = 3,
        source_count: int = 5,
        prompt_version: str = "v1_simple",
    ) -> GenerationRun:
        now = datetime.now(timezone.utc)
        run = GenerationRun(
            channel_id=channel_id,
            provider=self.provider.name,
            model_name=settings.generation_model_name,
            prompt_version=prompt_version,
            source_count=0,
            generated_count=0,
            status=GenerationStatus.PENDING,
            created_at=now,
        )
        session.add(run)
        await session.flush()

        if not settings.generation_enabled:
            run.status = GenerationStatus.DISABLED
            run.finished_at = now
            await session.commit()
            return run

        sources = await self._select_sources(session, channel_id, source_count)
        run.source_count = len(sources)
        if not sources:
            run.status = GenerationStatus.FAILED
            run.error_text = "No suitable submissions available for generation"
            run.finished_at = now
            await session.commit()
            return run

        prompt = self._build_prompt(sources, variant_count)

        try:
            variants = await self.provider.generate_variants(prompt, variant_count)
            for body_text in variants:
                tags = detect_tags(body_text)
                item = ContentItem(
                    channel_id=channel_id,
                    source_type=ContentSourceType.GENERATED,
                    body_text=body_text,
                    normalized_text=normalize_text(body_text),
                    text_hash=compute_text_hash(body_text) or "",
                    primary_tag=pick_primary_tag(tags),
                    tags=tags,
                    template_key="generated_question" if "?" in body_text else "generated_digest",
                    tone_key="soft_discussion",
                    priority=120,
                    review_required=True,
                    status=ContentItemStatus.PENDING_REVIEW,
                    generation_run_id=run.id,
                )
                session.add(item)
                await session.flush()
                for source in sources:
                    session.add(
                        ContentItemSource(
                            content_item_id=item.id,
                            submission_id=source.id,
                            role="generation_source",
                        )
                    )
            run.generated_count = len(variants)
            run.status = GenerationStatus.COMPLETED
            run.finished_at = datetime.now(timezone.utc)
            await session.commit()
            return run
        except Exception as ex:
            logger.exception("Generation failed for channel {}", channel_id)
            run.status = GenerationStatus.FAILED
            run.error_text = str(ex)
            run.finished_at = datetime.now(timezone.utc)
            await session.commit()
            return run

    async def _select_sources(
        self,
        session: AsyncSession,
        channel_id: int,
        limit: int,
    ) -> list[Submission]:
        preferred_order = case(
            (Submission.status == SubmissionStatus.APPROVED_AS_SOURCE, 0),
            (Submission.status == SubmissionStatus.CONTENT_CREATED, 1),
            (Submission.status == SubmissionStatus.PASTE_CANDIDATE, 2),
            (Submission.status == SubmissionStatus.NEW, 3),
            else_=99,
        )
        stmt = (
            select(Submission)
            .where(
                Submission.channel_id == channel_id,
                Submission.is_candidate_for_generation.is_(True),
                Submission.cleaned_text.is_not(None),
                Submission.status.in_(
                    [
                        SubmissionStatus.NEW,
                        SubmissionStatus.APPROVED_AS_SOURCE,
                        SubmissionStatus.CONTENT_CREATED,
                        SubmissionStatus.PASTE_CANDIDATE,
                    ]
                ),
            )
            .order_by(preferred_order.asc(), Submission.created_at.desc())
            .limit(limit)
        )
        return list((await session.execute(stmt)).scalars().all())

    def _build_prompt(self, sources: list[Submission], variant_count: int) -> str:
        tags = Counter(tag for submission in sources for tag in submission.detected_tags)
        top_tags = ", ".join(tag for tag, _ in tags.most_common(3)) or "student_life"
        source_lines = "\n".join(
            f"- {(submission.cleaned_text or submission.raw_text or '').strip()[:280]}"
            for submission in sources
        )
        return (
            f"Нужно подготовить {variant_count} коротких безопасных черновика постов для студенческого канала.\n"
            f"Главные темы: {top_tags}.\n"
            "Форматы допустимы только такие: question, topic_digest, motive_post.\n"
            "Не выдумывай историю от лица конкретного человека. Пиши нейтрально и мягко.\n"
            "Верни просто список вариантов, каждый в отдельной строке с номером.\n"
            f"Источники:\n{source_lines}"
        )

