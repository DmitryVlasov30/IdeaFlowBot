from src.legacy_delayed import delayed_publication_matches


def test_stale_delayed_publication_is_not_current_after_reschedule() -> None:
    delayed_message = {123: [2_000, 456]}

    assert not delayed_publication_matches(
        delayed_message,
        message_id=123,
        sender_id=456,
        expected_time=1_000,
    )


def test_current_delayed_publication_matches_latest_time() -> None:
    delayed_message = {123: [2_000, 456]}

    assert delayed_publication_matches(
        delayed_message,
        message_id=123,
        sender_id=456,
        expected_time=2_000,
    )


def test_cancelled_delayed_publication_is_not_current() -> None:
    assert not delayed_publication_matches(
        {},
        message_id=123,
        sender_id=456,
        expected_time=2_000,
    )
