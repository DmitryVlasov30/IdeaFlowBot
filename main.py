from src.master import MasterBot
from config import settings
import asyncio


async def main():
    main_bot = MasterBot(
        api_token_bot=settings.api_token_bot,
    )
    await main_bot.run_bot()


if __name__ == '__main__':
    asyncio.run(main())
