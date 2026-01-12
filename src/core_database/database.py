from sqlalchemy import insert, select, and_, delete, update

from src.core_database.models.base import Base
from src.core_database.models.banned_user import BannedUser
from src.core_database.models.bots_data import BotsData
from src.core_database.models.chat_admins import ChatAdmins
from src.core_database.models.public_posts import PublicPosts
from src.core_database.models.service_message import ServiceMessage
from src.core_database.models.db_helper import db_helper


def create_table():
    Base.metadata.create_all(db_helper.engine)


def drop_table():
    Base.metadata.drop_all(db_helper.engine)


class CrudBannedUser:
    @staticmethod
    def get_banned_users(id_user: int = None, id_channel: int = None):
        with db_helper.engine.connect() as conn:
            if id_user is None and id_channel is None:
                return conn.execute(select(BannedUser)).fetchall()
            elif id_user is None and id_channel is not None:
                return conn.execute(select(BannedUser).filter(BannedUser.id_channel == id_channel)).fetchall()
            elif id_channel is None and id_user is not None:
                return conn.execute(select(BannedUser).filter(BannedUser.id_user == id_user)).fetchall()
            else:
                return conn.execute(
                    select(BannedUser)
                    .filter(and_(
                        BannedUser.id_channel == id_channel,
                        BannedUser.id_user == id_user
                    ))
                ).fetchall()

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


class CrudBotsData:
    @staticmethod
    def get_bots_info():
        with db_helper.engine.connect() as conn:
            return conn.execute(select(BotsData)).fetchall()

    @staticmethod
    def add_bots_info(data: dict):
        with db_helper.engine.connect() as conn:
            conn.execute(insert(BotsData).values(data))
            conn.commit()

    @staticmethod
    def delete_bots_info(data: dict):
        with db_helper.engine.connect() as conn:
            conn.execute(
                delete(BotsData)
                .filter(and_(
                    BotsData.channel_id == data["channel_id"],
                    BotsData.bot_api_token == data["bot_api_token"],
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


class CrudServiceMessage:
    @staticmethod
    def get_service_message(bot_id: int):
        with db_helper.engine.connect() as conn:
            return conn.execute(select(ServiceMessage).filter(ServiceMessage.bot_id == bot_id)).fetchall()

    @staticmethod
    def add_service_message(data: dict):
        with db_helper.engine.connect() as conn:
            conn.execute(insert(ServiceMessage).values(data))
            conn.commit()

    @staticmethod
    def update_service_message(bot_id: int, hello_message: str, ban_user_message: str):
        with db_helper.engine.connect() as conn:
            conn.execute(
                update(ServiceMessage)
                .filter(ServiceMessage.bot_id == bot_id)
                .values(hello_message=hello_message, ban_user_message=ban_user_message)
            )
            conn.commit()


class CrudPublicPosts:
    @staticmethod
    def get_public_posts():
        with db_helper.engine.connect() as conn:
            return conn.execute(select(PublicPosts)).fetchall()

    @staticmethod
    def add_public_posts(data: dict):
        with db_helper.engine.connect() as conn:
            conn.execute(insert(PublicPosts).values(data))
            conn.commit()


if __name__ == '__main__':
    ...
