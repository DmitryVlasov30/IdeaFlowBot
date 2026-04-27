from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

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
from src.editorial.services.advertising import send_advertising_flow
from src.editorial.services.db_export import DatabaseExportService
from src.editorial.services.legacy_source import LegacyCollectorReader
from src.editorial.services.sql_export import SqlExportService
from src.editorial.services.telegram_actions import TelegramEditorialActions
from src.panel_markups import (
    build_admin_menu,
    build_channel_actions,
    build_channel_history_import_progress_actions,
    build_channel_history_import_start_actions,
    build_channel_slots_actions,
    build_channels_actions,
    build_content_actions,
    build_empty_paste_actions,
    build_extra_panel,
    build_main_panel,
    build_my_channels_actions,
    build_paste_actions,
    build_submission_actions,
    build_submission_history_actions,
    build_subbot_menu,
    build_subbot_remove_confirm,
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
        self.db_export_service = DatabaseExportService()
        self.sql_export_service = SqlExportService()
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

    async def _show_extra_panel(self, chat_id: int) -> None:
        await self.main_bot.send_message(
            chat_id=chat_id,
            text=(
                "Р”РѕРїРѕР»РЅРёС‚РµР»СЊРЅС‹Рµ С„СѓРЅРєС†РёРё.\n\n"
                "Р’С‹РіСЂСѓР·РєР° Р‘Р” СЃРѕР·РґР°С‘С‚ .db-СЃРЅРёРјРѕРє С‚РµРєСѓС‰РµР№ PostgreSQL-Р±Р°Р·С‹, "
                "С‡С‚РѕР±С‹ С„Р°Р№Р» РїРѕС‚РѕРј Р±С‹Р»Рѕ СѓРґРѕР±РЅРѕ РѕС‚РєСЂС‹С‚СЊ Рё СЃРјРѕС‚СЂРµС‚СЊ."
            ),
            reply_markup=build_extra_panel(),
        )
        return
        await self.main_bot.send_message(
            chat_id=chat_id,
            text=(
                "Дополнительные функции.\n\n"
                "Выгрузка БД создаёт SQLite-снимок со старой collector-базой и editorial-таблицами, "
                "чтобы файл потом было удобно открыть и смотреть."
            ),
            reply_markup=build_extra_panel(),
        )

    async def _send_database_export(self, chat_id: int) -> None:
        status_message = await self.main_bot.send_message(
            chat_id,
            "Р“РѕС‚РѕРІР»СЋ РІС‹РіСЂСѓР·РєСѓ Р±Р°Р·С‹ РґР°РЅРЅС‹С…. Р­С‚Рѕ РјРѕР¶РµС‚ Р·Р°РЅСЏС‚СЊ РЅРµСЃРєРѕР»СЊРєРѕ СЃРµРєСѓРЅРґ.",
        )
        export_path = None
        try:
            export_path = await self.db_export_service.export_snapshot()
            with export_path.open("rb") as snapshot_file:
                await self.main_bot.send_document(
                    chat_id=chat_id,
                    document=snapshot_file,
                    visible_file_name=export_path.name,
                    caption=(
                        "РЎРЅРёРјРѕРє Р±Р°Р·С‹ РіРѕС‚РѕРІ.\n"
                        "Р’РЅСѓС‚СЂРё: РІСЃРµ Р°РєС‚СѓР°Р»СЊРЅС‹Рµ С‚Р°Р±Р»РёС†С‹ РїСЂРѕРµРєС‚Р° РёР· С‚РµРєСѓС‰РµР№ PostgreSQL-Р±Р°Р·С‹."
                    ),
                )
        except Exception as ex:
            logger.exception("Failed to export database snapshot")
            await self.main_bot.send_message(chat_id, f"РќРµ СѓРґР°Р»РѕСЃСЊ РїРѕРґРіРѕС‚РѕРІРёС‚СЊ РІС‹РіСЂСѓР·РєСѓ Р‘Р”: {ex}")
        finally:
            try:
                await self.main_bot.delete_message(chat_id=chat_id, message_id=status_message.message_id)
            except Exception:
                pass
            if export_path and export_path.exists():
                export_path.unlink(missing_ok=True)
        return
        status_message = await self.main_bot.send_message(
            chat_id,
            "Готовлю выгрузку базы данных. Это может занять несколько секунд.",
        )
        export_path = None
        try:
            export_path = await self.db_export_service.export_snapshot()
            with export_path.open("rb") as snapshot_file:
                await self.main_bot.send_document(
                    chat_id=chat_id,
                    document=snapshot_file,
                    visible_file_name=export_path.name,
                    caption=(
                        "SQLite-снимок готов.\n"
                        "Внутри: исходные legacy-таблицы и editorial-таблицы с префиксом editorial__."
                    ),
                )
        except Exception as ex:
            logger.exception("Failed to export database snapshot")
            await self.main_bot.send_message(chat_id, f"Не удалось подготовить выгрузку БД: {ex}")
        finally:
            try:
                await self.main_bot.delete_message(chat_id=chat_id, message_id=status_message.message_id)
            except Exception:
                pass
            if export_path and export_path.exists():
                export_path.unlink(missing_ok=True)

    async def _show_extra_panel(self, chat_id: int) -> None:
        is_general_admin = self._is_general_admin(chat_id)
        await self.main_bot.send_message(
            chat_id=chat_id,
            text=(
                "\u0414\u043e\u043f\u043e\u043b\u043d\u0438\u0442\u0435\u043b\u044c\u043d\u044b\u0435 "
                "\u0444\u0443\u043d\u043a\u0446\u0438\u0438.\n\n"
                "\u0412\u044b\u0433\u0440\u0443\u0437\u043a\u0430 \u0411\u0414 \u0441\u043e\u0437\u0434\u0430\u0451\u0442 "
                ".db-\u0441\u043d\u0438\u043c\u043e\u043a \u0442\u0435\u043a\u0443\u0449\u0435\u0439 "
                "PostgreSQL-\u0431\u0430\u0437\u044b, \u0447\u0442\u043e\u0431\u044b \u0444\u0430\u0439\u043b "
                "\u043f\u043e\u0442\u043e\u043c \u0431\u044b\u043b\u043e \u0443\u0434\u043e\u0431\u043d\u043e "
                "\u043e\u0442\u043a\u0440\u044b\u0442\u044c \u0438 \u0441\u043c\u043e\u0442\u0440\u0435\u0442\u044c.\n\n"
                + (
                    "\u041a\u043d\u043e\u043f\u043a\u0430 SQL -> CSV \u043f\u043e\u0437\u0432\u043e\u043b\u044f\u0435\u0442 "
                    "\u0433\u0435\u043d\u0430\u0434\u043c\u0438\u043d\u0443 \u0432\u044b\u043f\u043e\u043b\u043d\u044f\u0442\u044c "
                    "\u043b\u044e\u0431\u043e\u0439 \u043e\u0434\u0438\u043d\u043e\u0447\u043d\u044b\u0439 SQL-\u0437\u0430\u043f\u0440\u043e\u0441 "
                    "\u0438 \u043f\u043e\u043b\u0443\u0447\u0430\u0442\u044c \u0440\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442 \u0432 CSV."
                    if is_general_admin
                    else
                    "\u041a\u043d\u043e\u043f\u043a\u0430 SQL -> CSV \u0434\u043b\u044f \u043c\u043e\u0434\u0435\u0440\u0430\u0442\u043e\u0440\u0430 "
                    "\u0440\u0430\u0437\u0440\u0435\u0448\u0430\u0435\u0442 \u0442\u043e\u043b\u044c\u043a\u043e SELECT-\u0437\u0430\u043f\u0440\u043e\u0441\u044b."
                )
            ),
            reply_markup=build_extra_panel(),
        )

    async def _send_database_export(self, chat_id: int) -> None:
        status_message = await self.main_bot.send_message(
            chat_id,
            "\u0413\u043e\u0442\u043e\u0432\u043b\u044e \u0432\u044b\u0433\u0440\u0443\u0437\u043a\u0443 "
            "\u0431\u0430\u0437\u044b \u0434\u0430\u043d\u043d\u044b\u0445. \u042d\u0442\u043e "
            "\u043c\u043e\u0436\u0435\u0442 \u0437\u0430\u043d\u044f\u0442\u044c "
            "\u043d\u0435\u0441\u043a\u043e\u043b\u044c\u043a\u043e \u0441\u0435\u043a\u0443\u043d\u0434.",
        )
        export_path = None
        try:
            export_path = await self.db_export_service.export_snapshot()
            with export_path.open("rb") as snapshot_file:
                await self.main_bot.send_document(
                    chat_id=chat_id,
                    document=snapshot_file,
                    visible_file_name=export_path.name,
                    caption=(
                        "\u0421\u043d\u0438\u043c\u043e\u043a \u0431\u0430\u0437\u044b "
                        "\u0433\u043e\u0442\u043e\u0432.\n"
                        "\u0412\u043d\u0443\u0442\u0440\u0438: \u0432\u0441\u0435 "
                        "\u0430\u043a\u0442\u0443\u0430\u043b\u044c\u043d\u044b\u0435 "
                        "\u0442\u0430\u0431\u043b\u0438\u0446\u044b \u043f\u0440\u043e\u0435\u043a\u0442\u0430 "
                        "\u0438\u0437 \u0442\u0435\u043a\u0443\u0449\u0435\u0439 PostgreSQL-\u0431\u0430\u0437\u044b."
                    ),
                )
        except Exception as ex:
            logger.exception("Failed to export database snapshot")
            await self.main_bot.send_message(
                chat_id,
                f"\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c "
                f"\u043f\u043e\u0434\u0433\u043e\u0442\u043e\u0432\u0438\u0442\u044c "
                f"\u0432\u044b\u0433\u0440\u0443\u0437\u043a\u0443 \u0411\u0414: {ex}",
            )
        finally:
            try:
                await self.main_bot.delete_message(chat_id=chat_id, message_id=status_message.message_id)
            except Exception:
                pass
            if export_path and export_path.exists():
                export_path.unlink(missing_ok=True)

    async def _send_sql_export_prompt(self, chat_id: int, allow_mutating: bool) -> None:
        self._set_user_state(chat_id, "await_sql_export", allow_mutating=allow_mutating)
        if allow_mutating:
            prompt_text = (
                "\u041e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u043e\u0434\u0438\u043d SQL-\u0437\u0430\u043f\u0440\u043e\u0441.\n"
                "\u0414\u043b\u044f \u0433\u0435\u043d\u0430\u0434\u043c\u0438\u043d\u0430 \u0440\u0430\u0437\u0440\u0435\u0448\u0451\u043d "
                "\u043b\u044e\u0431\u043e\u0439 \u043e\u0434\u0438\u043d\u043e\u0447\u043d\u044b\u0439 SQL.\n"
                "\u0420\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442 \u043f\u0440\u0438\u0434\u0451\u0442 CSV-\u0444\u0430\u0439\u043b\u043e\u043c."
            )
        else:
            prompt_text = (
                "\u041e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u043e\u0434\u0438\u043d SELECT-\u0437\u0430\u043f\u0440\u043e\u0441.\n"
                "\u0414\u043b\u044f \u043c\u043e\u0434\u0435\u0440\u0430\u0442\u043e\u0440\u0430 \u0440\u0430\u0437\u0440\u0435\u0448\u0451\u043d "
                "\u0442\u043e\u043b\u044c\u043a\u043e SELECT.\n"
                "\u0420\u0435\u0437\u0443\u043b\u044c\u0442\u0430\u0442 \u043f\u0440\u0438\u0434\u0451\u0442 CSV-\u0444\u0430\u0439\u043b\u043e\u043c."
            )
        await self.main_bot.send_message(chat_id, prompt_text)

    async def _send_sql_export_result(self, chat_id: int, query: str, allow_mutating: bool) -> None:
        status_message = await self.main_bot.send_message(
            chat_id,
            "\u0412\u044b\u043f\u043e\u043b\u043d\u044f\u044e SQL-\u0437\u0430\u043f\u0440\u043e\u0441 "
            "\u0438 \u0433\u043e\u0442\u043e\u0432\u043b\u044e CSV. \u042d\u0442\u043e \u043c\u043e\u0436\u0435\u0442 "
            "\u0437\u0430\u043d\u044f\u0442\u044c \u043d\u0435\u0441\u043a\u043e\u043b\u044c\u043a\u043e "
            "\u0441\u0435\u043a\u0443\u043d\u0434.",
        )
        export_path = None
        try:
            result = await self.sql_export_service.export_query(query=query, allow_mutating=allow_mutating)
            export_path = result.path
            with export_path.open("rb") as export_file:
                await self.main_bot.send_document(
                    chat_id=chat_id,
                    document=export_file,
                    visible_file_name=export_path.name,
                    caption=(
                        f"SQL -> CSV готов.\n"
                        f"Тип запроса: {result.statement_type}\n"
                        f"Строк в файле: {result.rows_written}"
                    ),
                )
        except Exception as ex:
            logger.exception("Failed to export SQL query result")
            await self.main_bot.send_message(
                chat_id,
                f"\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c "
                f"\u0432\u044b\u043f\u043e\u043b\u043d\u0438\u0442\u044c SQL: {ex}",
            )
        finally:
            try:
                await self.main_bot.delete_message(chat_id=chat_id, message_id=status_message.message_id)
            except Exception:
                pass
            if export_path and export_path.exists():
                export_path.unlink(missing_ok=True)

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

    async def _add_subbot_from_values(self, api_token: str, channel_username: str) -> tuple[str, int | None]:
        channel_username = await self._normalize_channel_username(channel_username)
        try:
            channel_chat = await self.main_bot.get_chat(channel_username)
            channel_id = channel_chat.id
        except Exception:
            logger.error("channel not found: {}", channel_username)
            return f"Канал {channel_username} не найден.", None

        bot = await SubBot.create(
            main_bot_username=self.bot_info.username,
            api_token_bot=api_token,
            channel_username=channel_username,
            hello_msg=settings.hello_msg,
            ban_usr_msg=settings.ban_msg,
            send_post_msg=settings.send_post_msg,
            callback_adv_action=self.callback_adv_send_message_v2,
            callback_new_submission=self.callback_new_submission_notification,
        )
        if bot.bot_info is None:
            return "\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043f\u043e\u043b\u0443\u0447\u0438\u0442\u044c \u0438\u043d\u0444\u043e \u043e \u0441\u0430\u0431\u0431\u043e\u0442\u0435. \u041f\u0440\u043e\u0432\u0435\u0440\u044c\u0442\u0435 token.", None

        channel_id = int(getattr(bot, "channel_id", channel_id))
        bot_username = bot.bot_info.username.replace("@", "")
        main_bot_username = (self.bot_info.username if self.bot_info else "").replace("@", "")
        if bot_username == main_bot_username:
            return (
                f"Token принадлежит general-боту @{bot_username}. "
                "Его нельзя привязывать как саббота: возьмите token именно отдельного бота-предложки из BotFather.",
                None,
            )

        for item in await self.bots_database.get_bots_info():
            existing_username = str(item[1]).replace("@", "")
            existing_channel_id = int(item[2])
            if existing_username != bot_username:
                continue
            if existing_channel_id != channel_id:
                return "\u042d\u0442\u043e\u0442 \u0441\u0430\u0431\u0431\u043e\u0442 \u0443\u0436\u0435 \u043f\u0440\u0438\u0432\u044f\u0437\u0430\u043d \u043a \u0434\u0440\u0443\u0433\u043e\u043c\u0443 \u043a\u0430\u043d\u0430\u043b\u0443.", None
            editorial_channel = await self.editorial_actions.ensure_channel_for_tg_channel_id(channel_id)
            if not self._is_subbot_running(bot_username, channel_id):
                await bot.run_bot()
                self.bots_work.append(bot)
            return "\u041f\u0440\u0438\u0432\u044f\u0437\u043a\u0430 \u0441\u0430\u0431\u0431\u043e\u0442\u0430 \u0443\u0436\u0435 \u0431\u044b\u043b\u0430 \u0432 \u0431\u0430\u0437\u0435; \u043a\u0430\u043d\u0430\u043b \u0440\u0435\u0430\u043a\u0442\u0438\u0432\u0438\u0440\u043e\u0432\u0430\u043d.", editorial_channel.id
        is_admin = await bot.check_admin(channel_id)
        if not is_admin:
            return (
                f"Token принадлежит @{bot_username}, но Telegram не видит этого бота админом канала {channel_username}. "
                f"Добавьте именно @{bot_username} в администраторы канала и попробуйте ещё раз.",
                None,
            )

        await self.bots_database.add_bots_info(
            {
                "channel_id": channel_id,
                "bot_username": bot_username,
                "bot_api_token": api_token,
            }
        )
        await bot.run_bot()
        self.bots_work.append(bot)
        editorial_channel = await self.editorial_actions.ensure_channel_for_tg_channel_id(channel_id)
        return f"Саббот {bot.bot_info.username} подключен к {channel_username}.", editorial_channel.id

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
        await self.editorial_actions.deactivate_channel_by_tg_channel_id(channel_id)
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

    def _is_subbot_running(self, username_bot: str, channel_id: int | None = None) -> bool:
        target_username = username_bot.replace("@", "")
        for bot in self.bots_work:
            bot_info = getattr(bot, "bot_info", None)
            running_username = (getattr(bot_info, "username", "") or "").replace("@", "")
            if running_username != target_username:
                continue
            if channel_id is None or getattr(bot, "channel_id", None) == channel_id:
                return True
        return False

    def _channel_label_from_runtime(self, tg_channel_id: int) -> str | None:
        for bot in self.bots_work:
            if getattr(bot, "channel_id", None) == tg_channel_id:
                return getattr(bot, "channel_username", None)
        return None

    def _channel_title_from_runtime(self, tg_channel_id: int) -> str | None:
        for bot in self.bots_work:
            if getattr(bot, "channel_id", None) == tg_channel_id:
                return getattr(bot, "channel_title", None)
        return None

    @staticmethod
    def _compose_channel_display_label(title: str | None, tag: str | None, short_code: str | None) -> str:
        clean_title = (title or "").strip()
        clean_tag = (tag or "").strip()
        clean_short_code = (short_code or "").strip()

        if clean_title and clean_tag:
            return f"{clean_title} {clean_tag}"
        if clean_title:
            return clean_title
        if clean_tag:
            return clean_tag
        if clean_short_code:
            return clean_short_code
        return "Канал"

    async def _get_channel_label(self, editorial_channel_id: int) -> str:
        channel = await self.editorial_actions.get_channel(editorial_channel_id)
        if channel is None:
            return f"Канал #{editorial_channel_id}"
        runtime_title = self._channel_title_from_runtime(channel.tg_channel_id)
        runtime_label = self._channel_label_from_runtime(channel.tg_channel_id)
        return self._compose_channel_display_label(runtime_title or channel.title, runtime_label, channel.short_code)

    def _weekday_label(self, weekday: int) -> str:
        return WEEKDAY_LABELS.get(weekday, str(weekday))

    @staticmethod
    def _is_time_token(value: str) -> bool:
        try:
            datetime.strptime(value, "%H:%M")
        except ValueError:
            return False
        return True

    def _parse_slot_input(self, raw_value: str) -> tuple[list[int], list[str]]:
        text = raw_value.strip()
        if not text:
            raise ValueError("Пустой ввод")

        parts = text.split()
        if self._is_time_token(parts[0]):
            days_token = "all"
            time_tokens = parts
        else:
            days_token = parts[0]
            time_tokens = parts[1:]

        if not time_tokens:
            raise ValueError("После дней недели укажите хотя бы одно время в формате HH:MM")

        slot_times: list[str] = []
        for time_token in time_tokens:
            try:
                datetime.strptime(time_token, "%H:%M")
            except ValueError as exc:
                raise ValueError(f"Время '{time_token}' должно быть в формате HH:MM") from exc
            slot_times.append(time_token)

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

        return sorted(set(weekdays)), slot_times

    def _parse_channel_setting_input(self, raw_value: str) -> tuple[str, str]:
        text = raw_value.strip()
        if not text:
            raise ValueError("Пустой ввод")

        parts = text.split(maxsplit=1)
        if len(parts) != 2:
            raise ValueError("Нужен формат: <параметр> <значение>")
        return parts[0].strip(), parts[1].strip()

    def _parse_ad_blackout_input(self, raw_value: str) -> tuple[int, str, str]:
        text = raw_value.strip()
        if not text:
            raise ValueError("Пустой ввод.")

        parts = text.split()
        if len(parts) != 3:
            raise ValueError("Нужен формат: <день месяца> <с HH:MM> <до HH:MM>.")

        try:
            day_of_month = int(parts[0])
        except ValueError as exc:
            raise ValueError("День месяца должен быть числом.") from exc
        if day_of_month < 1 or day_of_month > 31:
            raise ValueError("День месяца должен быть от 1 до 31.")

        for time_value in parts[1:]:
            try:
                datetime.strptime(time_value, "%H:%M")
            except ValueError as exc:
                raise ValueError(f"Время '{time_value}' должно быть в формате HH:MM.") from exc

        return day_of_month, parts[1], parts[2]

    async def _send_channel_settings_prompt(self, chat_id: int, channel_id: int) -> None:
        await self.editorial_actions.sync_channel_activity_from_bindings()
        channel = await self.editorial_actions.get_channel(channel_id)
        if channel is None:
            await self.main_bot.send_message(chat_id, f"РљР°РЅР°Р» {channel_id} РЅРµ РЅР°Р№РґРµРЅ.")
            return
        if not channel.is_active:
            await self.main_bot.send_message(chat_id, "\u041a\u0430\u043d\u0430\u043b \u043e\u0442\u0432\u044f\u0437\u0430\u043d \u0438 \u0441\u043a\u0440\u044b\u0442 \u0438\u0437 \u0430\u043a\u0442\u0438\u0432\u043d\u043e\u0439 \u043f\u0430\u043d\u0435\u043b\u0438.")
            return

        label = await self._get_channel_label(channel_id)
        settings_snapshot = await self.editorial_actions.get_channel_settings_snapshot(channel_id)
        lines = [
            f"Изменение параметров для {label}.",
            "",
            "Отправьте одну строку в формате:",
            "same_tag_cooldown_hours 24",
            "",
            "Для булевых полей используйте только true/false, yes/no, on/off или да/нет.",
            "",
            "Текущие доступные параметры:",
        ]
        lines.extend(
            f"{field_name} = {self._format_channel_setting_value(value)}"
            for field_name, value in settings_snapshot
        )
        await self.main_bot.send_message(chat_id, "\n".join(lines))

    async def _send_channel_history_import_offer(self, chat_id: int, channel_id: int) -> None:
        label = await self._get_channel_label(channel_id)
        await self.main_bot.send_message(
            chat_id,
            (
                f"Для {label} можно импортировать недавнюю историю канала.\n\n"
                "Если в канале уже публиковались тексты, которые совпадают с пастами из базы, "
                "бот запомнит это и не будет быстро переиспользовать такие пасты заново."
            ),
            reply_markup=build_channel_history_import_start_actions(channel_id),
        )

    @staticmethod
    def _extract_forwarded_channel_payload(message: Message) -> tuple[int | None, int | None, datetime | None]:
        source_chat_id = None
        source_message_id = getattr(message, "forward_from_message_id", None)
        original_published_at = None

        forward_from_chat = getattr(message, "forward_from_chat", None)
        if forward_from_chat is not None:
            source_chat_id = getattr(forward_from_chat, "id", None)

        forward_date = getattr(message, "forward_date", None)
        if isinstance(forward_date, datetime):
            original_published_at = forward_date if forward_date.tzinfo else forward_date.replace(tzinfo=timezone.utc)
        elif isinstance(forward_date, int):
            original_published_at = datetime.fromtimestamp(forward_date, tz=timezone.utc)

        forward_origin = getattr(message, "forward_origin", None)
        if forward_origin is not None:
            origin_chat = getattr(forward_origin, "chat", None)
            if origin_chat is not None and source_chat_id is None:
                source_chat_id = getattr(origin_chat, "id", None)
            origin_message_id = getattr(forward_origin, "message_id", None)
            if source_message_id is None and origin_message_id is not None:
                source_message_id = origin_message_id
            origin_date = getattr(forward_origin, "date", None)
            if original_published_at is None:
                if isinstance(origin_date, datetime):
                    original_published_at = origin_date if origin_date.tzinfo else origin_date.replace(tzinfo=timezone.utc)
                elif isinstance(origin_date, int):
                    original_published_at = datetime.fromtimestamp(origin_date, tz=timezone.utc)

        return source_chat_id, source_message_id, original_published_at

    async def _show_channels_menu(self, chat_id: int) -> None:
        channels = await self.editorial_actions.list_channels()
        if not channels:
            await self.main_bot.send_message(chat_id, "Каналов в editorial-слое пока нет. Сначала импортируйте legacy данные.")
            return

        buttons = []
        lines = ["Каналы:"]
        for item in channels:
            label = self._compose_channel_display_label(
                self._channel_title_from_runtime(item.tg_channel_id) or item.title,
                self._channel_label_from_runtime(item.tg_channel_id),
                item.short_code,
            )
            buttons.append((item.id, label))
            lines.append(f"{item.id}. {label}")

        await self.main_bot.send_message(
            chat_id,
            "\n".join(lines),
            reply_markup=build_channels_actions(buttons),
        )

    async def _show_my_channels_menu(self, chat_id: int, user_id: int) -> None:
        channels = await self.editorial_actions.list_user_moderation_feed_channels(user_id)
        if not channels:
            await self.main_bot.send_message(
                chat_id,
                (
                    "\u0423 \u0432\u0430\u0441 \u043f\u043e\u043a\u0430 \u043d\u0435 \u0432\u044b\u0431\u0440\u0430\u043d\u044b \u043a\u0430\u043d\u0430\u043b\u044b.\n\n"
                    "\u041e\u0442\u043a\u0440\u043e\u0439\u0442\u0435 '\u041a\u0430\u043d\u0430\u043b\u044b \u0438 \u0441\u043b\u043e\u0442\u044b', "
                    "\u0432\u044b\u0431\u0435\u0440\u0438\u0442\u0435 \u043a\u0430\u043d\u0430\u043b \u0438 \u0432\u043a\u043b\u044e\u0447\u0438\u0442\u0435 "
                    "'\u043f\u043e\u043b\u0443\u0447\u0435\u043d\u0438\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0439'."
                ),
                reply_markup=build_my_channels_actions([]),
            )
            return

        buttons = []
        lines = [
            "\u041c\u043e\u0438 \u043a\u0430\u043d\u0430\u043b\u044b.",
            "\u042d\u0442\u043e \u043a\u0430\u043d\u0430\u043b\u044b, \u0434\u043b\u044f \u043a\u043e\u0442\u043e\u0440\u044b\u0445 \u0443 \u0432\u0430\u0441 \u0432\u043a\u043b\u044e\u0447\u0435\u043d\u043e \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u0438\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0439.",
            "",
            "\u0412\u044b\u0431\u0435\u0440\u0438\u0442\u0435, \u043a\u0443\u0434\u0430 \u043e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c \u0440\u0443\u0447\u043d\u043e\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435:",
        ]
        for channel in channels:
            label = self._compose_channel_display_label(
                self._channel_title_from_runtime(channel.tg_channel_id) or channel.title,
                self._channel_label_from_runtime(channel.tg_channel_id),
                channel.short_code,
            )
            buttons.append((channel.id, label))
            lines.append(f"{len(buttons)}. {label}")

        await self.main_bot.send_message(
            chat_id,
            "\n".join(lines),
            reply_markup=build_my_channels_actions(buttons),
        )

    @staticmethod
    def _format_manual_channel_message_result(result) -> str:
        lines = [
            "\u0420\u0443\u0447\u043d\u043e\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435 \u043e\u0431\u0440\u0430\u0431\u043e\u0442\u0430\u043d\u043e.",
            f"\u041a\u0430\u043d\u0430\u043b\u043e\u0432 \u0432\u044b\u0431\u0440\u0430\u043d\u043e: {result.requested}",
            f"\u041e\u043f\u0443\u0431\u043b\u0438\u043a\u043e\u0432\u0430\u043d\u043e: {result.sent}",
        ]
        if result.blocked:
            lines.append(f"\u0417\u0430\u0431\u043b\u043e\u043a\u0438\u0440\u043e\u0432\u0430\u043d\u043e \u0440\u0435\u043a\u043b\u0430\u043c\u043d\u044b\u043c \u043e\u043a\u043d\u043e\u043c: {result.blocked}")
        if result.failed:
            lines.append(f"\u041e\u0448\u0438\u0431\u043e\u043a: {result.failed}")
        if result.content_item_ids:
            ids = ", ".join(map(str, result.content_item_ids))
            lines.append(f"Content items: {ids}")
        if result.publication_log_ids:
            ids = ", ".join(map(str, result.publication_log_ids))
            lines.append(f"Publication logs: {ids}")
        if result.errors:
            lines.append("")
            lines.append("\u0414\u0435\u0442\u0430\u043b\u0438:")
            lines.extend(result.errors[:5])
        return "\n".join(lines)

    @staticmethod
    def _format_channel_setting_value(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        return str(value)

    async def _format_ad_blackout(self, channel_id: int, blackout) -> str:
        channel = await self.editorial_actions.get_channel(channel_id)
        timezone_name = channel.timezone if channel is not None else "Europe/Moscow"
        tz = ZoneInfo(timezone_name)
        starts_at = blackout.starts_at.astimezone(tz)
        ends_at = blackout.ends_at.astimezone(tz)
        return f"{starts_at.strftime('%d.%m %H:%M')} - {ends_at.strftime('%d.%m %H:%M')}"

    async def _show_channel_menu(self, chat_id: int, channel_id: int, user_id: int | None = None) -> None:
        await self.editorial_actions.sync_channel_activity_from_bindings()
        channel = await self.editorial_actions.get_channel(channel_id)
        if channel is None:
            await self.main_bot.send_message(chat_id, f"Канал {channel_id} не найден.")
            return

        if not channel.is_active:
            await self.main_bot.send_message(chat_id, "\u041a\u0430\u043d\u0430\u043b \u043e\u0442\u0432\u044f\u0437\u0430\u043d \u0438 \u0441\u043a\u0440\u044b\u0442 \u0438\u0437 \u0430\u043a\u0442\u0438\u0432\u043d\u043e\u0439 \u043f\u0430\u043d\u0435\u043b\u0438.")
            return

        effective_user_id = user_id if user_id is not None else chat_id
        label = await self._get_channel_label(channel_id)
        notifications_enabled = await self.editorial_actions.is_channel_notifications_enabled(channel_id, effective_user_id)
        moderation_feed_enabled = await self.editorial_actions.is_channel_moderation_feed_enabled(channel_id, effective_user_id)
        settings_snapshot = await self.editorial_actions.get_channel_settings_snapshot(channel_id)
        ad_blackouts = await self.editorial_actions.list_channel_ad_blackouts(channel_id)
        summary_fields = {
            "min_gap_minutes",
            "slot_jitter_minutes",
            "max_posts_per_day",
            "max_paste_per_day",
            "same_tag_cooldown_hours",
            "same_template_cooldown_hours",
            "same_paste_cooldown_days",
            "allow_generated",
            "allow_pastes",
        }
        summary_lines = [
            f"{field_name} = {self._format_channel_setting_value(value)}"
            for field_name, value in settings_snapshot
            if field_name in summary_fields
        ]
        text_lines = [
            f"Канал: {label}",
            f"tg_channel_id: {channel.tg_channel_id}",
            f"timezone: {channel.timezone}",
            "",
            "Ключевые параметры:",
            *summary_lines,
        ]
        if ad_blackouts:
            text_lines.extend(["", "Рекламные окна:"])
            for blackout in ad_blackouts:
                text_lines.append(await self._format_ad_blackout(channel_id, blackout))
        await self.main_bot.send_message(
            chat_id,
            "\n".join(text_lines),
            reply_markup=build_channel_actions(channel_id, notifications_enabled, moderation_feed_enabled),
        )

    @staticmethod
    def _build_submission_open_markup(submission_id: int) -> InlineKeyboardMarkup:
        markup = InlineKeyboardMarkup()
        markup.add(InlineKeyboardButton("Открыть в панели", callback_data=f"submission:view:{submission_id}"))
        return markup

    async def callback_new_submission_notification(
        self,
        *,
        channel_tg_id: int,
        review_chat_id: int,
        review_message_id: int,
    ) -> None:
        submission = await self.editorial_actions.ensure_submission_for_review_message(
            channel_tg_id=channel_tg_id,
            review_chat_id=review_chat_id,
            review_message_id=review_message_id,
        )
        if submission is None:
            return

        recipient_ids = await self.editorial_actions.list_channel_notification_user_ids(submission.channel_id)
        if not recipient_ids:
            return

        channel_label = await self._get_channel_label(submission.channel_id)
        excerpt = self._submission_notification_excerpt(submission)
        notification_text = (
            f"Новое сообщение в канале {channel_label}\n"
            f"Тип: {self._submission_type_label(submission)}\n\n"
            f"{excerpt}"
        )
        reply_markup = self._build_submission_open_markup(submission.id)

        for recipient_id in recipient_ids:
            if not self._is_admin(recipient_id):
                continue
            try:
                await self.main_bot.send_message(
                    recipient_id,
                    notification_text,
                    reply_markup=reply_markup,
                )
            except Exception as ex:
                logger.error("Failed to deliver submission notification to {}: {}", recipient_id, ex)

    async def _show_channel_slots_menu(self, chat_id: int, channel_id: int) -> None:
        await self.editorial_actions.sync_channel_activity_from_bindings()
        channel = await self.editorial_actions.get_channel(channel_id)
        if channel is None:
            await self.main_bot.send_message(chat_id, f"Канал {channel_id} не найден.")
            return

        if not channel.is_active:
            await self.main_bot.send_message(chat_id, "\u041a\u0430\u043d\u0430\u043b \u043e\u0442\u0432\u044f\u0437\u0430\u043d \u0438 \u0441\u043a\u0440\u044b\u0442 \u0438\u0437 \u0430\u043a\u0442\u0438\u0432\u043d\u043e\u0439 \u043f\u0430\u043d\u0435\u043b\u0438.")
            return

        label = await self._get_channel_label(channel_id)
        slots = await self.editorial_actions.list_channel_slots(channel_id)
        slot_lines = [f"Слоты для {label}:"]
        if not slots:
            slot_lines.append("Слотов пока нет.")
        else:
            for slot in slots:
                slot_label = f"{self._weekday_label(slot.weekday)} {slot.slot_time.strftime('%H:%M')}"
                slot_lines.append(f"#{slot.id} {slot_label}")

        await self.main_bot.send_message(
            chat_id,
            "\n".join(slot_lines),
            reply_markup=build_channel_slots_actions(channel_id),
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

    def _submission_notification_excerpt(self, submission) -> str:
        body = (submission.cleaned_text or submission.raw_text or "").strip()
        if not body:
            if getattr(submission, "media_group_id", None):
                body = "<медиа-группа без подписи>"
            elif getattr(submission, "content_type", "text") != "text":
                body = f"<{self._submission_type_label(submission)} без подписи>"
            else:
                body = "<без текста>"

        lines = [line.strip() for line in body.splitlines() if line.strip()]
        excerpt = "\n".join(lines[:2]) if lines else body
        if len(excerpt) > 220:
            excerpt = excerpt[:217].rstrip() + "..."
        return excerpt

    async def _send_submission_card(
        self,
        chat_id: int,
        submission_id: int,
        *,
        history_mode: bool,
        has_next: bool = False,
    ) -> None:
        submission = await self.editorial_actions.get_submission(submission_id)
        if submission is None:
            await self.main_bot.send_message(chat_id, f"Сообщение {submission_id} не найдено.")
            return

        await self._send_submission_preview(chat_id, submission.id)
        markup = (
            build_submission_history_actions(
                submission.id,
                has_next,
                submission.is_anonymous,
                allow_moderation=self._submission_moderation_allowed(str(submission.status)),
            )
            if history_mode
            else build_submission_actions(
                submission.id,
                has_next,
                submission.is_anonymous,
                allow_moderation=True,
            )
        )
        await self.main_bot.send_message(
            chat_id,
            await self._format_submission(submission),
            reply_markup=markup,
        )

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

    async def _show_first_pending_submission(
        self,
        chat_id: int,
        current_id: int | None = None,
        user_id: int | None = None,
    ) -> None:
        effective_user_id = user_id if user_id is not None else chat_id
        submissions = await self.editorial_actions.list_pending_submissions(user_id=effective_user_id)
        if not submissions:
            selected_channel_ids = await self.editorial_actions.list_user_moderation_feed_channel_ids(effective_user_id)
            if selected_channel_ids:
                await self.main_bot.send_message(chat_id, "Новых сообщений для выбранных каналов нет.")
            else:
                await self.main_bot.send_message(chat_id, "Новых сообщений для review нет.")
            return

        index = 0
        if current_id is not None:
            for idx, item in enumerate(submissions):
                if item.id == current_id:
                    index = min(idx + 1, len(submissions) - 1)
                    break

        submission = submissions[index]
        await self._send_submission_card(
            chat_id,
            submission.id,
            history_mode=False,
            has_next=len(submissions) > index + 1,
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
        await self._send_submission_card(
            chat_id,
            submission.id,
            history_mode=True,
            has_next=len(submissions) > index + 1,
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
        if action != "await_import_channel_history":
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
            result_text, channel_id = await self._add_subbot_from_values(api_token, channel_username)
            await self.main_bot.send_message(message.chat.id, result_text)
            if channel_id is not None:
                await self._send_channel_history_import_offer(message.chat.id, channel_id)
            return True

        if action == "await_import_channel_history":
            channel_id = state["channel_id"]
            source_chat_id, source_message_id, original_published_at = self._extract_forwarded_channel_payload(message)
            channel = await self.editorial_actions.get_channel(channel_id)
            if channel is None:
                self._clear_user_state(message.chat.id)
                await self.main_bot.send_message(message.chat.id, f"Канал {channel_id} не найден.")
                return True
            if source_chat_id is None or source_message_id is None:
                await self.main_bot.send_message(
                    message.chat.id,
                    "Перешлите именно сообщение из нужного канала, а не скопированный текст.",
                    reply_markup=build_channel_history_import_progress_actions(channel_id),
                )
                return True
            if int(source_chat_id) != int(channel.tg_channel_id):
                await self.main_bot.send_message(
                    message.chat.id,
                    "Это сообщение переслано не из выбранного канала. Перешлите пост именно из нужного канала.",
                    reply_markup=build_channel_history_import_progress_actions(channel_id),
                )
                return True

            import_result = await self.editorial_actions.import_channel_history_message(
                channel_id=channel_id,
                source_chat_id=int(source_chat_id),
                source_message_id=int(source_message_id),
                content_type=message.content_type or "text",
                raw_text=(message.text or message.caption or "").strip() or None,
                original_published_at=original_published_at,
                imported_by=message.from_user.id if message.from_user else message.chat.id,
            )

            if import_result.duplicate:
                state["history_duplicates"] = int(state.get("history_duplicates", 0)) + 1
            elif import_result.saved:
                state["history_saved"] = int(state.get("history_saved", 0)) + 1

            if import_result.matched_paste_id is not None and not import_result.duplicate:
                state["history_matches"] = int(state.get("history_matches", 0)) + 1

            return True

        if action == "await_add_slot":
            channel_id = state["channel_id"]
            try:
                weekdays, slot_times = self._parse_slot_input(text_value)
            except ValueError as exc:
                await self.main_bot.send_message(
                    message.chat.id,
                    f"{exc}\n\nПримеры:\n10:00 15:00 16:00\nall 10:00 15:00\n0 09:30 18:00\n0,2,4 18:00 21:00",
                )
                return True
            created_count = await self.editorial_actions.add_slots(channel_id, slot_times, weekdays)
            label = await self._get_channel_label(channel_id)
            await self.main_bot.send_message(
                message.chat.id,
                f"Для {label} добавлено слотов: {created_count}.",
            )
            await self._show_channel_slots_menu(message.chat.id, channel_id)
            return True

        if action == "await_delete_slots":
            channel_id = state["channel_id"]
            try:
                weekdays, slot_times = self._parse_slot_input(text_value)
            except ValueError as exc:
                await self.main_bot.send_message(
                    message.chat.id,
                    f"{exc}\n\nПримеры:\n10:00 15:00 16:00\nall 10:00 15:00\n0 09:30 18:00\n0,2,4 18:00 21:00",
                )
                return True
            removed_count = await self.editorial_actions.remove_slots(channel_id, slot_times, weekdays)
            label = await self._get_channel_label(channel_id)
            await self.main_bot.send_message(
                message.chat.id,
                f"Для {label} удалено слотов: {removed_count}.",
            )
            await self._show_channel_slots_menu(message.chat.id, channel_id)
            return True

        if action == "await_add_ad_blackout":
            channel_id = state["channel_id"]
            try:
                day_of_month, start_time, end_time = self._parse_ad_blackout_input(text_value)
                blackout = await self.editorial_actions.create_channel_ad_blackout(
                    channel_id=channel_id,
                    day_of_month=day_of_month,
                    start_time=start_time,
                    end_time=end_time,
                    created_by=message.from_user.id if message.from_user else message.chat.id,
                )
            except ValueError as exc:
                await self.main_bot.send_message(
                    message.chat.id,
                    f"{exc}\n\nПример:\n21 15:00 18:00",
                )
                return True

            label = await self._get_channel_label(channel_id)
            await self.main_bot.send_message(
                message.chat.id,
                f"Для {label} добавлено рекламное окно:\n{await self._format_ad_blackout(channel_id, blackout)}",
            )
            await self._show_channel_menu(
                message.chat.id,
                channel_id,
                user_id=message.from_user.id if message.from_user else message.chat.id,
            )
            return True

        if action == "await_delete_ad_blackout":
            channel_id = state["channel_id"]
            try:
                day_of_month, start_time, end_time = self._parse_ad_blackout_input(text_value)
                blackout = await self.editorial_actions.delete_channel_ad_blackout(
                    channel_id=channel_id,
                    day_of_month=day_of_month,
                    start_time=start_time,
                    end_time=end_time,
                )
            except ValueError as exc:
                await self.main_bot.send_message(
                    message.chat.id,
                    f"{exc}\n\n\u041f\u0440\u0438\u043c\u0435\u0440:\n21 15:00 18:00",
                )
                return True

            label = await self._get_channel_label(channel_id)
            await self.main_bot.send_message(
                message.chat.id,
                f"\u0414\u043b\u044f {label} \u0443\u0434\u0430\u043b\u0435\u043d\u043e \u0440\u0435\u043a\u043b\u0430\u043c\u043d\u043e\u0435 \u043e\u043a\u043d\u043e:\n{await self._format_ad_blackout(channel_id, blackout)}",
            )
            await self._show_channel_menu(
                message.chat.id,
                channel_id,
                user_id=message.from_user.id if message.from_user else message.chat.id,
            )
            return True

        if action == "await_update_channel_setting":
            channel_id = state["channel_id"]
            try:
                field_name, raw_setting_value = self._parse_channel_setting_input(text_value)
                channel = await self.editorial_actions.update_channel_setting(
                    channel_id=channel_id,
                    field_name=field_name,
                    raw_value=raw_setting_value,
                )
            except ValueError as exc:
                await self.main_bot.send_message(
                    message.chat.id,
                    f"{exc}\n\nПример:\nsame_tag_cooldown_hours 24\nallow_pastes false",
                )
                await self._send_channel_settings_prompt(message.chat.id, channel_id)
                return True
            await self.main_bot.send_message(
                message.chat.id,
                f"Параметр {field_name} обновлён: {self._format_channel_setting_value(getattr(channel, field_name))}.",
            )
            await self._show_channel_menu(message.chat.id, channel_id, user_id=message.from_user.id if message.from_user else message.chat.id)
            return True

        if action == "await_generate_posts":
            channel_id = state["channel_id"]
            try:
                variant_count = int(text_value)
            except ValueError:
                await self.main_bot.send_message(
                    message.chat.id,
                    "\u041d\u0443\u0436\u043d\u043e \u0447\u0438\u0441\u043b\u043e \u0432\u0430\u0440\u0438\u0430\u043d\u0442\u043e\u0432. \u041d\u0430\u043f\u0440\u0438\u043c\u0435\u0440: 3",
                )
                return True
            if variant_count < 1 or variant_count > 10:
                await self.main_bot.send_message(
                    message.chat.id,
                    "\u041c\u043e\u0436\u043d\u043e \u0441\u0433\u0435\u043d\u0435\u0440\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u043e\u0442 1 \u0434\u043e 10 \u0447\u0435\u0440\u043d\u043e\u0432\u0438\u043a\u043e\u0432 \u0437\u0430 \u043e\u0434\u0438\u043d \u0437\u0430\u043f\u0443\u0441\u043a.",
                )
                return True

            label = await self._get_channel_label(channel_id)
            status_message = await self.main_bot.send_message(
                message.chat.id,
                f"\u0413\u0435\u043d\u0435\u0440\u0438\u0440\u0443\u044e {variant_count} \u0447\u0435\u0440\u043d\u043e\u0432\u0438\u043a\u043e\u0432 \u0434\u043b\u044f {label}. \u042d\u0442\u043e \u043c\u043e\u0436\u0435\u0442 \u0437\u0430\u043d\u044f\u0442\u044c \u0434\u043e \u043c\u0438\u043d\u0443\u0442\u044b.",
            )
            try:
                run = await self.editorial_actions.run_generation(
                    channel_id=channel_id,
                    variant_count=variant_count,
                    source_count=max(8, variant_count * 3),
                )
            except Exception as ex:
                await self.main_bot.send_message(
                    message.chat.id,
                    f"\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0437\u0430\u043f\u0443\u0441\u0442\u0438\u0442\u044c \u0433\u0435\u043d\u0435\u0440\u0430\u0446\u0438\u044e: {ex}",
                )
                return True
            finally:
                try:
                    await self.main_bot.delete_message(message.chat.id, status_message.message_id)
                except Exception:
                    pass

            if run.generated_count:
                await self.main_bot.send_message(
                    message.chat.id,
                    (
                        f"\u0413\u0435\u043d\u0435\u0440\u0430\u0446\u0438\u044f \u0433\u043e\u0442\u043e\u0432\u0430.\n"
                        f"Generation run #{run.id}\n"
                        f"\u0418\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432: {run.source_count}\n"
                        f"\u0421\u043e\u0437\u0434\u0430\u043d\u043e \u0447\u0435\u0440\u043d\u043e\u0432\u0438\u043a\u043e\u0432: {run.generated_count}\n\n"
                        "\u0421\u0435\u0439\u0447\u0430\u0441 \u043e\u043d\u0438 \u043b\u0435\u0436\u0430\u0442 \u0432 '\u0427\u0435\u0440\u043d\u043e\u0432\u0438\u043a\u0438 \u043d\u0430 review'."
                    ),
                )
                await self._show_first_pending_content(message.chat.id)
                return True

            error_text = f"\n\u041e\u0448\u0438\u0431\u043a\u0430: {run.error_text}" if run.error_text else ""
            await self.main_bot.send_message(
                message.chat.id,
                (
                    f"\u0413\u0435\u043d\u0435\u0440\u0430\u0446\u0438\u044f \u043d\u0435 \u0441\u043e\u0437\u0434\u0430\u043b\u0430 \u0447\u0435\u0440\u043d\u043e\u0432\u0438\u043a\u0438.\n"
                    f"Generation run #{run.id}\n"
                    f"\u0421\u0442\u0430\u0442\u0443\u0441: {run.status}\n"
                    f"\u0418\u0441\u0442\u043e\u0447\u043d\u0438\u043a\u043e\u0432: {run.source_count}"
                    f"{error_text}"
                ),
            )
            await self._show_channel_menu(
                message.chat.id,
                channel_id,
                user_id=message.from_user.id if message.from_user else message.chat.id,
            )
            return True

        if action == "await_edit_content_item":
            content_item_id = int(state["content_item_id"])
            if not text_value:
                self._set_user_state(message.chat.id, "await_edit_content_item", content_item_id=content_item_id)
                await self.main_bot.send_message(
                    message.chat.id,
                    "\u041d\u0443\u0436\u0435\u043d \u043d\u043e\u0432\u044b\u0439 \u0442\u0435\u043a\u0441\u0442 \u0447\u0435\u0440\u043d\u043e\u0432\u0438\u043a\u0430.",
                )
                return True
            try:
                item = await self.editorial_actions.update_content_item_text(content_item_id, text_value)
            except Exception as ex:
                await self.main_bot.send_message(
                    message.chat.id,
                    f"\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0438\u0437\u043c\u0435\u043d\u0438\u0442\u044c \u0447\u0435\u0440\u043d\u043e\u0432\u0438\u043a: {ex}",
                )
                return True
            await self.main_bot.send_message(
                message.chat.id,
                f"\u0427\u0435\u0440\u043d\u043e\u0432\u0438\u043a #{content_item_id} \u043e\u0431\u043d\u043e\u0432\u043b\u0451\u043d.",
            )
            await self.main_bot.send_message(
                message.chat.id,
                await self._format_content_item(item),
                reply_markup=build_content_actions(item.id, has_next=False),
            )
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

        if action == "await_manual_channel_message":
            channel_ids = [int(channel_id) for channel_id in state.get("channel_ids", [])]
            if not text_value:
                self._set_user_state(message.chat.id, "await_manual_channel_message", channel_ids=channel_ids)
                await self.main_bot.send_message(
                    message.chat.id,
                    "\u041d\u0443\u0436\u0435\u043d \u0442\u0435\u043a\u0441\u0442, \u043a\u043e\u0442\u043e\u0440\u044b\u0439 \u043d\u0443\u0436\u043d\u043e \u043e\u043f\u0443\u0431\u043b\u0438\u043a\u043e\u0432\u0430\u0442\u044c.",
                )
                return True
            try:
                result = await self.editorial_actions.publish_manual_message_to_channels(
                    channel_ids=channel_ids,
                    moderator_id=message.from_user.id if message.from_user else message.chat.id,
                    body_text=text_value,
                )
            except Exception as ex:
                await self.main_bot.send_message(
                    message.chat.id,
                    f"\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u043e\u0442\u043f\u0440\u0430\u0432\u0438\u0442\u044c \u0440\u0443\u0447\u043d\u043e\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435: {ex}",
                )
                return True
            await self.main_bot.send_message(
                message.chat.id,
                self._format_manual_channel_message_result(result),
            )
            await self._show_my_channels_menu(
                message.chat.id,
                user_id=message.from_user.id if message.from_user else message.chat.id,
            )
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

        if action == "await_sql_export":
            if not text_value:
                await self.main_bot.send_message(message.chat.id, "Нужен SQL-запрос.")
                return True
            await self._send_sql_export_result(
                chat_id=message.chat.id,
                query=text_value,
                allow_mutating=bool(state.get("allow_mutating")),
            )
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
            try:
                if await bots_data[bot].reschedule_delayed_if_publication_blocked(message_id, sender_id):
                    continue
                sent = await bots_data[bot].send_delayed_message(message_id, sender_id)
                if not sent:
                    continue
                await self.delayed_database.delete_delayed_posts(
                    {
                        "bot_id": bot,
                        "message_id": message_id,
                    }
                )
            except Exception as ex:
                logger.error(
                    "Failed to publish legacy delayed message {} for bot {}: {}",
                    message_id,
                    bot,
                    ex,
                )

    @logger.catch
    async def __delayed_posts_checker(self) -> None:
        poll_interval = min(settings.const_time_sleep, 5)
        while True:
            delayed_posts = {}
            for bot in self.bots_work:
                delayed_message = await bot.getter_delayed_info()
                info_lst = sorted(delayed_message.items(), key=lambda item: (item[1], item[0]))
                delayed_posts[bot.bot_info.id] = info_lst
            await self.__send_post(delayed_posts)
            await asyncio.sleep(poll_interval)

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

    @logger.catch
    async def callback_adv_send_message_v2(
        self,
        call: CallbackQuery,
        source_bot: AsyncTeleBot,
        channel_label: str,
        info_sender: User,
        source_text: str | None = None,
    ) -> None:
        await send_advertising_flow(
            bot=source_bot,
            recipient_user_id=info_sender.id,
            channel_label=channel_label,
            source_text=source_text or call.message.text or call.message.caption,
            sender_username=info_sender.username,
            sender_first_name=info_sender.first_name,
        )

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
            result_text, channel_id = await self._add_subbot_from_values(api_token, channel_username)
            await self.main_bot.send_message(message.chat.id, result_text)
            if channel_id is not None:
                await self._send_channel_history_import_offer(message.chat.id, channel_id)

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
                        await self._show_first_pending_submission(call.message.chat.id, user_id=call.from_user.id)
                    case "all_submissions":
                        await self._show_submission_history(call.message.chat.id)
                    case "content":
                        await self._show_first_pending_content(call.message.chat.id)
                    case "pastes":
                        await self._show_first_paste(call.message.chat.id)
                    case "channels":
                        await self._show_channels_menu(call.message.chat.id)
                    case "my_channels":
                        await self._show_my_channels_menu(call.message.chat.id, user_id=call.from_user.id)
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
                    case "extra":
                        await self._show_extra_panel(call.message.chat.id)
                    case "db_export":
                        await self.main_bot.answer_callback_query(call.id)
                        await self._send_database_export(call.message.chat.id)
                        return
                    case "sql_export":
                        await self.main_bot.answer_callback_query(call.id)
                        await self._send_sql_export_prompt(
                            chat_id=call.message.chat.id,
                            allow_mutating=self._is_general_admin(call.from_user.id),
                        )
                        return
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

            if data.startswith("submission:") and not data.startswith("submission:view:"):
                _prefix, action, value = data.split(":")
                submission_id = int(value)
                reviewer_id = call.from_user.id
                match action:
                    case "approve":
                        item = await self.editorial_actions.approve_submission(submission_id, reviewer_id)
                        await self.editorial_actions.sync_panel_submission_approved(submission_id)
                        await self.main_bot.send_message(call.message.chat.id, f"Сообщение {submission_id} одобрено. Content item #{item.id}.")
                        await self._show_first_pending_submission(call.message.chat.id, current_id=submission_id, user_id=call.from_user.id)
                    case "publish":
                        try:
                            log_item = await self.editorial_actions.publish_submission_now(submission_id, reviewer_id)
                        except ValueError as exc:
                            await self.main_bot.send_message(call.message.chat.id, str(exc))
                            await self.main_bot.answer_callback_query(call.id)
                            return
                        await self.editorial_actions.sync_panel_submission_approved(submission_id)
                        await self.main_bot.send_message(call.message.chat.id, f"Сообщение {submission_id} отправлено в publish pipeline. Log #{log_item.id}.")
                        await self._show_first_pending_submission(call.message.chat.id, current_id=submission_id, user_id=call.from_user.id)
                    case "paste":
                        paste = await self.editorial_actions.paste_submission(submission_id, reviewer_id)
                        await self.main_bot.send_message(call.message.chat.id, f"Создана паста #{paste.id}: {paste.title}")
                        await self._show_first_pending_submission(call.message.chat.id, current_id=submission_id, user_id=call.from_user.id)
                    case "hold":
                        await self.editorial_actions.hold_submission(submission_id)
                        await self.main_bot.send_message(call.message.chat.id, f"Сообщение {submission_id} отправлено в hold.")
                        await self._show_first_pending_submission(call.message.chat.id, current_id=submission_id, user_id=call.from_user.id)
                    case "reject":
                        await self.editorial_actions.reject_submission(submission_id)
                        await self.editorial_actions.sync_panel_submission_rejected(submission_id)
                        await self.main_bot.send_message(call.message.chat.id, f"Сообщение {submission_id} отклонено.")
                        await self._show_first_pending_submission(call.message.chat.id, current_id=submission_id, user_id=call.from_user.id)
                    case "ban":
                        result = await self.editorial_actions.ban_submission_author(submission_id, reviewer_id)
                        await self.editorial_actions.sync_panel_submission_banned(submission_id)
                        author_label = f"@{result.username}" if result.username else str(result.user_id)
                        if result.already_banned:
                            await self.main_bot.send_message(
                                call.message.chat.id,
                                f"РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ {author_label} СѓР¶Рµ Р±С‹Р» РІ Р±Р°РЅРµ. РЎРѕРѕР±С‰РµРЅРёРµ {submission_id} РѕС‚РєР»РѕРЅРµРЅРѕ.",
                            )
                        else:
                            await self.main_bot.send_message(
                                call.message.chat.id,
                                f"РџРѕР»СЊР·РѕРІР°С‚РµР»СЊ {author_label} Р·Р°Р±Р°РЅРµРЅ. РЎРѕРѕР±С‰РµРЅРёРµ {submission_id} РѕС‚РєР»РѕРЅРµРЅРѕ.",
                            )
                        await self._show_first_pending_submission(call.message.chat.id, current_id=submission_id, user_id=call.from_user.id)
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
                            await self.editorial_actions.send_submission_advertising_reply_v2(submission_id)
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
                        await self._show_first_pending_submission(call.message.chat.id, current_id=submission_id, user_id=call.from_user.id)
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("submission_all:next:"):
                submission_id = int(data.split(":")[-1])
                await self._show_submission_history(call.message.chat.id, current_id=submission_id)
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("submission_all:delete:"):
                submission_id = int(data.split(":")[-1])
                deleted_count = await self.editorial_actions.delete_submission(submission_id)
                await self.main_bot.send_message(
                    call.message.chat.id,
                    f"Удалено сообщений: {deleted_count}. Submission #{submission_id} убран из базы.",
                )
                await self._show_submission_history(call.message.chat.id, current_id=submission_id)
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("submission:view:"):
                submission_id = int(data.split(":")[-1])
                await self._send_submission_card(
                    call.message.chat.id,
                    submission_id,
                    history_mode=True,
                    has_next=False,
                )
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
                        try:
                            log_item = await self.editorial_actions.publish_content_item_now(content_item_id, reviewer_id)
                        except ValueError as exc:
                            await self.main_bot.send_message(call.message.chat.id, str(exc))
                            await self.main_bot.answer_callback_query(call.id)
                            return
                        await self.main_bot.send_message(call.message.chat.id, f"Контент {content_item_id} поставлен в публикацию. Log #{log_item.id}.")
                        await self._show_first_pending_content(call.message.chat.id, current_id=content_item_id)
                    case "edit":
                        item = await self.editorial_actions.get_content_item(content_item_id)
                        if item is None:
                            await self.main_bot.send_message(
                                call.message.chat.id,
                                f"\u0427\u0435\u0440\u043d\u043e\u0432\u0438\u043a #{content_item_id} \u043d\u0435 \u043d\u0430\u0439\u0434\u0435\u043d.",
                            )
                        else:
                            self._set_user_state(
                                call.message.chat.id,
                                "await_edit_content_item",
                                content_item_id=content_item_id,
                            )
                            await self.main_bot.send_message(
                                call.message.chat.id,
                                (
                                    f"\u041e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u043d\u043e\u0432\u044b\u0439 \u0442\u0435\u043a\u0441\u0442 \u0434\u043b\u044f \u0447\u0435\u0440\u043d\u043e\u0432\u0438\u043a\u0430 #{content_item_id}.\n"
                                    "\u041e\u043d \u043f\u0440\u043e\u0441\u0442\u043e \u0437\u0430\u043c\u0435\u043d\u0438\u0442 \u0442\u0435\u043a\u0443\u0449\u0438\u0439 \u0442\u0435\u043a\u0441\u0442, \u0442\u0438\u043f \u043a\u043e\u043d\u0442\u0435\u043d\u0442\u0430 \u043d\u0435 \u0438\u0437\u043c\u0435\u043d\u0438\u0442\u0441\u044f."
                                ),
                            )
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

            if data == "my_channels:all":
                channels = await self.editorial_actions.list_user_moderation_feed_channels(call.from_user.id)
                channel_ids = [int(channel.id) for channel in channels]
                if not channel_ids:
                    await self.main_bot.send_message(
                        call.message.chat.id,
                        "\u0423 \u0432\u0430\u0441 \u043f\u043e\u043a\u0430 \u043d\u0435 \u0432\u044b\u0431\u0440\u0430\u043d\u044b \u043a\u0430\u043d\u0430\u043b\u044b \u0434\u043b\u044f \u043f\u043e\u043b\u0443\u0447\u0435\u043d\u0438\u044f \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0439.",
                    )
                    await self.main_bot.answer_callback_query(call.id)
                    return
                self._set_user_state(
                    call.message.chat.id,
                    "await_manual_channel_message",
                    channel_ids=channel_ids,
                )
                await self.main_bot.send_message(
                    call.message.chat.id,
                    (
                        "\u041e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u043e\u0434\u043d\u0438\u043c \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u0435\u043c \u0442\u0435\u043a\u0441\u0442, "
                        f"\u043a\u043e\u0442\u043e\u0440\u044b\u0439 \u043d\u0443\u0436\u043d\u043e \u043e\u043f\u0443\u0431\u043b\u0438\u043a\u043e\u0432\u0430\u0442\u044c \u0432\u043e \u0432\u0441\u0435 \u0432\u044b\u0431\u0440\u0430\u043d\u043d\u044b\u0435 \u043a\u0430\u043d\u0430\u043b\u044b ({len(channel_ids)})."
                    ),
                )
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("my_channels:channel:"):
                channel_id = int(data.split(":")[-1])
                selected_channel_ids = set(await self.editorial_actions.list_user_moderation_feed_channel_ids(call.from_user.id))
                if channel_id not in selected_channel_ids:
                    await self.main_bot.answer_callback_query(
                        call.id,
                        "\u042d\u0442\u043e\u0442 \u043a\u0430\u043d\u0430\u043b \u043d\u0435 \u0432\u043a\u043b\u044e\u0447\u0451\u043d \u0432 \u0432\u0430\u0448\u0438 '\u043f\u043e\u0441\u0442\u0443\u043f\u0438\u0432\u0448\u0438\u0435 \u0441\u043e\u043e\u0431\u0449\u0435\u043d\u0438\u044f'.",
                        show_alert=True,
                    )
                    return
                label = await self._get_channel_label(channel_id)
                self._set_user_state(
                    call.message.chat.id,
                    "await_manual_channel_message",
                    channel_ids=[channel_id],
                )
                await self.main_bot.send_message(
                    call.message.chat.id,
                    (
                        f"\u041e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u0442\u0435\u043a\u0441\u0442, "
                        f"\u043a\u043e\u0442\u043e\u0440\u044b\u0439 \u043d\u0443\u0436\u043d\u043e \u043e\u043f\u0443\u0431\u043b\u0438\u043a\u043e\u0432\u0430\u0442\u044c \u0432 {label}."
                    ),
                )
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("channel:view:"):
                channel_id = int(data.split(":")[-1])
                await self._show_channel_menu(call.message.chat.id, channel_id, user_id=call.from_user.id)
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("channel:notify_toggle:"):
                channel_id = int(data.split(":")[-1])
                enabled = await self.editorial_actions.toggle_channel_notifications(channel_id, call.from_user.id)
                await self.main_bot.send_message(
                    call.message.chat.id,
                    "Уведомления включены." if enabled else "Уведомления выключены.",
                )
                await self._show_channel_menu(call.message.chat.id, channel_id, user_id=call.from_user.id)
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("channel:feed_toggle:"):
                channel_id = int(data.split(":")[-1])
                enabled = await self.editorial_actions.toggle_channel_moderation_feed(channel_id, call.from_user.id)
                await self.main_bot.send_message(
                    call.message.chat.id,
                    "Получение сообщений из канала включено." if enabled else "Получение сообщений из канала выключено.",
                )
                await self._show_channel_menu(call.message.chat.id, channel_id, user_id=call.from_user.id)
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("channel:ad_blackout:"):
                channel_id = int(data.split(":")[-1])
                self._set_user_state(call.message.chat.id, "await_add_ad_blackout", channel_id=channel_id)
                await self.main_bot.send_message(
                    call.message.chat.id,
                    "Отправьте рекламное окно в формате:\n"
                    "21 15:00 18:00\n\n"
                    "Это значит: 21 числа с 15:00 до 18:00 канал будет защищён от публикаций. "
                    "Если такая дата в текущем месяце уже прошла, будет выбран следующий месяц.",
                )
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("channel:delete_ad_blackout:"):
                channel_id = int(data.split(":")[-1])
                self._set_user_state(call.message.chat.id, "await_delete_ad_blackout", channel_id=channel_id)
                await self.main_bot.send_message(
                    call.message.chat.id,
                    "\u041e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u0440\u0435\u043a\u043b\u0430\u043c\u043d\u043e\u0435 \u043e\u043a\u043d\u043e, \u043a\u043e\u0442\u043e\u0440\u043e\u0435 \u043d\u0443\u0436\u043d\u043e \u0443\u0434\u0430\u043b\u0438\u0442\u044c, \u0432 \u0444\u043e\u0440\u043c\u0430\u0442\u0435:\n"
                    "21 15:00 18:00\n\n"
                    "\u0412\u0432\u043e\u0434 \u0434\u043e\u043b\u0436\u0435\u043d \u0441\u043e\u0432\u043f\u0430\u0434\u0430\u0442\u044c \u0441 \u0442\u0435\u043c \u043e\u043a\u043d\u043e\u043c, \u043a\u043e\u0442\u043e\u0440\u043e\u0435 \u0431\u044b\u043b\u043e \u0434\u043e\u0431\u0430\u0432\u043b\u0435\u043d\u043e.",
                )
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("channel:generate:"):
                channel_id = int(data.split(":")[-1])
                label = await self._get_channel_label(channel_id)
                self._set_user_state(call.message.chat.id, "await_generate_posts", channel_id=channel_id)
                await self.main_bot.send_message(
                    call.message.chat.id,
                    (
                        f"\u0421\u043a\u043e\u043b\u044c\u043a\u043e \u0447\u0435\u0440\u043d\u043e\u0432\u0438\u043a\u043e\u0432 \u0441\u0433\u0435\u043d\u0435\u0440\u0438\u0440\u043e\u0432\u0430\u0442\u044c \u0434\u043b\u044f {label}?\n\n"
                        "\u041e\u0442\u043f\u0440\u0430\u0432\u044c\u0442\u0435 \u0447\u0438\u0441\u043b\u043e \u043e\u0442 1 \u0434\u043e 10. \u041e\u0431\u044b\u0447\u043d\u043e \u0445\u0432\u0430\u0442\u0430\u0435\u0442 3."
                    ),
                )
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("channel:slots:"):
                channel_id = int(data.split(":")[-1])
                await self._show_channel_slots_menu(call.message.chat.id, channel_id)
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("channel:params:"):
                channel_id = int(data.split(":")[-1])
                self._set_user_state(call.message.chat.id, "await_update_channel_setting", channel_id=channel_id)
                await self._send_channel_settings_prompt(call.message.chat.id, channel_id)
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
                    "Отправьте одно или несколько времен через пробел.\n"
                    "Можно указать только время для всех дней или '<дни> <времена...>'.\n"
                    "Примеры:\n12:00 15:00 16:00\nall 10:00 15:00\n0 09:30 18:00\n0,2,4 18:00 21:00\n"
                    "Где 0 = понедельник, 6 = воскресенье.",
                )
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("channel:delete_slots:"):
                channel_id = int(data.split(":")[-1])
                self._set_user_state(call.message.chat.id, "await_delete_slots", channel_id=channel_id)
                await self.main_bot.send_message(
                    call.message.chat.id,
                    "Отправьте времена слотов, которые нужно удалить.\n"
                    "Можно указать только время для всех дней или '<дни> <времена...>'.\n"
                    "Примеры:\n12:00 15:00 16:00\nall 10:00 15:00\n0 09:30 18:00\n0,2,4 18:00 21:00\n"
                    "Где 0 = понедельник, 6 = воскресенье.",
                )
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
                deleted_paste_id, deleted_paste_title = await self.editorial_actions.delete_paste(paste_id)
                await self.main_bot.send_message(
                    call.message.chat.id,
                    f"Паста #{deleted_paste_id} удалена: {deleted_paste_title}",
                )
                await self._show_first_paste(call.message.chat.id, current_id=paste_id)
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("paste:delete:legacy_disabled:"):
                paste_id = int(data.split(":")[-1])
                deleted_paste_id, deleted_paste_title = await self.editorial_actions.delete_paste(paste_id)
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

            if data == "subbot:remove_cancel":
                if not self._is_general_admin(call.message.chat.id):
                    await self.main_bot.answer_callback_query(call.id, "\u0422\u043e\u043b\u044c\u043a\u043e \u0434\u043b\u044f \u0433\u0435\u043d\u0435\u0440\u0430\u043b\u044c\u043d\u043e\u0433\u043e \u0430\u0434\u043c\u0438\u043d\u0430.", show_alert=True)
                    return
                await self.main_bot.send_message(call.message.chat.id, "\u0423\u0434\u0430\u043b\u0435\u043d\u0438\u0435 \u0441\u0430\u0431\u0431\u043e\u0442\u0430 \u043e\u0442\u043c\u0435\u043d\u0435\u043d\u043e.")
                await self._show_subbots_menu(call.message.chat.id)
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("subbot:remove_confirm:"):
                if not self._is_general_admin(call.message.chat.id):
                    await self.main_bot.answer_callback_query(call.id, "\u0422\u043e\u043b\u044c\u043a\u043e \u0434\u043b\u044f \u0433\u0435\u043d\u0435\u0440\u0430\u043b\u044c\u043d\u043e\u0433\u043e \u0430\u0434\u043c\u0438\u043d\u0430.", show_alert=True)
                    return
                _, _, _, username_bot, channel_id = data.split(":")
                result_text = await self._remove_subbot_from_values(username_bot, int(channel_id))
                await self.main_bot.send_message(call.message.chat.id, result_text)
                await self._show_subbots_menu(call.message.chat.id)
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("subbot:remove:"):
                if not self._is_general_admin(call.message.chat.id):
                    await self.main_bot.answer_callback_query(call.id, "\u0422\u043e\u043b\u044c\u043a\u043e \u0434\u043b\u044f \u0433\u0435\u043d\u0435\u0440\u0430\u043b\u044c\u043d\u043e\u0433\u043e \u0430\u0434\u043c\u0438\u043d\u0430.", show_alert=True)
                    return
                _, _, username_bot, channel_id = data.split(":")
                await self.main_bot.send_message(
                    call.message.chat.id,
                    f"\u0412\u044b \u0442\u043e\u0447\u043d\u043e \u0445\u043e\u0442\u0438\u0442\u0435 \u0443\u0434\u0430\u043b\u0438\u0442\u044c \u0441\u0430\u0431\u0431\u043e\u0442\u0430 @{username_bot}?",
                    reply_markup=build_subbot_remove_confirm(username_bot, int(channel_id)),
                )
                await self.main_bot.answer_callback_query(call.id)
                return

            if data == "subbot:remove_cancel":
                if not self._is_general_admin(call.message.chat.id):
                    await self.main_bot.answer_callback_query(call.id, "РўРѕР»СЊРєРѕ РґР»СЏ РіРµРЅРµСЂР°Р»СЊРЅРѕРіРѕ Р°РґРјРёРЅР°.", show_alert=True)
                    return
                await self.main_bot.send_message(call.message.chat.id, "РЈРґР°Р»РµРЅРёРµ СЃР°Р±Р±РѕС‚Р° РѕС‚РјРµРЅРµРЅРѕ.")
                await self._show_subbots_menu(call.message.chat.id)
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("subbot:remove_confirm:"):
                if not self._is_general_admin(call.message.chat.id):
                    await self.main_bot.answer_callback_query(call.id, "РўРѕР»СЊРєРѕ РґР»СЏ РіРµРЅРµСЂР°Р»СЊРЅРѕРіРѕ Р°РґРјРёРЅР°.", show_alert=True)
                    return
                _, _, _, username_bot, channel_id = data.split(":")
                result_text = await self._remove_subbot_from_values(username_bot, int(channel_id))
                await self.main_bot.send_message(call.message.chat.id, result_text)
                await self._show_subbots_menu(call.message.chat.id)
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

            if data.startswith("channel_history:start:"):
                channel_id = int(data.split(":")[-1])
                self._set_user_state(
                    call.message.chat.id,
                    "await_import_channel_history",
                    channel_id=channel_id,
                    history_saved=0,
                    history_matches=0,
                    history_duplicates=0,
                )
                label = await self._get_channel_label(channel_id)
                await self.main_bot.send_message(
                    call.message.chat.id,
                    (
                        f"Импорт истории для {label} запущен.\n\n"
                        "Теперь пересылайте сюда сообщения из этого канала. "
                        "Когда закончите, нажмите 'Завершить импорт'."
                    ),
                    reply_markup=build_channel_history_import_progress_actions(channel_id),
                )
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("channel_history:finish:"):
                channel_id = int(data.split(":")[-1])
                state = self.user_states.get(call.message.chat.id, {})
                saved = int(state.get("history_saved", 0))
                matches = int(state.get("history_matches", 0))
                duplicates = int(state.get("history_duplicates", 0))
                if state.get("action") == "await_import_channel_history" and state.get("channel_id") == channel_id:
                    self._clear_user_state(call.message.chat.id)
                label = await self._get_channel_label(channel_id)
                await self.main_bot.send_message(
                    call.message.chat.id,
                    (
                        f"Импорт истории для {label} завершён.\n"
                        f"Сохранено сообщений: {saved}\n"
                        f"Найдено совпадений с пастами: {matches}\n"
                        f"Пропущено дублей: {duplicates}"
                    ),
                )
                await self.main_bot.answer_callback_query(call.id)
                return

            if data.startswith("channel_history:cancel:"):
                channel_id = int(data.split(":")[-1])
                state = self.user_states.get(call.message.chat.id, {})
                if state.get("action") == "await_import_channel_history" and state.get("channel_id") == channel_id:
                    self._clear_user_state(call.message.chat.id)
                await self.main_bot.send_message(call.message.chat.id, "Импорт истории отменён.")
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
                        callback_adv_action=self.callback_adv_send_message_v2,
                        callback_new_submission=self.callback_new_submission_notification,
                    )
                    await bot.run_bot()
                    self.bots_work.append(bot)
            self.delayed_task = asyncio.create_task(self.__delayed_posts_checker())
            await self.main_bot.polling(none_stop=True)
        except Exception as ex:
            logger.error("bot: @{}, mistake: {}", self.bot_info.username if self.bot_info else "unknown", ex)
