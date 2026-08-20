import asyncio
from datetime import timedelta

import pytest

from src.editorial.services.telegram_resilience import (
    TelegramAPIError,
    TelegramOperationTimeout,
    is_transient_telegram_error,
    publisher_retry_delay,
    run_telegram_operation,
    telegram_retry_after_seconds,
)


@pytest.mark.asyncio
async def test_telegram_operation_has_hard_wall_clock_timeout() -> None:
    with pytest.raises(TelegramOperationTimeout, match="sendMessage exceeded"):
        await run_telegram_operation(
            asyncio.sleep(0.05),
            operation="sendMessage",
            timeout_seconds=0.001,
        )


def test_timeout_gateway_and_rate_limit_errors_are_transient() -> None:
    assert is_transient_telegram_error(TimeoutError("timed out"))
    assert is_transient_telegram_error(RuntimeError("504 Gateway Timeout"))
    assert is_transient_telegram_error(RuntimeError("Too Many Requests: retry after 8"))
    assert not is_transient_telegram_error(RuntimeError("400 Bad Request: chat not found"))


def test_retry_after_from_telegram_is_respected(monkeypatch) -> None:
    class TooManyRequests(Exception):
        error_code = 429
        result_json = {"parameters": {"retry_after": 120}}

    error = TooManyRequests("rate limited")
    assert telegram_retry_after_seconds(error) == 120
    assert publisher_retry_delay(1, error) == timedelta(seconds=120)


def test_structured_api_error_preserves_retry_after() -> None:
    error = TelegramAPIError(
        {
            "ok": False,
            "error_code": 429,
            "description": "Too Many Requests",
            "parameters": {"retry_after": 180},
        }
    )

    assert is_transient_telegram_error(error)
    assert telegram_retry_after_seconds(error) == 180
    assert publisher_retry_delay(1, error) == timedelta(seconds=180)
