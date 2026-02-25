from requests import HTTPError

from config import settings
from src.core_database.database import CrudBotsData
from src.worker import SubBot
from src.utils import filter_admin

from telebot.async_telebot import AsyncTeleBot
from telebot.types import BotCommand, BotCommandScopeChat, Message
import requests
from threading import Thread
import asyncio


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
        self.main_bot = AsyncTeleBot(self.api_token_bot)
        self.bots_work = []

        self.chats = settings.moderators
        self.chats.add(settings.general_admin)

        asyncio.create_task(self.__setup_bot_info())
        self.__setup_handlers()

    async def __setup_bot_info(self):
        await self.main_bot.set_my_commands(
            commands=self.commands,
            scope=BotCommandScopeChat(*self.chats),
        )
        self.bot_info = await self.main_bot.get_me()

    def __setup_handlers(self):
        @self.main_bot.message_handler(commands=["bots"])
        @filter_admin
        async def get_all_subbot(message: Message):
            all_info = await self.bots_database.get_bots_info()
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
            await self.main_bot.send_message(message.chat.id, answer)

        @self.main_bot.message_handler(commands=["add"])
        @filter_admin
        async def add_bot(message: Message):
            command, api_token, channel_username = message.text.split(" ")
            if "https" in channel_username:
                channel_username = "@" + channel_username.split("/")[-1]
            if "@" not in channel_username:
                channel_username = "@" + channel_username

            try:
                channel_id = (await self.main_bot.get_chat(channel_username)).id
            except Exception as e:
                await self.main_bot.send_message(message.chat.id, "канал не найден")
                return
            print(1)
            bot = await SubBot.create(
                api_token_bot=api_token,
                channel_username=channel_username,
                hello_msg=settings.hello_msg,
                ban_usr_msg=settings.ban_msg,
                send_post_msg=settings.send_post_msg,
            )
            print(await bot.check_admin(channel_id))
            if not (await bot.check_admin(channel_id)):
                await self.main_bot.send_message(
                    message.chat.id,
                    text=f"добавьте бота в администраторы канала: {channel_username}"
                )
                return
            for bots in await self.bots_database.get_bots_info():
                if bots[1] == bot.bot_info.username.replace("@", ""):
                    await self.main_bot.send_message(
                        text="бот уже привязан к чату",
                        chat_id=message.chat.id
                    )
                    return
            await self.bots_database.add_bots_info({
                "channel_id": channel_id,
                "bot_username": bot.bot_info.username,
                "bot_api_token": api_token,
            })
            await bot.run_bot()
            self.bots_work.append(bot)
            await self.main_bot.send_message(
                message.chat.id,
                "бот добавлен"
            )

        @self.main_bot.message_handler(commands=["remove"])
        @filter_admin
        async def remove_bot(message: Message):
            command, username_bot, channel_username = message.text.split(" ")
            try:
                channel_id = await self.main_bot.get_chat(channel_username)
                channel_id = channel_id.id
            except Exception as e:
                await self.main_bot.send_message(message.chat.id, "канала не существует")
                return
            await self.bots_database.delete_bots_info(
                {
                    "bot_username": username_bot.replace("@", ""),
                    "channel_id": channel_id
                }
            )
            index_bot = -1
            print(self.bots_work)
            for idx in range(len(self.bots_work)):
                username = (await self.bots_work[idx].getter_name()).replace("@", "")
                if username == username_bot.replace("@", ""):
                    index_bot = idx
                    await self.bots_work[idx][1].stop_bot()
                    print(self.bots_work)

            print(index_bot)
            if index_bot == -1:
                return
            else:
                del self.bots_work[index_bot]

            await self.main_bot.send_message(
                message.chat.id,
                text=f"бот отвязан"
            )

        @self.main_bot.message_handler(content_types=["text", "video", "photo"])
        @filter_admin
        async def push_msg(message: Message):
            if message.content_type != "text" and message.caption is None:
                return

            for idx in range(len(self.bots_work)):
                await self.bots_work[idx].push_message(
                    type_message="media" if message.content_type in ("video", "photo") else "text",
                    data=message,
                )

    async def run_bot(self):
        self.bot_info = await self.main_bot.get_me()
        bots_lst = await self.bots_database.get_bots_info()
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
                print(channel_username)
                bot = await SubBot.create(
                    api_token_bot=api_token,
                    channel_username=channel_username,
                    hello_msg=settings.hello_msg,
                    ban_usr_msg=settings.ban_msg,
                    send_post_msg=settings.send_post_msg
                )
                await bot.run_bot()
                self.bots_work.append(bot)
            await self.main_bot.infinity_polling(timeout=10)
        except Exception as ex:
            print(f"[ERROR] bot: @{self.bot_info.username}, mistake: {ex}")
