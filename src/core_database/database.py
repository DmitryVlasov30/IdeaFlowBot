from sqlalchemy import insert, select, and_, delete, update

from src.core_database.models.base import Base
from src.core_database.models.banned_user import BannedUser
from src.core_database.models.channel_suggest import ChannelSuggest
from src.core_database.models.chat_admins import ChatAdmins
from src.core_database.models.db_helper import db_helper


def create_table():
    Base.metadata.create_all(db_helper.engine)


def drop_table():
    Base.metadata.drop_all(db_helper.engine)


class CrudBannedUser:
    @staticmethod
    def get_banned_users():
        with db_helper.engine.connect() as conn:
            result = conn.execute(select(BannedUser)).fetchall()
            return result

    @staticmethod
    def add_banned_user(user: dict):
        with db_helper.engine.connect() as conn:
            stmt = (
                insert(BannedUser).values(user)
            )
            conn.execute(stmt)
            conn.commit()

    @staticmethod
    def delete_banned_user(user: dict):
        with db_helper.engine.connect() as conn:
            stmt = (
                delete(BannedUser)
                .filter(and_(
                    BannedUser.id_user == user["id_user"],
                    BannedUser.id_channel == user["id_channel"]
                ))
            )
            conn.execute(stmt)
            conn.commit()


class CrudChannelSuggest:
    @staticmethod
    def get_chat_suggest():
        with db_helper.engine.connect() as conn:
            return conn.execute(select(ChannelSuggest)).fetchall()

    @staticmethod
    def add_chat_suggest(data: dict):
        with db_helper.engine.connect() as conn:
            conn.execute(insert(ChannelSuggest).values(data))
            conn.commit()

    @staticmethod
    def delete_chat_suggest(data: dict):
        with db_helper.engine.connect() as conn:
            conn.execute(
                delete(ChannelSuggest)
                .filter(and_(
                    ChannelSuggest.channel_id == data["channel_id"],
                    ChannelSuggest.bot_id == data["bot_id"],
                ))
            )
            conn.commit()


class CrudChatAdmins:
    @staticmethod
    def get_chat_admins(bot: int = None, chat: int = None):
        with db_helper.engine.connect() as conn:
            if bot is None and chat is None:
                return conn.execute(select(ChatAdmins)).fetchall()
            elif bot is None:
                return conn.execute(select(ChatAdmins).filter(ChatAdmins.chat_id == chat)).fetchall()
            elif chat is None:
                return conn.execute(select(ChatAdmins).filter(ChatAdmins.bot_id == bot)).fetchall()
            else:
                return conn.execute(
                    select(ChatAdmins)
                    .filter(and_(
                        ChatAdmins.chat_id == chat,
                        ChatAdmins.bot_id == bot
                    ))
                ).fetchall()

    @staticmethod
    def add_chat_admins(data: dict):
        with db_helper.engine.connect() as conn:
            conn.execute(insert(ChatAdmins).values(data))
            conn.commit()

    @staticmethod
    def delete_chat_admins(data: dict):
        with db_helper.engine.connect() as conn:
            conn.execute(
                delete(ChatAdmins)
                .filter(and_(
                    ChatAdmins.chat_id == data["chat_id"],
                    ChatAdmins.bot_id == data["bot_id"],
                ))
            )
            conn.commit()

