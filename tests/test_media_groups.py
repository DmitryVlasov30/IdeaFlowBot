import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.markups import MarkupButton
from src.master import MasterBot
from src.worker import SubBot


def _message(message_id: int, *, caption: str | None = None):
    return SimpleNamespace(
        message_id=message_id,
        id=message_id,
        caption=caption,
        media_group_id="album-1",
        chat=SimpleNamespace(id=1001),
    )


@pytest.mark.asyncio
async def test_legacy_review_copies_album_once_and_saves_each_message_link() -> None:
    copied_messages = [SimpleNamespace(message_id=501), SimpleNamespace(message_id=502)]
    bot = SimpleNamespace(
        copy_messages=AsyncMock(return_value=copied_messages),
        edit_message_reply_markup=AsyncMock(),
        get_chat=AsyncMock(return_value=SimpleNamespace(username="author")),
    )
    subbot = SubBot.__new__(SubBot)
    subbot.sup_bot = bot
    subbot.chat_suggest = -10055
    subbot.channel_id = -10077
    subbot.channel_username = "@channel"
    subbot.channel_title = "Channel"
    subbot.bot_info = SimpleNamespace(username="suggest_bot")
    subbot.callback_new_submission = AsyncMock()
    subbot._save_incoming_message = AsyncMock()

    messages = [_message(12), _message(11, caption="Album caption")]
    await subbot._send_media_group_to_legacy_chat(messages)

    bot.copy_messages.assert_awaited_once_with(
        chat_id=-10055,
        from_chat_id=1001,
        message_ids=[11, 12],
    )
    bot.edit_message_reply_markup.assert_awaited_once()
    assert bot.edit_message_reply_markup.await_args.kwargs["message_id"] == 501
    assert subbot._save_incoming_message.await_args_list == [
        ((messages[1], copied_messages[0]), {}),
        ((messages[0], copied_messages[1]), {}),
    ]
    subbot.callback_new_submission.assert_awaited_once_with(
        channel_tg_id=-10077,
        review_chat_id=-10055,
        review_message_id=501,
    )


@pytest.mark.asyncio
async def test_media_group_queue_debounces_until_all_items_arrive() -> None:
    subbot = SubBot.__new__(SubBot)
    subbot.MEDIA_GROUP_SETTLE_SECONDS = 0.01
    subbot._media_group_messages = {}
    subbot._media_group_flush_tasks = {}
    subbot._media_group_lock = asyncio.Lock()
    subbot._send_media_group_to_legacy_chat = AsyncMock()
    subbot.bot_info = SimpleNamespace(username="suggest_bot")
    subbot.chat_suggest = -10055

    first = _message(11)
    second = _message(12)
    await subbot._queue_media_group(first)
    await subbot._queue_media_group(second)
    await subbot._media_group_flush_tasks[(1001, "album-1")]

    subbot._send_media_group_to_legacy_chat.assert_awaited_once_with([first, second])
    assert subbot._media_group_messages == {}
    assert subbot._media_group_flush_tasks == {}


@pytest.mark.asyncio
async def test_legacy_approval_publishes_album_with_copy_messages(monkeypatch) -> None:
    bot = SimpleNamespace(
        token="1:test",
        get_chat=AsyncMock(return_value=SimpleNamespace(id=1001, username="author")),
        copy_messages=AsyncMock(
            return_value=[SimpleNamespace(message_id=701), SimpleNamespace(message_id=702)]
        ),
        copy_message=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
        send_message=AsyncMock(),
    )
    monkeypatch.setattr(
        "src.markups.should_add_publication_signature",
        AsyncMock(return_value=False),
    )
    call = SimpleNamespace(
        data="send_suggest;1001",
        message=SimpleNamespace(
            message_id=501,
            chat=SimpleNamespace(id=-10055),
            content_type="photo",
            text=None,
            caption="Album caption",
        ),
    )

    sent = await MarkupButton(bot).send_suggest(
        call,
        "@channel",
        -10077,
        False,
        "Channel",
        media_group_message_ids=[501, 502],
    )

    assert sent is True
    bot.copy_messages.assert_awaited_once_with(
        chat_id=-10077,
        from_chat_id=-10055,
        message_ids=[501, 502],
    )
    bot.copy_message.assert_not_awaited()


@pytest.mark.asyncio
async def test_panel_album_preview_uses_one_media_group_fallback() -> None:
    preview = SimpleNamespace(
        media_group_id="album-1",
        preview_file_ids=["photo-file", "video-file"],
        preview_file_sizes=[100, 200],
        preview_content_types=["photo", "video"],
        content_type="photo",
        channel_tg_id=-10077,
    )
    master = MasterBot.__new__(MasterBot)
    master.legacy_reader = SimpleNamespace(
        get_bot_binding=AsyncMock(return_value=SimpleNamespace(bot_api_token="2:test"))
    )
    master.main_bot = SimpleNamespace(send_message=AsyncMock())
    master._send_binary_preview_media_group = AsyncMock()
    master._send_binary_preview_item = AsyncMock()

    sent = await master._send_submission_preview_fallback(1001, preview)

    assert sent is True
    master._send_binary_preview_media_group.assert_awaited_once_with(
        chat_id=1001,
        bot_token="2:test",
        file_ids=["photo-file", "video-file"],
        content_types=["photo", "video"],
        default_content_type="photo",
    )
    master._send_binary_preview_item.assert_not_awaited()


@pytest.mark.asyncio
async def test_panel_prefers_rebuilt_album_over_separate_legacy_copies() -> None:
    preview = SimpleNamespace(
        media_group_id="album-1",
        preview_file_ids=["one", "two"],
        review_message_ids=[501, 502],
        review_chat_id=-10055,
    )
    master = MasterBot.__new__(MasterBot)
    master.editorial_actions = SimpleNamespace(
        get_submission_preview=AsyncMock(return_value=preview)
    )
    master._send_submission_preview_fallback = AsyncMock(return_value=True)
    master.main_bot = SimpleNamespace(copy_message=AsyncMock())

    await master._send_submission_preview(1001, 42)

    master._send_submission_preview_fallback.assert_awaited_once_with(1001, preview)
    master.main_bot.copy_message.assert_not_awaited()
