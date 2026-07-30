from __future__ import annotations

import argparse
import asyncio

from loguru import logger

from src.editorial.config import settings
from src.editorial.db.session import session_factory
from src.editorial.services.auto_slot_planner import AutoSlotPlannerService
from src.editorial.services.channel_profile_service import ChannelProfileService
from src.editorial.services.channel_service import ChannelService
from src.editorial.services.generation.service import GenerationService
from src.editorial.services.import_legacy import LegacyImporter
from src.editorial.services.publisher import PublisherService
from src.editorial.services.scheduler import SchedulerService


async def _run_importer(limit: int | None) -> None:
    async with session_factory() as session:
        result = await LegacyImporter().import_new(session, limit=limit)
        logger.info("Importer finished: {}", result)


async def _run_scheduler() -> None:
    async with session_factory() as session:
        result = await SchedulerService().run(session)
        logger.info("Scheduler finished: {}", result)


async def _run_auto_slot_planner(channel_id: int | None = None) -> None:
    async with session_factory() as session:
        result = await AutoSlotPlannerService().run(session, channel_id=channel_id)
        logger.info("Auto slot planner finished: {}", result)


async def _run_channel_profile_sync(channel_id: int | None = None, skip_subscriber_counts: bool = False) -> None:
    async with session_factory() as session:
        result = await ChannelProfileService().sync_profiles_by_subscribers(
            session,
            channel_id=channel_id,
            update_subscriber_counts=not skip_subscriber_counts,
        )
        logger.info("Channel profile sync finished: {}", result)


async def _upsert_channel_profile(args) -> None:
    raw_settings = _parse_key_value_items(args.settings or [])
    async with session_factory() as session:
        profile = await ChannelProfileService().upsert_profile(
            session,
            slug=args.slug,
            title=args.title,
            min_subscribers=args.min_subscribers,
            max_subscribers=args.max_subscribers,
            priority=args.priority,
            is_active=args.is_active,
            raw_settings=raw_settings,
        )
        logger.info("Channel setting profile saved: {} ({})", profile.slug, profile.id)


async def _apply_channel_profile(channel_id: int, profile_slug: str, auto_enabled: bool) -> None:
    async with session_factory() as session:
        channel = await ChannelProfileService().apply_profile_to_channel(
            session,
            channel_id=channel_id,
            profile_slug=profile_slug,
            auto_enabled=auto_enabled,
        )
        logger.info("Applied profile {} to channel {}", profile_slug, channel.id)


async def _run_publisher() -> None:
    async with session_factory() as session:
        result = await PublisherService().run(session)
        logger.info("Publisher finished: {}", result)


async def _run_generation(channel_id: int, variants: int, sources: int) -> None:
    async with session_factory() as session:
        result = await GenerationService().generate_for_channel(
            session=session,
            channel_id=channel_id,
            variant_count=variants,
            source_count=sources,
        )
        logger.info("Generation finished: {}", result)


async def _seed_slots(channel_id: int, slot_times: list[str], weekdays: list[int] | None) -> None:
    async with session_factory() as session:
        created = await ChannelService().seed_daily_slots(
            session=session,
            channel_id=channel_id,
            slot_times=slot_times,
            weekdays=weekdays,
        )
        logger.info("Created {} slots for channel {}", len(created), channel_id)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="IdeaFlow editorial workers")
    subparsers = parser.add_subparsers(dest="command", required=True)

    importer = subparsers.add_parser("import-legacy")
    importer.add_argument("--limit", type=int, default=settings.legacy_import_batch_size)

    subparsers.add_parser("schedule")
    auto_slots = subparsers.add_parser("auto-slots")
    auto_slots.add_argument("--channel-id", type=int)
    profile_sync = subparsers.add_parser("sync-channel-profiles")
    profile_sync.add_argument("--channel-id", type=int)
    profile_sync.add_argument("--skip-subscriber-counts", action="store_true")
    upsert_profile = subparsers.add_parser("upsert-channel-profile")
    upsert_profile.add_argument("--slug", required=True)
    upsert_profile.add_argument("--title")
    upsert_profile.add_argument("--min-subs", type=int, dest="min_subscribers")
    upsert_profile.add_argument("--max-subs", type=int, dest="max_subscribers")
    upsert_profile.add_argument("--priority", type=int)
    upsert_profile.add_argument("--is-active", type=_parse_bool_arg)
    upsert_profile.add_argument("--set", action="append", dest="settings")
    apply_profile = subparsers.add_parser("apply-channel-profile")
    apply_profile.add_argument("--channel-id", type=int, required=True)
    apply_profile.add_argument("--profile", required=True)
    apply_profile.add_argument("--auto-enabled", action="store_true")
    subparsers.add_parser("publish")

    generate = subparsers.add_parser("generate")
    generate.add_argument("--channel-id", type=int, required=True)
    generate.add_argument("--variants", type=int, default=3)
    generate.add_argument("--sources", type=int, default=5)

    seed_slots = subparsers.add_parser("seed-slots")
    seed_slots.add_argument("--channel-id", type=int, required=True)
    seed_slots.add_argument("--slot", action="append", dest="slots", required=True)
    seed_slots.add_argument("--weekday", action="append", dest="weekdays", type=int)
    return parser


async def main_async() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "import-legacy":
        await _run_importer(args.limit)
    elif args.command == "schedule":
        await _run_scheduler()
    elif args.command == "auto-slots":
        await _run_auto_slot_planner(args.channel_id)
    elif args.command == "sync-channel-profiles":
        await _run_channel_profile_sync(args.channel_id, args.skip_subscriber_counts)
    elif args.command == "upsert-channel-profile":
        await _upsert_channel_profile(args)
    elif args.command == "apply-channel-profile":
        await _apply_channel_profile(args.channel_id, args.profile, args.auto_enabled)
    elif args.command == "publish":
        await _run_publisher()
    elif args.command == "generate":
        await _run_generation(args.channel_id, args.variants, args.sources)
    elif args.command == "seed-slots":
        await _seed_slots(args.channel_id, args.slots, args.weekdays)


def main() -> None:
    asyncio.run(main_async())


def _parse_key_value_items(items: list[str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Expected key=value, got '{item}'")
        key, value = item.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def _parse_bool_arg(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError(f"Expected boolean value, got '{value}'")


if __name__ == "__main__":
    main()

