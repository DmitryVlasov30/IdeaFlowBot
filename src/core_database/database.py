import asyncio

from sqlalchemy import insert, select, and_, delete, update, Delete

from src.core_database.models.base import Base
from src.core_database.models.banned_user import BannedUser
from src.core_database.models.bots_data import BotsData
from src.core_database.models.chat_admins import ChatAdmins
from src.core_database.models.service_message import ServiceMessage
from src.core_database.models.users import UserData
from src.core_database.models.delayed_posts import DelayedPost
from src.core_database.models.anonym_message import AnonymMessage
from src.core_database.models.db_helper import db_helper
from src.core_database.models.advertising import Advertising
from src.core_database.models.sender_info import SenderData
from src.core_database.models.admin_actions import AdminActionData


async def create_table():
    async with db_helper.engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def drop_table():
    async with db_helper.engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


class CrudUserData:
    @staticmethod
    async def get_user_data(user_id: int = None, bot_username: str = None) -> list:
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
    async def insert_user(data: dict) -> None:
        async with db_helper.engine.connect() as conn:
            stmt = (
                insert(UserData).values(data)
            )
            await conn.execute(stmt)
            await conn.commit()

    @staticmethod
    async def delete_user_data(user_id: int, bot_username: str) -> None:
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
    async def get_banned_users(id_user: int = None, id_channel: int = None) -> list:
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
    async def add_banned_user(user: dict) -> None:
        async with db_helper.engine.connect() as conn:
            stmt = (
                insert(BannedUser).values(user)
            )
            await conn.execute(stmt)
            await conn.commit()

    @staticmethod
    async def delete_banned_user(user: dict) -> None:
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
    async def get_bots_info() -> list:
        async with db_helper.engine.connect() as conn:
            return (await conn.execute(select(BotsData))).fetchall()

    @staticmethod
    async def add_bots_info(data: dict) -> None:
        async with db_helper.engine.connect() as conn:
            await conn.execute(insert(BotsData).values(data))
            await conn.commit()

    @staticmethod
    async def delete_bots_info(data: dict) -> None:
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
    async def get_chat_admins(bot: int = None, chat: int = None) -> list | int:
        async with db_helper.engine.connect() as conn:
            if bot is not None and chat is None:
                result = (await conn.execute(select(ChatAdmins).filter(ChatAdmins.bot_id == bot))).fetchall()
                return result[0][1] if result else None
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
    async def add_chat_admins(data: dict) -> None:
        async with db_helper.engine.connect() as conn:
            await conn.execute(insert(ChatAdmins).values(data))
            await conn.commit()

    @staticmethod
    async def delete_chat_admins(data: dict) -> None:
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
    async def get_service_message(bot_id: int) -> list:
        async with db_helper.engine.connect() as conn:
            return (await conn.execute(select(ServiceMessage).filter(ServiceMessage.bot_id == bot_id))).fetchall()

    @staticmethod
    async def add_service_message(data: dict) -> None:
        async with db_helper.engine.connect() as conn:
            await conn.execute(insert(ServiceMessage).values(data))
            await conn.commit()

    @staticmethod
    async def update_service_message(
            bot_id: int,
            hello_message: str,
            ban_user_message: str,
            send_post_message: str
    ) -> None:
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


class CrudDelayedPosts:
    @staticmethod
    async def get_delayed_posts(bot_id=None) -> list:
        async with db_helper.engine.connect() as conn:
            if bot_id is None:
                return (await conn.execute(select(DelayedPost))).fetchall()
            else:
                return (await conn.execute(select(DelayedPost).filter(DelayedPost.bot_id == bot_id))).fetchall()

    @staticmethod
    async def add_delayed_posts(data: dict) -> None:
        async with db_helper.engine.connect() as conn:
            await conn.execute(insert(DelayedPost).values(data))
            await conn.commit()

    @staticmethod
    async def setter_post(bot_id: int, new_time_seconds: int, message_id: int) -> None:
        async with db_helper.engine.connect() as conn:
            await conn.execute(
                update(DelayedPost)
                .filter(and_(DelayedPost.bot_id == bot_id, DelayedPost.message_id == message_id))
                .values(
                    time_seconds=new_time_seconds,
                )
            )
            await conn.commit()

    @staticmethod
    async def delete_delayed_posts(data: dict) -> None:
        async with db_helper.engine.connect() as conn:
            await conn.execute(
                delete(DelayedPost)
                .filter(and_(DelayedPost.bot_id == data['bot_id'], DelayedPost.message_id == data['message_id']))
            )
            await conn.commit()


