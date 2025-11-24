from pathlib import Path

import httpx
import pytest
import respx

from curateur.api.cache import MetadataCache
from curateur.api.client import ScreenScraperClient
from curateur.api.throttle import ThrottleManager, RateLimit
from curateur.scanner.rom_types import ROMInfo, ROMType


def _base_config() -> dict:
    return {
        "screenscraper": {
            "devid": "dev",
            "devpassword": "devpass",
            "softname": "curateur",
            "user_id": "user",
            "user_password": "pass",
        },
        "api": {"request_timeout": 5, "max_retries": 1},
        "scraping": {"name_verification": "normal", "scrape_mode": "changed"},
    }


@pytest.mark.unit
def test_build_redacted_url_hides_credentials():
    client = ScreenScraperClient(
        config=_base_config(),
        throttle_manager=ThrottleManager(RateLimit(calls=10, window_seconds=60)),
        client=None,
        cache=None,
    )
    url = "https://api.screenscraper.fr/api2/jeuInfos.php"
    redacted = client._build_redacted_url(url, {"devpassword": "secret", "sspassword": "pw"})
    assert "secret" not in redacted
    assert "pw" not in redacted
    assert "redacted" in redacted


@pytest.mark.integration
@pytest.mark.asyncio
async def test_query_game_parses_response_and_updates_cache(tmp_path: Path):
    throttle = ThrottleManager(RateLimit(calls=10, window_seconds=60))
    cache = MetadataCache(gamelist_directory=tmp_path)
    config = _base_config()

    rom_path = tmp_path / "Alpha Quest.nes"
    rom_info = ROMInfo(
        path=rom_path,
        filename="Alpha Quest.nes",
        basename="Alpha Quest",
        rom_type=ROMType.STANDARD,
        system="nes",
        query_filename="Alpha Quest.nes",
        file_size=2048,
        hash_value="ABC123",
    )

    xml = b"""
    <Data>
      <ssuser>
        <id>1</id><niveau>1</niveau><maxthreads>3</maxthreads>
        <maxrequestspermin>60</maxrequestspermin>
        <requeststoday>10</requeststoday>
        <maxrequestsperday>200</maxrequestsperday>
        <requestskotoday>0</requestskotoday>
        <maxrequestskoperday>10</maxrequestskoperday>
      </ssuser>
      <jeu id="99">
        <noms><nom region="us">Alpha Quest</nom></noms>
        <systeme>nes</systeme>
        <medias>
          <media type="screenshot" format="png" region="us">http://example/shot.png</media>
        </medias>
      </jeu>
    </Data>
    """

    async with httpx.AsyncClient() as http_client:
        client = ScreenScraperClient(
            config=config,
            throttle_manager=throttle,
            client=http_client,
            cache=cache,
        )

        with respx.mock(assert_all_called=True) as mock:
            mock.get("https://api.screenscraper.fr/api2/jeuInfos.php").respond(200, content=xml)

            result = await client.query_game(rom_info)

    assert result["name"] == "Alpha Quest"
    assert result["media"]["screenshot"][0]["url"].endswith("shot.png")

    cached = cache.get("ABC123", rom_size=2048)
    assert cached and cached["response"]["name"] == "Alpha Quest"
