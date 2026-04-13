from __future__ import annotations

from dataclasses import dataclass
import os


def _get_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _get_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    return int(raw)


@dataclass(slots=True)
class EditorialSettings:
    postgres_dsn: str = os.getenv(
        "EDITORIAL_POSTGRES_DSN",
        "postgresql+asyncpg://postgres:postgres@postgres:5432/ideaflow_editorial",
    )
    editorial_api_host: str = os.getenv("EDITORIAL_API_HOST", "0.0.0.0")
    editorial_api_port: int = _get_int("EDITORIAL_API_PORT", 8080)
    redis_dsn: str = os.getenv("EDITORIAL_REDIS_DSN", "redis://redis:6379/0")
    editorial_log_level: str = os.getenv("EDITORIAL_LOG_LEVEL", "INFO")
    review_api_key: str | None = os.getenv("EDITORIAL_REVIEW_API_KEY")
    legacy_import_batch_size: int = _get_int("EDITORIAL_IMPORT_BATCH_SIZE", 200)
    scheduler_window_minutes: int = _get_int("EDITORIAL_SCHEDULER_WINDOW_MINUTES", 15)
    publisher_batch_size: int = _get_int("EDITORIAL_PUBLISHER_BATCH_SIZE", 20)
    generation_default_provider: str = os.getenv("EDITORIAL_GENERATION_PROVIDER", "stub")
    generation_openrouter_base_url: str = os.getenv(
        "OPENROUTER_BASE_URL",
        "https://openrouter.ai/api/v1",
    )
    generation_openrouter_api_key: str | None = os.getenv("OPENROUTER_API_KEY")
    generation_model_name: str = os.getenv(
        "EDITORIAL_GENERATION_MODEL",
        "openrouter/auto",
    )
    generation_enabled: bool = _get_bool("EDITORIAL_GENERATION_ENABLED", True)
    similarity_threshold: float = float(os.getenv("EDITORIAL_SIMILARITY_THRESHOLD", "0.82"))
    minimum_submission_length: int = _get_int("EDITORIAL_MIN_SUBMISSION_LENGTH", 20)
    default_timezone: str = os.getenv("EDITORIAL_DEFAULT_TIMEZONE", "Europe/Moscow")
    scheduler_enabled: bool = _get_bool("EDITORIAL_SCHEDULER_ENABLED", True)
    publisher_enabled: bool = _get_bool("EDITORIAL_PUBLISHER_ENABLED", True)


settings = EditorialSettings()

