import asyncio

import aiohttp
from aiohttp import TCPConnector
from loguru import logger

from sqlalchemy.exc import IntegrityError
from telebot.async_telebot import AsyncTeleBot
from telebot import asyncio_helper
from telebot.asyncio_helper import ApiTelegramException
from telebot.types import (Message, InlineKeyboardMarkup,
                           InlineKeyboardButton, CallbackQuery,
                           ChatMemberUpdated, BotCommand, BotCommandScopeAllGroupChats)

from src.core_database.database import (CrudChatAdmins, CrudBannedUser,
                                        CrudServiceMessage, CrudPublicPosts, CrudUserData, CrudDelayedPosts)
from src.utils import Utils, filter_chats
from config import settings
from src.markups import MarkupButton
from datetime import datetime, timedelta, timezone


class SubBot:
    def __init__(self, api_token_bot: str, channel_username: str, hello_msg: str, ban_usr_msg: str, send_post_msg: str):
        self.polling_task = None
        self.bot_info = None

        self.delayed_messages_minutes = [0, 15, 30, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

        self.hello_msg = hello_msg
        self.ban_usr_msg = ban_usr_msg
        self.send_post_msg = send_post_msg

        self.commands = [
            BotCommand("ban_lst", "список забаненных пользователей"),
            BotCommand("unban", "разблокировка пользователя после команды нужно указать id"),
            BotCommand("update_hello", "изменение приветственного сообщения,"
                                       " после команды нужно текстом указать приветствие"),
            BotCommand("update_ban_user", "изменение сообщения при бане,"
                                          " после команды нужно текстом указать приветствие"),
            BotCommand("update_send_post", "изменение сообщения при отправке поста пользователем"),
            BotCommand("get_msg", "возвращает сервисные сообщения")
        ]

        self.admins_database = CrudChatAdmins()
        self.ban_database = CrudBannedUser()
        self.service_msg_database = CrudServiceMessage()
        self.public_posts = CrudPublicPosts()
        self.user_database = CrudUserData()
        self.delayed_database = CrudDelayedPosts()

        self.token = api_token_bot
        self.channel_username = channel_username
        asyncio_helper.proxy = settings.proxies["http"]
        asyncio_helper.REQUEST_LIMIT = 100
        self.sup_bot = AsyncTeleBot(self.token)
        self.users_data = set()

        self.delayed_message = {}

        self.chat_suggests = None

    @classmethod
    @logger.catch
    async def create(cls,
                     api_token_bot: str,
                     channel_username: str,
                     hello_msg: str,
                     ban_usr_msg: str,
                     send_post_msg: str
                     ):
        self = cls(api_token_bot, channel_username, hello_msg, ban_usr_msg, send_post_msg)
        logger.info("init")
        await self.__setup_bot_info()
        logger.info("setup bot info")
        await self.__setup_service_msg()
        logger.info("setup service msg")
        await self.__setup_handlers()
        logger.info("setup handlers")

        logger.info("create")
        return self

    @logger.catch
    async def __setup_bot_info(self):
        await self.sup_bot.set_my_commands(
            commands=self.commands,
            scope=BotCommandScopeAllGroupChats(),
        )
        await self.sup_bot.set_my_commands(
            commands=self.commands,
            scope=BotCommandScopeAllGroupChats(),
        )
        self.bot_info = await self.sup_bot.get_me()
        self.channel_id = (await self.sup_bot.get_chat(self.channel_username)).id
        self.chat_suggest = (await self.admins_database.get_chat_admins(bot=self.bot_info.id))
        logger.info(f"{self.chat_suggest}")
        users = await self.user_database.get_user_data(bot_username=self.bot_info.username)
        self.users_data = set(user_id for user_id, bot_username, id_el in users)
        delayed_message = await self.delayed_database.get_delayed_posts(bot_id=self.bot_info.id)
        self.delayed_message = {}
        for bot_id, time_seconds, message_id, sender_id, id_item in delayed_message:
            self.delayed_message[message_id] = (time_seconds, sender_id)

    @logger.catch
    async def __setup_service_msg(self):
        message_info = await self.service_msg_database.get_service_message(self.bot_info.id)
        if message_info:
            self.hello_msg = message_info[0][1]
            self.ban_usr_msg = message_info[0][2]
            self.send_post_msg = message_info[0][3]
        else:
            await self.service_msg_database.add_service_message({
                "bot_id": self.bot_info.id,
                "hello_message": self.hello_msg,
                "ban_user_message": self.ban_usr_msg,
                "send_post_message": self.send_post_msg,
            })

    @logger.catch
    async def __setup_handlers(self):
        async def answer_for_ban_user(message: Message):
            await self.sup_bot.send_message(chat_id=message.chat.id, text=self.ban_usr_msg)

        async def save_post(call: CallbackQuery):
            if call.message.content_type == "text":
                await self.public_posts.add_public_posts({
                    "channel_id": self.channel_id,
                    "posts_title": call.message.text,
                })

        async def __check_exist_user(message: Message):
            try:
                if message.chat.id not in self.users_data:
                    await self.user_database.insert_user(
                        {
                            "user_id": message.chat.id,
                            "bot_username": self.bot_info.username
                        }
                    )
                    self.users_data.add(message.chat.id)
            except IntegrityError:
                pass

        @logger.catch
        @self.sup_bot.message_handler(commands=['start'])
        async def start(message: Message, is_command=True):
            if message.chat.id < 0:
                return
            await __check_exist_user(message)
            message_text = self.hello_msg
            if not is_command:
                message_text = f"Чтобы продолжить, подпишитесь на канал: {self.channel_username}"

            markup = InlineKeyboardMarkup()
            btn_subscribe = InlineKeyboardButton(
                text=f"подпишитесь на канал -> {self.channel_username}",
                url=f"https://t.me/{self.channel_username[1:]}",
            )
            markup.add(btn_subscribe)
            logger.info("start")
            info_subscribe = await self.sup_bot.get_chat_member(user_id=message.chat.id, chat_id=self.channel_id)
            if info_subscribe.status != "left":
                markup = None
                if not is_command:
                    message_text = self.send_post_msg

            await self.sup_bot.send_message(message.chat.id, message_text, reply_markup=markup)

        @logger.catch
        @self.sup_bot.message_handler(commands=["ban_lst"])
        @filter_chats
        async def ban_lst(message: Message):
            all_info = await self.ban_database.get_banned_users()
            answer = "Забаненные пользователи:\n"
            for id_user, id_channel, bot_id, id_db in all_info:
                if bot_id == self.bot_info.id:
                    user_info = await self.sup_bot.get_chat(id_user)
                    answer += f"`{user_info.id}` `{user_info.username}`\n"
            await self.sup_bot.send_message(chat_id=message.chat.id, text=answer, parse_mode='Markdown')

        @logger.catch
        @self.sup_bot.message_handler(commands=["unban"])
        @filter_chats
        async def unban_user(message: Message):
            user_id = message.text.split()[1]
            all_ban_user = await self.ban_database.get_banned_users(id_user=int(user_id), id_channel=self.channel_id)
            if all_ban_user:
                await self.ban_database.delete_banned_user({"id_user": user_id, "id_channel": self.channel_id})
                await self.sup_bot.send_message(message.chat.id, "пользователь разбанен")
            else:
                await self.sup_bot.send_message(message.chat.id, "пользователь не забанен")

        @logger.catch
        @self.sup_bot.message_handler(commands=["update_hello"])
        @filter_chats
        async def update_hello(message: Message):
            hello_msg = message.text[13:]
            self.hello_msg = hello_msg
            await self.service_msg_database.update_service_message(**{
                "bot_id": self.bot_info.id,
                "hello_message": hello_msg.strip(),
                "ban_user_message": self.ban_usr_msg.strip(),
                "send_post_message": self.send_post_msg.strip(),
            })
            await self.sup_bot.send_message(message.chat.id, "👍")

        @logger.catch
        @self.sup_bot.message_handler(commands=["update_ban_user"])
        @filter_chats
        async def update_ban_user(message: Message):
            ban_usr_msg = message.text[16:]
            self.ban_usr_msg = ban_usr_msg
            await self.service_msg_database.update_service_message(**{
                "bot_id": self.bot_info.id,
                "hello_message": self.hello_msg.strip(),
                "ban_user_message": self.ban_usr_msg.strip(),
                "send_post_message": self.send_post_msg.strip(),
            })
            await self.sup_bot.send_message(message.chat.id, "👍")

        @logger.catch
        @self.sup_bot.message_handler(commands=["update_send_post"])
        async def update_send_post(message: Message):
            msg_send = message.text[17:]
            self.send_post_msg = msg_send
            await self.service_msg_database.update_service_message(**{
                "bot_id": self.bot_info.id,
                "hello_message": self.hello_msg.strip(),
                "ban_user_message": self.ban_usr_msg.strip(),
                "send_post_message": msg_send.strip(),
            })
            await self.sup_bot.send_message(message.chat.id, "👍")

        @logger.catch
        @self.sup_bot.message_handler(commands=["get_msg"])
        @filter_chats
        async def get_msg(message: Message):
            answer = (f"*Приветствие*:\n\n"
                      f"{self.hello_msg}\n\n"
                      f"*Сообщение при бане*\n\n"
                      f"{self.ban_usr_msg}\n\n"
                      f"*Сообщение при отправке сообщения*\n\n"
                      f"{self.send_post_msg}\n\n")
            await self.sup_bot.send_message(message.chat.id, answer, parse_mode="Markdown")

        @logger.catch
        @self.sup_bot.my_chat_member_handler()
        async def add_chat_member(chat_member_info: ChatMemberUpdated):
            if chat_member_info.chat.type == "channel":
                return

            info_chat = await self.sup_bot.get_chat_member(chat_member_info.chat.id, settings.general_admin)
            # print(info_chat)
            if info_chat.status not in ("administrator", "creator"):
                await self.sup_bot.leave_chat(chat_member_info.chat.id)
                return
            # print(chat_member_info)
            if chat_member_info.chat.id > 0 and chat_member_info.new_chat_member.status == "kicked":
                try:
                    await self.user_database.delete_user_data(
                        user_id=chat_member_info.chat.id,
                        bot_username=self.bot_info.username
                    )
                except:
                    return
            if chat_member_info.new_chat_member.status == "administrator":
                await self.admins_database.add_chat_admins({
                    "bot_id": self.bot_info.id,
                    "chat_id": chat_member_info.chat.id,
                })
                self.chat_suggest = chat_member_info.chat.id
            else:
                chats = await self.admins_database.get_chat_admins(bot=self.bot_info.id, chat=chat_member_info.chat.id)
                if chats:
                    await self.admins_database.delete_chat_admins({
                        "bot_id": self.bot_info.id,
                        "chat_id": chat_member_info.chat.id,
                    })
                self.chat_suggest = None

        @logger.catch
        @self.sup_bot.message_handler(
            func=lambda message: message.reply_to_message is not None
        )
        async def reply_to_message(message: Message):
            info = message.json
            if not info["reply_to_message"]["from"]["is_bot"]:
                return
            info_sender = message.json["reply_to_message"]["reply_markup"]["inline_keyboard"][0][0]["callback_data"]
            print(info_sender)
            user_id = int(info_sender.split(";")[1])
            await self.sup_bot.send_message(
                chat_id=user_id,
                text=message.text
            )

        @logger.catch
        @self.sup_bot.message_handler(content_types=["text", "photo", "video", "animation"])
        async def get_suggest(message: Message):
            print(self.chat_suggest)
            if message.chat.id < 0:
                return
            await __check_exist_user(message)
            info_subscribe = await self.sup_bot.get_chat_member(user_id=message.chat.id, chat_id=self.channel_id)
            await start(message, is_command=False)
            logger.info("123")
            if info_subscribe.status == "left":
                return

            if message.chat.id == self.chat_suggest or message.chat.id < 0:
                return

            if await Utils.check_banned_user(message.chat.id, self.channel_id):
                await answer_for_ban_user(message)
                return

            if self.chat_suggest is None:
                await self.sup_bot.send_message(
                    chat_id=settings.general_admin,
                    text="Бот предлога не добавлен в чат"
                )
                return

            await MarkupButton(self.sup_bot).main_menu(message, self.chat_suggest)

        @logger.catch
        async def send_suggest(call: CallbackQuery):
            try:
                await save_post(call)
                user_info = await self.sup_bot.get_chat(call.data.split(";")[1])
                markup = InlineKeyboardMarkup()
                addition_info = InlineKeyboardButton(
                    text=f"@{user_info.username}",
                    callback_data=f"add_info;{user_info.id}"
                )
                markup.add(addition_info)
                await self.sup_bot.copy_message(
                    chat_id=self.channel_id,
                    from_chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                )
                await self.sup_bot.edit_message_reply_markup(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=markup,
                )
            except Exception as ex:
                await self.sup_bot.send_message(chat_id=call.message.chat.id, text=f"Произошла ошибка при обработки: {ex}")

        @logger.catch
        async def add_ban_user(call: CallbackQuery):
            user_info = await self.sup_bot.get_chat(call.data.split(";")[1])

            markup = InlineKeyboardMarkup()
            addition_info = InlineKeyboardButton(
                text=f"@{user_info.username}",
                callback_data=f"add_info;{user_info.id}"
            )
            markup.add(addition_info)

            await self.ban_database.add_banned_user({
                "id_user": user_info.id,
                "id_channel": self.channel_id,
                "bot_id": self.bot_info.id
            })

            await self.sup_bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=markup,
            )
            await self.sup_bot.send_message(
                text=f"@{user_info.username} забанен",
                chat_id=self.chat_suggest,
            )

        async def get_timestamp_public(time) -> float:
            tz = timezone(timedelta(hours=3))
            hour, minute = map(int, time.split(':'))
            now = datetime.now(tz)
            target = now.replace(hour=hour, minute=minute)
            if now >= target:
                target += timedelta(days=1)

            time_public = target.timestamp()
            return time_public

        @logger.catch
        async def save_delayed_post(call: CallbackQuery):
            command, day_div, time, message_id, sender_id = call.data.split(";")
            time_public = await get_timestamp_public(time)

            message_id = int(message_id)
            print(self.delayed_message)
            print(message_id)
            if message_id in self.delayed_message:
                self.delayed_message[message_id] = (int(time_public), sender_id)
                await self.delayed_database.setter_post(
                    bot_id=self.bot_info.id,
                    message_id=message_id,
                    new_time_seconds=int(time_public),
                )
                return
            await self.delayed_database.add_delayed_posts({
                "bot_id": self.bot_info.id,
                "time_seconds": int(time_public),
                "message_id": message_id,
                "sender_id": sender_id
            })
            self.delayed_message[message_id] = (int(time_public), sender_id)

        @logger.catch
        @self.sup_bot.callback_query_handler(func=lambda call: True)
        async def callback(call: CallbackQuery):
            buttons_func = MarkupButton(self.sup_bot)
            match call.data.split(";")[0]:
                case "banned_user":
                    await add_ban_user(call)
                case "add_info":
                    await buttons_func.add_info(call)
                case "send_suggest":
                    await send_suggest(call)
                case "reject":
                    await buttons_func.reject_post(call)
                case "delayed_button":
                    if "Отложено" in call.message.text:
                        del self.delayed_message[call.message.id]
                        await self.delayed_database.delete_delayed_posts({
                            "bot_id": self.bot_info.id,
                            "message_id": call.message.id,
                        })
                    logger.info("delayed_button")
                    await buttons_func.delayed_post(call)
                case "morning" | "dinner" | "evening" | "night":
                    await buttons_func.delayed_day(call, call.data.split(";")[0], int(call.data.split(";")[-1]))
                case "back_to_main_menu":
                    await buttons_func.main_menu(call.message, self.chat_suggest, is_send=False)
                case "day_choice":
                    await save_delayed_post(call)
                    await buttons_func.delayed_buttons_times(call, int(call.data.split(";")[-1]))
                case "reject_delayed":
                    await self.delayed_database.delete_delayed_posts({
                        "bot_id": self.bot_info.id,
                        "message_id": call.message.id,
                    })
                    del self.delayed_message[call.message.id]
                    await buttons_func.reject_post(call)

    @logger.catch
    async def check_admin(self, channel_id) -> bool:
        try:
            info = await self.sup_bot.get_chat_member(channel_id, self.bot_info.id)
            return True
        except ApiTelegramException:
            return False

    async def stop_bot(self):
        if self.polling_task:
            self.polling_task.cancel()
            try:
                await self.polling_task
            except asyncio.CancelledError:
                print(f"Бот {self.bot_info.username} остановлен")

    async def push_message(self, type_message: str, data: Message):
        users = await self.user_database.get_user_data(bot_username=self.bot_info.username)
        for user in users:
            try:
                if type_message == "text":
                    await self.sup_bot.send_message(
                        text=data.text[5:].strip(),
                        chat_id=user[0]
                    )
            except ApiTelegramException:
                print(data)
                continue
            except Exception as e:
                print(e)

    async def getter_name(self):
        return self.bot_info.username

    async def getter_delayed_info(self) -> dict:
        return self.delayed_message

    async def send_delayed_message(self, message_id, sender_id):
        del self.delayed_message[message_id]
        await self.sup_bot.copy_message(
            from_chat_id=self.chat_suggest,
            chat_id=self.channel_id,
            message_id=message_id,
        )
        await MarkupButton(self.sup_bot).push_post_button(self.chat_suggest, message_id, sender_id)

    async def run_bot(self):
        self.bot_info = await self.sup_bot.get_me()
        try:
            print(f"[OK] bot @{self.bot_info.username} working")
            self.polling_task = asyncio.create_task(self.sup_bot.infinity_polling(timeout=10))
        except Exception as ex:
            print(f"[ERROR] bot: @{self.bot_info.username}, mistake: {ex}")
