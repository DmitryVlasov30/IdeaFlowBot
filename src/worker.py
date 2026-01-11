from pprint import pprint

from telebot import TeleBot
from telebot.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ChatMemberUpdated


class SubBot:
    def __init__(self, api_token_bot: str, channel_username: str, hello_msg: str):
        self.bot_info = None
        self.chat_suggest = None
        self.chat_member = None

        self.token = api_token_bot
        self.channel_username = channel_username
        self.hello_msg = hello_msg
        self.sup_bot = TeleBot(self.token)
        self.__setup_handlers()

    def __setup_handlers(self):
        @self.sup_bot.message_handler(commands=['start'])
        def start(message: Message):
            self.sup_bot.send_message(message.chat.id, self.hello_msg)

        @self.sup_bot.my_chat_member_handler()
        def add_chat_member(chat_member_info: ChatMemberUpdated):
            print(chat_member_info.chat.id, chat_member_info.new_chat_member, chat_member_info.old_chat_member)
            if chat_member_info.new_chat_member.status == "administrator":
                self.chat_suggest = chat_member_info.chat.id
            elif chat_member_info.new_chat_member.status == "member":
                self.chat_member = chat_member_info.chat.id
            else:
                self.chat_member = None
                self.chat_suggest = None

        @self.sup_bot.message_handler(content_types=["text", "photo", "video"])
        def get_suggest(message: Message):
            if message.chat.id == self.chat_suggest or message.chat.id == self.chat_member:
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

            if self.chat_member is None:
                print(2)
                return

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
            pass

        def reject_post(call: CallbackQuery):
            info_sender = call.data.split(";")[1]
            message_id = call.message.message_id
            self.sup_bot.delete_message(
                chat_id=call.message.chat.id,
                message_id=message_id,
            )

        @self.sup_bot.callback_query_handler(func=lambda call: True)
        def callback(call: CallbackQuery):
            match call.data.split(";")[0]:
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
