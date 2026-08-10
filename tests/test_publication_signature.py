from src.editorial.models.channel import Channel
from src.editorial.services.publisher import PublisherService
from src.editorial.services.publication_signature import (
    channel_publication_signature_html,
    format_publication_html,
    publication_signature_skip_bot_username,
    publication_signature_html,
    should_add_publication_signature,
)
import src.editorial.services.publication_signature as signature_service

import pytest


def test_publication_signature_uses_title_as_link_label() -> None:
    signature = publication_signature_html(title="Подслушано РУТ МИИТ", channel_ref="@MIITrussia")

    assert signature == '<a href="https://t.me/MIITrussia"><i>Подслушано РУТ МИИТ</i></a>'


def test_format_publication_html_appends_signature_after_blank_line() -> None:
    text = format_publication_html(
        "Как проходят семинары у Стоюхина?",
        signature_html='<a href="https://t.me/MIITrussia"><i>Подслушано РУТ МИИТ</i></a>',
    )

    assert text == (
        "Как проходят семинары у Стоюхина?\n\n"
        '<a href="https://t.me/MIITrussia"><i>Подслушано РУТ МИИТ</i></a>'
    )


def test_channel_publication_signature_escapes_title() -> None:
    channel = Channel(
        tg_channel_id=-1001,
        short_code="MIITrussia",
        title="Подслушано <РУТ>",
    )

    assert channel_publication_signature_html(channel, "@MIITrussia") == (
        '<a href="https://t.me/MIITrussia"><i>Подслушано &lt;РУТ&gt;</i></a>'
    )


def test_publisher_signature_is_disabled_by_default(monkeypatch) -> None:
    monkeypatch.delenv("PUBLICATION_SIGNATURE_ENABLED", raising=False)
    channel = Channel(tg_channel_id=-1001, short_code="MIITrussia", title="Подслушано РУТ МИИТ")

    assert PublisherService().format_publication_text("Текст", channel, channel_signature="@MIITrussia") == "Текст"
    assert PublisherService.publication_parse_mode() is None


def test_publisher_signature_can_be_enabled(monkeypatch) -> None:
    monkeypatch.setenv("PUBLICATION_SIGNATURE_ENABLED", "true")
    channel = Channel(tg_channel_id=-1001, short_code="MIITrussia", title="Подслушано РУТ МИИТ")

    assert PublisherService().format_publication_text("Текст", channel, channel_signature="@MIITrussia") == (
        'Текст\n\n<a href="https://t.me/MIITrussia"><i>Подслушано РУТ МИИТ</i></a>'
    )
    assert PublisherService.publication_parse_mode() == "HTML"


def test_publication_signature_skip_bot_username_normalizes_env(monkeypatch) -> None:
    monkeypatch.setenv("PUBLICATION_SIGNATURE_SKIP_IF_ADMIN_BOT_USERNAME", " @OtherSignatureBot ")

    assert publication_signature_skip_bot_username() == "othersignaturebot"


def test_publisher_signature_can_be_suppressed_for_channel(monkeypatch) -> None:
    monkeypatch.setenv("PUBLICATION_SIGNATURE_ENABLED", "true")
    channel = Channel(tg_channel_id=-1001, short_code="MIITrussia", title="Podslushano")

    assert PublisherService().format_publication_text(
        "Text",
        channel,
        channel_signature="@MIITrussia",
        add_channel_signature=False,
    ) == "Text"


@pytest.mark.asyncio
async def test_should_add_publication_signature_skips_when_configured_bot_is_admin(monkeypatch) -> None:
    monkeypatch.setenv("PUBLICATION_SIGNATURE_ENABLED", "true")
    monkeypatch.setenv("PUBLICATION_SIGNATURE_SKIP_IF_ADMIN_BOT_USERNAME", "@OtherSignatureBot")

    async def fake_channel_has_signature_skip_bot(*, bot_token: str, channel_id: int) -> bool:
        assert bot_token == "token"
        assert channel_id == -1001
        return True

    monkeypatch.setattr(signature_service, "channel_has_signature_skip_bot", fake_channel_has_signature_skip_bot)

    assert await should_add_publication_signature(bot_token="token", channel_id=-1001) is False


@pytest.mark.asyncio
async def test_should_add_publication_signature_keeps_signature_when_skip_bot_is_absent(monkeypatch) -> None:
    monkeypatch.setenv("PUBLICATION_SIGNATURE_ENABLED", "true")
    monkeypatch.setenv("PUBLICATION_SIGNATURE_SKIP_IF_ADMIN_BOT_USERNAME", "@OtherSignatureBot")

    async def fake_channel_has_signature_skip_bot(*, bot_token: str, channel_id: int) -> bool:
        return False

    monkeypatch.setattr(signature_service, "channel_has_signature_skip_bot", fake_channel_has_signature_skip_bot)

    assert await should_add_publication_signature(bot_token="token", channel_id=-1001) is True
