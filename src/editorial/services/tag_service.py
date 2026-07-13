from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re

from sqlalchemy import delete as sql_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.editorial.models.enums import ChannelPasteTagRuleMode, TagAssignmentSource, TagMatchType
from src.editorial.models.paste import PasteLibrary
from src.editorial.models.tag import ChannelPasteTagRule, PasteTagAssignment, TagDefinition, TagKeyword
from src.editorial.utils.text import detect_tags as legacy_detect_tags
from src.editorial.utils.text import normalize_text


DEFAULT_TAG_RULES: dict[str, tuple[str, int, tuple[str, ...]]] = {
    "study": ("Учёба", 10, ("сесс", "экзам", "зачет", "препод", "лекц", "лаба")),
    "relationships": ("Отношения", 20, ("парень", "девуш", "отношен", "любов", "бывш")),
    "dorm": ("Общага", 30, ("общага", "общежит", "коменда")),
    "money": ("Деньги и работа", 40, ("деньг", "стипенд", "работ", "зарплат")),
    "social": ("Социалка", 50, ("друз", "компан", "тусов", "вечерин")),
    "question": ("Вопросы", 60, ("кто", "как", "что делать", "посоветуйте", "подскажите")),
}

SLUG_RE = re.compile(r"[^0-9a-zа-яё_]+", re.IGNORECASE)


@dataclass(slots=True)
class PasteTagSummary:
    auto_tags: list[str]
    manual_tags: list[str]
    all_tags: list[str]
    primary_tag: str | None


