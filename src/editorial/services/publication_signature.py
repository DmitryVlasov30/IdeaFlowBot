from __future__ import annotations

from html import escape
import os

import aiohttp
from loguru import logger

from config import settings as legacy_settings
from src.editorial.models.channel import Channel


def publication_signature_enabled() -> bool:
    return os.getenv("PUBLICATION_SIGNATURE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


def normalize_bot_username(username: str | None) -> str | None:
    value = (username or "").strip().lstrip("@").lower()
    return value or None


def publication_signature_skip_bot_username() -> str | None:
    return normalize_bot_username(os.getenv("PUBLICATION_SIGNATURE_SKIP_IF_ADMIN_BOT_USERNAME"))


async def channel_has_signature_skip_bot(*, bot_token: str, channel_id: int) -> bool:
    target_username = publication_signature_skip_bot_username()
    if not target_username:
        return False

    request_kwargs = {}
    try:
        proxy = legacy_settings.proxies.get("http")
    except Exception:
        proxy = None
    if proxy:
        request_kwargs["proxy"] = proxy

    payload = {
        "chat_id": channel_id,
        "return_bots": True,
    }
    url = f"https://api.telegram.org/bot{bot_token}/getChatAdministrators"
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload, **request_kwargs) as response:
            result = await response.json()

    if not result.get("ok"):
        raise RuntimeError(result.get("description", str(result)))

    for admin in result.get("result") or []:
        user = admin.get("user") or {}
        if not user.get("is_bot"):
            continue
        if normalize_bot_username(user.get("username")) == target_username:
            return True
    return False


async def should_add_publication_signature(*, bot_token: str, channel_id: int) -> bool:
    if not publication_signature_enabled():
        return False
    if not publication_signature_skip_bot_username():
        return True
    try:
        return not await channel_has_signature_skip_bot(
            bot_token=bot_token,
            channel_id=channel_id,
        )
    except Exception as ex:
        logger.warning(
            "Failed to check publication signature skip bot for channel {}: {}",
            channel_id,
            ex,
        )
        return True


def public_channel_url(channel_ref: str | None) -> str | None:
    value = (channel_ref or "").strip()
    if not value:
        return None
    if value.startswith("https://t.me/"):
        return value
    if value.startswith("http://t.me/"):
        return "https://t.me/" + value.removeprefix("http://t.me/").strip("/")
    if value.startswith("@"):
        return f"https://t.me/{value[1:]}"
    if "/" not in value and not value.startswith("-"):
        return f"https://t.me/{value}"
    return None


def publication_signature_html(*, title: str | None, channel_ref: str | None) -> str:
    display_title = (title or channel_ref or "").strip().lstrip("@") or "Подслушано"
    url = public_channel_url(channel_ref)
    label = f"<i>{escape(display_title)}</i>"
    if not url:
        return label
    return f'<a href="{escape(url, quote=True)}">{label}</a>'


def channel_publication_signature_html(
    channel: Channel,
    channel_ref: str | None = None,
    title: str | None = None,
) -> str:
    fallback_ref = channel_ref or channel.short_code
    return publication_signature_html(title=title or channel.title, channel_ref=fallback_ref)


def format_publication_html(
    text: str | None,
    *,
    signature_html: str,
    author: str | None = None,
) -> str:
    parts: list[str] = []
    cleaned_text = (text or "").strip()
    if cleaned_text:
        parts.append(escape(cleaned_text))
    if author:
        parts.append(escape(author))
    parts.append(signature_html)
    return "\n\n".join(parts)
