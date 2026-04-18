import pytz
import json
from telebot.types import Message, CallbackQuery, InlineKeyboardButton
from datetime import datetime, timedelta, timezone
from loguru import logger

from src.core_database.database import CrudBannedUser, CrudPostData
from src.core_database.models.sender_info import SenderData
from src.core_database.models.admin_actions import AdminActionData
from config import settings


class Utils:
    def __init__(self):
        self.db_banned = CrudBannedUser()
        self.sender_data = CrudPostData(SenderData)
        self.action_admin = CrudPostData(AdminActionData)

    @staticmethod
    def _extract_preview_file_id(message: Message) -> str | None:
        if message.content_type == "photo" and message.photo:
            return message.photo[-1].file_id
        if message.content_type == "video" and message.video is not None:
            return message.video.file_id
        if message.content_type == "animation" and message.animation is not None:
            return message.animation.file_id
        return None

    @staticmethod
    def _extract_preview_file_size(message: Message) -> int | None:
        if message.content_type == "photo" and message.photo:
            return message.photo[-1].file_size
        if message.content_type == "video" and message.video is not None:
            return message.video.file_size
        if message.content_type == "animation" and message.animation is not None:
            return message.animation.file_size
        return None

    @staticmethod
    def _serialize_entity_value(value):
        if value is None:
            return None
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, list):
            return [Utils._serialize_entity_value(item) for item in value if item is not None]
        if isinstance(value, dict):
            return {
                key: Utils._serialize_entity_value(item)
                for key, item in value.items()
                if item is not None
            }
        if hasattr(value, "to_dict"):
            return Utils._serialize_entity_value(value.to_dict())
        if hasattr(value, "__dict__"):
            return {
                key: Utils._serialize_entity_value(item)
                for key, item in value.__dict__.items()
                if not key.startswith("_") and item is not None
            }
        return str(value)

    @staticmethod
    def _extract_entities_json(message: Message) -> str | None:
        entities = message.entities if message.content_type == "text" else message.caption_entities
        if not entities:
            raw_payload = None
            if message.content_type == "text":
                raw_payload = message.json.get("entities")
            elif message.caption is not None:
                raw_payload = message.json.get("caption_entities")
            if not raw_payload:
                return None
            return json.dumps(raw_payload, ensure_ascii=False)

        payload = [Utils._serialize_entity_value(entity) for entity in entities]
        payload = [item for item in payload if item]
        if not payload:
            return None
        return json.dumps(payload, ensure_ascii=False)

    async def check_banned_user(self, id_user: int, id_channel: int) -> bool:
        all_info = await self.db_banned.get_banned_users(id_user=id_user, id_channel=id_channel)
        return bool(all_info)

    @staticmethod
    async def get_timestamp_public(time) -> float:
        tz = timezone(timedelta(hours=3))
        hour, minute = map(int, time.split(':'))
        now = datetime.now(tz)
        target = now.replace(hour=hour, minute=minute)
        if now >= target:
            target += timedelta(days=1)

        time_public = target.timestamp()
        return time_public

    @staticmethod
    async def get_timestamp_to_time(timestamp) -> str:
        tz = timezone(timedelta(hours=3))
        return datetime.fromtimestamp(timestamp, tz=tz).strftime('%H:%M')

    @staticmethod
    async def conversion_to_moscow_time(timestamp):
        utc_date = datetime.fromtimestamp(timestamp, tz=pytz.utc)
        local_tz = pytz.timezone('Europe/Moscow')
        local_date = utc_date.astimezone(local_tz)
        return local_date.timestamp()

    @logger.catch
    async def save_post(self, call: CallbackQuery, channel_id, info_sender, bot_info) -> None:
        timestamp = datetime.now(pytz.timezone('Europe/Moscow')).timestamp()
        logger.debug(timestamp)
        data = {
            "user_id":  info_sender.id,
            "channel_id": channel_id,
            "bot_username": bot_info,
            "username": info_sender.username if info_sender.username is not None else "",
            "first_name": info_sender.first_name,
            "message_id": call.message.id,
            "chat_id": call.message.chat.id,
            "text_post": "",
            "content_type": call.message.content_type,
            "media_group_id": getattr(call.message, "media_group_id", None),
            "preview_file_id": self._extract_preview_file_id(call.message),
            "preview_file_size": self._extract_preview_file_size(call.message),
            "entities_json": self._extract_entities_json(call.message),
            "timestamp": int(timestamp),
            }
        if call.message.content_type == "text":
            data["text_post"] = call.message.text
        elif call.message.caption is not None:
            data["text_post"] = call.message.caption

        await self._save_sender_record(data)

    @logger.catch
    async def save_incoming_message(self, message: Message, channel_id: int, bot_info: str) -> None:
        await self.save_incoming_message_with_review(
            message=message,
            channel_id=channel_id,
            bot_info=bot_info,
            review_chat_id=None,
            review_message_id=None,
        )

    @logger.catch
    async def save_incoming_message_with_review(
            self,
            message: Message,
            channel_id: int,
            bot_info: str,
            review_chat_id: int | None,
            review_message_id: int | None,
    ) -> None:
        timestamp = datetime.now(pytz.timezone('Europe/Moscow')).timestamp()
        data = {
            "user_id": message.from_user.id,
            "channel_id": channel_id,
            "bot_username": bot_info,
            "username": message.from_user.username if message.from_user.username is not None else "",
            "first_name": message.from_user.first_name,
            "message_id": message.id,
            "chat_id": message.chat.id,
            "text_post": "",
            "content_type": message.content_type,
            "media_group_id": getattr(message, "media_group_id", None),
            "preview_file_id": self._extract_preview_file_id(message),
            "preview_file_size": self._extract_preview_file_size(message),
            "entities_json": self._extract_entities_json(message),
            "review_chat_id": review_chat_id,
            "review_message_id": review_message_id,
            "timestamp": int(timestamp),
        }
        if message.content_type == "text":
            data["text_post"] = message.text
        elif message.caption is not None:
            data["text_post"] = message.caption

        await self._save_sender_record(data)

    async def _save_sender_record(self, data: dict) -> None:
        existing = await self.sender_data.get_first_by_filters(
            channel_id=data["channel_id"],
            bot_username=data["bot_username"],
            message_id=data["message_id"],
            chat_id=data["chat_id"],
        )
        if existing:
            return
        await self.sender_data.add_public_posts(data)

    @logger.catch
    async def save_admin_action(self, call):
        timestamp = datetime.now(pytz.timezone('Europe/Moscow')).timestamp()
        data = {
            "message_id": call.message.id,
            "chat_id": call.message.chat.id,
            "admin_id": call.message.from_user.id,
            "timestamp": int(timestamp),
            "button": call.data.split(";")[0],
        }
        await self.action_admin.add_public_posts(data)

    @staticmethod
    @logger.catch
    async def get_anon(message: Message):
        reply_markup = message.reply_markup.keyboard
        logger.debug(reply_markup)
        anon_markup: InlineKeyboardButton = reply_markup[2][1]
        is_anon = anon_markup.callback_data.split(";")[-1]
        return True if is_anon == "True" else False

    @staticmethod
    @logger.catch
    async def check_link(message: Message) -> bool:
        if message.entities is None and message.caption_entities is None:
            if message.text is None and message.caption is None:
                return False
            if message.text is None:
                text = message.caption
            else:
                text = message.text
            return "http" in text or "https" in text
        if message.entities is None:
            check_lst = message.caption_entities
        else:
            check_lst = message.entities
        for el in check_lst:
            if el.type == "text_link":
                return True
        return False


def filter_chats(func):
    def wrapper(message: Message):
        if (message.chat.id < 0 or
                message.chat.id == settings.general_admin or
                message.chat.id in settings.moderators):
            return func(message)
    return wrapper


def filter_admin(func):
    def wrapper(message: Message):
        if message.chat.id == settings.general_admin or message.chat.id in settings.moderators:
            return func(message)
    return wrapper
