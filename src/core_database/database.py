from sqlalchemy import insert, select, and_, delete, update

from src.core_database.models.base import Base
from src.core_database.models.banned_user import BannedUser
from src.core_database.models.bots_data import BotsData
from src.core_database.models.chat_admins import ChatAdmins
from src.core_database.models.public_posts import PublicPosts
from src.core_database.models.service_message import ServiceMessage
from src.core_database.models.users import UserData
from src.core_database.models.db_helper import db_helper


async def create_table():
    async with db_helper.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all(db_helper.engine))


async def drop_table():
    async with db_helper.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all(db_helper.engine))


class CrudUserData:
    @staticmethod
    async def get_user_data(user_id: int = None, bot_username: str = None):
        async with db_helper.engine.connect() as conn:
            if user_id is None and bot_username is None:
                return (await conn.execute(select(UserData))).fetchall()
            elif bot_username is None:
                return (await conn.execute(select(UserData).filter(UserData.user_id == user_id))).fetchall()
            elif user_id is None:
                return (await conn.execute(select(UserData).filter(UserData.bot_username == bot_username))).fetchall()
            else:
                return (await conn.execute(
                    select(UserData)
                    .filter(and_(UserData.user_id == user_id, UserData.bot_username == bot_username))
                )).fetchall()

    @staticmethod
    async def insert_user(data: dict):
        async with db_helper.engine.connect() as conn:
            stmt = (
                insert(UserData).values(data)
            )
            await conn.execute(stmt)
            await conn.commit()

    @staticmethod
    async def delete_user_data(user_id: int, bot_username: str):
        async with db_helper.engine.connect() as conn:
            stmt = (
                delete(UserData)
                .filter(and_(
                    UserData.user_id == user_id,
                    UserData.bot_username == bot_username
                ))
            )
            await conn.execute(stmt)
            await conn.commit()


class CrudBannedUser:
    @staticmethod
    async def get_banned_users(id_user: int = None, id_channel: int = None):
        async with db_helper.engine.connect() as conn:
            if id_user is None and id_channel is None:
                return (await conn.execute(select(BannedUser))).fetchall()
            elif id_user is None and id_channel is not None:
                return (await conn.execute(select(BannedUser).filter(BannedUser.id_channel == id_channel))).fetchall()
            elif id_channel is None and id_user is not None:
                return (await conn.execute(select(BannedUser).filter(BannedUser.id_user == id_user))).fetchall()
            else:
                return (await conn.execute(
                    select(BannedUser)
                    .filter(and_(
                        BannedUser.id_channel == id_channel,
                        BannedUser.id_user == id_user
                    ))
                )).fetchall()

    @staticmethod
    async def add_banned_user(user: dict):
        async with db_helper.engine.connect() as conn:
            stmt = (
                insert(BannedUser).values(user)
            )
            await conn.execute(stmt)
            await conn.commit()

    @staticmethod
    async def delete_banned_user(user: dict):
        async with db_helper.engine.connect() as conn:
            stmt = (
                delete(BannedUser)
                .filter(and_(
                    BannedUser.id_user == user["id_user"],
                    BannedUser.id_channel == user["id_channel"]
                ))
            )
            await conn.execute(stmt)
            await conn.commit()


class CrudBotsData:
    @staticmethod
    async def get_bots_info():
        async with db_helper.engine.connect() as conn:
            return (await conn.execute(select(BotsData))).fetchall()

    @staticmethod
    async def add_bots_info(data: dict):
        async with db_helper.engine.connect() as conn:
            await conn.execute(insert(BotsData).values(data))
            await conn.commit()

    @staticmethod
    async def delete_bots_info(data: dict):
        async with db_helper.engine.connect() as conn:
            await conn.execute(
                delete(BotsData)
                .filter(and_(
                    BotsData.channel_id == data["channel_id"],
                    BotsData.bot_username == data["bot_username"],
                ))
            )
            await conn.commit()


class CrudChatAdmins:
    @staticmethod
    async def get_chat_admins(bot: int = None, chat: int = None):
        async with db_helper.engine.connect() as conn:
            if bot is None and chat is None:
                return (await conn.execute(select(ChatAdmins))).fetchall()
            elif bot is None:
                return (await conn.execute(select(ChatAdmins).filter(ChatAdmins.chat_id == chat))).fetchall()
            elif chat is None:
                return (await conn.execute(select(ChatAdmins).filter(ChatAdmins.bot_id == bot))).fetchall()
            else:
                return (await conn.execute(
                    select(ChatAdmins)
                    .filter(and_(
                        ChatAdmins.chat_id == chat,
                        ChatAdmins.bot_id == bot
                    ))
                )).fetchall()

    @staticmethod
    async def add_chat_admins(data: dict):
        async with db_helper.engine.connect() as conn:
            await conn.execute(insert(ChatAdmins).values(data))
            await conn.commit()

    @staticmethod
    async def delete_chat_admins(data: dict):
        async with db_helper.engine.connect() as conn:
            await conn.execute(
                delete(ChatAdmins)
                .filter(and_(
                    ChatAdmins.chat_id == data["chat_id"],
                    ChatAdmins.bot_id == data["bot_id"],
                ))
            )
            await conn.commit()


class CrudServiceMessage:
    @staticmethod
    async def get_service_message(bot_id: int):
        async with db_helper.engine.connect() as conn:
            return (await conn.execute(select(ServiceMessage).filter(ServiceMessage.bot_id == bot_id))).fetchall()

    @staticmethod
    async def add_service_message(data: dict):
        async with db_helper.engine.connect() as conn:
            await conn.execute(insert(ServiceMessage).values(data))
            await conn.commit()

    @staticmethod
    async def update_service_message(bot_id: int, hello_message: str, ban_user_message: str, send_post_message: str):
        async with db_helper.engine.connect() as conn:
            await conn.execute(
                update(ServiceMessage)
                .filter(ServiceMessage.bot_id == bot_id)
                .values(
                    hello_message=hello_message,
                    ban_user_message=ban_user_message,
                    send_post_message=send_post_message
                )
            )
            await conn.commit()


class CrudPublicPosts:
    @staticmethod
    async def get_public_posts():
        async with db_helper.engine.connect() as conn:
            return (await conn.execute(select(PublicPosts))).fetchall()

    @staticmethod
    async def add_public_posts(data: dict):
        async with db_helper.engine.connect() as conn:
            await conn.execute(insert(PublicPosts).values(data))
            await conn.commit()


if __name__ == '__main__':
    drop_table()
    create_table()
