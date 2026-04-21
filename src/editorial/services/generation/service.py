from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import re

from loguru import logger
from sqlalchemy import case, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.editorial.config import settings
from src.editorial.models.channel import Channel
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


BAD_VARIANT_PHRASES = (
    "есть ли вам",
    "отвечайте на материалы",
    "отвечайте материалы",
    "отвечайте на",
    "что кажется вам наиболее полезным для изучения",
    "конспекты или материалы с прошлых пар",
    "с прошлых пар",
    "говорят, там",
    "кто-то находил",
    "кто нибудь находил",
    "кто-нибудь находил тетрадь",
    "находил тетрад",
    "находил блокнот",
    "забыла",
    "забыл",
    "потеряла",
    "потерял",
    "аудитории а-",
    "аудитория а-",
    "кабинет а-",
    "тематическим проектам",
    "на след неделе",
    "на следующей неделе",
    "на прошлой неделе",
    "экзамен уже на носу",
    "шпаргалк",
)

QUESTION_OR_COMMUNITY_MARKERS = (
    "кто ",
    "как ",
    "где ",
    "какие ",
    "какой ",
    "какая ",
    "куда ",
    "подскажите",
    "поделитесь",
    "есть тут",
    "есть ли",
    "у кого",
    "что думаете",
    "может кто",
    "кто знает",
    "посоветуйте",
    "нужны",
    "ищу",
)

FAKE_PRECISION_PATTERNS = (
    re.compile(r"\b[а-яёa-z]-\d{2,4}\b", re.IGNORECASE),
    re.compile(r"\bаудитори[яи]\s+[а-яёa-z]?-?\d{2,4}\b", re.IGNORECASE),
    re.compile(r"\bкабинет\s+[а-яёa-z]?-?\d{2,4}\b", re.IGNORECASE),
)


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
        prompt_version: str = "v2_realistic_student_posts",
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

        channel = await session.get(Channel, channel_id)
        if channel is None:
            run.status = GenerationStatus.FAILED
            run.error_text = f"Channel {channel_id} not found"
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

        requested_count = min(12, max(variant_count + 2, variant_count * 2))
        prompt = self._build_prompt(
            sources=sources,
            variant_count=requested_count,
            channel_name=self._channel_prompt_name(channel),
        )

        try:
            raw_variants = await self.provider.generate_variants(prompt, requested_count)
            run.model_name = getattr(self.provider, "last_model_name", run.model_name)
            variants = self._prepare_variants(raw_variants, variant_count)
            if not variants:
                run.status = GenerationStatus.FAILED
                run.error_text = "Provider returned no usable variants"
                run.finished_at = datetime.now(timezone.utc)
                await session.commit()
                return run

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
            run.model_name = getattr(self.provider, "last_model_name", run.model_name)
            run.error_text = str(ex) or ex.__class__.__name__
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

    @staticmethod
    def _channel_prompt_name(channel: Channel) -> str:
        title = (channel.title or "").strip()
        short_code = (channel.short_code or "").strip()
        if title and short_code and title.lower() != short_code.lower():
            return f"{title} ({short_code})"
        return title or short_code or f"channel {channel.id}"

    @staticmethod
    def _prepare_variants(variants: list[str], limit: int) -> list[str]:
        prepared: list[str] = []
        seen: set[str] = set()
        for raw_variant in variants:
            variant = raw_variant.strip(" \n\t-–—")
            variant = re.sub(r"^\d+[.)]\s*", "", variant).strip()
            variant = re.sub(r"\s+", " ", variant)
            if not GenerationService._looks_like_good_variant(variant):
                continue
            key = normalize_text(variant)
            if not key or key in seen:
                continue
            seen.add(key)
            prepared.append(variant[:900])
            if len(prepared) >= limit:
                break
        return prepared

    @staticmethod
    def _looks_like_good_variant(variant: str) -> bool:
        if len(variant) < 35 or len(variant) > 900:
            return False

        normalized = normalize_text(variant)
        if not normalized:
            return False

        words = re.findall(r"[а-яёa-z0-9]+", normalized, flags=re.IGNORECASE)
        if len(words) < 7:
            return False

        if any(phrase in normalized for phrase in BAD_VARIANT_PHRASES):
            return False

        if any(pattern.search(normalized) for pattern in FAKE_PRECISION_PATTERNS):
            return False

        return "?" in variant or any(marker in normalized for marker in QUESTION_OR_COMMUNITY_MARKERS)

    def _build_prompt(
        self,
        *,
        sources: list[Submission],
        variant_count: int,
        channel_name: str,
    ) -> str:
        tags = Counter(tag for submission in sources for tag in submission.detected_tags)
        top_tags = ", ".join(tag for tag, _ in tags.most_common(3)) or "student_life"
        source_lines = "\n".join(
            f"- {(submission.cleaned_text or submission.raw_text or '').strip()[:280]}"
            for submission in sources
        )
        banned_phrases = ", ".join(f'"{phrase}"' for phrase in BAD_VARIANT_PHRASES[:8])
        return (
            "You generate draft posts for an anonymous Russian student Telegram channel.\n"
            f"Channel name: {channel_name}\n"
            f"Draft count: {variant_count}\n"
            f"Theme tags from sources: {top_tags}\n\n"
            "Output language: natural, idiomatic Russian only. Do not write explanations.\n\n"
            "How to use the channel name:\n"
            "- Treat it as soft context. If it clearly contains a university name or acronym, broad references are allowed.\n"
            "- Do not invent buildings, classrooms, groups, teachers, exact dates, schedules, events, lost items, or local slang.\n\n"
            "How to use source messages:\n"
            "- Use them only as thematic hints.\n"
            "- Keep the topic specific enough to feel real, but do not fabricate concrete personal facts.\n"
            "- If a source mentions a subject like math, physics, exams, dorms, admissions, sport, music, or social life, you may build around that broad topic.\n\n"
            "Good draft types:\n"
            "1. A concrete study/help question with a clear subject or topic.\n"
            "2. A social question like 'are there people into X here?' when X is broad and plausible.\n"
            "3. A calm discussion prompt about a common student situation.\n"
            "4. A request for resources with a clear topic, not vague 'some classes'.\n"
            "5. A short advice request without fake personal drama.\n"
            "6. A neutral campus/community question that could naturally appear in a university anonymous channel.\n\n"
            "Hard quality rules:\n"
            "- Every draft must be grammatically correct Russian. Before final output, silently proofread each draft.\n"
            "- Reject machine-translated phrases and broken constructions.\n"
            "- Never use phrases like: "
            f"{banned_phrases}.\n"
            "- Do not write generic filler like 'what is most useful for studying?' unless it has a concrete subject.\n"
            "- Do not create fake exact rooms like A-308 or invented incidents like a found notebook.\n"
            "- Do not invent timing like 'next week', 'tomorrow', or 'exam is soon' unless the source says it.\n"
            "- Do not ask for cheating materials or cheat sheets.\n"
            "- No hashtags. At most one emoji across the entire output.\n\n"
            "Style:\n"
            "- 1-3 sentences per draft.\n"
            "- Plain student Telegram language, not official editorial language.\n"
            "- A little informal is fine, but do not use insults or calls for conflict.\n"
            "- Prefer questions that a real student might send anonymously.\n\n"
            "Return exactly the requested number of drafts as a numbered list. Output only the drafts.\n\n"
            f"Source messages:\n{source_lines}"
        )
