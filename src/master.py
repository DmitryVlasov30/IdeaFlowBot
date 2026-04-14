from __future__ import annotations

from datetime import datetime, timedelta, timezone
import asyncio

import aiohttp
from loguru import logger
from requests import HTTPError
from telebot.async_telebot import AsyncTeleBot, asyncio_helper
from telebot.types import BotCommand, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message, User

from config import settings
from src.core_database.database import CrudBotAdmins, CrudBotsData, CrudDelayedPosts
from src.editorial.services.telegram_actions import TelegramEditorialActions
from src.panel_markups import (
    build_admin_menu,
    build_channels_actions,
    build_content_actions,
    build_main_panel,
    build_submission_actions,
    build_subbot_menu,
)
from src.utils import filter_admin
from src.worker import SubBot


class MasterBot:
    def __init__(self, api_token_bot: str):
        self.delayed_task = None
        self.bot_info = None
        self.flag_register_push_message = False
        self.user_states: dict[int, dict] = {}

        self.bots_database = CrudBotsData()
        self.delayed_database = CrudDelayedPosts()
        self.bot_admins_database = CrudBotAdmins()
        self.editorial_actions = TelegramEditorialActions()

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

    async def _answer_panel(self, chat_id: int, text: str = "Панель управления") -> None:
        await self.main_bot.send_message(
            chat_id=chat_id,
            text=text,
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

    async def _add_subbot_from_values(self, api_token: str, channel_username: str, admin_chat_id: int) -> str:
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

    async def _show_channels_menu(self, chat_id: int) -> None:
        channels = await self.editorial_actions.list_channels()
        if not channels:
            await self.main_bot.send_message(chat_id, "Каналов в editorial-слое пока нет. Сначала импортируйте legacy данные.")
            return
        buttons = [(item.id, item.title or item.short_code) for item in channels]
        lines = [f"{item.id}. {item.title or item.short_code} (tg {item.tg_channel_id})" for item in channels]
        await self.main_bot.send_message(
            chat_id,
            "Каналы:\n" + "\n".join(lines),
            reply_markup=build_channels_actions(buttons),
        )

    def _format_submission(self, submission: SubmissionLike) -> str:
        body = submission.cleaned_text or submission.raw_text or "<без текста>"
        if len(body) > 3000:
            body = body[:3000] + "..."
        tags = ", ".join(submission.detected_tags) if submission.detected_tags else "нет"
        return (
            f"Сообщение #{submission.id}\n"
            f"Канал ID: {submission.channel_id}\n"
            f"Пользователь: @{submission.username or '-'} / {submission.first_name or '-'}\n"
            f"Статус: {submission.status}\n"
            f"Теги: {tags}\n\n"
            f"{body}"
        )

    def _format_content_item(self, item: ContentLike) -> str:
        body = item.body_text
        if len(body) > 3000:
            body = body[:3000] + "..."
        tags = ", ".join(item.tags) if item.tags else "нет"
        return (
            f"Контент #{item.id}\n"
            f"Канал ID: {item.channel_id}\n"
            f"Источник: {item.source_type}\n"
            f"Статус: {item.status}\n"
            f"Теги: {tags}\n\n"
            f"{body}"
        )

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
        await self.main_bot.send_message(
            chat_id,
            self._format_submission(submission),
            reply_markup=build_submission_actions(submission.id, len(submissions) > index + 1),
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
            self._format_content_item(item),
            reply_markup=build_content_actions(item.id, len(items) > index + 1),
        )

    async def _handle_stateful_admin_text(self, message: Message) -> bool:
        state = self.user_states.get(message.chat.id)
        if not state:
            return False

        action = state["action"]
        self._clear_user_state(message.chat.id)

        if action == "await_add_moderator":
            try:
                user_id = int(message.text.strip())
            except ValueError:
                await self.main_bot.send_message(message.chat.id, "Нужен числовой Telegram user id.")
                return True
            await self.bot_admins_database.add_admin({"user_id": user_id})
            settings.moderators.add(user_id)
            self.chats.add(user_id)
            await self.main_bot.send_message(message.chat.id, f"Модератор {user_id} добавлен.")
            return True

        if action == "await_add_subbot":
            parts = message.text.strip().split(maxsplit=1)
            if len(parts) != 2:
                await self.main_bot.send_message(message.chat.id, "Отправьте строку в формате: <api_token> @channel_username")
                return True
            api_token, channel_username = parts
            result_text = await self._add_subbot_from_values(api_token, channel_username, message.chat.id)
            await self.main_bot.send_message(message.chat.id, result_text)
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
    async def callback_adv_send_message(self, call: CallbackQuery, channel_username: str, info_sender) -> None:
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
            result_text = await self._add_subbot_from_values(api_token, channel_username, message.chat.id)
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
            if not self._is_admin(call.message.chat.id):
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
                    case "content":
                        await self._show_first_pending_content(call.message.chat.id)
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
                        if not self._is_general_admin(call.message.chat.id):
                            await self.main_bot.answer_callback_query(call.id, "Только для генерального админа.", show_alert=True)
                            return
                        await self._show_admins_menu(call.message.chat.id)
                    case "subbots":
                        if not self._is_general_admin(call.message.chat.id):
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
                    case "publish":
                        log_item = await self.editorial_actions.publish_submission_now(submission_id, reviewer_id)
                        await self.main_bot.send_message(call.message.chat.id, f"Сообщение {submission_id} отправлено в publish pipeline. Log #{log_item.id}.")
                    case "paste":
                        paste = await self.editorial_actions.paste_submission(submission_id, reviewer_id)
                        await self.main_bot.send_message(call.message.chat.id, f"Создана паста #{paste.id}: {paste.title}")
                    case "hold":
                        await self.editorial_actions.hold_submission(submission_id)
                        await self.main_bot.send_message(call.message.chat.id, f"Сообщение {submission_id} отправлено в hold.")
                    case "reject":
                        await self.editorial_actions.reject_submission(submission_id)
                        await self.main_bot.send_message(call.message.chat.id, f"Сообщение {submission_id} отклонено.")
                    case "next":
                        await self._show_first_pending_submission(call.message.chat.id, current_id=submission_id)
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
                    case "publish":
                        log_item = await self.editorial_actions.publish_content_item_now(content_item_id, reviewer_id)
                        await self.main_bot.send_message(call.message.chat.id, f"Контент {content_item_id} поставлен в публикацию. Log #{log_item.id}.")
                    case "hold":
                        await self.editorial_actions.hold_content_item(content_item_id, reviewer_id)
                        await self.main_bot.send_message(call.message.chat.id, f"Контент {content_item_id} отправлен в hold.")
                    case "reject":
                        await self.editorial_actions.reject_content_item(content_item_id, reviewer_id)
                        await self.main_bot.send_message(call.message.chat.id, f"Контент {content_item_id} отклонен.")
                    case "next":
                        await self._show_first_pending_content(call.message.chat.id, current_id=content_item_id)
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("channel:seed:"):
                channel_id = int(data.split(":")[-1])
                created_count = await self.editorial_actions.seed_default_slots(channel_id)
                await self.main_bot.send_message(
                    call.message.chat.id,
                    f"Для канала {channel_id} создано {created_count} стандартных слотов.",
                )
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


class SubmissionLike:
    id: int
    channel_id: int
    username: str | None
    first_name: str | None
    cleaned_text: str | None
    raw_text: str | None
    detected_tags: list[str]
    status: str


class ContentLike:
    id: int
    channel_id: int
    source_type: str
    status: str
    body_text: str
    tags: list[str]
