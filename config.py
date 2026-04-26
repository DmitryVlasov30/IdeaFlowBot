from __future__ import annotations

from dataclasses import dataclass, field
import os


def _split_int_collection(raw: str) -> list[int]:
    if not raw:
        return []
    return [int(item.strip()) for item in raw.split(",") if item.strip()]


@dataclass
class Settings:
    api_token_bot: str = os.getenv("BOT_API_TOKEN", "")
    general_admin: int = int(os.getenv("GENERAL_ADMIN", "0"))
    moderators: set[int] = field(default_factory=lambda: set(_split_int_collection(os.getenv("MODERATORS", ""))))
    hello_msg: str = os.getenv(
        "HELLO_MSG",
        "Здравствуйте!\n\nНапишите ваш вопрос или историю, и мы отправим ее на модерацию.",
    )
    ban_msg: str = os.getenv(
        "BAN_MSG",
        "К сожалению, модератор ограничил для вас отправку новых сообщений в эту предложку.",
    )
    send_post_msg: str = os.getenv(
        "SEND_POST_MSG",
        "Спасибо за сообщение. Если модератор его одобрит, мы опубликуем его позже.",
    )
    logging_path: str = os.getenv("LOGGING_PATH", "logs/bot.log")
    const_time_sleep: float = float(os.getenv("CONST_TIME_SLEEP", "30"))
    proxy_user: str = os.getenv("PROXY_USER", "")
    proxy_password: str = os.getenv("PROXY_PASSWORD", "")
    proxy_host_port: str = os.getenv("PROXY_HOST_PORT", "")
    shift_time_seconds: int = int(os.getenv("SHIFT_TIME_SECONDS", "3600"))
    sup_bot_limit: int = int(os.getenv("SUP_BOT_LIMIT", "20"))
    media_preview_max_mb: int = int(os.getenv("MEDIA_PREVIEW_MAX_MB", "20"))
    advertiser: list[int] = field(default_factory=lambda: _split_int_collection(os.getenv("ADVERTISER_IDS", "")))
    advertising_manager_username: str = os.getenv("ADVERTISING_MANAGER_USERNAME", "@ivanblk")
    advertising_bot_token: str = os.getenv(
        "ADVERTISING_BOT_TOKEN",
        "8150027786:AAFvsKzexPaJ6YCEWlHkKgoFtv3giN7rubk",
    )
    advertising_text: str = os.getenv(
        "ADVERTISING_TEXT",
        "Спасибо! Ваш запрос передан рекламному менеджеру. С вами свяжутся отдельно.",
    )

    @property
    def proxies(self) -> dict[str, str | None]:
        if self.proxy_host_port and self.proxy_user and self.proxy_password:
            proxy = f"http://{self.proxy_user}:{self.proxy_password}@{self.proxy_host_port}"
        elif self.proxy_host_port:
            proxy = f"http://{self.proxy_host_port}"
        else:
            proxy = None
        return {
            "http": proxy,
            "https": proxy,
        }


settings = Settings()
