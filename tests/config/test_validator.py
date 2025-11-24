import pytest

from curateur.config.validator import validate_config, ValidationError


def _base_config(es_systems_path: str) -> dict:
    return {
        "screenscraper": {
            "user_id": "user",
            "user_password": "pass",
            "devid": "dev",
            "devpassword": "devpass",
            "softname": "curateur",
        },
        "paths": {
            "roms": "/roms",
            "media": "/media",
            "gamelists": "/gamelists",
            "es_systems": es_systems_path,
        },
        "scraping": {
            "systems": ["nes"],
            "preferred_regions": ["us", "eu"],
            "preferred_language": "en",
            "gamelist_integrity_threshold": 0.9,
            "scrape_mode": "changed",
            "name_verification": "normal",
        },
        "media": {"media_types": ["covers", "screenshots"], "validation_mode": "normal"},
        "api": {"request_timeout": 10, "max_retries": 3, "retry_backoff_seconds": 1, "quota_warning_threshold": 0.5},
        "logging": {"level": "INFO", "console": True, "file": None},
        "runtime": {
            "dry_run": True,
            "hash_algorithm": "crc32",
            "crc_size_limit": 1024,
            "enable_cache": True,
            "rate_limit_override_enabled": False,
            "rate_limit_override": {"max_workers": 1, "requests_per_minute": 60, "daily_quota": 10000},
        },
        "search": {"enable_search_fallback": True, "confidence_threshold": 0.7, "max_results": 5},
    }


@pytest.mark.unit
def test_validate_config_accepts_valid_config(tmp_path, es_systems_file):
    cfg = _base_config(str(es_systems_file))
    validate_config(cfg)  # Should not raise


@pytest.mark.unit
def test_validate_config_collects_errors(tmp_path):
    # Point es_systems to missing file to trigger path validation
    cfg = _base_config(str(tmp_path / "missing.xml"))
    cfg["screenscraper"]["user_id"] = ""
    cfg["scraping"]["gamelist_integrity_threshold"] = "bad"
    cfg["media"]["media_types"] = "covers"
    cfg["api"]["max_retries"] = "a lot"
    cfg["api"]["quota_warning_threshold"] = 2
    cfg["search"]["confidence_threshold"] = 2
    cfg["runtime"]["hash_algorithm"] = "xxhash"
    cfg["runtime"]["crc_size_limit"] = -1
    cfg["runtime"]["rate_limit_override_enabled"] = "yes"
    cfg["runtime"]["rate_limit_override"] = {"max_workers": 11}
    cfg["logging"]["file"] = 123

    with pytest.raises(ValidationError) as exc:
        validate_config(cfg)

    msg = str(exc.value)
    assert "screenscraper.user_id is required" in msg
    assert "paths.es_systems file not found" in msg
    assert "gamelist_integrity_threshold must be between 0.0 and 1.0" in msg or "must be a number" in msg
    assert "media.media_types must be a list" in msg
    assert "api.max_retries must be an integer" in msg
    assert "api.quota_warning_threshold must be between 0.0 and 1.0" in msg
    assert "search.confidence_threshold must be between 0.0 and 1.0" in msg
    assert "runtime.hash_algorithm must be one of" in msg
    assert "runtime.crc_size_limit must be a non-negative integer" in msg
    assert "runtime.rate_limit_override_enabled must be a boolean" in msg
    assert "runtime.rate_limit_override.max_workers must be between 1 and 10" in msg
    assert "logging.file must be a string path or null" in msg

