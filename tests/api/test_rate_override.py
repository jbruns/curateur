import pytest

from curateur.api.rate_override import RateLimitOverride


@pytest.mark.unit
def test_rate_override_applies_api_limits_when_disabled():
    config = {"runtime": {"rate_limit_override_enabled": False}}
    override = RateLimitOverride(config)
    limits = override.get_effective_limits({"maxthreads": 3, "maxrequestspermin": 90, "maxrequestsperday": 5000})
    assert limits.max_threads == 3
    assert limits.requests_per_minute == 90
    assert limits.daily_quota == 5000
    assert override.is_enabled() is False
    assert "DISABLED" in override.get_override_summary()


@pytest.mark.unit
def test_rate_override_caps_user_values_and_warns():
    config = {
        "runtime": {
            "rate_limit_override_enabled": True,
            "rate_limit_override": {"max_threads": 10, "requests_per_minute": 200, "daily_quota": 30000},
        }
    }
    override = RateLimitOverride(config)
    limits = override.get_effective_limits({"maxthreads": 4, "maxrequestspermin": 120, "maxrequestsperday": 20000})
    assert limits.max_threads == 4  # capped
    assert limits.requests_per_minute == 120  # capped
    assert limits.daily_quota == 20000  # capped
    assert override.is_enabled() is True
    summary = override.get_override_summary()
    assert "max_threads" in summary and "requests_per_minute" in summary
