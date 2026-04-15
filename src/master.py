from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp
from loguru import logger
from requests import HTTPError
from telebot.async_telebot import AsyncTeleBot, asyncio_helper
from telebot.types import (
    BotCommand,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    User,
)

from config import settings
from src.core_database.database import CrudBotAdmins, CrudBotsData, CrudDelayedPosts
from src.editorial.models.enums import SubmissionStatus
from src.editorial.services.legacy_source import LegacyCollectorReader
from src.editorial.services.telegram_actions import TelegramEditorialActions
from src.panel_markups import (
    build_admin_menu,
    build_channel_slots_actions,
    build_channels_actions,
    build_content_actions,
    build_empty_paste_actions,
    build_main_panel,
    build_paste_actions,
    build_submission_actions,
    build_submission_history_actions,
    build_subbot_menu,
)
from src.utils import filter_admin
from src.worker import SubBot


WEEKDAY_LABELS = {
    0: "Пн",
    1: "Вт",
    2: "Ср",
    3: "Чт",
    4: "Пт",
    5: "Сб",
    6: "Вс",
}


class MasterBot:
    def __init__(self, api_token_bot: str):
        self.delayed_task = None
        self.bot_info = None
        self.flag_register_push_message = False
        self.user_states: dict[int, dict[str, Any]] = {}

        self.bots_database = CrudBotsData()
        self.delayed_database = CrudDelayedPosts()
        self.bot_admins_database = CrudBotAdmins()
        self.editorial_actions = TelegramEditorialActions()
        self.legacy_reader = LegacyCollectorReader()

        self.commands = [
            BotCommand("panel", "открыть панель управления"),
            BotCommand("bots", "список подключенных сабботов"),
            BotCommand("add", "добавить саббота: /add <token> @channel"),
            BotCommand("delete", "удалить саббота: /delete @bot @channel"),
            BotCommand("push", "подготовить ручную рассылку"),
        ]

        self.api_token_bot = api_token_bot
        asyncio_helper.proxy = settings.proxies["http"]
        asyncio_helper.REQUEST_LIMIT = settings.sup_bot_limit
        self.main_bot = AsyncTeleBot(self.api_token_bot)
        self.bots_work: list[SubBot] = []

        self.chats = settings.moderators
        self.chats.add(settings.general_admin)

        asyncio.create_task(self.__bootstrap())
        self.__setup_handlers()
        logger.info("init bot")

    async def __bootstrap(self) -> None:
        await self.__load_dynamic_admins()
        await self.__setup_bot_info()

    async def __load_dynamic_admins(self) -> None:
        rows = await self.bot_admins_database.get_admins()
        for row in rows:
            settings.moderators.add(row[0])
        self.chats = settings.moderators
        self.chats.add(settings.general_admin)

    async def __setup_bot_info(self) -> None:
        await self.main_bot.set_my_commands(commands=self.commands)
        self.bot_info = await self.main_bot.get_me()

    def _is_general_admin(self, user_id: int) -> bool:
        return user_id == settings.general_admin

    def _is_admin(self, user_id: int) -> bool:
        return self._is_general_admin(user_id) or user_id in settings.moderators

    def _set_user_state(self, user_id: int, action: str, **payload) -> None:
        self.user_states[user_id] = {"action": action, **payload}

    def _clear_user_state(self, user_id: int) -> None:
        self.user_states.pop(user_id, None)

    async def _answer_panel(self, chat_id: int, text: str | None = None) -> None:
        panel_text = text or (
            "Панель управления.\n\n"
            "Поступившие сообщения: новые сырые сообщения пользователей, которые еще не превращены в пост.\n"
            "Все сообщения: журнал submissions из базы, включая уже обработанные записи.\n"
            "Черновики на review: уже собранные content items, которые ждут финального approve.\n"
            "Пасты: библиотека сохраненных текстов, которые можно переиспользовать."
        )
        await self.main_bot.send_message(
            chat_id=chat_id,
            text=panel_text,
            reply_markup=build_main_panel(self._is_general_admin(chat_id)),
        )

    async def _list_subbots_text(self) -> str:
        all_info = await self.bots_database.get_bots_info()
        if not all_info:
            return "Сабботы пока не подключены."

        lines = ["Подключенные сабботы:"]
        async with aiohttp.ClientSession() as session:
            for api_token, bot_username, channel_id, _row_id in all_info:
                channel_username = None
                try:
                    channel_username = await self._fetch_channel_username(session, api_token, channel_id)
                except Exception as ex:
                    logger.error(ex)
                lines.append(
                    f"@{bot_username} -> {('@' + channel_username) if channel_username else channel_id}"
                )
        return "\n".join(lines)

    async def _fetch_channel_username(self, session: aiohttp.ClientSession, api_token: str, channel_id: int) -> str:
        url = f"https://api.telegram.org/bot{api_token}/getchat?chat_id={channel_id}"
        request_kwargs = {}
        if settings.proxies["http"]:
            request_kwargs["proxy"] = settings.proxies["http"]
        async with session.get(url, **request_kwargs) as response:
            result = await response.json()
            if not result["ok"]:
                raise HTTPError(result)
            return result["result"]["username"]

    async def _normalize_channel_username(self, channel_username: str) -> str:
        if "https" in channel_username:
            channel_username = "@" + channel_username.split("/")[-1]
        if "@" not in channel_username:
            channel_username = "@" + channel_username
        return channel_username

    async def _add_subbot_from_values(self, api_token: str, channel_username: str) -> str:
        channel_username = await self._normalize_channel_username(channel_username)
        try:
            channel_id = (await self.main_bot.get_chat(channel_username)).id
        except Exception:
            logger.error("channel not found: {}", channel_username)
            return f"Канал {channel_username} не найден."

        bot = await SubBot.create(
            main_bot_username=self.bot_info.username,
            api_token_bot=api_token,
            channel_username=channel_username,
            hello_msg=settings.hello_msg,
            ban_usr_msg=settings.ban_msg,
            send_post_msg=settings.send_post_msg,
            callback_adv_action=self.callback_adv_send_message,
        )
        is_admin = await bot.check_admin(channel_id)
        if not is_admin:
            return f"Сначала добавьте саббота в администраторы канала {channel_username}."

        for item in await self.bots_database.get_bots_info():
            if item[1] == bot.bot_info.username.replace("@", ""):
                return "Этот саббот уже привязан к каналу."

        await self.bots_database.add_bots_info(
            {
                "channel_id": channel_id,
                "bot_username": bot.bot_info.username,
                "bot_api_token": api_token,
            }
        )
        await bot.run_bot()
        self.bots_work.append(bot)
        return f"Саббот {bot.bot_info.username} подключен к {channel_username}."

    async def _remove_subbot_from_values(self, username_bot: str, channel_id: int) -> str:
        await self.bots_database.delete_bots_info(
            {
                "bot_username": username_bot.replace("@", ""),
                "channel_id": channel_id,
            }
        )
        index_bot = -1
        for idx in range(len(self.bots_work)):
            username = (await self.bots_work[idx].getter_name()).replace("@", "")
            if username == username_bot.replace("@", ""):
                index_bot = idx
                await self.bots_work[idx].stop_bot()
                break

        if index_bot != -1:
            del self.bots_work[index_bot]
        return f"Саббот {username_bot} отвязан."

    async def _get_dynamic_moderators(self) -> list[int]:
        rows = await self.bot_admins_database.get_admins()
        return sorted(row[0] for row in rows)

    async def _show_admins_menu(self, chat_id: int) -> None:
        dynamic_admins = await self._get_dynamic_moderators()
        text = "Динамические модераторы:\n"
        text += "\n".join(map(str, dynamic_admins)) if dynamic_admins else "Пока никого нет."
        await self.main_bot.send_message(chat_id, text, reply_markup=build_admin_menu(dynamic_admins))

    async def _show_subbots_menu(self, chat_id: int) -> None:
        bots = await self.bots_database.get_bots_info()
        buttons = [(item[1].replace("@", ""), item[2]) for item in bots]
        await self.main_bot.send_message(
            chat_id,
            await self._list_subbots_text(),
            reply_markup=build_subbot_menu(buttons),
        )

    def _channel_label_from_runtime(self, tg_channel_id: int) -> str | None:
        for bot in self.bots_work:
            if getattr(bot, "channel_id", None) == tg_channel_id:
                return getattr(bot, "channel_username", None)
        return None

    async def _get_channel_label(self, editorial_channel_id: int) -> str:
        channel = await self.editorial_actions.get_channel(editorial_channel_id)
        if channel is None:
            return f"Канал #{editorial_channel_id}"
        runtime_label = self._channel_label_from_runtime(channel.tg_channel_id)
        if runtime_label:
            return runtime_label
        return channel.title or channel.short_code or f"tg {channel.tg_channel_id}"

    def _weekday_label(self, weekday: int) -> str:
        return WEEKDAY_LABELS.get(weekday, str(weekday))

    def _parse_slot_input(self, raw_value: str) -> tuple[list[int], str]:
        text = raw_value.strip()
        if not text:
            raise ValueError("Пустой ввод")

        parts = text.split()
        if len(parts) == 1:
            days_token = "all"
            time_token = parts[0]
        elif len(parts) == 2:
            days_token, time_token = parts
        else:
            raise ValueError("Используйте формат '<дни> HH:MM' или просто 'HH:MM'")

        try:
            datetime.strptime(time_token, "%H:%M")
        except ValueError as exc:
            raise ValueError("Время должно быть в формате HH:MM") from exc

        if days_token.lower() in {"all", "*"}:
            weekdays = [0, 1, 2, 3, 4, 5, 6]
        else:
            weekdays = []
            for item in days_token.split(","):
                item = item.strip()
                if not item:
                    continue
                weekday = int(item)
                if weekday < 0 or weekday > 6:
                    raise ValueError("Дни недели должны быть числами от 0 до 6")
                weekdays.append(weekday)
            if not weekdays:
                raise ValueError("Не удалось распознать дни недели")

        return sorted(set(weekdays)), time_token

    async def _show_channels_menu(self, chat_id: int) -> None:
        channels = await self.editorial_actions.list_channels()
        if not channels:
            await self.main_bot.send_message(chat_id, "Каналов в editorial-слое пока нет. Сначала импортируйте legacy данные.")
            return

        buttons = []
        lines = ["Каналы:"]
        for item in channels:
            label = self._channel_label_from_runtime(item.tg_channel_id) or item.title or item.short_code
            buttons.append((item.id, label))
            lines.append(f"{item.id}. {label}")

        await self.main_bot.send_message(
            chat_id,
            "\n".join(lines),
            reply_markup=build_channels_actions(buttons),
        )

    async def _show_channel_slots_menu(self, chat_id: int, channel_id: int) -> None:
        channel = await self.editorial_actions.get_channel(channel_id)
        if channel is None:
            await self.main_bot.send_message(chat_id, f"Канал {channel_id} не найден.")
            return

        label = await self._get_channel_label(channel_id)
        slots = await self.editorial_actions.list_channel_slots(channel_id)
        slot_lines = [f"Слоты для {label}:"]
        slot_buttons: list[tuple[int, str]] = []
        if not slots:
            slot_lines.append("Слотов пока нет.")
        else:
            for slot in slots:
                slot_label = f"{self._weekday_label(slot.weekday)} {slot.slot_time.strftime('%H:%M')}"
                slot_lines.append(f"#{slot.id} {slot_label}")
                slot_buttons.append((slot.id, slot_label))

        await self.main_bot.send_message(
            chat_id,
            "\n".join(slot_lines),
            reply_markup=build_channel_slots_actions(channel_id, slot_buttons),
        )

    def _submission_moderation_allowed(self, status: str) -> bool:
        return status in {SubmissionStatus.NEW.value, SubmissionStatus.HOLD.value}

    def _submission_status_label(self, status: str) -> str:
        labels = {
            SubmissionStatus.NEW.value: "новое",
            SubmissionStatus.APPROVED_AS_SOURCE.value: "одобрено как источник",
            SubmissionStatus.PASTE_CANDIDATE.value: "сохранено как паста",
            SubmissionStatus.CONTENT_CREATED.value: "черновик создан",
            SubmissionStatus.REJECTED.value: "отклонено",
            SubmissionStatus.HOLD.value: "hold",
        }
        return labels.get(status, status)

    def _content_status_label(self, status: str) -> str:
        labels = {
            "draft": "черновик",
            "pending_review": "на review",
            "approved": "одобрено",
            "scheduled": "запланировано",
            "published": "опубликовано",
            "rejected": "отклонено",
            "hold": "hold",
        }
        return labels.get(status, status)

    def _submission_type_label(self, submission) -> str:
        if getattr(submission, "media_group_id", None):
            return "медиа-группа"
        labels = {
            "text": "текст",
            "photo": "фото",
            "video": "видео",
            "animation": "gif",
        }
        return labels.get(getattr(submission, "content_type", "text"), getattr(submission, "content_type", "text"))

    def _submission_author_tag(self, submission) -> str:
        return f"@{submission.username}" if submission.username else "@None"

    async def _format_submission(self, submission) -> str:
        body = submission.cleaned_text or submission.raw_text
        if not body:
            if getattr(submission, "media_group_id", None):
                body = "<медиа-группа без подписи>"
            elif getattr(submission, "content_type", "text") != "text":
                body = f"<{self._submission_type_label(submission)} без подписи>"
            else:
                body = "<без текста>"
        if len(body) > 3000:
            body = body[:3000] + "..."
        tags = ", ".join(submission.detected_tags) if submission.detected_tags else "нет"
        channel_label = await self._get_channel_label(submission.channel_id)
        username = f"@{submission.username}" if submission.username else "-"
        first_name = submission.first_name or "-"
        primary_item = await self.editorial_actions.get_submission_primary_content_item(submission.id)
        if primary_item is None:
            status_label = self._submission_status_label(str(submission.status))
            pipeline_line = "Публикация: еще не создан content item"
        else:
            status_label = self._content_status_label(str(primary_item.status))
            pipeline_line = (
                f"Пайплайн: content #{primary_item.id}, "
                f"статус submission = {self._submission_status_label(str(submission.status))}"
            )
        return (
            f"Сообщение #{submission.id}\n"
            f"Канал: {channel_label}\n"
            f"Тип: {self._submission_type_label(submission)}\n"
            f"Пользователь: {username} / {first_name}\n"
            f"Режим автора: {'анон' if submission.is_anonymous else f'не анон ({self._submission_author_tag(submission)})'}\n"
            f"Статус: {status_label}\n"
            f"{pipeline_line}\n"
            f"Теги: {tags}\n\n"
            f"{body}"
        )

    async def _format_content_item(self, item) -> str:
        body = item.body_text
        if len(body) > 3000:
            body = body[:3000] + "..."
        tags = ", ".join(item.tags) if item.tags else "нет"
        channel_label = await self._get_channel_label(item.channel_id)
        return (
            f"Контент #{item.id}\n"
            f"Канал: {channel_label}\n"
            f"Источник: {item.source_type}\n"
            f"Статус: {item.status}\n"
            f"Теги: {tags}\n\n"
            f"{body}"
        )

    async def _format_paste(self, paste) -> str:
        body = paste.body_text
        if len(body) > 3000:
            body = body[:3000] + "..."
        tags = ", ".join(paste.tags) if paste.tags else "нет"
        return (
            f"Паста #{paste.id}\n"
            f"Заголовок: {paste.title}\n"
            f"Статус: {paste.status}\n"
            f"Теги: {tags}\n"
            f"Primary tag: {paste.primary_tag or '-'}\n\n"
            f"{body}"
        )

    async def _send_submission_preview(self, chat_id: int, submission_id: int) -> None:
        preview = await self.editorial_actions.get_submission_preview(submission_id)
        if preview is None or not preview.review_message_ids:
            return

        try:
            if len(preview.review_message_ids) == 1:
                await self.main_bot.copy_message(
                    chat_id=chat_id,
                    from_chat_id=preview.review_chat_id,
                    message_id=preview.review_message_ids[0],
                )
                return

            url = f"https://api.telegram.org/bot{self.api_token_bot}/copyMessages"
            payload = {
                "chat_id": chat_id,
                "from_chat_id": preview.review_chat_id,
                "message_ids": preview.review_message_ids,
            }
            request_kwargs = {}
            if settings.proxies["http"]:
                request_kwargs["proxy"] = settings.proxies["http"]
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, **request_kwargs) as response:
                    result = await response.json()
            if not result.get("ok"):
                raise RuntimeError(result.get("description", str(result)))
        except Exception as ex:
            logger.error("Failed to send submission preview for {}: {}", submission_id, ex)
            await self._send_submission_preview_fallback(chat_id, preview)

    async def _send_submission_preview_fallback(self, chat_id: int, preview) -> None:
        if not preview.preview_file_ids:
            return

        max_preview_bytes = settings.media_preview_max_mb * 1024 * 1024
        if any(size and size > max_preview_bytes for size in preview.preview_file_sizes):
            await self.main_bot.send_message(
                chat_id,
                (
                    "Медиа слишком большое для быстрого предпросмотра в главном боте. "
                    "Его всё ещё можно approve и публиковать, но превью здесь пропущено."
                ),
            )
            return

        binding = await self.legacy_reader.get_bot_binding(preview.channel_tg_id)
        if binding is None:
            logger.error("Failed to build preview fallback: no bot binding for channel {}", preview.channel_tg_id)
            return

        try:
            if preview.media_group_id and len(preview.preview_file_ids) > 1:
                for index, file_id in enumerate(preview.preview_file_ids):
                    item_type = preview.preview_content_types[index] if index < len(preview.preview_content_types) else preview.content_type
                    await self._send_binary_preview_item(
                        chat_id=chat_id,
                        bot_token=binding.bot_api_token,
                        file_id=file_id,
                        content_type=item_type,
                    )
                return

            first_type = preview.preview_content_types[0] if preview.preview_content_types else preview.content_type
            await self._send_binary_preview_item(
                chat_id=chat_id,
                bot_token=binding.bot_api_token,
                file_id=preview.preview_file_ids[0],
                content_type=first_type,
            )
        except Exception as ex:
            logger.error("Failed to send preview fallback for submission: {}", ex)

    async def _send_binary_preview_item(
        self,
        chat_id: int,
        bot_token: str,
        file_id: str,
        content_type: str,
    ) -> None:
        subbot = AsyncTeleBot(bot_token)
        file_info = await subbot.get_file(file_id)
        file_url = f"https://api.telegram.org/file/bot{bot_token}/{file_info.file_path}"

        request_kwargs = {}
        if settings.proxies["http"]:
            request_kwargs["proxy"] = settings.proxies["http"]

        async with aiohttp.ClientSession() as session:
            async with session.get(file_url, **request_kwargs) as response:
                response.raise_for_status()
                payload = await response.read()

        filename = file_info.file_path.split("/")[-1] or "preview.bin"
        form = aiohttp.FormData()
        form.add_field("chat_id", str(chat_id))

        send_method = "sendPhoto"
        field_name = "photo"
        mime_type = "image/jpeg"
        if content_type == "video":
            send_method = "sendVideo"
            field_name = "video"
            mime_type = "video/mp4"
        elif content_type == "animation":
            send_method = "sendAnimation"
            field_name = "animation"
            mime_type = "image/gif"

        form.add_field(
            field_name,
            payload,
            filename=filename,
            content_type=mime_type,
        )

        api_url = f"https://api.telegram.org/bot{self.api_token_bot}/{send_method}"
        async with aiohttp.ClientSession() as session:
            async with session.post(api_url, data=form, **request_kwargs) as response:
                result = await response.json()
        if not result.get("ok"):
            raise RuntimeError(result.get("description", str(result)))

    async def _show_first_pending_submission(self, chat_id: int, current_id: int | None = None) -> None:
        submissions = await self.editorial_actions.list_pending_submissions()
        if not submissions:
            await self.main_bot.send_message(chat_id, "Новых сообщений для review нет.")
            return

        index = 0
        if current_id is not None:
            for idx, item in enumerate(submissions):
                if item.id == current_id:
                    index = min(idx + 1, len(submissions) - 1)
                    break

        submission = submissions[index]
        await self._send_submission_preview(chat_id, submission.id)
        await self.main_bot.send_message(
            chat_id,
            await self._format_submission(submission),
            reply_markup=build_submission_actions(
                submission.id,
                len(submissions) > index + 1,
                submission.is_anonymous,
                allow_moderation=True,
            ),
        )

    async def _show_submission_history(self, chat_id: int, current_id: int | None = None) -> None:
        submissions = await self.editorial_actions.list_recent_submissions(limit=None)
        if not submissions:
            await self.main_bot.send_message(chat_id, "История сообщений пока пуста.")
            return

        index = 0
        if current_id is not None:
            for idx, item in enumerate(submissions):
                if item.id == current_id:
                    index = min(idx + 1, len(submissions) - 1)
                    break

        submission = submissions[index]
        await self._send_submission_preview(chat_id, submission.id)
        await self.main_bot.send_message(
            chat_id,
            await self._format_submission(submission),
            reply_markup=build_submission_history_actions(
                submission.id,
                len(submissions) > index + 1,
                submission.is_anonymous,
                allow_moderation=self._submission_moderation_allowed(str(submission.status)),
            ),
        )

    async def _show_first_pending_content(self, chat_id: int, current_id: int | None = None) -> None:
        items = await self.editorial_actions.list_pending_content_items()
        if not items:
            await self.main_bot.send_message(chat_id, "Контента в pending_review нет.")
            return

        index = 0
        if current_id is not None:
            for idx, item in enumerate(items):
                if item.id == current_id:
                    index = min(idx + 1, len(items) - 1)
                    break

        item = items[index]
        await self.main_bot.send_message(
            chat_id,
            await self._format_content_item(item),
            reply_markup=build_content_actions(item.id, len(items) > index + 1),
        )

    async def _show_first_paste(self, chat_id: int, current_id: int | None = None) -> None:
        pastes = await self.editorial_actions.list_pastes(limit=None)
        if not pastes:
            await self.main_bot.send_message(
                chat_id,
                "В библиотеке паст пока ничего нет.",
                reply_markup=build_empty_paste_actions(),
            )
            return

        index = 0
        if current_id is not None:
            for idx, item in enumerate(pastes):
                if item.id == current_id:
                    index = min(idx + 1, len(pastes) - 1)
                    break

        paste = pastes[index]
        await self.main_bot.send_message(
            chat_id,
            await self._format_paste(paste),
            reply_markup=build_paste_actions(paste.id, len(pastes) > index + 1),
        )

    async def _handle_stateful_admin_text(self, message: Message) -> bool:
        state = self.user_states.get(message.chat.id)
        if not state:
            return False

        action = state["action"]
        self._clear_user_state(message.chat.id)
        text_value = (message.text or message.caption or "").strip()

        if action == "await_add_moderator":
            try:
                user_id = int(text_value)
            except ValueError:
                await self.main_bot.send_message(message.chat.id, "Нужен числовой Telegram user id.")
                return True
            await self.bot_admins_database.add_admin({"user_id": user_id})
            settings.moderators.add(user_id)
            self.chats.add(user_id)
            await self.main_bot.send_message(message.chat.id, f"Модератор {user_id} добавлен.")
            return True

        if action == "await_add_subbot":
            parts = text_value.split(maxsplit=1)
            if len(parts) != 2:
                await self.main_bot.send_message(message.chat.id, "Отправьте строку в формате: <api_token> @channel_username")
                return True
            api_token, channel_username = parts
            result_text = await self._add_subbot_from_values(api_token, channel_username)
            await self.main_bot.send_message(message.chat.id, result_text)
            return True

        if action == "await_add_slot":
            channel_id = state["channel_id"]
            try:
                weekdays, slot_time = self._parse_slot_input(text_value)
            except ValueError as exc:
                await self.main_bot.send_message(
                    message.chat.id,
                    f"{exc}\n\nПримеры:\n10:00\nall 10:00\n0 09:30\n0,2,4 18:00",
                )
                return True
            created_count = await self.editorial_actions.add_slots(channel_id, slot_time, weekdays)
            label = await self._get_channel_label(channel_id)
            await self.main_bot.send_message(
                message.chat.id,
                f"Для {label} добавлено слотов: {created_count}.",
            )
            await self._show_channel_slots_menu(message.chat.id, channel_id)
            return True

        if action == "await_add_paste":
            body_text = text_value
            if not body_text:
                await self.main_bot.send_message(message.chat.id, "Нужен текст пасты.")
                return True
            title = None
            if "::" in body_text:
                raw_title, raw_body = body_text.split("::", maxsplit=1)
                if raw_title.strip() and raw_body.strip():
                    title = raw_title.strip()
                    body_text = raw_body.strip()
            paste = await self.editorial_actions.create_manual_paste(
                body_text=body_text,
                reviewer_id=message.from_user.id if message.from_user else message.chat.id,
                title=title,
            )
            await self.main_bot.send_message(message.chat.id, f"Паста #{paste.id} добавлена: {paste.title}")
            await self._show_first_paste(message.chat.id, current_id=paste.id)
            return True

        if action == "await_reply_submission":
            submission_id = state["submission_id"]
            if not text_value:
                await self.main_bot.send_message(message.chat.id, "Нужен текст сообщения для пользователя.")
                return True
            try:
                await self.editorial_actions.reply_to_submission_author(submission_id, text_value)
            except Exception as ex:
                await self.main_bot.send_message(message.chat.id, f"Не удалось отправить сообщение: {ex}")
                return True
            await self.main_bot.send_message(message.chat.id, f"Ответ пользователю по сообщению {submission_id} отправлен.")
            return True

        return False

    @logger.catch
    async def __send_post(self, delayed_post) -> None:
        tz = timezone(timedelta(hours=3))
        now = datetime.now(tz)
        bots_data = {bot.bot_info.id: bot for bot in self.bots_work}

        public_data = []
        for bot, info_post in delayed_post.items():
            for message_id, info in info_post:
                time_post, sender_id = info
                if now.timestamp() >= time_post:
                    public_data.append((message_id, sender_id, bot))

        for message_id, sender_id, bot in public_data:
            await self.delayed_database.delete_delayed_posts(
                {
                    "bot_id": bot,
                    "message_id": message_id,
                }
            )
            await bots_data[bot].send_delayed_message(message_id, sender_id)

    @logger.catch
    async def __delayed_posts_checker(self) -> None:
        while True:
            delayed_posts = {}
            for bot in self.bots_work:
                delayed_message = await bot.getter_delayed_info()
                info_lst = sorted(delayed_message.items(), key=lambda item: (item[1], item[0]))
                delayed_posts[bot.bot_info.id] = info_lst
            await self.__send_post(delayed_posts)
            await asyncio.sleep(settings.const_time_sleep)

    @logger.catch
    async def callback_adv_send_message(self, call: CallbackQuery, channel_username: str, info_sender: User) -> None:
        text_adv = call.message.text if call.message.text is not None else call.message.caption
        message = (
            f"<b>реклама:</b> {channel_username}\n"
            f"<blockquote expandable>{text_adv if text_adv is not None else 'текста нет'}</blockquote>\n"
            f"отправитель: {info_sender.id if info_sender.username is None else ('@' + info_sender.username)}, "
            f"ник: <b>{info_sender.first_name}</b>\n"
        )
        for adv_admin in settings.advertiser:
            try:
                await self.main_bot.send_message(
                    text=message,
                    chat_id=adv_admin,
                    parse_mode="HTML",
                )
            except Exception as ex:
                logger.error(ex)

    def __setup_handlers(self) -> None:
        @self.main_bot.message_handler(commands=["start", "panel"])
        async def start(message: Message) -> None:
            if not self._is_admin(message.chat.id):
                await self.main_bot.send_message(
                    message.chat.id,
                    "Это служебный бот сети. Панель доступна только администраторам.",
                )
                return
            await self._answer_panel(message.chat.id)

        @self.main_bot.message_handler(commands=["push"])
        @filter_admin
        async def register_push_message(message: Message) -> None:
            await self.main_bot.send_message(settings.general_admin, "Отправьте пост, который нужно разослать.")
            self.flag_register_push_message = True

        @self.main_bot.message_handler(commands=["bots"])
        @filter_admin
        async def get_all_subbot(message: Message) -> None:
            await self.main_bot.send_message(message.chat.id, await self._list_subbots_text())

        @self.main_bot.message_handler(commands=["add"])
        @filter_admin
        async def add_bot(message: Message) -> None:
            parts = message.text.split(maxsplit=2)
            if len(parts) != 3:
                await self.main_bot.send_message(message.chat.id, "Формат команды: /add <token> @channel")
                return
            _command, api_token, channel_username = parts
            result_text = await self._add_subbot_from_values(api_token, channel_username)
            await self.main_bot.send_message(message.chat.id, result_text)

        @self.main_bot.message_handler(commands=["delete"])
        @filter_admin
        async def remove_bot(message: Message) -> None:
            parts = message.text.split(maxsplit=2)
            if len(parts) != 3:
                await self.main_bot.send_message(message.chat.id, "Формат команды: /delete @bot @channel")
                return
            _command, username_bot, channel_username = parts
            channel_username = await self._normalize_channel_username(channel_username)
            try:
                channel_id = (await self.main_bot.get_chat(channel_username)).id
            except Exception:
                await self.main_bot.send_message(message.chat.id, "Канал не найден.")
                return
            result_text = await self._remove_subbot_from_values(username_bot, channel_id)
            await self.main_bot.send_message(message.chat.id, result_text)

        @self.main_bot.message_handler(content_types=["text", "video", "photo"])
        @filter_admin
        async def push_msg(message: Message) -> None:
            if await self._handle_stateful_admin_text(message):
                return

            if self.flag_register_push_message:
                markup = InlineKeyboardMarkup()
                self.flag_register_push_message = False
                message_id_push = message.id
                markup.add(
                    InlineKeyboardButton(text="Опубликовать", callback_data=f"push;{message_id_push}"),
                    InlineKeyboardButton(text="Удалить", callback_data=f"reject_push;{message_id_push}"),
                )
                await self.main_bot.copy_message(
                    from_chat_id=settings.general_admin,
                    chat_id=settings.general_admin,
                    message_id=message_id_push,
                    reply_markup=markup,
                )

        @logger.catch
        @self.main_bot.callback_query_handler(func=lambda call: True)
        async def callback(call: CallbackQuery) -> None:
            if not self._is_admin(call.from_user.id):
                await self.main_bot.answer_callback_query(call.id, "Доступно только администраторам.", show_alert=True)
                return

            data = call.data
            if data.startswith("panel:"):
                action = data.split(":")[1]
                match action:
                    case "main":
                        await self._answer_panel(call.message.chat.id)
                    case "import":
                        result = await self.editorial_actions.import_new()
                        await self.main_bot.send_message(
                            call.message.chat.id,
                            f"Импорт завершен.\nПросмотрено: {result.scanned}\nИмпортировано: {result.imported}\n"
                            f"Пропущено дублей: {result.skipped_duplicates}\nСоздано каналов: {result.channels_created}",
                        )
                    case "submissions":
                        await self.editorial_actions.import_new()
                        await self._show_first_pending_submission(call.message.chat.id)
                    case "all_submissions":
                        await self._show_submission_history(call.message.chat.id)
                    case "content":
                        await self._show_first_pending_content(call.message.chat.id)
                    case "pastes":
                        await self._show_first_paste(call.message.chat.id)
                    case "channels":
                        await self._show_channels_menu(call.message.chat.id)
                    case "scheduler":
                        result = await self.editorial_actions.run_scheduler()
                        await self.main_bot.send_message(
                            call.message.chat.id,
                            f"Scheduler отработал.\nКаналов: {result.channels_checked}\n"
                            f"Слотов: {result.slots_checked}\nЗапланировано: {result.scheduled_items}",
                        )
                    case "publisher":
                        result = await self.editorial_actions.run_publisher()
                        await self.main_bot.send_message(
                            call.message.chat.id,
                            f"Publisher отработал.\nПопыток: {result.attempted}\n"
                            f"Успешно: {result.sent}\nОшибок: {result.failed}",
                        )
                    case "admins":
                        if not self._is_general_admin(call.from_user.id):
                            await self.main_bot.answer_callback_query(call.id, "Только для генерального админа.", show_alert=True)
                            return
                        await self._show_admins_menu(call.message.chat.id)
                    case "subbots":
                        if not self._is_general_admin(call.from_user.id):
                            await self.main_bot.answer_callback_query(call.id, "Только для генерального админа.", show_alert=True)
                            return
                        await self._show_subbots_menu(call.message.chat.id)
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("submission:"):
                _prefix, action, value = data.split(":")
                submission_id = int(value)
                reviewer_id = call.from_user.id
                match action:
                    case "approve":
                        item = await self.editorial_actions.approve_submission(submission_id, reviewer_id)
                        await self.main_bot.send_message(call.message.chat.id, f"Сообщение {submission_id} одобрено. Content item #{item.id}.")
                        await self._show_first_pending_submission(call.message.chat.id, current_id=submission_id)
                    case "publish":
                        log_item = await self.editorial_actions.publish_submission_now(submission_id, reviewer_id)
                        await self.main_bot.send_message(call.message.chat.id, f"Сообщение {submission_id} отправлено в publish pipeline. Log #{log_item.id}.")
                        await self._show_first_pending_submission(call.message.chat.id, current_id=submission_id)
                    case "paste":
                        paste = await self.editorial_actions.paste_submission(submission_id, reviewer_id)
                        await self.main_bot.send_message(call.message.chat.id, f"Создана паста #{paste.id}: {paste.title}")
                        await self._show_first_pending_submission(call.message.chat.id, current_id=submission_id)
                    case "hold":
                        await self.editorial_actions.hold_submission(submission_id)
                        await self.main_bot.send_message(call.message.chat.id, f"Сообщение {submission_id} отправлено в hold.")
                        await self._show_first_pending_submission(call.message.chat.id, current_id=submission_id)
                    case "reject":
                        await self.editorial_actions.reject_submission(submission_id)
                        await self.main_bot.send_message(call.message.chat.id, f"Сообщение {submission_id} отклонено.")
                        await self._show_first_pending_submission(call.message.chat.id, current_id=submission_id)
                    case "toggle_anon":
                        submission = await self.editorial_actions.get_submission(submission_id)
                        if submission is None:
                            await self.main_bot.send_message(call.message.chat.id, f"Сообщение {submission_id} не найдено.")
                        else:
                            updated = await self.editorial_actions.set_submission_anonymous(
                                submission_id=submission_id,
                                is_anonymous=not submission.is_anonymous,
                            )
                            mode_text = "анон" if updated.is_anonymous else f"не анон ({self._submission_author_tag(updated)})"
                            await self.main_bot.send_message(
                                call.message.chat.id,
                                f"Для сообщения {submission_id} установлен режим: {mode_text}.",
                            )
                            await self.main_bot.send_message(
                                call.message.chat.id,
                                await self._format_submission(updated),
                                reply_markup=build_submission_actions(
                                    updated.id,
                                    has_next=False,
                                    is_anonymous=updated.is_anonymous,
                                    allow_moderation=self._submission_moderation_allowed(str(updated.status)),
                                ),
                            )
                    case "advertise":
                        try:
                            await self.editorial_actions.send_submission_advertising_reply(submission_id)
                            await self.main_bot.send_message(
                                call.message.chat.id,
                                f"Пользователю по сообщению {submission_id} отправлена инструкция по рекламе.",
                            )
                        except Exception as ex:
                            await self.main_bot.send_message(
                                call.message.chat.id,
                                f"Не удалось отправить рекламный ответ: {ex}",
                            )
                    case "reply":
                        self._set_user_state(call.message.chat.id, "await_reply_submission", submission_id=submission_id)
                        await self.main_bot.send_message(
                            call.message.chat.id,
                            "Отправьте одним сообщением текст, который нужно переслать автору предложки.",
                        )
                    case "next":
                        await self._show_first_pending_submission(call.message.chat.id, current_id=submission_id)
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("submission_all:next:"):
                submission_id = int(data.split(":")[-1])
                await self._show_submission_history(call.message.chat.id, current_id=submission_id)
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("content:"):
                _prefix, action, value = data.split(":")
                content_item_id = int(value)
                reviewer_id = call.from_user.id
                match action:
                    case "approve":
                        await self.editorial_actions.approve_content_item(content_item_id, reviewer_id)
                        await self.main_bot.send_message(call.message.chat.id, f"Контент {content_item_id} одобрен.")
                        await self._show_first_pending_content(call.message.chat.id, current_id=content_item_id)
                    case "publish":
                        log_item = await self.editorial_actions.publish_content_item_now(content_item_id, reviewer_id)
                        await self.main_bot.send_message(call.message.chat.id, f"Контент {content_item_id} поставлен в публикацию. Log #{log_item.id}.")
                        await self._show_first_pending_content(call.message.chat.id, current_id=content_item_id)
                    case "hold":
                        await self.editorial_actions.hold_content_item(content_item_id, reviewer_id)
                        await self.main_bot.send_message(call.message.chat.id, f"Контент {content_item_id} отправлен в hold.")
                        await self._show_first_pending_content(call.message.chat.id, current_id=content_item_id)
                    case "reject":
                        await self.editorial_actions.reject_content_item(content_item_id, reviewer_id)
                        await self.main_bot.send_message(call.message.chat.id, f"Контент {content_item_id} отклонен.")
                        await self._show_first_pending_content(call.message.chat.id, current_id=content_item_id)
                    case "next":
                        await self._show_first_pending_content(call.message.chat.id, current_id=content_item_id)
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("channel:view:"):
                channel_id = int(data.split(":")[-1])
                await self._show_channel_slots_menu(call.message.chat.id, channel_id)
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("channel:seed:"):
                channel_id = int(data.split(":")[-1])
                created_count = await self.editorial_actions.seed_default_slots(channel_id)
                label = await self._get_channel_label(channel_id)
                await self.main_bot.send_message(
                    call.message.chat.id,
                    f"Для {label} создано стандартных слотов: {created_count}.",
                )
                await self._show_channel_slots_menu(call.message.chat.id, channel_id)
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("channel:add_slot:"):
                channel_id = int(data.split(":")[-1])
                self._set_user_state(call.message.chat.id, "await_add_slot", channel_id=channel_id)
                await self.main_bot.send_message(
                    call.message.chat.id,
                    "Отправьте слот в формате 'HH:MM' для всех дней или '<дни> HH:MM'.\n"
                    "Примеры:\n10:00\nall 10:00\n0 09:30\n0,2,4 18:00\n"
                    "Где 0 = понедельник, 6 = воскресенье.",
                )
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("slot:delete:"):
                slot_id = int(data.split(":")[-1])
                slot = await self.editorial_actions.remove_slot(slot_id)
                if slot is None:
                    await self.main_bot.send_message(call.message.chat.id, f"Слот {slot_id} не найден.")
                else:
                    label = await self._get_channel_label(slot.channel_id)
                    await self.main_bot.send_message(
                        call.message.chat.id,
                        f"Слот {self._weekday_label(slot.weekday)} {slot.slot_time.strftime('%H:%M')} удален из {label}.",
                    )
                    await self._show_channel_slots_menu(call.message.chat.id, slot.channel_id)
                await self.main_bot.answer_callback_query(call.id)
                return

            if data == "paste:add":
                self._set_user_state(call.message.chat.id, "await_add_paste")
                await self.main_bot.send_message(
                    call.message.chat.id,
                    "Отправьте текст пасты одним сообщением.\n"
                    "Если хотите задать заголовок вручную, используйте формат:\n"
                    "Заголовок :: Текст пасты",
                )
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("paste:delete:"):
                paste_id = int(data.split(":")[-1])
                paste = await self.editorial_actions.archive_paste(paste_id)
                await self.main_bot.send_message(call.message.chat.id, f"Паста #{paste.id} переведена в archived.")
                await self._show_first_paste(call.message.chat.id, current_id=paste_id)
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("paste:next:"):
                paste_id = int(data.split(":")[-1])
                await self._show_first_paste(call.message.chat.id, current_id=paste_id)
                await self.main_bot.answer_callback_query(call.id)
                return

            if data == "admin:add":
                if not self._is_general_admin(call.message.chat.id):
                    await self.main_bot.answer_callback_query(call.id, "Только для генерального админа.", show_alert=True)
                    return
                self._set_user_state(call.message.chat.id, "await_add_moderator")
                await self.main_bot.send_message(call.message.chat.id, "Отправьте numeric Telegram user id нового модератора.")
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("admin:remove:"):
                if not self._is_general_admin(call.message.chat.id):
                    await self.main_bot.answer_callback_query(call.id, "Только для генерального админа.", show_alert=True)
                    return
                user_id = int(data.split(":")[-1])
                await self.bot_admins_database.delete_admin(user_id)
                settings.moderators.discard(user_id)
                self.chats.discard(user_id)
                await self.main_bot.send_message(call.message.chat.id, f"Модератор {user_id} удален.")
                await self.main_bot.answer_callback_query(call.id)
                return

            if data == "subbot:add":
                if not self._is_general_admin(call.message.chat.id):
                    await self.main_bot.answer_callback_query(call.id, "Только для генерального админа.", show_alert=True)
                    return
                self._set_user_state(call.message.chat.id, "await_add_subbot")
                await self.main_bot.send_message(call.message.chat.id, "Отправьте строку: <api_token> @channel_username")
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("subbot:remove:"):
                if not self._is_general_admin(call.message.chat.id):
                    await self.main_bot.answer_callback_query(call.id, "Только для генерального админа.", show_alert=True)
                    return
                _, _, username_bot, channel_id = data.split(":")
                result_text = await self._remove_subbot_from_values(username_bot, int(channel_id))
                await self.main_bot.send_message(call.message.chat.id, result_text)
                await self.main_bot.answer_callback_query(call.id)
                return

            match data.split(";")[0]:
                case "push":
                    await self.main_bot.answer_callback_query(call.id, "Ручная push-рассылка пока оставлена как заглушка.")
                case "reject_push":
                    await self.main_bot.delete_message(
                        chat_id=settings.general_admin,
                        message_id=int(data.split(";")[1]),
                    )
                    await self.main_bot.answer_callback_query(call.id)

    @logger.catch
    async def run_bot(self) -> None:
        logger.info("run_bot")
        await self.__load_dynamic_admins()
        self.bot_info = await self.main_bot.get_me()
        bots_lst = await self.bots_database.get_bots_info()

        try:
            logger.info("main bot @{} working", self.bot_info.username)
            async with aiohttp.ClientSession() as session:
                for api_token, bot_username, channel_id, _id_row in bots_lst:
                    channel_username = await self._fetch_channel_username(session, api_token, channel_id)
                    bot = await SubBot.create(
                        main_bot_username=self.bot_info.username,
                        api_token_bot=api_token,
                        channel_username="@" + channel_username,
                        hello_msg=settings.hello_msg,
                        ban_usr_msg=settings.ban_msg,
                        send_post_msg=settings.send_post_msg,
                        callback_adv_action=self.callback_adv_send_message,
                    )
                    await bot.run_bot()
                    self.bots_work.append(bot)
            self.delayed_task = asyncio.create_task(self.__delayed_posts_checker())
            await self.main_bot.polling(none_stop=True)
        except Exception as ex:
            logger.error("bot: @{}, mistake: {}", self.bot_info.username if self.bot_info else "unknown", ex)
