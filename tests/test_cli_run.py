import argparse
from pathlib import Path

import pytest

import curateur.cli as cli
from curateur.workflow.orchestrator import SystemResult
from curateur.config.es_systems import SystemDefinition


class DummyConnectionPool:
    def __init__(self, config):
        self.config = config
        self.client = DummyHTTPClient()

    def create_client(self, max_connections=10):
        return self.client


class DummyHTTPClient:
    def __init__(self):
        self.closed = False

    async def aclose(self):
        self.closed = True


class DummyAPIClient:
    def __init__(self, *args, **kwargs):
        self.cache = None
        self.client = None

    async def get_user_info(self):
        return {"maxthreads": 1, "maxrequestspermin": 60, "requeststoday": 0, "maxrequestsperday": 10}


class DummyThreadPool:
    def __init__(self, *args, **kwargs):
        self.max_concurrent = 1
        self.shutdown_called = False
        self.stopped = False

    def initialize_pools(self, limits=None):
        self.max_concurrent = limits.get("maxthreads", 1) if limits else 1

    async def stop_workers(self):
        self.stopped = True

    async def shutdown(self, wait=True):
        self.shutdown_called = True


class DummyOrchestrator:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    async def scrape_system(self, system, media_types, preferred_regions, progress_tracker=None):
        return SystemResult(
            system_name=system.fullname,
            total_roms=0,
            scraped=0,
            failed=0,
            skipped=0,
            results=[],
        )


@pytest.mark.asyncio
async def test_run_scraper_happy_path(monkeypatch, tmp_path: Path, capsys):
    # Minimal config and paths
    roms = tmp_path / "roms"
    media = tmp_path / "media"
    gamelists = tmp_path / "gamelists"
    for d in (roms, media, gamelists):
        d.mkdir()

    config = {
        "logging": {"console": False},
        "scraping": {"systems": [], "preferred_regions": ["us"], "name_verification": "normal"},
        "runtime": {"dry_run": True},
        "paths": {
            "roms": str(roms),
            "media": str(media),
            "gamelists": str(gamelists),
            "es_systems": str(tmp_path / "es_systems.xml"),
        },
        "media": {"media_types": ["covers"]},
        "api": {"request_timeout": 5, "max_retries": 1},
        "search": {},
    }

    # Fake system definitions
    fake_system = SystemDefinition(
        name="nes",
        fullname="NES",
        path=str(roms),
        extensions=[".nes"],
        platform="nes",
    )

    monkeypatch.setattr(cli, "parse_es_systems", lambda path: [fake_system])
    monkeypatch.setattr(cli, "ConnectionPoolManager", DummyConnectionPool, raising=False)
    monkeypatch.setattr(cli, "ScreenScraperClient", DummyAPIClient, raising=False)
    monkeypatch.setattr(cli, "ThreadPoolManager", DummyThreadPool, raising=False)
    monkeypatch.setattr(cli, "WorkflowOrchestrator", DummyOrchestrator, raising=False)
    monkeypatch.setattr(cli, "scan_system", lambda *args, **kwargs: [], raising=False)

    args = argparse.Namespace(clear_cache=False)

    code = await cli.run_scraper(config, args)
    assert code == 0

    out = capsys.readouterr().out
    assert "curateur v" in out


@pytest.mark.asyncio
async def test_run_scraper_parse_error(monkeypatch, tmp_path: Path):
    config = {
        "logging": {"console": False},
        "scraping": {"systems": [], "preferred_regions": ["us"], "name_verification": "normal"},
        "runtime": {"dry_run": True},
        "paths": {
            "roms": str(tmp_path),
            "media": str(tmp_path),
            "gamelists": str(tmp_path),
            "es_systems": str(tmp_path / "es_systems.xml"),
        },
        "media": {"media_types": ["covers"]},
        "api": {"request_timeout": 5, "max_retries": 1},
        "search": {},
    }

    monkeypatch.setattr(cli, "parse_es_systems", lambda path: (_ for _ in ()).throw(Exception("bad es")))

    code = await cli.run_scraper(config, argparse.Namespace(clear_cache=False))
    assert code == 1
