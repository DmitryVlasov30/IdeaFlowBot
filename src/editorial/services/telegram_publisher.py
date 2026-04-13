from __future__ import annotations

from telebot.async_telebot import AsyncTeleBot, asyncio_helper

from config import settings as legacy_settings


class TelegramPublisherAdapter:
    def __init__(self) -> None:
        proxy = None
        try:
            proxy = legacy_settings.proxies.get("http")
        except Exception:
            proxy = None
        if proxy:
            asyncio_helper.proxy = proxy

    async def send_text(self, bot_token: str, channel_id: int, text: str) -> int:
        bot = AsyncTeleBot(bot_token)
        message = await bot.send_message(chat_id=channel_id, text=text)
        return int(message.message_id)

