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
        "api": {"request_timeout": 10, "max_retries": 3, "retry_backoff_seconds": 1},
        "logging": {"level": "INFO", "console": True},
        "runtime": {"dry_run": True, "threads": 2},
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
    cfg["search"]["confidence_threshold"] = 2

    with pytest.raises(ValidationError) as exc:
        validate_config(cfg)

    msg = str(exc.value)
    assert "screenscraper.user_id is required" in msg
    assert "paths.es_systems file not found" in msg
    assert "gamelist_integrity_threshold must be between 0.0 and 1.0" in msg or "must be a number" in msg
    assert "media.media_types must be a list" in msg
    assert "api.max_retries must be an integer" in msg
    assert "search.confidence_threshold must be between 0.0 and 1.0" in msg
