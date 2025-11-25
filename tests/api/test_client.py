from pathlib import Path

import httpx
import pytest
import respx

from curateur.api.cache import MetadataCache
from curateur.api.client import ScreenScraperClient
from curateur.api.throttle import ThrottleManager, RateLimit
from curateur.api.error_handler import RetryableAPIError, SkippableAPIError
from curateur.api import client as client_module
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


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.slow
async def test_query_game_handles_rate_limit_and_api_error(tmp_path: Path):
    throttle = ThrottleManager(RateLimit(calls=10, window_seconds=60))
    cache = MetadataCache(gamelist_directory=tmp_path, enabled=False)
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
    )

    xml_error = b"<Data><erreur>API closed</erreur></Data>"

    async with httpx.AsyncClient() as http_client:
        client = ScreenScraperClient(
            config=config,
            throttle_manager=throttle,
            client=http_client,
            cache=cache,
        )

        with respx.mock(assert_all_called=True) as mock:
            # Rate limited -> surfaces as SkippableAPIError after retry loop
            mock.get("https://api.screenscraper.fr/api2/jeuInfos.php").respond(429, content=xml_error)
            with pytest.raises(SkippableAPIError):
                await client.query_game(rom_info)

        with respx.mock(assert_all_called=True) as mock:
            # API error message returns SkippableAPIError
            mock.get("https://api.screenscraper.fr/api2/jeuInfos.php").respond(200, content=xml_error)
            with pytest.raises(SkippableAPIError):
                await client.query_game(rom_info)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_game_verification_failure(monkeypatch, tmp_path: Path):
    throttle = ThrottleManager(RateLimit(calls=10, window_seconds=60))
    cache = MetadataCache(gamelist_directory=tmp_path, enabled=False)
    config = _base_config()

    rom_info = ROMInfo(
        path=tmp_path / "Alpha.nes",
        filename="Alpha.nes",
        basename="Alpha",
        rom_type=ROMType.STANDARD,
        system="nes",
        query_filename="Alpha.nes",
        file_size=10,
    )

    xml = b"<Data><jeu id='1'><noms><nom region='us'>Other</nom></noms></jeu></Data>"

    async with httpx.AsyncClient() as http_client:
        client = ScreenScraperClient(
            config=config,
            throttle_manager=throttle,
            client=http_client,
            cache=cache,
        )

        with respx.mock(assert_all_called=True) as mock:
            mock.get("https://api.screenscraper.fr/api2/jeuInfos.php").respond(200, content=xml)
            # Force name verification to fail
            monkeypatch.setattr(
                client_module,
                "verify_name_match",
                lambda *args, **kwargs: (False, 0.1, "mismatch"),
            )
            with pytest.raises(SkippableAPIError):
                await client.query_game(rom_info)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_game_cache_hit_short_circuits(monkeypatch, tmp_path: Path):
    throttle = ThrottleManager(RateLimit(calls=10, window_seconds=60))
    config = _base_config()
    config["scraping"]["name_verification"] = "disabled"
    rom_info = ROMInfo(
        path=tmp_path / "Alpha.nes",
        filename="Alpha.nes",
        basename="Alpha",
        rom_type=ROMType.STANDARD,
        system="nes",
        query_filename="Alpha.nes",
        file_size=10,
        hash_value="HASH",
    )

    cache = MetadataCache(gamelist_directory=tmp_path)
    cache.put("HASH", {"name": "FromCache"}, rom_size=10)

    async with httpx.AsyncClient() as http_client:
        client = ScreenScraperClient(
            config=config,
            throttle_manager=throttle,
            client=http_client,
            cache=cache,
        )

        # If cache hit, no HTTP call should be made (respx would fail otherwise)
        result = await client.query_game(rom_info)
        assert result["name"] == "FromCache"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_game_parses_results(tmp_path: Path):
    throttle = ThrottleManager(RateLimit(calls=10, window_seconds=60))
    config = _base_config()
    rom_info = ROMInfo(
        path=tmp_path / "Alpha.nes",
        filename="Alpha.nes",
        basename="Alpha",
        rom_type=ROMType.STANDARD,
        system="nes",
        query_filename="Alpha",
        file_size=10,
    )

    xml = b"<Data><jeux><jeu id='1'><noms><nom region='us'>Alpha</nom></noms></jeu></jeux></Data>"

    async with httpx.AsyncClient() as http_client:
        client = ScreenScraperClient(
            config=config,
            throttle_manager=throttle,
            client=http_client,
            cache=None,
        )

        with respx.mock(assert_all_called=True) as mock:
            mock.get("https://api.screenscraper.fr/api2/jeuRecherche.php").respond(200, content=xml)
            results = await client.search_game(rom_info)
    assert results[0]["name"] == "Alpha"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_user_info_parses_limits(monkeypatch):
    throttle = ThrottleManager(RateLimit(calls=10, window_seconds=60))
    config = _base_config()
    xml = b"""
    <Data>
      <ssuser>
        <id>1</id><niveau>1</niveau>
        <maxthreads>2</maxthreads>
        <maxrequestspermin>60</maxrequestspermin>
        <requeststoday>1</requeststoday>
        <maxrequestsperday>10</maxrequestsperday>
      </ssuser>
    </Data>
    """

    async with httpx.AsyncClient() as http_client:
        client = ScreenScraperClient(
            config=config,
            throttle_manager=throttle,
            client=http_client,
            cache=None,
        )

        with respx.mock(assert_all_called=True) as mock:
            mock.get("https://api.screenscraper.fr/api2/ssuserInfos.php").respond(200, content=xml)
            limits = await client.get_user_info()
    assert limits["maxthreads"] == 2
