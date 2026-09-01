from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.editorial.services.advertising import (
    build_advertising_alert_text,
    send_advertising_flow,
)


def test_advertising_alert_contains_clickable_submission_author_id() -> None:
    text = build_advertising_alert_text(
        channel_label="@channel",
        source_text="Хочу рекламу",
        sender_user_id=123456789,
        sender_username="submission_author",
        sender_first_name="Author",
    )

    assert "отправитель: @submission_author" in text
    assert 'tg id: <a href="tg://user?id=123456789">123456789</a>' in text


@pytest.mark.asyncio
async def test_advertising_flow_uses_recipient_as_linked_submission_author(monkeypatch) -> None:
    source_bot = SimpleNamespace(send_message=AsyncMock())
    alert_bot = SimpleNamespace(send_message=AsyncMock())
    monkeypatch.setattr(
        "src.editorial.services.advertising._build_advertising_alert_bot",
        lambda: alert_bot,
    )
    monkeypatch.setattr(
        "src.editorial.services.advertising.resolve_advertising_targets",
        lambda: [9001],
    )

    await send_advertising_flow(
        bot=source_bot,
        recipient_user_id=123456789,
        channel_label="@channel",
        source_text="Хочу рекламу",
        sender_username="submission_author",
        sender_first_name="Author",
    )

    source_bot.send_message.assert_awaited_once()
    assert source_bot.send_message.await_args.kwargs["chat_id"] == 123456789
    alert_bot.send_message.assert_awaited_once()
    alert_kwargs = alert_bot.send_message.await_args.kwargs
    assert alert_kwargs["chat_id"] == 9001
    assert alert_kwargs["parse_mode"] == "HTML"
    assert 'href="tg://user?id=123456789"' in alert_kwargs["text"]
