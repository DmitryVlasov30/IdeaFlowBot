import asyncio
from threading import Timer

from sqlalchemy.exc import IntegrityError
from telebot.async_telebot import AsyncTeleBot
from telebot.asyncio_helper import ApiTelegramException
from telebot.types import (Message, InlineKeyboardMarkup,
                           InlineKeyboardButton, CallbackQuery,
                           ChatMemberUpdated, BotCommand, BotCommandScopeAllGroupChats)

from src.core_database.database import CrudChatAdmins, CrudBannedUser, CrudServiceMessage, CrudPublicPosts, CrudUserData
from src.utils import Utils, filter_chats
from config import settings


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

        self.token = api_token_bot
        self.channel_username = channel_username
        self.sup_bot = AsyncTeleBot(self.token)
        self.users_data = set()
        asyncio.create_task(self.__setup_bot_info())

        self.chat_suggests = None
        if self.chat_suggests:
            self.chat_suggest = self.chat_suggests[0][-2]
        else:
            self.chat_suggest = None

    @classmethod
    async def create(cls,
                     api_token_bot: str,
                     channel_username: str,
                     hello_msg: str,
                     ban_usr_msg: str,
                     send_post_msg: str
                     ):
        self = cls(api_token_bot, channel_username, hello_msg, ban_usr_msg, send_post_msg)
        await self.__setup_bot_info()
        await self.__setup_service_msg()
        await self.__setup_handlers()

        return self

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
        self.chat_suggest = (await self.admins_database.get_chat_admins(bot=self.bot_info.id))[0][1]
        # print(self.chat_suggest)
        users = await self.user_database.get_user_data(bot_username=self.bot_info.username)
        self.users_data = set(user_id for user_id, bot_username, id_el in users)

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

        @self.sup_bot.message_handler(commands=['start'])
        async def start(message: Message, is_command=True):
            if message.chat.id < 0:
                return
            await __check_exist_user(message)
            message_text = self.hello_msg
            if not is_command:
                message_text += f"Подпишитесь на канал: {self.channel_username}"

            markup = InlineKeyboardMarkup()
            btn_subscribe = InlineKeyboardButton(
                text=f"подпишитесь на канал -> {self.channel_username}",
                url=f"https://t.me/{self.channel_username[1:]}",
            )
            markup.add(btn_subscribe)
            info_subscribe = await self.sup_bot.get_chat_member(user_id=message.chat.id, chat_id=self.channel_id)
            if info_subscribe.status != "left":
                markup = None
                if not is_command:
                    message_text = self.send_post_msg

            await self.sup_bot.send_message(message.chat.id, message_text, reply_markup=markup)

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
                chats = self.admins_database.get_chat_admins(bot=self.bot_info.id, chat=chat_member_info.chat.id)
                if chats:
                    await self.admins_database.delete_chat_admins({
                        "bot_id": self.bot_info.id,
                        "chat_id": chat_member_info.chat.id,
                    })
                self.chat_suggest = None

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

        @self.sup_bot.message_handler(content_types=["text", "photo", "video", "animation"])
        async def get_suggest(message: Message):
            if message.chat.id < 0:
                return
            await __check_exist_user(message)
            info_subscribe = await self.sup_bot.get_chat_member(user_id=message.chat.id, chat_id=self.channel_id)
            await start(message, is_command=False)
            print(1)
            if info_subscribe.status == "left":
                return

            if message.chat.id == self.chat_suggest or message.chat.id < 0:
                return

            if await Utils.check_banned_user(message.chat.id, self.channel_id):
                await answer_for_ban_user(message)
                return

            markup = InlineKeyboardMarkup(row_width=2)

            banned_user = InlineKeyboardButton(
                text="👮‍♂️бан",
                callback_data=f"banned_user;{message.chat.id};0"
            )
            addition_info = InlineKeyboardButton(
                text=f"@{message.chat.username}",
                callback_data=f"add_info;{message.chat.id};0"
            )
            send_button = InlineKeyboardButton(
                text="✅Одобрить",
                callback_data=f"send_suggest;{message.chat.id};0"
            )
            reject_button = InlineKeyboardButton(
                text="❌Отклонить",
                callback_data=f"reject;{message.chat.id};0"
            )

            delayed_button = InlineKeyboardButton(
                text="Не откладывать",
                callback_data=f"delayed_button;{message.chat.id};0"
            )

            markup.add(banned_user, addition_info)
            markup.add(send_button, reject_button)
            markup.add(delayed_button)

            if self.chat_suggest is None:
                await self.sup_bot.send_message(
                    chat_id=settings.general_admin,
                    text="Бот предлога не добавлен в чат"
                )
                return

            if self.bot_info.username == "spletni_love_bot":
                if message.content_type == "text":
                    await self.sup_bot.send_message(
                        chat_id=self.chat_suggest,
                        text=message.text + "\n💌",
                        reply_markup=markup
                    )
                elif message.content_type == "photo":
                    if message.caption is None:
                        await self.sup_bot.send_photo(
                            chat_id=self.chat_suggest,
                            caption="💌",
                            photo=message.photo,
                            reply_markup=markup
                        )
                    else:
                        await self.sup_bot.send_photo(
                            chat_id=self.chat_suggest,
                            caption=message.caption + "\n💌",
                            photo=message.photo,
                            reply_markup=markup
                        )
                elif message.content_type == "video":
                    if message.caption is None:
                        await self.sup_bot.send_video(
                            chat_id=self.chat_suggest,
                            caption="💌",
                            video=message.video,
                            reply_markup=markup
                        )
                    else:
                        await self.sup_bot.send_video(
                            chat_id=self.chat_suggest,
                            caption=message.caption + "\n💌",
                            video=message.video,
                            reply_markup=markup
                        )
                else:
                    await self.sup_bot.copy_message(
                        chat_id=self.chat_suggest,
                        from_chat_id=message.chat.id,
                        message_id=message.message_id,
                        reply_markup=markup,
                    )
                return
            print(self.chat_suggest)
            await self.sup_bot.copy_message(
                chat_id=self.chat_suggest,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
                reply_markup=markup,
            )

        async def add_info(call: CallbackQuery):
            info = await self.sup_bot.get_chat(call.data.split(";")[1])
            msg = "информация: \n" + f"id: `{info.id}`\n" + f"username @{info.username}\n" + f"name: `{info.first_name}`"
            if info.last_name is not None:
                msg += f" last_name: `{info.last_name}`"
            await self.sup_bot.send_message(
                chat_id=call.message.chat.id,
                text=msg,
                parse_mode="Markdown",
            )

        async def __send_suggest(call: CallbackQuery):
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

        async def send_suggest(call: CallbackQuery):
            command, chat_id, time = call.data.split(";")
            if int(time) == 0:
                await __send_suggest(call)
                return

            seconds_time = self.delayed_messages_minutes[int(time)]
            time = int(time)
            if time <= 3:
                text_btn = f"Отложено на {seconds_time} минут"
                seconds_time *= 60
            else:
                if seconds_time == 1:
                    text_btn = f"Отложено на {seconds_time} час"
                elif 2 <= seconds_time <= 4:
                    text_btn = f"Отложено на {seconds_time} часа"
                else:
                    text_btn = f"Отложено на {seconds_time} часов"
                seconds_time *= 60 * 60

            print(seconds_time)
            markup = InlineKeyboardMarkup()
            btn_info = InlineKeyboardButton(
                text=text_btn,
                callback_data=f"info_delayed;{time}"
            )
            markup.add(btn_info)
            await self.sup_bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=markup,
            )
            timer_th = Timer(
                seconds_time,
                __send_suggest, args=(
                    call,
                )
            )
            timer_th.start()

        async def reject_post(call: CallbackQuery):
            message_id = call.message.message_id
            await self.sup_bot.delete_message(
                chat_id=call.message.chat.id,
                message_id=message_id,
            )

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

        async def delayed_post(call: CallbackQuery):
            command, message_chat_id, time = call.data.split(";")
            next_time = (int(time) + 1) % len(self.delayed_messages_minutes)
            user_info = await self.sup_bot.get_chat(message_chat_id)
            message_btn = "Не откладывать"
            info = self.delayed_messages_minutes[next_time]
            if 0 < next_time <= 2:
                message_btn = f"Отложить на {info} минут"
            elif next_time != 0:
                if next_time == 3:
                    message_btn = f"Отложить на {info} час"
                elif 1 < next_time <= 6:
                    message_btn = f"Отложить на {info} часа"
                else:
                    message_btn = f"Отложить на {info} часов"

            markup = InlineKeyboardMarkup()

            banned_user = InlineKeyboardButton(
                text="👮‍♂️бан",
                callback_data=f"banned_user;{message_chat_id};{next_time}"
            )
            addition_info = InlineKeyboardButton(
                text=f"@{user_info.username}",
                callback_data=f"add_info;{message_chat_id};{next_time}"
            )
            send_button = InlineKeyboardButton(
                text="✅Одобрить",
                callback_data=f"send_suggest;{message_chat_id};{next_time}"
            )
            reject_button = InlineKeyboardButton(
                text="❌Отклонить",
                callback_data=f"reject;{message_chat_id};{next_time}"
            )

            delayed_button = InlineKeyboardButton(
                text=message_btn,
                callback_data=f"delayed_button;{message_chat_id};{next_time}"
            )

            markup.add(banned_user, addition_info)
            markup.add(send_button, reject_button)
            markup.add(delayed_button)

            await self.sup_bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=markup,
            )

        @self.sup_bot.callback_query_handler(func=lambda call: True)
        async def callback(call: CallbackQuery):
            match call.data.split(";")[0]:
                case "banned_user":
                    await add_ban_user(call)
                case "add_info":
                    await add_info(call)
                case "send_suggest":
                    await send_suggest(call)
                case "reject":
                    await reject_post(call)
                case "delayed_button":
                    await delayed_post(call)

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

    async def run_bot(self):
        self.bot_info = await self.sup_bot.get_me()
        try:
            print(f"[OK] bot @{self.bot_info.username} working")
            self.polling_task = asyncio.create_task(self.sup_bot.infinity_polling(timeout=10))
        except Exception as ex:
            print(f"[ERROR] bot: @{self.bot_info.username}, mistake: {ex}")
