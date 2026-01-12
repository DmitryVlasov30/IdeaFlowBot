from telebot.types import Message

from src.core_database.database import CrudBannedUser
from config import settings


class Utils:
    @staticmethod
    def check_banned_user(id_user: int, id_channel: int) -> bool:
        db_session = CrudBannedUser()
        all_info = db_session.get_banned_users(id_user=id_user, id_channel=id_channel)
        return bool(all_info)


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