class TagService:
    @staticmethod
    def normalize_slug(value: str) -> str:
        normalized = normalize_text(value).replace(" ", "_")
        normalized = SLUG_RE.sub("_", normalized).strip("_")
        return normalized[:64]

    async def ensure_default_tags(self, session: AsyncSession) -> None:
        existing_count = await session.scalar(select(func.count()).select_from(TagDefinition))
        if existing_count:
            return

        for slug, (title, priority, keywords) in DEFAULT_TAG_RULES.items():
            tag = TagDefinition(slug=slug, title=title, priority=priority, is_active=True)
            session.add(tag)
            await session.flush()
            for keyword in keywords:
                session.add(
                    TagKeyword(
                        tag_id=tag.id,
                        keyword=keyword,
                        normalized_keyword=normalize_text(keyword),
                        match_type=TagMatchType.CONTAINS,
                        is_active=True,
                    )
                )
        await session.flush()

    async def list_tags(self, session: AsyncSession, include_inactive: bool = True) -> list[TagDefinition]:
        await self.ensure_default_tags(session)
        stmt = select(TagDefinition).order_by(TagDefinition.priority.asc(), TagDefinition.slug.asc())
        if not include_inactive:
            stmt = stmt.where(TagDefinition.is_active.is_(True))
        return list((await session.execute(stmt)).scalars().all())

    async def get_tag_by_slug(self, session: AsyncSession, slug: str) -> TagDefinition | None:
        normalized_slug = self.normalize_slug(slug)
        if not normalized_slug:
            return None
        return await session.scalar(select(TagDefinition).where(TagDefinition.slug == normalized_slug).limit(1))

    async def create_tag(
        self,
        session: AsyncSession,
        *,
        slug: str,
        title: str | None = None,
        description: str | None = None,
        priority: int = 100,
        created_by: int | None = None,
    ) -> TagDefinition:
        normalized_slug = self.normalize_slug(slug)
        if not normalized_slug:
            raise ValueError("Tag slug is empty")
        existing = await self.get_tag_by_slug(session, normalized_slug)
        if existing is not None:
            raise ValueError(f"Tag {normalized_slug} already exists")
        tag = TagDefinition(
            slug=normalized_slug,
            title=(title or normalized_slug).strip()[:120],
            description=description,
            priority=priority,
            is_active=True,
            created_by=created_by,
        )
        session.add(tag)
        await session.commit()
        await session.refresh(tag)
        return tag

    async def set_tag_active(self, session: AsyncSession, *, slug: str, is_active: bool) -> TagDefinition:
        tag = await self.get_tag_by_slug(session, slug)
        if tag is None:
            raise ValueError(f"Tag {slug} not found")
        tag.is_active = is_active
        await session.commit()
        await session.refresh(tag)
        return tag

    async def list_keywords(self, session: AsyncSession, tag_slug: str) -> list[TagKeyword]:
        tag = await self.get_tag_by_slug(session, tag_slug)
        if tag is None:
            raise ValueError(f"Tag {tag_slug} not found")
        stmt = select(TagKeyword).where(TagKeyword.tag_id == tag.id).order_by(TagKeyword.keyword.asc())
        return list((await session.execute(stmt)).scalars().all())

    async def add_keyword(
        self,
        session: AsyncSession,
        *,
        tag_slug: str,
        keyword: str,
        match_type: TagMatchType = TagMatchType.CONTAINS,
    ) -> TagKeyword:
        tag = await self.get_tag_by_slug(session, tag_slug)
        if tag is None:
            raise ValueError(f"Tag {tag_slug} not found")
        cleaned_keyword = keyword.strip()
        normalized_keyword = normalize_text(cleaned_keyword)
        if not normalized_keyword:
            raise ValueError("Keyword is empty")
        existing = await session.scalar(
            select(TagKeyword)
            .where(
                TagKeyword.tag_id == tag.id,
                TagKeyword.normalized_keyword == normalized_keyword,
                TagKeyword.match_type == match_type,
            )
            .limit(1)
        )
        if existing is not None:
            existing.keyword = cleaned_keyword
            existing.is_active = True
            await session.commit()
            await session.refresh(existing)
            return existing

        row = TagKeyword(
            tag_id=tag.id,
            keyword=cleaned_keyword,
            normalized_keyword=normalized_keyword,
            match_type=match_type,
            is_active=True,
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row

    async def remove_keyword(self, session: AsyncSession, keyword_id: int) -> TagKeyword:
        keyword = await session.get(TagKeyword, keyword_id)
        if keyword is None:
            raise ValueError(f"Keyword {keyword_id} not found")
        keyword.is_active = False
        await session.commit()
        await session.refresh(keyword)
        return keyword

    async def detect_tags(self, session: AsyncSession, text: str | None) -> list[str]:
        normalized = normalize_text(text)
        if not normalized:
            return []
        await self.ensure_default_tags(session)
        rows = list(
            (
                await session.execute(
                    select(TagDefinition, TagKeyword)
                    .join(TagKeyword, TagKeyword.tag_id == TagDefinition.id)
                    .where(TagDefinition.is_active.is_(True), TagKeyword.is_active.is_(True))
                    .order_by(TagDefinition.priority.asc(), TagDefinition.slug.asc(), TagKeyword.id.asc())
                )
            ).all()
        )
        if not rows:
            return legacy_detect_tags(text)

        found: list[str] = []
        seen: set[str] = set()
        for tag, keyword in rows:
            if tag.slug in seen:
                continue
            if self._matches(normalized, keyword):
                found.append(tag.slug)
                seen.add(tag.slug)
        return found

    async def pick_primary_tag(self, session: AsyncSession, tags: list[str]) -> str | None:
        if not tags:
            return None
        ordered = await self._ordered_active_slugs(session, tags)
        return ordered[0] if ordered else tags[0]

    async def apply_tags_to_content_cache(self, session: AsyncSession, text: str | None) -> tuple[list[str], str | None]:
        tags = await self.detect_tags(session, text)
        return tags, await self.pick_primary_tag(session, tags)

    async def sync_paste_auto_tags(self, session: AsyncSession, paste: PasteLibrary) -> PasteTagSummary:
        await self.ensure_default_tags(session)
        await session.execute(
            sql_delete(PasteTagAssignment).where(
                PasteTagAssignment.paste_id == paste.id,
                PasteTagAssignment.source == TagAssignmentSource.AUTO,
            )
        )
        auto_slugs = await self.detect_tags(session, paste.body_text)
        tag_map = await self._tag_map_by_slug(session, auto_slugs)
        now = datetime.now(timezone.utc)
        for slug in auto_slugs:
            tag = tag_map.get(slug)
            if tag is None:
                continue
            session.add(
                PasteTagAssignment(
                    paste_id=paste.id,
                    tag_id=tag.id,
                    source=TagAssignmentSource.AUTO,
                    created_at=now,
                )
            )
        await session.flush()
        return await self.refresh_paste_tag_cache(session, paste)

    async def add_paste_manual_tag(
        self,
        session: AsyncSession,
        *,
        paste: PasteLibrary,
        tag_slug: str,
        created_by: int | None,
    ) -> PasteTagSummary:
        tag = await self.get_tag_by_slug(session, tag_slug)
        if tag is None:
            raise ValueError(f"Tag {tag_slug} not found")
        existing = await session.scalar(
            select(PasteTagAssignment)
            .where(
                PasteTagAssignment.paste_id == paste.id,
                PasteTagAssignment.tag_id == tag.id,
                PasteTagAssignment.source == TagAssignmentSource.MANUAL,
            )
            .limit(1)
        )
        if existing is None:
            session.add(
                PasteTagAssignment(
                    paste_id=paste.id,
                    tag_id=tag.id,
                    source=TagAssignmentSource.MANUAL,
                    created_by=created_by,
                    created_at=datetime.now(timezone.utc),
                )
            )
            await session.flush()
        return await self.refresh_paste_tag_cache(session, paste)

    async def remove_paste_manual_tag(
        self,
        session: AsyncSession,
        *,
        paste: PasteLibrary,
        tag_slug: str,
    ) -> PasteTagSummary:
        tag = await self.get_tag_by_slug(session, tag_slug)
        if tag is None:
            raise ValueError(f"Tag {tag_slug} not found")
        await session.execute(
            sql_delete(PasteTagAssignment).where(
                PasteTagAssignment.paste_id == paste.id,
                PasteTagAssignment.tag_id == tag.id,
                PasteTagAssignment.source == TagAssignmentSource.MANUAL,
            )
        )
        await session.flush()
        return await self.refresh_paste_tag_cache(session, paste)

    async def set_paste_primary_tag(self, session: AsyncSession, *, paste: PasteLibrary, tag_slug: str) -> PasteTagSummary:
        normalized_slug = self.normalize_slug(tag_slug)
        current_tags = set(paste.tags or [])
        if normalized_slug not in current_tags:
            raise ValueError(f"Paste does not have tag {normalized_slug}")
        paste.primary_tag = normalized_slug
        await session.flush()
        return await self.get_paste_tag_summary(session, paste)

    async def refresh_paste_tag_cache(self, session: AsyncSession, paste: PasteLibrary) -> PasteTagSummary:
        summary = await self.get_paste_tag_summary(session, paste, use_cache=False)
        paste.tags = summary.all_tags
        if paste.primary_tag not in summary.all_tags:
            paste.primary_tag = await self.pick_primary_tag(session, summary.all_tags)
        await session.flush()
        return await self.get_paste_tag_summary(session, paste, use_cache=True)

    async def get_paste_tag_summary(
        self,
        session: AsyncSession,
        paste: PasteLibrary,
        *,
        use_cache: bool = True,
    ) -> PasteTagSummary:
        if use_cache and paste.tags:
            all_tags = list(paste.tags or [])
            auto_tags, manual_tags = await self._paste_assignment_slugs(session, paste.id)
            return PasteTagSummary(auto_tags=auto_tags, manual_tags=manual_tags, all_tags=all_tags, primary_tag=paste.primary_tag)

        auto_tags, manual_tags = await self._paste_assignment_slugs(session, paste.id)
        all_tags = await self._ordered_active_slugs(session, list(dict.fromkeys([*auto_tags, *manual_tags])))
        return PasteTagSummary(auto_tags=auto_tags, manual_tags=manual_tags, all_tags=all_tags, primary_tag=paste.primary_tag)

    async def add_channel_paste_tag_rule(
        self,
        session: AsyncSession,
        *,
        channel_id: int,
        tag_slug: str,
        mode: ChannelPasteTagRuleMode,
        created_by: int | None = None,
    ) -> ChannelPasteTagRule:
        tag = await self.get_tag_by_slug(session, tag_slug)
        if tag is None:
            raise ValueError(f"Tag {tag_slug} not found")
        existing = await session.scalar(
            select(ChannelPasteTagRule)
            .where(
                ChannelPasteTagRule.channel_id == channel_id,
                ChannelPasteTagRule.tag_id == tag.id,
                ChannelPasteTagRule.mode == mode,
            )
            .limit(1)
        )
        if existing is not None:
            existing.is_active = True
            await session.commit()
            await session.refresh(existing)
            return existing
        rule = ChannelPasteTagRule(
            channel_id=channel_id,
            tag_id=tag.id,
            mode=mode,
            is_active=True,
            created_by=created_by,
        )
        session.add(rule)
        await session.commit()
        await session.refresh(rule)
        return rule

    async def remove_channel_paste_tag_rule(
        self,
        session: AsyncSession,
        *,
        channel_id: int,
        tag_slug: str,
        mode: ChannelPasteTagRuleMode,
    ) -> int:
        tag = await self.get_tag_by_slug(session, tag_slug)
        if tag is None:
            raise ValueError(f"Tag {tag_slug} not found")
        result = await session.execute(
            sql_delete(ChannelPasteTagRule).where(
                ChannelPasteTagRule.channel_id == channel_id,
                ChannelPasteTagRule.tag_id == tag.id,
                ChannelPasteTagRule.mode == mode,
            )
        )
        await session.commit()
        return int(result.rowcount or 0)

    async def list_channel_paste_tag_rules(self, session: AsyncSession, channel_id: int) -> list[tuple[ChannelPasteTagRule, TagDefinition]]:
        await self.ensure_default_tags(session)
        return list(
            (
                await session.execute(
                    select(ChannelPasteTagRule, TagDefinition)
                    .join(TagDefinition, TagDefinition.id == ChannelPasteTagRule.tag_id)
                    .where(ChannelPasteTagRule.channel_id == channel_id)
                    .order_by(ChannelPasteTagRule.mode.asc(), TagDefinition.priority.asc(), TagDefinition.slug.asc())
                )
            ).all()
        )

    async def is_paste_allowed_for_channel_tags(
        self,
        session: AsyncSession,
        *,
        paste: PasteLibrary,
        channel_id: int,
    ) -> bool:
        paste_tags = set(paste.tags or [])
        if paste.primary_tag:
            paste_tags.add(paste.primary_tag)

        now = datetime.now(timezone.utc)
        rows = list(
            (
                await session.execute(
                    select(ChannelPasteTagRule, TagDefinition)
                    .join(TagDefinition, TagDefinition.id == ChannelPasteTagRule.tag_id)
                    .where(
                        ChannelPasteTagRule.channel_id == channel_id,
                        ChannelPasteTagRule.is_active.is_(True),
                        TagDefinition.is_active.is_(True),
                        (ChannelPasteTagRule.starts_at.is_(None) | (ChannelPasteTagRule.starts_at <= now)),
                        (ChannelPasteTagRule.ends_at.is_(None) | (ChannelPasteTagRule.ends_at > now)),
                    )
                )
            ).all()
        )
        excluded = {tag.slug for rule, tag in rows if rule.mode == ChannelPasteTagRuleMode.EXCLUDE}
        if paste_tags & excluded:
            return False

        included = {tag.slug for rule, tag in rows if rule.mode == ChannelPasteTagRuleMode.INCLUDE}
        if included and not (paste_tags & included):
            return False

        return True

    async def _paste_assignment_slugs(self, session: AsyncSession, paste_id: int) -> tuple[list[str], list[str]]:
        rows = list(
            (
                await session.execute(
                    select(PasteTagAssignment, TagDefinition)
                    .join(TagDefinition, TagDefinition.id == PasteTagAssignment.tag_id)
                    .where(PasteTagAssignment.paste_id == paste_id, TagDefinition.is_active.is_(True))
                    .order_by(TagDefinition.priority.asc(), TagDefinition.slug.asc())
                )
            ).all()
        )
        auto_tags: list[str] = []
        manual_tags: list[str] = []
        for assignment, tag in rows:
            if assignment.source == TagAssignmentSource.AUTO:
                auto_tags.append(tag.slug)
            elif assignment.source == TagAssignmentSource.MANUAL:
                manual_tags.append(tag.slug)
        return list(dict.fromkeys(auto_tags)), list(dict.fromkeys(manual_tags))

    async def _ordered_active_slugs(self, session: AsyncSession, slugs: list[str]) -> list[str]:
        normalized_slugs = [self.normalize_slug(slug) for slug in slugs if self.normalize_slug(slug)]
        if not normalized_slugs:
            return []
        rows = list(
            (
                await session.execute(
                    select(TagDefinition)
                    .where(TagDefinition.slug.in_(normalized_slugs), TagDefinition.is_active.is_(True))
                    .order_by(TagDefinition.priority.asc(), TagDefinition.slug.asc())
                )
            ).scalars().all()
        )
        ordered = [tag.slug for tag in rows]
        for slug in normalized_slugs:
            if slug not in ordered:
                ordered.append(slug)
        return list(dict.fromkeys(ordered))

    async def _tag_map_by_slug(self, session: AsyncSession, slugs: list[str]) -> dict[str, TagDefinition]:
        if not slugs:
            return {}
        rows = list(
            (
                await session.execute(
                    select(TagDefinition).where(TagDefinition.slug.in_(slugs), TagDefinition.is_active.is_(True))
                )
            ).scalars().all()
        )
        return {tag.slug: tag for tag in rows}

    @staticmethod
    def _matches(normalized_text_value: str, keyword: TagKeyword) -> bool:
        marker = keyword.normalized_keyword
        if not marker:
            return False
        if keyword.match_type == TagMatchType.WORD:
            return re.search(rf"(?<!\w){re.escape(marker)}(?!\w)", normalized_text_value, flags=re.IGNORECASE) is not None
        if keyword.match_type == TagMatchType.REGEX:
            try:
                return re.search(marker, normalized_text_value, flags=re.IGNORECASE) is not None
            except re.error:
                return False
        return marker in normalized_text_value
