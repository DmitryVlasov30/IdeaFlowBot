from telebot.types import Message, CallbackQuery
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
    @logger.catch
    async def save_post(call: CallbackQuery, public_posts, channel_id) -> None:
        if call.message.content_type == "text":
            await public_posts.add_public_posts({
                "channel_id": channel_id,
                "posts_title": call.message.text,
            })


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
