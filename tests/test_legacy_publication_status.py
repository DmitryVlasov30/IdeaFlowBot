from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.editorial.models.enums import ContentItemStatus
from src.legacy_publication_status import LegacyPublicationStatusService


class _SessionContext:
    def __init__(self, session) -> None:
        self.session = session

    async def __aenter__(self):
        return self.session

    async def __aexit__(self, exc_type, exc, traceback) -> None:
        return None


@pytest.mark.asyncio
async def test_published_content_updates_legacy_review_with_approving_admin(monkeypatch) -> None:
    item = SimpleNamespace(
        id=11,
        status=ContentItemStatus.PUBLISHED,
        origin_submission_id=101,
    )
    submission = SimpleNamespace(id=101, channel_id=7, legacy_row_id=55, source_user_id=1001)
    channel = SimpleNamespace(tg_channel_id=-1007)
    approval = SimpleNamespace(reviewer_id=987654321)
    session = SimpleNamespace(
        get=AsyncMock(side_effect=[item, submission, channel]),
        scalar=AsyncMock(return_value=approval),
    )
    monkeypatch.setattr(
        "src.legacy_publication_status.session_factory",
        lambda: _SessionContext(session),
    )

    moderation = SimpleNamespace(get_related_submissions=AsyncMock(return_value=[submission]))
    review_row = SimpleNamespace(
        id=55,
        user_id=1001,
        review_chat_id=-100123,
        review_message_id=4321,
    )
    reader = SimpleNamespace(
        fetch_sender_rows_by_ids=AsyncMock(return_value=[review_row]),
        get_bot_binding=AsyncMock(return_value=SimpleNamespace(bot_api_token="1:token")),
    )
    bot = SimpleNamespace(
        get_chat_member=AsyncMock(
            return_value=SimpleNamespace(
                user=SimpleNamespace(username="review_admin", first_name="Admin")
            )
        ),
        get_chat=AsyncMock(),
        edit_message_reply_markup=AsyncMock(return_value=True),
        close_session=AsyncMock(),
    )
    monkeypatch.setattr(
        "src.editorial.services.telegram_publisher.AsyncTeleBot",
        lambda _token: bot,
    )

    updated = await LegacyPublicationStatusService(
        legacy_reader=reader,
        moderation=moderation,
    ).mark_content_item_published(item.id)

    assert updated == 1
    bot.get_chat_member.assert_awaited_once_with(review_row.review_chat_id, approval.reviewer_id)
    bot.get_chat.assert_not_awaited()
    edit_kwargs = bot.edit_message_reply_markup.await_args.kwargs
    assert edit_kwargs["chat_id"] == review_row.review_chat_id
    assert edit_kwargs["message_id"] == review_row.review_message_id
    assert edit_kwargs["reply_markup"].to_dict()["inline_keyboard"] == [
        [
            {
                "text": "@review_admin (опубликовано)",
                "callback_data": "add_info;1001",
            }
        ]
    ]
    bot.close_session.assert_awaited_once()
