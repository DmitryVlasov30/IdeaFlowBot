from types import SimpleNamespace

import pytest

from src.utils import Utils


def _message(text=None, caption=None, entities=None, caption_entities=None, reply_markup=None):
    return SimpleNamespace(
        text=text,
        caption=caption,
        entities=entities,
        caption_entities=caption_entities,
        reply_markup=reply_markup,
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


@pytest.mark.asyncio
async def test_check_link_detects_external_inline_button() -> None:
    message = _message(
        text="Реклама",
        reply_markup=SimpleNamespace(
            keyboard=[[SimpleNamespace(url="https://advertiser.example", login_url=None, web_app=None)]],
        ),
    )

    assert await Utils.check_link(message, ignored_channel_ref="@MIITrussia")


@pytest.mark.asyncio
async def test_check_link_ignores_own_channel_inline_button() -> None:
    message = _message(
        text="Наш канал",
        reply_markup=SimpleNamespace(
            keyboard=[[SimpleNamespace(url="https://t.me/MIITrussia/123", login_url=None, web_app=None)]],
        ),
    )

    assert not await Utils.check_link(message, ignored_channel_ref="@MIITrussia")
