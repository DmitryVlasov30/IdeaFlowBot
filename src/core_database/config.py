from pathlib import Path
import os

BASE_DIR = Path(__file__).parent.parent.parent


class Settings:
    @property
    def legacy_sqlite_path(self) -> Path:
        raw_path = os.getenv("LEGACY_SQLITE_SOURCE_PATH")
        if raw_path:
            return Path(raw_path)
        return BASE_DIR / "data" / "bot_network_db.db"

    @property
    def database_url(self) -> str:
        explicit_url = os.getenv("LEGACY_DATABASE_URL")
        if explicit_url:
            return explicit_url

        editorial_postgres_dsn = os.getenv("EDITORIAL_POSTGRES_DSN")
        if editorial_postgres_dsn:
            return editorial_postgres_dsn

        return f"sqlite+aiosqlite:///{self.legacy_sqlite_path}"

    db_echo: bool = False


settings = Settings()
