from requests import HTTPError

from config import settings
from src.core_database.database import CrudBotsData
from src.worker import SubBot
from src.utils import filter_admin

from telebot import TeleBot
from telebot.types import BotCommand, BotCommandScopeChat, Message
import requests
from threading import Thread


class MasterBot:
    def __init__(self, api_token_bot):
        self.bot_info = None

        self.bots_database = CrudBotsData()

        self.commands = [
            BotCommand("bots", "выводит список подчиненных ботов"),
            BotCommand("add", "добавление нового бота, указывай api токен, потом ссылку на канал"),
            BotCommand("remove", "сначала юз бота, потом юз канала")
        ]

        self.api_token_bot = api_token_bot
        self.main_bot = TeleBot(self.api_token_bot)
        self.bots_thread = []
        self.bots_work = []

        chats = settings.moderators
        chats.add(settings.general_admin)

        self.main_bot.set_my_commands(
            commands=self.commands,
            scope=BotCommandScopeChat(*chats),
        )

        self.__setup_handlers()

    def __setup_handlers(self):
        @self.main_bot.message_handler(commands=["bots"])
        @filter_admin
        def get_all_subbot(message: Message):
            all_info = self.bots_database.get_bots_info()
            print(all_info)
            answer = "боты:\n"
            for api_token, bot_username, channel_id, id_row in all_info:
                print(1)
                channel_username = ""
                try:
                    result = requests.get(
                        url=f"https://api.telegram.org/bot{api_token}/getchat",
                        params={"chat_id": channel_id}
                    ).json()
                    if result["ok"]:
                        channel_username = result["result"]["username"]
                    else:
                        raise HTTPError(result)
                except:
                    print(bot_username, channel_id)
                    continue
                answer += (f"channel: @{channel_username}\n"
                           f"bot: @{bot_username}\n\n")
            answer += "\n"
            self.main_bot.send_message(message.chat.id, answer)

        @self.main_bot.message_handler(commands=["add"])
        @filter_admin
        def add_bot(message: Message):
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
                ban_usr_msg=settings.ban_msg,
                send_post_msg=settings.send_post_msg,
            )

            if not bot.check_admin(channel_id):
                self.main_bot.send_message(
                    message.chat.id,
                    text=f"добавьте бота в администраторы канала: {channel_username}"
                )
                return
            for bots in self.bots_database.get_bots_info():
                if bots[1] == bot.bot_info.username.replace("@", ""):
                    self.main_bot.send_message(
                        text="бот уже привязан к чату",
                        chat_id=message.chat.id
                    )
                    return
            self.bots_database.add_bots_info({
                "channel_id": channel_id,
                "bot_username": bot.bot_info.username,
                "bot_api_token": api_token,
            })
            th_bot = Thread(target=bot.run_bot, daemon=True, name=f"{bot.bot_info.username}-bot")
            th_bot.start()
            self.bots_thread.append(th_bot)
            self.bots_work.append(bot)
            self.main_bot.send_message(
                message.chat.id,
                "бот добавлен"
            )

        @self.main_bot.message_handler(commands=["remove"])
        @filter_admin
        def remove_bot(message: Message):
            command, username_bot, channel_username = message.text.split(" ")
            try:
                channel_id = self.main_bot.get_chat(channel_username).id
            except Exception as e:
                self.main_bot.send_message(message.chat.id, "канала не существует")
                return
            self.bots_database.delete_bots_info({"bot_username": username_bot.replace("@", ""), "channel_id": channel_id})
            index_bot = -1
            print(self.bots_thread)
            print(self.bots_work)
            for idx in range(len(self.bots_thread)):
                if self.bots_thread[idx].name == f"{username_bot.replace("@", "")}-bot":
                    index_bot = idx
                    self.bots_work[idx].stop_bot()
                    print(self.bots_thread)

            print(list(map(lambda th: th.is_alive(), self.bots_thread)), "<---")

            print(index_bot)
            if index_bot == -1:
                return
            else:
                del self.bots_thread[index_bot]

            self.main_bot.send_message(
                message.chat.id,
                text=f"бот отвязан"
            )

        @self.main_bot.message_handler(content_types=["text", "video", "photo"])
        @filter_admin
        def push_msg(message: Message):
            if message.content_type != "text" and message.caption is None:
                return

            for idx in range(len(self.bots_thread)):
                self.bots_work[idx].push_message(
                    type_message="media" if message.content_type in ("video", "photo") else "text",
                    data=message,
                )

    def run_bot(self):
        self.bot_info = self.main_bot.get_me()
        bots_lst = self.bots_database.get_bots_info()
        print(bots_lst)
        # self.bots_database.delete_bots_info({"bot_username": "Podslushano_mtusi_bot", "channel_id": "-1003005269923"})
        try:
            print(f"main bot @{self.bot_info.username} working")
            for api_token, bot_username, channel_id, id_row in bots_lst:
                # https://core.telegram.org/bots/api#getchat

                result = requests.get(
                    url=f"https://api.telegram.org/bot{api_token}/getchat",
                    params={"chat_id": channel_id}
                ).json()
                if result["ok"]:
                    channel_username = result["result"]["username"]
                else:
                    raise HTTPError(result)

                print(channel_id)
                channel_username = "@" + channel_username
                print(channel_username)
                bot = SubBot(
                    api_token_bot=api_token,
                    channel_username=channel_username,
                    hello_msg=settings.hello_msg,
                    ban_usr_msg=settings.ban_msg,
                    send_post_msg=settings.send_post_msg
                )
                th_bot = Thread(target=bot.run_bot, daemon=True, name=f"{bot.bot_info.username}-bot")
                th_bot.start()
                self.bots_thread.append(th_bot)
                self.bots_work.append(bot)
            self.main_bot.infinity_polling(timeout=10, long_polling_timeout=150)
        except Exception as ex:
            print(f"[ERROR] bot: @{self.bot_info.username}, mistake: {ex}")
