from __future__ import annotations

import argparse
import asyncio

from loguru import logger

from src.editorial.config import settings
from src.editorial.db.session import session_factory
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
    elif args.command == "publish":
        await _run_publisher()
    elif args.command == "generate":
        await _run_generation(args.channel_id, args.variants, args.sources)
    elif args.command == "seed-slots":
        await _seed_slots(args.channel_id, args.slots, args.weekdays)


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()

