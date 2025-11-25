import argparse
from pathlib import Path

import pytest

import curateur.cli as cli
from curateur.config.loader import ConfigError


def _minimal_config(tmp_path: Path) -> dict:
    return {
        "logging": {"console": False},
        "scraping": {"systems": [], "preferred_regions": ["us"], "name_verification": "normal"},
        "runtime": {"dry_run": False},
        "paths": {
            "roms": str(tmp_path),
            "media": str(tmp_path),
            "gamelists": str(tmp_path),
            "es_systems": str(tmp_path / "es_systems.xml"),
        },
    }


def test_create_parser_includes_flags():
    parser = cli.create_parser()
    args = parser.parse_args(["--dry-run", "--enable-search", "--search-threshold", "0.8", "--interactive-search"])
    assert args.dry_run is True
    assert args.enable_search is True
    assert args.search_threshold == 0.8
    assert args.interactive_search is True


def test_main_handles_config_error(monkeypatch):
    monkeypatch.setattr(cli, "load_config", lambda path=None: (_ for _ in ()).throw(ConfigError("bad config")))
    code = cli.main([])
    assert code == 1


def test_main_applies_overrides_and_calls_runner(monkeypatch, tmp_path):
    cfg = _minimal_config(tmp_path)

    def fake_load_config(path=None):
        return cfg.copy()

    called = {}

    async def fake_run_scraper(config, args):
        called["config"] = config
        called["args"] = args
        return 0

    monkeypatch.setattr(cli, "load_config", fake_load_config)
    monkeypatch.setattr(cli, "validate_config", lambda config: None)
    monkeypatch.setattr(cli, "run_scraper", fake_run_scraper)

    code = cli.main(["--dry-run", "--systems", "nes", "snes"])
    assert code == 0
    assert called["config"]["runtime"]["dry_run"] is True
    assert called["config"]["scraping"]["systems"] == ["nes", "snes"]
