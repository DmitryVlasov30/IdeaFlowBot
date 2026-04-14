from src.master import MasterBot
from config import settings
from loguru import logger
from src.core_database.database import create_table
import asyncio

logger.add(settings.logging_path, level="DEBUG")


async def main():
    await create_table()
    main_bot = MasterBot(
        api_token_bot=settings.api_token_bot,
    )
    await main_bot.run_bot()


if __name__ == '__main__':
    asyncio.run(main())
