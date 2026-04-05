import pytz
from telebot.types import Message, CallbackQuery, InlineKeyboardButton
from datetime import datetime, timedelta, timezone
from loguru import logger

from src.core_database.database import CrudBannedUser
from config import settings


class Utils:
    @staticmethod
    async def check_banned_user(id_user: int, id_channel: int) -> bool:
        db_session = CrudBannedUser()
        all_info = await db_session.get_banned_users(id_user=id_user, id_channel=id_channel)
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

    @staticmethod
    @logger.catch
    async def save_post(call: CallbackQuery, public_posts, channel_id, info_sender, bot_info) -> None:
        data = {
            "user_id":  info_sender.id,
            "channel_id": channel_id,
            "bot_username": bot_info.username,
            "username": info_sender.username,
            "first_name": info_sender.first_name,
            "message_id": call.message.id,
            "chat_id": call.message.chat.id,
            "text_post": None
            }
        if call.message.content_type == "text":
            data["text_post"] = call.message.text
        elif call.message.caption is not None:
            data["text_post"] = call.message.caption

        await public_posts.add_public_posts(data)

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
        if message.content_type == "text":
            return "http" in message.text or "https" in message.text
        elif message.caption is not None:
            return "http" in message.caption or "https" in message.caption
        else:
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
