import asyncio

import pytest

from curateur.api import error_handler
from curateur.api.error_handler import (
    RetryableAPIError,
    SkippableAPIError,
    FatalAPIError,
    ErrorCategory,
)


class StubThrottle:
    def __init__(self):
        self.calls = []

    def handle_rate_limit(self, endpoint, retry_after):
        self.calls.append((endpoint, retry_after))


@pytest.mark.unit
def test_handle_http_status_routes_errors_and_notifies_throttle():
    throttle = StubThrottle()
    with pytest.raises(RetryableAPIError):
        error_handler.handle_http_status(
            429,
            context="jeuInfos",
            throttle_manager=throttle,
            endpoint="jeuInfos.php",
            retry_after=12,
        )

    assert throttle.calls == [("jeuInfos.php", 12)]

    with pytest.raises(SkippableAPIError):
        error_handler.handle_http_status(404, context="missing")

    with pytest.raises(FatalAPIError):
        error_handler.handle_http_status(430, context="quota")


@pytest.mark.unit
@pytest.mark.asyncio
async def test_retry_with_backoff_retries_then_succeeds(monkeypatch):
    attempts = {"count": 0}

    async def flaky():
        attempts["count"] += 1
        if attempts["count"] < 3:
            raise RetryableAPIError("temporary")
        return "ok"

    # Avoid actual sleeping during backoff
    sleep_calls = []

    async def fake_sleep(duration):
        sleep_calls.append(duration)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    result = await error_handler.retry_with_backoff(
        flaky, max_attempts=4, initial_delay=0.1, backoff_factor=2.0, context="test"
    )

    assert result == "ok"
    assert attempts["count"] == 3
    assert sleep_calls == [0.1, 0.2]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_retry_with_backoff_stops_on_non_retryable():
    async def bad():
        raise SkippableAPIError("invalid request")

    with pytest.raises(SkippableAPIError):
        await error_handler.retry_with_backoff(bad, max_attempts=3)


@pytest.mark.unit
def test_categorize_error_mapping():
    retryable = RetryableAPIError("timeout")
    skip = SkippableAPIError("not found")
    fatal = FatalAPIError("fatal")

    assert error_handler.categorize_error(retryable)[1] == ErrorCategory.RETRYABLE
    assert error_handler.categorize_error(skip)[1] == ErrorCategory.NOT_FOUND
    assert error_handler.categorize_error(fatal)[1] == ErrorCategory.FATAL
