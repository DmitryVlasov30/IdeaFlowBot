from pathlib import Path

BASE_DIR = Path(__file__).parent.parent.parent


class Settings:
    @property
    def database_url(self) -> str:
        return f"sqlite:///{BASE_DIR}/data/bot_network_db.db"

    db_echo: bool = True


settings = Settings()
