from src.master import MasterBot
from config import settings


def main():
    main_bot = MasterBot(
        api_token_bot=settings.api_token_bot,
    )
    main_bot.run_bot()


if __name__ == '__main__':
    main()