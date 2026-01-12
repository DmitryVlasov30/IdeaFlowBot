from config import settings
from src.core_database.database import CrudBotsData
from src.worker import SubBot
from src.utils import filter_admin

from telebot import TeleBot
from requests import get
from threading import Thread


class MasterBot:
    def __init__(self, api_token_bot):
        self.bot_info = None

        self.bots_database = CrudBotsData()

        self.api_token_bot = api_token_bot
        self.main_bot = TeleBot(self.api_token_bot)
        self.bots_thread = []
        self.__setup_handlers()

    def __setup_handlers(self):
        @self.main_bot.message_handler(commands=["bots"])
        @filter_admin
        def get_all_subbot(message):
            all_info = self.bots_database.get_bots_info()
            answer = "боты:\n"
            for api_token, bot_username, channel_id, id_row in all_info:
                response = get(f"https://api.telegram.org/bot{api_token}/getMe").json()
                if response["ok"]:
                    username = response["result"]["username"]
                else:
                    username = "username не удалось получить"
                username_channel = self.main_bot.get_chat(channel_id).username
                answer += (f"channel: `{username_channel}`\n"
                           f"bot: `{username}`\n\n")
            answer += "\n"
            self.main_bot.send_message(message.chat.id, answer, parse_mode="Markdown")

        @self.main_bot.message_handler(commands=["add"])
        @filter_admin
        def add_bot(message):
            command, api_token, channel_username = message.text.split(" ")
            if "https" in channel_username:
                channel_username = "@" + channel_username.split("/")[-1]
            if "@" not in channel_username:
                channel_username = "@" + channel_username

            try:
                channel_id = self.main_bot.get_chat(channel_username).id
            except Exception as e:
                self.main_bot.send_message(message.chat.id, "канал не найден")
                return
            bot = SubBot(
                api_token_bot=api_token,
                channel_username=channel_username,
                hello_msg=settings.hello_msg,
                ban_usr_msg=settings.ban_msg
            )
            th_bot = Thread(target=bot.run_bot, daemon=True, name=f"{bot.bot_info.username}-bot")
            th_bot.start()
            self.bots_thread.append(th_bot)
            self.bots_database.add_bots_info({
                "channel_id": channel_id,
                "bot_username": bot.bot_info.username,
                "bot_api_token": api_token,
            })
            self.main_bot.send_message(
                message.chat.id,
                "бот добавлен"
            )

        @self.main_bot.message_handler(commands=["remove"])
        @filter_admin
        def remove_bot(message):
            command, username_bot, channel_username = message.text.split(" ")
            try:
                channel_id = self.main_bot.get_chat(channel_username).id
            except Exception as e:
                self.main_bot.send_message(message.chat.id, "канала не существует")
                return
            self.bots_database.delete_bots_info({"bot_username": username_bot, "channel": channel_id})
            index_bot = -1
            for idx in range(len(self.bots_thread)):
                if self.bots_thread[idx].name == f"{username_bot}-bot":
                    index_bot = idx
                    self.bots_thread[idx].stop()

            if index_bot == -1:
                return
            else:
                del self.bots_thread[index_bot]

    def run_bot(self):
        self.bot_info = self.main_bot.get_me()
        bots_lst = self.bots_database.get_bots_info()
        try:
            print(f"main bot @{self.bot_info.username} working")
            for api_token, bot_username, channel_id, id_row in bots_lst:
                channel_username = "@" + self.main_bot.get_chat(channel_id).username
                bot = SubBot(
                    api_token_bot=api_token,
                    channel_username=channel_username,
                    hello_msg=settings.hello_msg,
                    ban_usr_msg=settings.ban_msg,
                )
                th_bot = Thread(target=bot.run_bot, daemon=True, name=f"{bot.bot_info.username}-bot")
                th_bot.start()
                self.bots_thread.append(th_bot)
            self.main_bot.infinity_polling(timeout=10, long_polling_timeout=150)
        except Exception as ex:
            print(f"[ERROR] bot: @{self.bot_info.username}, mistake: {ex}")
