from types import SimpleNamespace

import pytest

from src.utils import Utils


def _message(text=None, caption=None, entities=None, caption_entities=None):
    return SimpleNamespace(
        text=text,
        caption=caption,
        entities=entities,
        caption_entities=caption_entities,
    )


def _text_link(url: str):
    return SimpleNamespace(type="text_link", url=url)


@pytest.mark.asyncio
async def test_check_link_ignores_own_channel_text_link() -> None:
    message = _message(
        text="Подслушано РУТ МИИТ",
        entities=[_text_link("https://t.me/MIITrussia")],
    )

    assert not await Utils.check_link(message, ignored_channel_ref="@MIITrussia")


@pytest.mark.asyncio
async def test_check_link_detects_external_text_link() -> None:
    message = _message(
        text="Реклама",
        entities=[_text_link("https://example.com")],
    )

    assert await Utils.check_link(message, ignored_channel_ref="@MIITrussia")


@pytest.mark.asyncio
async def test_check_link_detects_external_link_when_own_link_is_present() -> None:
    message = _message(
        text="https://t.me/MIITrussia https://example.com",
    )

    assert await Utils.check_link(message, ignored_channel_ref="@MIITrussia")


@pytest.mark.asyncio
async def test_check_link_ignores_own_raw_channel_link() -> None:
    message = _message(text="https://t.me/MIITrussia")

    assert not await Utils.check_link(message, ignored_channel_ref="@MIITrussia")
