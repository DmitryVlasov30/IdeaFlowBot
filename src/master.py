from datetime import timezone, timedelta, datetime

from requests import HTTPError

from config import settings
from src.core_database.database import CrudBotsData, CrudDelayedPosts
from src.worker import SubBot
from src.utils import filter_admin

from telebot.async_telebot import AsyncTeleBot, asyncio_helper
from telebot.types import BotCommand, BotCommandScopeChat, Message, InlineKeyboardMarkup, InlineKeyboardButton, \
    CallbackQuery, User
from loguru import logger
import asyncio
import aiohttp


class MasterBot:
    def __init__(self, api_token_bot):
        self.delayed_task = None
        self.bot_info = None
        self.flag_register_push_message = False

        self.bots_database = CrudBotsData()
        self.delayed_database = CrudDelayedPosts()

        self.commands = [
            BotCommand("bots", "выводит список подчиненных ботов"),
            BotCommand("add", "добавление нового бота, указывай api токен, потом ссылку на канал"),
            BotCommand("remove", "сначала юз бота, потом юз канала")
        ]

        self.api_token_bot = api_token_bot
        asyncio_helper.proxy = settings.proxies["http"]
        asyncio_helper.REQUEST_LIMIT = settings.sup_bot_limit
        self.main_bot = AsyncTeleBot(self.api_token_bot)
        self.bots_work = []

        self.chats = settings.moderators
        self.chats.add(settings.general_admin)

        asyncio.create_task(self.__setup_bot_info())
        self.__setup_handlers()
        logger.info("init bot")

    @logger.catch
    async def __send_post(self, delayed_post) -> None:
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
    async def __delayed_posts_checker(self) -> None:
        while True:
            delayed_posts = {}
            for bot in self.bots_work:
                delayed_message = await bot.getter_delayed_info()
                info_lst = sorted(delayed_message.items(), key=lambda item: (item[1], item[0]))
                delayed_posts[bot.bot_info.id] = info_lst

            info_delayed_posts = list(filter(lambda el: el[1], delayed_posts.items()))
            if info_delayed_posts:
                logger.info(f"delayed posts checker: {info_delayed_posts}")
            await self.__send_post(delayed_posts)
            await asyncio.sleep(settings.const_time_sleep)

    async def __setup_bot_info(self) -> None:
        await self.main_bot.set_my_commands(
            commands=self.commands,
            scope=BotCommandScopeChat(*self.chats),
        )
        self.bot_info = await self.main_bot.get_me()

    def __setup_handlers(self):
        @self.main_bot.message_handler(commands=["push"])
        @filter_admin
        async def register_push_message(message: Message) -> None:
            await self.main_bot.send_message(settings.general_admin, "напишите пост, который хотите разослать")
            self.flag_register_push_message = True

        @self.main_bot.message_handler(commands=["bots"])
        @filter_admin
        async def get_all_subbot(message: Message) -> None:
            all_info = await self.bots_database.get_bots_info()

            logger.info("command Bots")
            if len(all_info) == 0:
                await self.main_bot.send_message(settings.general_admin, "ботов не добавлено")
                return
            answer = "боты:\n"
            async with aiohttp.ClientSession() as session:
                for api_token, bot_username, channel_id, id_row in all_info:
                    channel_username = ""
                    # noinspection PyBroadException
                    try:
                        url = f"https://api.telegram.org/bot{api_token}/getchat?chat_id={channel_id}"
                        proxy_auth = aiohttp.BasicAuth(settings.proxy_user, settings.proxy_password)
                        logger.info(f"{api_token}, {channel_id}")
                        async with session.get(url, proxy=f"http://{settings.proxy_host_port}", proxy_auth=proxy_auth) as response:
                            result = await response.json()
                            if result["ok"]:
                                channel_username = result["result"]["username"]
                            else:
                                logger.error(f"{api_token}, {channel_id}, {result}")
                                raise HTTPError(result)
                    except:
                        logger.error(f"{bot_username}, {channel_id}")
                        continue
                    answer += (f"channel: @{channel_username}\n"
                               f"bot: @{bot_username}\n\n")
                await session.close()
            answer += "\n"
            await self.main_bot.send_message(settings.general_admin, answer)

        @self.main_bot.message_handler(commands=["add"])
        @filter_admin
        @logger.catch
        async def add_bot(message: Message) -> None:
            try:
                command, api_token, channel_username = message.text.split(" ")
                logger.info(
                    f"add func, user: {message.chat.username},"
                    f" api_token: {api_token},"
                    f" channel_username: {channel_username}"
                )

            except ValueError:
                logger.error(f"error, text message: {message.text}")
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
                logger.error(f"channel not found, channel_username: {channel_username}")
                await self.main_bot.send_message(message.chat.id, "канал не найден")
                return
            bot = await SubBot.create(
                api_token_bot=api_token,
                channel_username=channel_username,
                hello_msg=settings.hello_msg,
                ban_usr_msg=settings.ban_msg,
                send_post_msg=settings.send_post_msg,
            )
            logger.info("init bot")
            is_admin = await bot.check_admin(channel_id)
            logger.info(f"check admin: {is_admin}")
            if not is_admin:
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
            logger.info("add bot to database")

        @self.main_bot.message_handler(commands=["start"])
        @logger.catch
        async def start(message: Message) -> None:
            logger.info(f"id: {message.chat.id}, username: {message.chat.username}")
            await self.main_bot.send_message(
                settings.general_admin,
                "work"
            )

        @self.main_bot.message_handler(commands=["delete"])
        @filter_admin
        async def remove_bot(message: Message) -> None:
            command, username_bot, channel_username = message.text.split(" ")
            logger.info(f"args: {username_bot}, {channel_username}")
            # noinspection PyBroadException
            try:
                channel_id = (await self.main_bot.get_chat(channel_username)).id
            except Exception:
                logger.error(f"channel not found, channel_username: {channel_username}")
                await self.main_bot.send_message(message.chat.id, "канала не существует")
                return
            await self.bots_database.delete_bots_info(
                {
                    "bot_username": username_bot.replace("@", ""),
                    "channel_id": channel_id
                }
            )
            index_bot = -1
            logger.info(f"bots: {self.bots_work}")
            for idx in range(len(self.bots_work)):
                username = (await self.bots_work[idx].getter_name()).replace("@", "")
                if username == username_bot.replace("@", ""):
                    index_bot = idx
                    await self.bots_work[idx].stop_bot()
                    logger.info(f"new list: {self.bots_work}")

            if index_bot == -1:
                logger.error(f"bot not found, username: {username_bot}")
                return
            else:
                logger.info(f"bot {username_bot} deleted")
                del self.bots_work[index_bot]

            await self.main_bot.send_message(
                message.chat.id,
                text=f"бот отвязан"
            )

        @self.main_bot.message_handler(content_types=["text", "video", "photo"])
        @filter_admin
        async def push_msg(message: Message) -> None:
            logger.info("push msg")
            if self.flag_register_push_message:
                markup = InlineKeyboardMarkup()
                self.flag_register_push_message = False
                message_id_push = message.id
                button_push = InlineKeyboardButton(
                    text="опубликовать",
                    callback_data=f"push;{message_id_push}"
                )
                button_reject = InlineKeyboardButton(
                    text="удалить",
                    callback_data=f"reject_push;{message_id_push}"
                )
                markup.add(button_push)
                markup.add(button_reject)
                await self.main_bot.copy_message(
                    from_chat_id=settings.general_admin,
                    chat_id=settings.general_admin,
                    message_id=message_id_push,
                    reply_markup=markup,
                )

        @logger.catch
        @self.main_bot.callback_query_handler(func=lambda call: True)
        async def callback(call: CallbackQuery) -> None:
            match call.data.split(";")[0]:
                case "push":
                    pass
                case "reject_push":
                    await self.main_bot.delete_message(
                        chat_id=settings.general_admin,
                        message_id=int(call.data.split(";")[1])
                    )

    @logger.catch
    async def run_bot(self) -> None:
        logger.info("run_bot")
        self.bot_info: User = (await self.main_bot.get_me())
        logger.info(self.bot_info.username)
        bots_lst = await self.bots_database.get_bots_info()
        logger.info(list(map(lambda el: (el[1], el[2]), bots_lst)))
        try:
            logger.info(f"main bot @{self.bot_info.username} working")
            async with aiohttp.ClientSession() as session:
                for api_token, bot_username, channel_id, id_row in bots_lst:
                    url = f"https://api.telegram.org/bot{api_token}/getchat?chat_id={channel_id}"
                    proxy_auth = aiohttp.BasicAuth(settings.proxy_user, settings.proxy_password)
                    async with session.get(url, proxy=f"http://{settings.proxy_host_port}", proxy_auth=proxy_auth) as response:
                        result = await response.json()
                        if result["ok"]:
                            channel_username = result["result"]["username"]
                        else:
                            logger.error(f"{result}\n{api_token}\n{url}")
                            raise HTTPError(result)

                        channel_username = "@" + channel_username
                        logger.info(f"connected: {channel_username}")
                        bot = await SubBot.create(
                            main_bot_username=self.bot_info.username,
                            api_token_bot=api_token,
                            channel_username=channel_username,
                            hello_msg=settings.hello_msg,
                            ban_usr_msg=settings.ban_msg,
                            send_post_msg=settings.send_post_msg
                        )
                        await bot.run_bot()
                        self.bots_work.append(bot)
            self.delayed_task = asyncio.create_task(self.__delayed_posts_checker())
            logger.info("bots worked")
            await self.main_bot.polling(none_stop=True)
        except Exception as ex:
            logger.error(f"bot: @{self.bot_info.username}, mistake: {ex}")
