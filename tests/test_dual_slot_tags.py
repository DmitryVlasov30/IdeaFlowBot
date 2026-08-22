from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.markups import MarkupButton, build_slot_status_markup


@pytest.mark.asyncio
async def test_approved_slot_markup_shows_sender_and_moderator_tags() -> None:
    bot = SimpleNamespace(
        get_chat=AsyncMock(
            return_value=SimpleNamespace(username="suggest_sender", first_name="Sender")
        ),
        edit_message_reply_markup=AsyncMock(),
    )

    await MarkupButton(bot).approve_to_slot_button(
        chat_id=-100123,
        message_id=4321,
        sender_id=1001,
        moderator_id=987654321,
        moderator_username="review_admin",
        moderator_first_name="Admin",
    )

    markup = bot.edit_message_reply_markup.await_args.kwargs["reply_markup"].to_dict()
    assert markup["inline_keyboard"] == [
        [
            {
                "text": "👤 @suggest_sender",
                "callback_data": "add_info;1001",
            }
        ],
        [
            {
                "text": "✅ @review_admin (одобрено в слот)",
                "callback_data": "add_info;987654321",
            }
        ],
        [
            {
                "text": "↩️ Отменить слот",
                "callback_data": "cancel_approve_to_slot;1001",
            }
        ],
    ]


def test_published_slot_markup_keeps_sender_and_moderator_tags() -> None:
    markup = build_slot_status_markup(
        sender_id=1001,
        sender_username="suggest_sender",
        sender_first_name="Sender",
        moderator_id=987654321,
        moderator_username="review_admin",
        moderator_first_name="Admin",
        state="published",
    ).to_dict()

    assert markup["inline_keyboard"] == [
        [
            {
                "text": "👤 @suggest_sender",
                "callback_data": "add_info;1001",
            }
        ],
        [
            {
                "text": "✅ @review_admin (опубликовано)",
                "callback_data": "add_info;987654321",
            }
        ],
    ]
