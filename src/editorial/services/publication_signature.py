from __future__ import annotations

from html import escape
import os

from src.editorial.models.channel import Channel


def publication_signature_enabled() -> bool:
    return os.getenv("PUBLICATION_SIGNATURE_ENABLED", "false").strip().lower() in {"1", "true", "yes", "on"}


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


def channel_publication_signature_html(channel: Channel, channel_ref: str | None = None) -> str:
    fallback_ref = channel_ref or channel.short_code
    return publication_signature_html(title=channel.title, channel_ref=fallback_ref)


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
