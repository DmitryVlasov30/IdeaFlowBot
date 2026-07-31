from src.editorial.models.channel import Channel
from src.editorial.services.publisher import PublisherService
from src.editorial.services.publication_signature import (
    channel_publication_signature_html,
    format_publication_html,
    publication_signature_html,
)


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