class CrudAnonymMessage:
    @staticmethod
    async def get_posts(chat_id=None, message_id=None) -> list | tuple:
        async with (db_helper.engine.connect() as conn):
            if chat_id is None and message_id is None:
                return (await conn.execute(select(AnonymMessage))).fetchall()
            if chat_id is None:
                return (await conn.execute(
                    select(AnonymMessage).filter(AnonymMessage.message_id == message_id)
                )).fetchall()
            if message_id is None:
                return (await conn.execute(
                    select(AnonymMessage).filter(AnonymMessage.chat_id == chat_id)
                ))
            else:
                return (await conn.execute(
                    select(AnonymMessage)
                    .filter(and_(AnonymMessage.message_id == message_id, AnonymMessage.chat_id == chat_id))
                )).fetchall()[0]

    @staticmethod
    async def delete_posts(data: dict) -> None:
        async with db_helper.engine.connect() as conn:
            await conn.execute(
                Delete(AnonymMessage)
                .filter(and_(
                    data["message_id"] == AnonymMessage.message_id,
                    data["chat_id"] == AnonymMessage.chat_id,
                ))
            )
            await conn.commit()

    @staticmethod
    async def add_posts(data: dict) -> None:
        async with db_helper.engine.connect() as conn:
            await conn.execute(insert(AnonymMessage).values(data))
            await conn.commit()

    @staticmethod
    async def check_item(message_id, chat_id) -> bool:
        async with db_helper.engine.connect() as conn:
            items = await conn.execute(
                select(AnonymMessage)
                .filter(and_(AnonymMessage.message_id == message_id, AnonymMessage.chat_id == chat_id))
            )
            return bool(items.fetchall())


class CrudAdvertising:
    @staticmethod
    async def get_advertising(channel_id=None, post_id=None) -> list | tuple:
        async with db_helper.engine.connect() as conn:
            if channel_id is None and post_id is None:
                return (await conn.execute(select(Advertising))).fetchall()
            if channel_id is None:
                return (await conn.execute(
                    select(Advertising).filter(Advertising.post_id == post_id)
                )).fetchall()
            if post_id is None:
                return (await conn.execute(
                    select(Advertising).filter(Advertising.channel_id == channel_id)
                )).fetchall()
            else:
                return (await conn.execute(
                    select(Advertising)
                    .filter(and_(Advertising.post_id == post_id, Advertising.channel_id == channel_id))
                )).fetchall()

    @staticmethod
    async def add_advertising(channel_id: int, post_id: int, time: int) -> None:
        async with db_helper.engine.connect() as conn:
            await conn.execute(insert(Advertising).values(
                post_id=post_id,
                channel_id=channel_id,
                time=time,
            ))
            await conn.commit()

    @staticmethod
    async def delete_advertising(channel_id: int, post_id: int) -> None:
        async with db_helper.engine.connect() as conn:
            await conn.execute(
                delete(Advertising)
                .filter(and_(Advertising.post_id == post_id, Advertising.channel_id == channel_id))
            )
            await conn.commit()


class CrudPostData:
    def __init__(self, table):
        self.table = table

    async def get_public_posts(self) -> list:
        async with db_helper.engine.connect() as conn:
            return (await conn.execute(select(self.table))).fetchall()

    async def add_public_posts(self, data: dict) -> None:
        async with db_helper.engine.connect() as conn:
            await conn.execute(insert(self.table).values(data))
            await conn.commit()


async def main():
    db = CrudAdvertising()
    await db.delete_advertising(
        channel_id=-1003091383282,
        post_id=373,
    )

if __name__ == '__main__':
    asyncio.run(create_table())
