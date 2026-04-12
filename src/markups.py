from telebot import formatting
from telebot.async_telebot import AsyncTeleBot
from telebot.types import InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
from loguru import logger

from src.core_database.config import settings
from src.utils import Utils
from config import settings


class MarkupButton:
    def __init__(self, bot: AsyncTeleBot):
        self.bot = bot
        self.morning_time = {
            "8:00": {"hour": 8, "minute": 0},
            "8:15": {"hour": 8, "minute": 15},
            "8:30": {"hour": 8, "minute": 30},
            "8:45": {"hour": 8, "minute": 45},
            "9:00": {"hour": 9, "minute": 0},
            "9:15": {"hour": 9, "minute": 15},
            "9:30": {"hour": 9, "minute": 30},
            "9:45": {"hour": 9, "minute": 45},
            "10:00": {"hour": 10, "minute": 0},
            "10:15": {"hour": 10, "minute": 15},
            "10:30": {"hour": 10, "minute": 30},
            "10:45": {"hour": 10, "minute": 45},
            "11:00": {"hour": 11, "minute": 0},
            "11:15": {"hour": 11, "minute": 15},
            "11:30": {"hour": 11, "minute": 30},
            "11:45": {"hour": 11, "minute": 45},
        }

        self.dinner_time = {
            "12:00": {"hour": 12, "minute": 0},
            "12:15": {"hour": 12, "minute": 15},
            "12:30": {"hour": 12, "minute": 30},
            "12:45": {"hour": 12, "minute": 45},
            "13:00": {"hour": 13, "minute": 0},
            "13:15": {"hour": 13, "minute": 15},
            "13:30": {"hour": 13, "minute": 30},
            "13:45": {"hour": 13, "minute": 45},
            "14:00": {"hour": 14, "minute": 0},
            "14:15": {"hour": 14, "minute": 15},
            "14:30": {"hour": 14, "minute": 30},
            "15:00": {"hour": 15, "minute": 30},
            "15:15": {"hour": 15, "minute": 15},
            "15:30": {"hour": 15, "minute": 30},
            "15:45": {"hour": 15, "minute": 45},
            "16:00": {"hour": 16, "minute": 0},
            "16:15": {"hour": 16, "minute": 15},
            "16:30": {"hour": 16, "minute": 30},
            "16:45": {"hour": 16, "minute": 45},
        }

        self.evening_time = {
            "17:00": {"hour": 17, "minute": 0},
            "17:15": {"hour": 17, "minute": 15},
            "17:30": {"hour": 17, "minute": 30},
            "17:45": {"hour": 17, "minute": 45},
            "18:00": {"hour": 18, "minute": 0},
            "18:15": {"hour": 18, "minute": 15},
            "18:30": {"hour": 18, "minute": 30},
            "18:45": {"hour": 18, "minute": 45},
            "19:00": {"hour": 19, "minute": 0},
            "19:15": {"hour": 19, "minute": 15},
            "19:30": {"hour": 19, "minute": 30},
            "19:45": {"hour": 19, "minute": 45},
            "20:00": {"hour": 20, "minute": 0},
            "20:15": {"hour": 20, "minute": 15},
            "20:30": {"hour": 20, "minute": 30},
            "20:45": {"hour": 20, "minute": 45},
            "21:00": {"hour": 21, "minute": 0},
            "21:15": {"hour": 21, "minute": 15},
            "21:30": {"hour": 21, "minute": 30},
            "21:45": {"hour": 21, "minute": 45},
        }

        self.night_time = {
            "22:00": {"hour": 22, "minute": 0},
            "22:15": {"hour": 22, "minute": 15},
            "22:30": {"hour": 22, "minute": 30},
            "22:45": {"hour": 22, "minute": 45},
            "23:00": {"hour": 23, "minute": 0},
            "23:15": {"hour": 23, "minute": 15},
            "23:30": {"hour": 23, "minute": 30},
            "23:45": {"hour": 23, "minute": 45},
            "00:00": {"hour": 0, "minute": 0},
            "00:15": {"hour": 0, "minute": 15},
            "00:30": {"hour": 0, "minute": 30},
            "00:45": {"hour": 0, "minute": 45},
            "1:00": {"hour": 1, "minute": 0},
            "1:15": {"hour": 1, "minute": 15},
            "1:30": {"hour": 1, "minute": 30},
            "1:45": {"hour": 1, "minute": 45},
            "2:00": {"hour": 2, "minute": 0},
            "2:15": {"hour": 2, "minute": 15},
            "2:30": {"hour": 2, "minute": 30},
            "2:45": {"hour": 2, "minute": 45},
            "3:00": {"hour": 3, "minute": 0},
            "3:15": {"hour": 3, "minute": 15},
            "3:30": {"hour": 3, "minute": 30},
            "3:45": {"hour": 3, "minute": 45},
        }

    @logger.catch
    async def delayed_post(self, call: CallbackQuery):
        markup = InlineKeyboardMarkup(row_width=4)

        chat_id = call.data.split(";")[-1]
        back_button = InlineKeyboardButton(
            text="Назад",
            callback_data=f"back_to_main_menu;{chat_id}",
        )
        morning_button = InlineKeyboardButton(
            text="утро",
            callback_data=f"morning;{chat_id}"
        )
        dinner_button = InlineKeyboardButton(text="обед", callback_data=f"dinner;{chat_id}")
        evening_button = InlineKeyboardButton(text="вечер", callback_data=f"evening;{chat_id}")
        night_button = InlineKeyboardButton(text="ночь", callback_data=f"night;{chat_id}")

        markup.add(morning_button, dinner_button, evening_button, night_button)
        markup.add(back_button)
        await self.bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup,
        )

    @logger.catch
    async def delayed_day(self, call: CallbackQuery, day_div, sender_id, advertising_data):
        logger.info(f"args: {day_div}, {sender_id}")
        if day_div == "morning":
            data_button = self.morning_time
        elif day_div == "dinner":
            data_button = self.dinner_time
        elif day_div == "evening":
            data_button = self.evening_time
        else:
            data_button = self.night_time
        markup = InlineKeyboardMarkup(row_width=5)
        button_lst = []
        interval_lst = list(map(lambda x: (x[1], x[1] + settings.shift_time_seconds), advertising_data))
        for item, el in data_button.items():
            time_public = await Utils.get_timestamp_public(item)
            flag_skip = False
            for interval_down, interval_up in interval_lst:
                if interval_down <= time_public <= interval_up:
                    flag_skip = True

            if flag_skip:
                logger.debug(f"time: {interval_lst}, time_public: {time_public}")
                continue
            button = InlineKeyboardButton(
                text=item,
                callback_data=f"day_choice;{day_div};{item};{call.message.message_id};{sender_id}",
            )
            button_lst.append(button)
        back_button = InlineKeyboardButton(
            text="назад",
            callback_data=f"delayed_button;{sender_id}"
        )
        markup.add(*button_lst)
        markup.add(back_button)
        await self.bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup,
        )

    @logger.catch
    async def reject_post(self, call: CallbackQuery):
        message_id = call.message.message_id
        user_info = await self.bot.get_chat(call.data.split(";")[1])
        markup = InlineKeyboardMarkup(row_width=2)
        button_info = InlineKeyboardButton(
            text=f"@{user_info.username} (Отклонено)",
            callback_data=f"add_info;{user_info.id}"
        )
        markup.add(button_info)
        await self.bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=message_id,
            reply_markup=markup,
        )

    @logger.catch
    async def add_info(self, call: CallbackQuery):
        info = await self.bot.get_chat(call.data.split(";")[1])
        user = formatting.escape_markdown(info.username)
        msg = "информация: \n" + f"id: `{info.id}`\n" + f"username @{user}\n" + f"name: `{info.first_name}`"
        await self.bot.send_message(
            chat_id=call.message.chat.id,
            text=msg,
            parse_mode="Markdown",
        )

    @logger.catch
    async def main_menu(self,
                        sender_id,
                        chat_id,
                        message_id,
                        chat_suggest,
                        is_send: bool = True,
                        is_anon: bool = False
                        ):
        markup = InlineKeyboardMarkup(row_width=3)

        logger.debug(chat_id)
        info_user = await self.bot.get_chat(chat_id)
        banned_user = InlineKeyboardButton(
            text="👮‍♂️бан",
            callback_data=f"banned_user;{chat_id}"
        )
        addition_info = InlineKeyboardButton(
            text=f"@{info_user.username}",
            callback_data=f"add_info;{chat_id}"
        )
        send_button = InlineKeyboardButton(
            text="✅Одобрить",
            callback_data=f"send_suggest;{chat_id}"
        )
        reject_button = InlineKeyboardButton(
            text="❌Отклонить",
            callback_data=f"reject;{chat_id}"
        )

        delayed_button = InlineKeyboardButton(
            text="⌛️Отложка",
            callback_data=f"delayed_button;{chat_id}"
        )

        anon_button = InlineKeyboardButton(
            text=f"🥷АНОН" if not is_anon else "🤵НЕ АНОН",
            callback_data=f"anonym_button;{chat_id}"
        )

        advertising_button = InlineKeyboardButton(
            text="💵Реклама",
            callback_data=f"advertising_button;{chat_id}"
        )

        markup.add(banned_user, addition_info, anon_button)
        markup.add(send_button, reject_button)
        markup.add(delayed_button, advertising_button)
        if is_send:
            await self.bot.copy_message(
                chat_id=chat_suggest,
                from_chat_id=sender_id,
                message_id=message_id,
                reply_markup=markup,
            )
        else:
            await self.bot.edit_message_reply_markup(
                chat_id=sender_id,
                message_id=message_id,
                reply_markup=markup,
            )

    @logger.catch
    async def delayed_buttons_times(self, call: CallbackQuery, sender_id):
        markup = InlineKeyboardMarkup(row_width=2)
        time = call.data.split(";")[2]
        logger.info(f"{call.message.chat.id, call.message.text}")
        button_reject = InlineKeyboardButton(
            text="удалить",
            callback_data=f"reject_delayed;{sender_id}"
        )
        info_sender = await self.bot.get_chat(sender_id)
        button_info = InlineKeyboardButton(
            text=f"@{info_sender.username}",
            callback_data=f"add_info;{sender_id}"
        )
        logger.info(call.data)
        button_time = InlineKeyboardButton(
            text=f"Отложено до {time}",
            callback_data=f"delayed_button;{sender_id}"
        )
        markup.add(button_reject, button_info)
        markup.add(button_time)
        await self.bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup,
        )

    @logger.catch
    async def push_post_button(self, chat_id, message_id, sender_id=None):
        markup = InlineKeyboardMarkup()
        info_sender = await self.bot.get_chat(sender_id)
        button_info = InlineKeyboardButton(
            text=f"@{info_sender.username}",
            callback_data=f"add_info;{sender_id}"
        )
        markup.add(button_info)
        await self.bot.edit_message_reply_markup(
            chat_id=chat_id,
            message_id=message_id,
            reply_markup=markup
        )

    @logger.catch
    async def send_suggest(self, call, channel_username, channel_id, is_anon):
        try:
            markup_post = None

            user_info = await self.bot.get_chat(call.data.split(";")[1])
            logger.info(f"send post: {channel_username}, {user_info.id, user_info.username}")

            markup = InlineKeyboardMarkup()
            addition_info = InlineKeyboardButton(
                text=f"@{user_info.username}",
                callback_data=f"add_info;{user_info.id}"
            )
            markup.add(addition_info)

            if is_anon:
                markup_post = InlineKeyboardMarkup()
                info_post_sender = InlineKeyboardButton(
                    text=f"@{user_info.username}",
                    url=f"https://t.me/{user_info.username}"
                )
                markup_post.add(info_post_sender)

            await self.bot.copy_message(
                chat_id=channel_id,
                from_chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=markup_post,
            )
            await self.bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=markup,
            )
            logger.info("send post success")
        except Exception as ex:
            logger.error(ex)
            await self.bot.send_message(chat_id=call.message.chat.id, text=f"Произошла ошибка при обработки: {ex}")

    @logger.catch
    async def add_ban_user(self, call: CallbackQuery, ban_database, channel_id, bot_info, chat_suggest):
        try:
            user_info = await self.bot.get_chat(call.data.split(";")[1])

            logger.info(f"get banned user: {user_info.username, user_info.id}")
            markup = InlineKeyboardMarkup()
            addition_info = InlineKeyboardButton(
                text=f"@{user_info.username}",
                callback_data=f"add_info;{user_info.id}"
            )
            markup.add(addition_info)

            await ban_database.add_banned_user({
                "id_user": user_info.id,
                "id_channel": channel_id,
                "bot_id": bot_info.id
            })

            await self.bot.edit_message_reply_markup(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                reply_markup=markup,
            )
            await self.bot.send_message(
                text=f"@{user_info.username}, id: {user_info.id} забанен",
                chat_id=chat_suggest,
            )
        except Exception as ex:
            logger.error(ex)

    @logger.catch
    async def get_markup(self, timestamp, sender_id) -> InlineKeyboardMarkup:
        sender_info = await self.bot.get_chat(sender_id)
        markup = InlineKeyboardMarkup(row_width=2)
        button_reject = InlineKeyboardButton(
            text="удалить",
            callback_data=f"reject_delayed;{sender_id}"
        )
        button_info = InlineKeyboardButton(
            text=f"@{sender_info.username}",
            callback_data=f"add_info;{sender_id}"
        )
        time = await Utils.get_timestamp_to_time(timestamp)
        logger.debug(f"time: {time}")
        button_time = InlineKeyboardButton(
            text=f"Отложено до {time}",
            callback_data=f"delayed_button;{sender_id}"
        )
        markup.add(button_reject, button_info)
        markup.add(button_time)
        return markup

    async def advertising_button(self, call: CallbackQuery):
        logger.info(f"advertising button: {call.data}")
        markup = InlineKeyboardMarkup()
        sender_id = call.data.split(";")[1]
        sender_info = await self.bot.get_chat(sender_id)
        button_info = InlineKeyboardButton(
            text=f"@{sender_info.username} (реклама отправлена)",
            callback_data=f"add_info;{sender_id}"
        )
        markup.add(button_info)
        await self.bot.send_message(text=settings.advertising_text, chat_id=sender_id)
        await self.bot.edit_message_reply_markup(
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            reply_markup=markup,
        )

