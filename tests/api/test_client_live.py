import os
from pathlib import Path

import httpx
import pytest

from curateur.api.client import ScreenScraperClient
from curateur.api.throttle import ThrottleManager, RateLimit
from curateur.scanner.rom_types import ROMInfo, ROMType


def _live_config() -> dict:
    return {
        "screenscraper": {
            "devid": os.getenv("SCREENSCRAPER_DEV_ID", ""),
            "devpassword": os.getenv("SCREENSCRAPER_DEV_PASSWORD", ""),
            "softname": os.getenv("SCREENSCRAPER_SOFTNAME", "curateur_live_test"),
            "user_id": os.getenv("SCREENSCRAPER_USER_ID", ""),
            "user_password": os.getenv("SCREENSCRAPER_USER_PASSWORD", ""),
        },
        "api": {"request_timeout": 10, "max_retries": 1},
        "scraping": {"name_verification": "normal", "scrape_mode": "changed"},
    }


def _has_creds() -> bool:
    envs = [
        "SCREENSCRAPER_DEV_ID",
        "SCREENSCRAPER_DEV_PASSWORD",
        "SCREENSCRAPER_USER_ID",
        "SCREENSCRAPER_USER_PASSWORD",
    ]
    return all(os.getenv(e) for e in envs)


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_ssuserinfos_auth(monkeypatch):
    if not _has_creds():
        pytest.skip("Live credentials not provided")

    config = _live_config()
    throttle = ThrottleManager(RateLimit(calls=60, window_seconds=60))

    async with httpx.AsyncClient() as http_client:
        client = ScreenScraperClient(
            config=config,
            throttle_manager=throttle,
            client=http_client,
            cache=None,
        )
        info = await client.get_user_info()

    assert "niveau" in info
    assert info["niveau"] == 1


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_search_game(monkeypatch, tmp_path: Path):
    if not _has_creds():
        pytest.skip("Live credentials not provided")

    config = _live_config()
    throttle = ThrottleManager(RateLimit(calls=60, window_seconds=60))
    rom_info = ROMInfo(
        path=tmp_path / "Super Mario Bros.nes",
        filename="Super Mario Bros.nes",
        basename="Super Mario Bros",
        rom_type=ROMType.STANDARD,
        system="nes",
        query_filename="Super Mario Bros",
        file_size=1024,
    )

    async with httpx.AsyncClient() as http_client:
        client = ScreenScraperClient(
            config=config,
            throttle_manager=throttle,
            client=http_client,
            cache=None,
        )
        results = await client.search_game(rom_info, max_results=2)

    assert isinstance(results, list)
    assert results, "Expected at least one search result"
