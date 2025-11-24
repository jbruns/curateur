import math
from collections import deque

import pytest

from curateur.api.throttle import ThrottleManager, RateLimit


@pytest.mark.unit
@pytest.mark.asyncio
async def test_wait_if_needed_records_calls_without_wait():
    throttle = ThrottleManager(default_limit=RateLimit(calls=2, window_seconds=60))

    waited1 = await throttle.wait_if_needed("jeuInfos.php")
    waited2 = await throttle.wait_if_needed("jeuInfos.php")

    assert waited1 == 0
    assert waited2 == 0
    stats = throttle.get_stats("jeuInfos.php")
    assert stats["recent_calls"] == 2
    assert stats["in_backoff"] is False


@pytest.mark.unit
def test_handle_rate_limit_sets_backoff_and_clears_history(monkeypatch):
    throttle = ThrottleManager(default_limit=RateLimit(calls=5, window_seconds=60))

    # Prime call history
    throttle.call_history["jeuInfos.php"] = deque([1, 2, 3])  # type: ignore[attr-defined]

    # Deterministic jitter
    monkeypatch.setattr("random.uniform", lambda a, b: 1.0)
    throttle.handle_rate_limit("jeuInfos.php", retry_after=10)

    stats = throttle.get_stats("jeuInfos.php")
    assert stats["in_backoff"] is True
    # With jitter=1 and first 429, multiplier should be 1.0
    assert math.isclose(stats["backoff_multiplier"], 1.0)
    # Call history cleared when adaptive
    assert throttle.call_history["jeuInfos.php"] == deque()  # type: ignore[attr-defined]


@pytest.mark.unit
def test_update_concurrency_limit_rescales_media_semaphore():
    throttle = ThrottleManager(default_limit=RateLimit(calls=10, window_seconds=60), max_concurrent=2)
    assert throttle.concurrency_semaphore._value == 2  # type: ignore[attr-defined]
    # Default media semaphore starts at 20
    assert throttle.media_download_semaphore._value == 20  # type: ignore[attr-defined]

    throttle.update_concurrency_limit(5)

    assert throttle.concurrency_semaphore._value == 5  # type: ignore[attr-defined]
    assert throttle.media_download_semaphore._value == 25  # type: ignore[attr-defined]
