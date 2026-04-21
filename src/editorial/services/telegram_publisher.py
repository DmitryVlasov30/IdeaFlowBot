from __future__ import annotations

import aiohttp

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

    async def get_chat_tag(self, bot_token: str, channel_id: int) -> str | None:
        bot = AsyncTeleBot(bot_token)
        chat = await bot.get_chat(channel_id)
        username = getattr(chat, "username", None)
        if username:
            return f"@{username}"
        return None

    async def send_text_with_entities(
        self,
        bot_token: str,
        channel_id: int,
        text: str,
        entities: list[dict],
    ) -> int:
        payload = {
            "chat_id": channel_id,
            "text": text,
            "entities": entities,
        }
        request_kwargs = {}
        proxy = None
        try:
            proxy = legacy_settings.proxies.get("http")
        except Exception:
            proxy = None
        if proxy:
            request_kwargs["proxy"] = proxy

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, **request_kwargs) as response:
                result = await response.json()
        if not result.get("ok"):
            raise RuntimeError(result.get("description", str(result)))
        return int(result["result"]["message_id"])

    async def copy_message(
        self,
        bot_token: str,
        channel_id: int,
        from_chat_id: int,
        message_id: int,
        caption: str | None = None,
    ) -> int:
        bot = AsyncTeleBot(bot_token)
        message = await bot.copy_message(
            chat_id=channel_id,
            from_chat_id=from_chat_id,
            message_id=message_id,
            caption=caption,
        )
        return int(message.message_id)

    async def copy_messages(
        self,
        bot_token: str,
        channel_id: int,
        from_chat_id: int,
        message_ids: list[int],
    ) -> int:
        if len(message_ids) == 1:
            return await self.copy_message(
                bot_token=bot_token,
                channel_id=channel_id,
                from_chat_id=from_chat_id,
                message_id=message_ids[0],
            )

        payload = {
            "chat_id": channel_id,
            "from_chat_id": from_chat_id,
            "message_ids": message_ids,
        }
        request_kwargs = {}
        proxy = None
        try:
            proxy = legacy_settings.proxies.get("http")
        except Exception:
            proxy = None
        if proxy:
            request_kwargs["proxy"] = proxy

        url = f"https://api.telegram.org/bot{bot_token}/copyMessages"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, **request_kwargs) as response:
                result = await response.json()
        if not result.get("ok"):
            raise RuntimeError(result.get("description", str(result)))

        copied_items = result.get("result") or []
        if not copied_items:
            raise RuntimeError("Telegram returned no copied messages")
        return int(copied_items[0]["message_id"])
