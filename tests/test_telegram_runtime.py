from src.telegram_runtime import calculate_telegram_request_limit


def test_request_limit_reserves_capacity_for_configured_max_subbots() -> None:
    assert calculate_telegram_request_limit(
        current_subbot_count=0,
        max_subbot_count=200,
        configured_limit=20,
    ) == 824


def test_request_limit_uses_current_count_when_it_exceeds_configured_max() -> None:
    assert calculate_telegram_request_limit(
        current_subbot_count=250,
        max_subbot_count=200,
        configured_limit=20,
    ) == 1024


def test_request_limit_respects_explicitly_higher_configured_limit() -> None:
    assert calculate_telegram_request_limit(
        current_subbot_count=51,
        max_subbot_count=200,
        configured_limit=1_000,
    ) == 1_000
