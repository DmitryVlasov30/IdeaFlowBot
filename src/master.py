from datetime import timezone, timedelta, datetime

from requests import HTTPError

from config import settings
from src.core_database.database import CrudBotsData, CrudDelayedPosts
from src.worker import SubBot
from src.utils import filter_admin

from telebot.async_telebot import AsyncTeleBot, asyncio_helper
from telebot.types import BotCommand, BotCommandScopeChat, Message
from loguru import logger
import asyncio
import aiohttp


class MasterBot:
    def __init__(self, api_token_bot):
        self.delayed_task = None
        self.bot_info = None

        self.bots_database = CrudBotsData()
        self.delayed_database = CrudDelayedPosts()

        self.commands = [
            BotCommand("bots", "выводит список подчиненных ботов"),
            BotCommand("add", "добавление нового бота, указывай api токен, потом ссылку на канал"),
            BotCommand("remove", "сначала юз бота, потом юз канала")
        ]

        self.api_token_bot = api_token_bot
        asyncio_helper.proxy = settings.proxies["http"]
        asyncio_helper.REQUEST_LIMIT = 500
        self.main_bot = AsyncTeleBot(self.api_token_bot)
        self.bots_work = []

        self.chats = settings.moderators
        self.chats.add(settings.general_admin)

        asyncio.create_task(self.__setup_bot_info())
        self.__setup_handlers()
        logger.info("init bot")

    @logger.catch
    async def __send_post(self, delayed_post):
        tz = timezone(timedelta(hours=3))
        now = datetime.now(tz)
        bots_data = {}
        for bot in self.bots_work:
            bots_data[bot.bot_info.id] = bot

        public_data = []
        for bot, info_post in delayed_post.items():
            for message_id, info in info_post:
                time_post, sender_id = info
                if now.timestamp() >= time_post:
                    public_data.append((message_id, sender_id, bot))

        for message_id, sender_id, bot in public_data:
            await self.delayed_database.delete_delayed_posts({
                "bot_id": bot,
                "message_id": message_id,
            })

            await bots_data[bot].send_delayed_message(message_id, sender_id)

    @logger.catch
    async def __delayed_posts_checker(self):
        while True:
            delayed_posts = {}
            for bot in self.bots_work:
                delayed_message = await bot.getter_delayed_info()
                info_lst = sorted(delayed_message.items(), key=lambda item: (item[1], item[0]))
                delayed_posts[bot.bot_info.id] = info_lst

            print(delayed_posts)
            await self.__send_post(delayed_posts)
            await asyncio.sleep(settings.const_time_sleep)

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
            async with aiohttp.ClientSession() as session:
                for api_token, bot_username, channel_id, id_row in all_info:
                    channel_username = ""
                    # noinspection PyBroadException
                    try:
                        url = f"https://api.telegram.org/bot{api_token}/getchat?chat_id={channel_id}"
                        proxy_auth = aiohttp.BasicAuth(settings.proxy_user, settings.proxy_password)
                        print(12)
                        async with session.get(url, proxy=f"http://{settings.proxy_host_port}", proxy_auth=proxy_auth) as response:
                            result = await response.json()
                            if result["ok"]:
                                channel_username = result["result"]["username"]
                            else:
                                raise HTTPError(result)
                    except:
                        print(bot_username, channel_id)
                        continue
                    answer += (f"channel: @{channel_username}\n"
                               f"bot: @{bot_username}\n\n")
                await session.close()
            answer += "\n"
            await self.main_bot.send_message(message.chat.id, answer)

        @self.main_bot.message_handler(commands=["add"])
        @filter_admin
        @logger.catch
        async def add_bot(message: Message):
            try:
                command, api_token, channel_username = message.text.split(" ")
            except ValueError:
                await self.main_bot.send_message(settings.general_admin, "указаны не правильные входные данные")
                return
            if "https" in channel_username:
                channel_username = "@" + channel_username.split("/")[-1]
            if "@" not in channel_username:
                channel_username = "@" + channel_username

            # noinspection PyBroadException
            try:
                channel_id = (await self.main_bot.get_chat(channel_username)).id
            except Exception:
                await self.main_bot.send_message(message.chat.id, "канал не найден")
                return
            print(1)
            logger.info("add")
            bot = await SubBot.create(
                api_token_bot=api_token,
                channel_username=channel_username,
                hello_msg=settings.hello_msg,
                ban_usr_msg=settings.ban_msg,
                send_post_msg=settings.send_post_msg,
            )
            logger.info("init bot")
            print(await bot.check_admin(channel_id))
            if not (await bot.check_admin(channel_id)):
                await self.main_bot.send_message(
                    message.chat.id,
                    text=f"добавьте бота в администраторы канала: {channel_username}"
                )
                return
            for bots in (await self.bots_database.get_bots_info()):
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

        @self.main_bot.message_handler(commands=["start"])
        @logger.catch
        async def start(message: Message):
            print(message)

            await self.main_bot.send_message(
                settings.general_admin, "start"
            )

        @self.main_bot.message_handler(commands=["remove"])
        @filter_admin
        async def remove_bot(message: Message):
            command, username_bot, channel_username = message.text.split(" ")

            # noinspection PyBroadException
            try:
                channel_id = await self.main_bot.get_chat(channel_username)
                channel_id = channel_id.id
            except Exception:
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
                    await self.bots_work[idx].stop_bot()
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

    @logger.catch
    async def run_bot(self):
        print("run")
        self.bot_info = await self.main_bot.get_me()
        print(self.bot_info)
        bots_lst = await self.bots_database.get_bots_info()
        print(bots_lst)
        try:
            print(f"main bot @{self.bot_info.username} working")
            for api_token, bot_username, channel_id, id_row in bots_lst:
                url = f"https://api.telegram.org/bot{api_token}/getchat?chat_id={channel_id}"
                proxy_auth = aiohttp.BasicAuth(settings.proxy_user, settings.proxy_password)
                async with aiohttp.ClientSession() as session:
                    async with session.get(url, proxy=f"http://{settings.proxy_host_port}", proxy_auth=proxy_auth) as response:
                        result = await response.json()
                        if result["ok"]:
                            channel_username = result["result"]["username"]
                        else:
                            print(result, api_token, url)
                            raise HTTPError(result)

                        print(channel_id)
                        channel_username = "@" + channel_username
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
            self.delayed_task = asyncio.create_task(self.__delayed_posts_checker())
            print(1234)
            await self.main_bot.polling(none_stop=True)
        except Exception as ex:
            print(f"[ERROR] bot: @{self.bot_info.username}, mistake: {ex}")
