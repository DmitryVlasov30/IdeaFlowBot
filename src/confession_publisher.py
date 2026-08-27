from __future__ import annotations

import asyncio

from loguru import logger
from telebot.async_telebot import AsyncTeleBot
from telebot.types import Message

from config import settings
from src.editorial.db.session import session_factory
from src.editorial.services.confession_service import ConfessionService


CONFESSION_CONTENT_TYPES = [
    "text",
    "photo",
    "video",
    "animation",
    "sticker",
    "document",
    "audio",
    "voice",
    "video_note",
]


class ConfessionPublisherRuntime:
    """One bot that owns the confession paste storage and publishes to all targets."""

    def __init__(self, *, publisher_id: int, bot_api_token: str, bot_user_id: int) -> None:
        self.publisher_id = int(publisher_id)
        self.bot_api_token = bot_api_token
        self.bot_user_id = int(bot_user_id)
        self.bot = AsyncTeleBot(bot_api_token)
        self.polling_task: asyncio.Task | None = None
        self.service = ConfessionService()
        self._setup_handlers()

    @staticmethod
    def _message_body(message: Message) -> str | None:
        value = (message.text or message.caption or "").strip()
        if value:
            return value
        sticker = getattr(message, "sticker", None)
        if sticker is not None and getattr(sticker, "emoji", None):
            return str(sticker.emoji)
        return None

    @staticmethod
    def _is_service_message(message: Message) -> bool:
        value = message.text if message.text is not None else message.caption
        return bool(value and value.lstrip().startswith("/"))

    def _setup_handlers(self) -> None:
        @self.bot.message_handler(commands=["connect_confessions"])
        async def connect_storage(message: Message) -> None:
            if message.chat.type not in {"group", "supergroup"}:
                await self.bot.reply_to(
                    message,
                    "Эту команду нужно отправить в закрытой группе, которая будет хранилищем паст.",
                )
                return
            parts = (message.text or "").split(maxsplit=1)
            if len(parts) != 2:
                await self.bot.reply_to(message, "Нужен код: /connect_confessions CODE")
                return
            try:
                member = await self.bot.get_chat_member(message.chat.id, self.bot_user_id)
                raw_status = getattr(member, "status", "")
                member_status = str(getattr(raw_status, "value", raw_status))
                if member_status not in {"administrator", "creator"}:
                    raise ValueError(
                        "Сначала добавьте этого бота в администраторы группы, иначе он не увидит все новые пасты."
                    )
                async with session_factory() as session:
                    await self.service.bind_storage_chat(
                        session,
                        publisher_id=self.publisher_id,
                        bind_code=parts[1],
                        storage_chat_id=message.chat.id,
                        storage_chat_title=getattr(message.chat, "title", None),
                    )
            except ValueError as exc:
                await self.bot.reply_to(message, str(exc))
                return
            except Exception as exc:
                logger.exception("Failed to bind confession storage chat {}", message.chat.id)
                await self.bot.reply_to(message, f"Не удалось подключить чат: {exc}")
                return
            await self.bot.reply_to(
                message,
                "Чат подключён. Теперь каждое новое сообщение здесь будет сохранено как паста признавашек.",
            )

        async def store_message(message: Message) -> None:
            if self._is_service_message(message):
                return
            try:
                async with session_factory() as session:
                    _paste, created = await self.service.create_storage_paste(
                        session,
                        publisher_id=self.publisher_id,
                        storage_chat_id=message.chat.id,
                        storage_message_id=message.message_id,
                        content_type=message.content_type or "text",
                        body_text=self._message_body(message),
                        created_by=message.from_user.id if message.from_user else None,
                    )
                if created:
                    logger.info(
                        "Saved confession paste from chat {} message {}",
                        message.chat.id,
                        message.message_id,
                    )
            except ValueError as exc:
                if "не из подключённого" not in str(exc):
                    logger.warning("Confession paste was not saved: {}", exc)
            except Exception:
                logger.exception(
                    "Failed to save confession paste from chat {} message {}",
                    message.chat.id,
                    message.message_id,
                )

        self.bot.register_message_handler(store_message, content_types=CONFESSION_CONTENT_TYPES)
        self.bot.register_channel_post_handler(store_message, content_types=CONFESSION_CONTENT_TYPES)

    async def start(self) -> None:
        bot_info = await self.bot.get_me()
        logger.info("[OK] confession publisher @{} working", bot_info.username)
        self.polling_task = asyncio.create_task(
            self.bot.infinity_polling(
                timeout=10,
                request_timeout=settings.telegram_request_timeout_seconds,
            )
        )

    async def stop(self) -> None:
        if self.polling_task is not None and not self.polling_task.done():
            self.polling_task.cancel()
            try:
                await self.polling_task
            except asyncio.CancelledError:
                pass
        try:
            await self.bot.close_session()
        except Exception:
            pass
