from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.editorial.models.enums import ContentFamily, PasteDeliveryMode, PasteStatus
from src.editorial.models.paste import PasteLibrary
from src.editorial.services.confession_service import ConfessionService
from src.editorial.services.paste_service import PasteAvailabilityContext
from src.editorial.services.publisher import PublisherService
from src.confession_publisher import ConfessionPublisherRuntime


def _paste(paste_id: int, family: str) -> PasteLibrary:
    paste = PasteLibrary(
        title=f"paste-{paste_id}",
        body_text=f"body-{paste_id}",
        normalized_text=f"body-{paste_id}",
        text_hash=f"hash-{paste_id}",
        content_family=family,
        delivery_mode=(
            PasteDeliveryMode.TELEGRAM_COPY.value
            if family == ContentFamily.CONFESSION.value
            else PasteDeliveryMode.TEXT.value
        ),
        tags=[],
        status=PasteStatus.ACTIVE,
        global_cooldown_days=0,
        per_channel_cooldown_days=0,
        allow_all_channels=True,
        min_channel_activity_score=0,
    )
    paste.id = paste_id
    return paste


def test_confession_channel_only_receives_confession_pastes() -> None:
    ordinary = _paste(1, ContentFamily.OVERHEARD.value)
    confession = _paste(2, ContentFamily.CONFESSION.value)
    context = PasteAvailabilityContext(
        reference_now=datetime(2026, 8, 27, tzinfo=timezone.utc),
        channel_ids=frozenset({10}),
        pastes=[ordinary, confession],
        channel_families={10: ContentFamily.CONFESSION.value},
        global_included={"ordinary-only-rule"},
    )

    assert context.available_for_channel(10) == [confession]


@pytest.mark.parametrize(
    ("text", "caption", "expected"),
    [
        ("/ служебное сообщение", None, True),
        ("   /не сохранять", None, True),
        (None, "/ подпись к фото", True),
        ("обычная паста / со слешем внутри", None, False),
        (None, "обычная подпись", False),
    ],
)
def test_slash_prefix_marks_storage_message_as_service(
    text: str | None,
    caption: str | None,
    expected: bool,
) -> None:
    message = SimpleNamespace(text=text, caption=caption)

    assert ConfessionPublisherRuntime._is_service_message(message) is expected


@pytest.mark.asyncio
async def test_confession_paste_is_published_with_copy_message() -> None:
    paste = _paste(2, ContentFamily.CONFESSION.value)
    paste.storage_chat_id = -100500
    paste.storage_message_id = 77
    session = SimpleNamespace(get=AsyncMock(return_value=paste))
    adapter = SimpleNamespace(copy_message=AsyncMock(return_value=901))
    service = PublisherService(telegram_adapter=adapter)
    item = SimpleNamespace(origin_paste_id=paste.id)
    channel = SimpleNamespace(tg_channel_id=-100700)

    message_id = await service._publish_submission_based_item(
        session,
        item,
        channel,
        "123:publisher",
    )

    assert message_id == 901
    adapter.copy_message.assert_awaited_once_with(
        bot_token="123:publisher",
        channel_id=-100700,
        from_chat_id=-100500,
        message_id=77,
    )


@pytest.mark.asyncio
async def test_storage_message_becomes_telegram_copy_paste() -> None:
    publisher = SimpleNamespace(id=3, is_active=True, storage_chat_id=-100500)
    session = SimpleNamespace(
        get=AsyncMock(return_value=publisher),
        scalar=AsyncMock(return_value=None),
        add=Mock(),
        commit=AsyncMock(),
        refresh=AsyncMock(),
    )

    paste, created = await ConfessionService().create_storage_paste(
        session,
        publisher_id=3,
        storage_chat_id=-100500,
        storage_message_id=77,
        content_type="sticker",
        body_text="💘",
        created_by=42,
    )

    assert created is True
    assert paste.content_family == ContentFamily.CONFESSION.value
    assert paste.delivery_mode == PasteDeliveryMode.TELEGRAM_COPY.value
    assert paste.storage_chat_id == -100500
    assert paste.storage_message_id == 77
    session.add.assert_called_once_with(paste)
