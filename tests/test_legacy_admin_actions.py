from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.markups import MarkupButton
from src.utils import Utils


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "callback_data",
    [
        "send_suggest;1001",
        "day_choice;morning;2026-08-21;0;1001",
        "approve_to_slot;1001",
    ],
)
async def test_legacy_approval_saves_admin_who_pressed_button(callback_data):
    utils = Utils.__new__(Utils)
    utils.action_admin = SimpleNamespace(add_public_posts=AsyncMock())
    call = SimpleNamespace(
        data=callback_data,
        from_user=SimpleNamespace(id=987654321),
        message=SimpleNamespace(
            id=4321,
            chat=SimpleNamespace(id=-1001234567890),
            from_user=SimpleNamespace(id=111222333, is_bot=True),
        ),
    )

    await utils.save_admin_action(call)

    saved = utils.action_admin.add_public_posts.await_args.args[0]
    assert saved["admin_id"] == call.from_user.id
    assert saved["admin_id"] != call.message.from_user.id
    assert saved["button"] == callback_data.split(";", 1)[0]
    assert saved["message_id"] == call.message.id
    assert saved["chat_id"] == call.message.chat.id


@pytest.mark.asyncio
async def test_successful_legacy_publication_is_not_retried_when_markup_update_fails(
    monkeypatch,
):
    bot = SimpleNamespace(
        token="1:test",
        get_chat=AsyncMock(return_value=SimpleNamespace(id=1001, username="author")),
        copy_message=AsyncMock(return_value=SimpleNamespace(message_id=55)),
        edit_message_reply_markup=AsyncMock(side_effect=TimeoutError("timed out")),
        send_message=AsyncMock(),
    )
    monkeypatch.setattr(
        "src.markups.should_add_publication_signature",
        AsyncMock(return_value=False),
    )
    call = SimpleNamespace(
        data="send_suggest;1001",
        message=SimpleNamespace(
            message_id=4321,
            chat=SimpleNamespace(id=-1001234567890),
            content_type="text",
            text="test",
            caption=None,
        ),
    )

    sent = await MarkupButton(bot).send_suggest(
        call,
        "@channel",
        -1009876543210,
        False,
        "Channel",
    )

    assert sent is True
    bot.copy_message.assert_awaited_once()
    bot.edit_message_reply_markup.assert_awaited_once()
    bot.send_message.assert_not_awaited()
