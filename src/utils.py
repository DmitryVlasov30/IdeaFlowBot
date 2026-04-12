import pytz
from telebot.types import Message, CallbackQuery, InlineKeyboardButton
from datetime import datetime, timedelta, timezone
from loguru import logger

from src.core_database.database import CrudBannedUser, CrudPostData
from src.core_database.models.sender_info import SenderData
from src.core_database.models.admin_actions import AdminActionData
from config import settings


class Utils:
    def __init__(self):
        self.db_banned = CrudBannedUser()
        self.sender_data = CrudPostData(SenderData)
        self.action_admin = CrudPostData(AdminActionData)

    async def check_banned_user(self, id_user: int, id_channel: int) -> bool:
        all_info = await self.db_banned.get_banned_users(id_user=id_user, id_channel=id_channel)
        return bool(all_info)

    @staticmethod
    async def get_timestamp_public(time) -> float:
        tz = timezone(timedelta(hours=3))
        hour, minute = map(int, time.split(':'))
        now = datetime.now(tz)
        target = now.replace(hour=hour, minute=minute)
        if now >= target:
            target += timedelta(days=1)

        time_public = target.timestamp()
        return time_public

    @staticmethod
    async def get_timestamp_to_time(timestamp) -> str:
        tz = timezone(timedelta(hours=3))
        return datetime.fromtimestamp(timestamp, tz=tz).strftime('%H:%M')

    @staticmethod
    async def conversion_to_moscow_time(timestamp):
        utc_date = datetime.fromtimestamp(timestamp, tz=pytz.utc)
        local_tz = pytz.timezone('Europe/Moscow')
        local_date = utc_date.astimezone(local_tz)
        return local_date.timestamp()

    @logger.catch
    async def save_post(self, call: CallbackQuery, channel_id, info_sender, bot_info) -> None:
        timestamp = datetime.now(pytz.timezone('Europe/Moscow')).timestamp()
        logger.debug(timestamp)
        data = {
            "user_id":  info_sender.id,
            "channel_id": channel_id,
            "bot_username": bot_info,
            "username": info_sender.username if info_sender.username is not None else "",
            "first_name": info_sender.first_name,
            "message_id": call.message.id,
            "chat_id": call.message.chat.id,
            "text_post": None,
            "timestamp": int(timestamp),
            }
        if call.message.content_type == "text":
            data["text_post"] = call.message.text
        elif call.message.caption is not None:
            data["text_post"] = call.message.caption

        await self.sender_data.add_public_posts(data)

    @logger.catch
    async def save_admin_action(self, call):
        timestamp = datetime.now(pytz.timezone('Europe/Moscow')).timestamp()
        data = {
            "message_id": call.message.id,
            "chat_id": call.message.chat.id,
            "admin_id": call.message.from_user.id,
            "timestamp": int(timestamp),
            "button": call.data.split(";")[0],
        }
        await self.action_admin.add_public_posts(data)

    @staticmethod
    @logger.catch
    async def get_anon(message: Message):
        reply_markup = message.reply_markup.keyboard
        logger.debug(reply_markup)
        anon_markup: InlineKeyboardButton = reply_markup[2][1]
        is_anon = anon_markup.callback_data.split(";")[-1]
        return True if is_anon == "True" else False

    @staticmethod
    @logger.catch
    async def check_link(message: Message) -> bool:
        if message.entities is None and message.caption_entities is None:
            if message.text is None and message.caption is None:
                return False
            if message.text is None:
                text = message.caption
            else:
                text = message.text
            return "http" in text or "https" in text
        if message.entities is None:
            check_lst = message.caption_entities
        else:
            check_lst = message.entities
        for el in check_lst:
            if el.type == "text_link":
                return True
        return False


def filter_chats(func):
    def wrapper(message: Message):
        if (message.chat.id < 0 or
                message.chat.id == settings.general_admin or
                message.chat.id in settings.moderators):
            return func(message)
    return wrapper


def filter_admin(func):
    def wrapper(message: Message):
        if message.chat.id == settings.general_admin or message.chat.id in settings.moderators:
            return func(message)
    return wrapper
