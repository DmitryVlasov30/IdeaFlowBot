from telebot import TeleBot
from telebot.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ChatMemberUpdated

from src.core_database.database import CrudChatAdmins, CrudBannedUser


class SubBot:
    def __init__(self, api_token_bot: str, channel_username: str, hello_msg: str):
        self.bot_info = None

        self.admins_database = CrudChatAdmins()
        self.ban_database = CrudBannedUser()

        self.token = api_token_bot
        self.channel_username = channel_username
        self.hello_msg = hello_msg
        self.sup_bot = TeleBot(self.token)
        self.bot_info = self.sup_bot.get_me()

        self.chat_suggests = self.admins_database.get_chat_admins(bot=self.bot_info.id)
        if self.chat_suggests:
            self.chat_suggest = self.chat_suggests[0][-2]
        else:
            self.chat_suggest = None
        self.channel_id = self.sup_bot.get_chat(channel_username).id
        self.__setup_handlers()

    def __setup_handlers(self):
        @self.sup_bot.message_handler(commands=['start'])
        def start(message: Message):
            self.sup_bot.send_message(message.chat.id, self.hello_msg)

        @self.sup_bot.my_chat_member_handler()
        def add_chat_member(chat_member_info: ChatMemberUpdated):
            if chat_member_info.new_chat_member.status == "administrator":
                self.admins_database.add_chat_admins({
                    "bot_id": self.bot_info.id,
                    "chat_id": chat_member_info.chat.id,
                })
                self.chat_suggest = chat_member_info.chat.id
            else:
                chats = self.admins_database.get_chat_admins(bot=self.bot_info.id, chat=chat_member_info.chat.id)
                if chats:
                    self.admins_database.delete_chat_admins({
                        "bot_id": self.bot_info.id,
                        "chat_id": chat_member_info.chat.id,
                    })
                self.chat_suggest = None

        @self.sup_bot.message_handler(content_types=["text", "photo", "video"])
        def get_suggest(message: Message):
            if message.chat.id == self.chat_suggest or message.chat.id < 0:
                return
            markup = InlineKeyboardMarkup(row_width=2)

            banned_user = InlineKeyboardButton(
                text="👮‍♂️бан",
                callback_data=f"banned_user;{message.chat.id}"
            )
            addition_info = InlineKeyboardButton(
                text=f"@{message.chat.username}",
                callback_data=f"add_info;{message.chat.id}"
            )
            send_button = InlineKeyboardButton(
                text="✅Одобрить",
                callback_data=f"send_suggest;{message.chat.id}"
            )
            reject_button = InlineKeyboardButton(
                text="❌Отклонить",
                callback_data=f"reject;{message.chat.id}"
            )

            markup.add(banned_user, addition_info)
            markup.add(send_button, reject_button)

            if self.chat_suggest is None:
                print(1)
                return

            self.sup_bot.copy_message(
                chat_id=self.chat_suggest,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
                reply_markup=markup,
            )

        def add_info(call: CallbackQuery):
            info = self.sup_bot.get_chat(call.data.split(";")[1])
            data_msg = (f"информация: \n"
                        f"id: `{info.id}`\n"
                        f"username: `{info.username}`\n"
                        f"name: `{info.first_name}` `{info.last_name if info.last_name is not None else ''}`\n")
            self.sup_bot.send_message(
                chat_id=call.message.chat.id,
                text=data_msg,
                parse_mode="Markdown",
            )

        def send_suggest(call: CallbackQuery):
            try:
                user_info = self.sup_bot.get_chat(call.data.split(";")[1])
                markup = InlineKeyboardMarkup()
                addition_info = InlineKeyboardButton(
                    text=f"@{user_info.username}",
                    callback_data=f"add_info;{user_info.id}"
                )
                markup.add(addition_info)
                self.sup_bot.copy_message(
                    chat_id=self.channel_id,
                    from_chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                )
                self.sup_bot.edit_message_reply_markup(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    reply_markup=markup,
                )
            except Exception as ex:
                self.sup_bot.send_message(chat_id=call.message.chat.id, text=f"Произошла ошибка при обработки: {ex}")

        def reject_post(call: CallbackQuery):
            message_id = call.message.message_id
            self.sup_bot.delete_message(
                chat_id=call.message.chat.id,
                message_id=message_id,
            )

        def add_ban_user(call: CallbackQuery):
            ...

        @self.sup_bot.callback_query_handler(func=lambda call: True)
        def callback(call: CallbackQuery):
            match call.data.split(";")[0]:
                case "banned_user":
                    add_ban_user(call)
                case "add_info":
                    add_info(call)
                case "send_suggest":
                    send_suggest(call)
                case "reject":
                    reject_post(call)

    def run_bot(self):
        self.bot_info = self.sup_bot.get_me()
        try:
            print(f"[OK] bot @{self.bot_info.username} working")
            self.sup_bot.infinity_polling(timeout=10, long_polling_timeout=150)
        except Exception as ex:
            print(f"[ERROR] bot: @{self.bot_info.username}, mistake: {ex}")

