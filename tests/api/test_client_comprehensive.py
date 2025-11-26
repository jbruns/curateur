"""
- get_user_info error handling
- search_game functionality
- Name verification scenarios
- Cache miss scenarios
- Error handling paths
- Shutdown scenarios
"""

from pathlib import Path
from unittest.mock import Mock, AsyncMock, patch
import httpx
import pytest
import respx
import asyncio

from curateur.api.client import ScreenScraperClient, APIEndpoint
from curateur.api.cache import MetadataCache
from curateur.api.throttle import ThrottleManager, RateLimit
from curateur.api.error_handler import SkippableAPIError, FatalAPIError
from curateur.scanner.rom_types import ROMInfo, ROMType


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def base_config():
    """Basic configuration for API client."""
    return {
        "screenscraper": {
            "devid": "dev",
            "devpassword": "devpass",
            "softname": "curateur",
            "user_id": "testuser",
            "user_password": "testpass",
        },
        "api": {
            "request_timeout": 5,
            "max_retries": 2,
            "retry_backoff_seconds": 0.1
        },
        "scraping": {
            "name_verification": "normal",
            "scrape_mode": "changed"
        },
    }


@pytest.fixture
def throttle():
    """Create throttle manager."""
    return ThrottleManager(RateLimit(calls=10, window_seconds=60))


@pytest.fixture
def test_rom_info(tmp_path):
    """Create test ROM info."""
    rom_path = tmp_path / "TestGame.nes"
    return ROMInfo(
        path=rom_path,
        filename="TestGame.nes",
        basename="TestGame",
        rom_type=ROMType.STANDARD,
        system="nes",
        query_filename="TestGame.nes",
        file_size=32768,
        hash_value="ABCD1234",
        hash_type="crc32"
    )


# ============================================================================
# Tests for get_user_info - Error Handling
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_user_info_timeout_error(base_config, throttle):
    """Test get_user_info handles timeout errors."""
    async with httpx.AsyncClient() as http_client:
        client = ScreenScraperClient(
            config=base_config,
            throttle_manager=throttle,
            client=http_client,
            cache=None
        )

        with respx.mock:
            respx.get("https://api.screenscraper.fr/api2/ssuserInfos.php").mock(
                side_effect=httpx.TimeoutException("Timeout")
            )

            with pytest.raises(SystemExit) as exc_info:
                await client.get_user_info()

            assert exc_info.value.code == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_user_info_connection_error(base_config, throttle):
    """Test get_user_info handles connection errors."""
    async with httpx.AsyncClient() as http_client:
        client = ScreenScraperClient(
            config=base_config,
            throttle_manager=throttle,
            client=http_client,
            cache=None
        )

        with respx.mock:
            respx.get("https://api.screenscraper.fr/api2/ssuserInfos.php").mock(
                side_effect=httpx.ConnectError("Connection failed")
            )

            with pytest.raises(SystemExit):
                await client.get_user_info()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_user_info_invalid_credentials(base_config, throttle):
    """Test get_user_info handles 401/403 errors."""
    async with httpx.AsyncClient() as http_client:
        client = ScreenScraperClient(
            config=base_config,
            throttle_manager=throttle,
            client=http_client,
            cache=None
        )

        with respx.mock:
            respx.get("https://api.screenscraper.fr/api2/ssuserInfos.php").respond(401)

            with pytest.raises(SystemExit):
                await client.get_user_info()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_user_info_http_error(base_config, throttle):
    """Test get_user_info handles other HTTP errors."""
    async with httpx.AsyncClient() as http_client:
        client = ScreenScraperClient(
            config=base_config,
            throttle_manager=throttle,
            client=http_client,
            cache=None
        )

        with respx.mock:
            respx.get("https://api.screenscraper.fr/api2/ssuserInfos.php").respond(500)

            with pytest.raises(SystemExit):
                await client.get_user_info()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_user_info_invalid_xml(base_config, throttle):
    """Test get_user_info handles invalid XML."""
    async with httpx.AsyncClient() as http_client:
        client = ScreenScraperClient(
            config=base_config,
            throttle_manager=throttle,
            client=http_client,
            cache=None
        )

        with respx.mock:
            respx.get("https://api.screenscraper.fr/api2/ssuserInfos.php").respond(
                200,
                content=b"<invalid xml"
            )

            with pytest.raises(SystemExit):
                await client.get_user_info()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_user_info_no_user_data(base_config, throttle):
    """Test get_user_info handles missing user data."""
    async with httpx.AsyncClient() as http_client:
        client = ScreenScraperClient(
            config=base_config,
            throttle_manager=throttle,
            client=http_client,
            cache=None
        )

        xml = b"<Data><empty></empty></Data>"

        with respx.mock:
            respx.get("https://api.screenscraper.fr/api2/ssuserInfos.php").respond(
                200,
                content=xml
            )

            with pytest.raises(SystemExit):
                await client.get_user_info()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_user_info_insufficient_level(base_config, throttle):
    """Test get_user_info handles insufficient user level."""
    async with httpx.AsyncClient() as http_client:
        client = ScreenScraperClient(
            config=base_config,
            throttle_manager=throttle,
            client=http_client,
            cache=None
        )

        xml = b"""
        <Data>
          <ssuser>
            <id>testuser</id>
            <niveau>0</niveau>
            <maxthreads>1</maxthreads>
          </ssuser>
        </Data>
        """

        with respx.mock:
            respx.get("https://api.screenscraper.fr/api2/ssuserInfos.php").respond(
                200,
                content=xml
            )

            with pytest.raises(SystemExit):
                await client.get_user_info()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_user_info_success(base_config, throttle):
    """Test successful get_user_info."""
    async with httpx.AsyncClient() as http_client:
        client = ScreenScraperClient(
            config=base_config,
            throttle_manager=throttle,
            client=http_client,
            cache=None
        )

        xml = b"""
        <Data>
          <ssuser>
            <id>testuser</id>
            <niveau>1</niveau>
            <maxthreads>3</maxthreads>
            <maxrequestspermin>60</maxrequestspermin>
            <requeststoday>50</requeststoday>
            <maxrequestsperday>200</maxrequestsperday>
          </ssuser>
        </Data>
        """

        with respx.mock:
            respx.get("https://api.screenscraper.fr/api2/ssuserInfos.php").respond(
                200,
                content=xml
            )

            result = await client.get_user_info()

            assert result['niveau'] == 1
            assert result['maxthreads'] == 3
            assert client._rate_limits_initialized is True


# ============================================================================
# Tests for query_game - Error Scenarios
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_game_shutdown_requested(base_config, throttle, test_rom_info):
    """Test query_game respects shutdown event."""
    async with httpx.AsyncClient() as http_client:
        client = ScreenScraperClient(
            config=base_config,
            throttle_manager=throttle,
            client=http_client,
            cache=None
        )

        shutdown_event = asyncio.Event()
        shutdown_event.set()

        with pytest.raises(asyncio.CancelledError):
            await client.query_game(test_rom_info, shutdown_event=shutdown_event)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_game_unknown_platform(base_config, throttle, tmp_path):
    """Test query_game handles unknown platform."""
    rom_info = ROMInfo(
        path=tmp_path / "game.bin",
        filename="game.bin",
        basename="game",
        rom_type=ROMType.STANDARD,
        system="unknown_system",  # Unknown platform
        query_filename="game.bin",
        file_size=1024,
        hash_value="ABC123"
    )

    async with httpx.AsyncClient() as http_client:
        client = ScreenScraperClient(
            config=base_config,
            throttle_manager=throttle,
            client=http_client,
            cache=None
        )

        with pytest.raises(SkippableAPIError, match="Platform not mapped"):
            await client.query_game(rom_info)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_game_name_verification_failure(base_config, throttle, test_rom_info):
    """Test query_game handles name verification failure."""
    async with httpx.AsyncClient() as http_client:
        client = ScreenScraperClient(
            config=base_config,
            throttle_manager=throttle,
            client=http_client,
            cache=None
        )

        # Response with very different name
        xml = b"""
        <Data>
          <ssuser>
            <id>1</id><niveau>1</niveau><maxthreads>3</maxthreads>
            <maxrequestspermin>60</maxrequestspermin>
          </ssuser>
          <jeu id="123">
            <noms><nom region="us">CompletelyDifferentGame</nom></noms>
            <systeme>nes</systeme>
          </jeu>
        </Data>
        """

        with respx.mock:
            respx.get("https://api.screenscraper.fr/api2/jeuInfos.php").respond(
                200,
                content=xml
            )

            with pytest.raises(SkippableAPIError, match="Name verification failed"):
                await client.query_game(test_rom_info)


# ============================================================================
# Tests for search_game
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_game_success(base_config, throttle, tmp_path):
    """Test successful search_game."""
    async with httpx.AsyncClient() as http_client:
        client = ScreenScraperClient(
            config=base_config,
            throttle_manager=throttle,
            client=http_client,
            cache=None
        )

        # Create ROMInfo for the search
        rom_info = ROMInfo(
            path=tmp_path / "AlphaQuest.nes",
            filename="AlphaQuest.nes",
            basename="AlphaQuest",
            rom_type=ROMType.STANDARD,
            system="nes",
            query_filename="Alpha Quest",
            file_size=32768,
            hash_value="ABC123"
        )

        xml = b"""
        <Data>
          <ssuser>
            <id>1</id><niveau>1</niveau><maxthreads>3</maxthreads>
            <maxrequestspermin>60</maxrequestspermin>
          </ssuser>
          <jeux>
            <jeu id="123">
              <noms><nom region="us">Alpha Quest</nom></noms>
              <systeme>nes</systeme>
            </jeu>
            <jeu id="456">
              <noms><nom region="us">Alpha Quest 2</nom></noms>
              <systeme>nes</systeme>
            </jeu>
          </jeux>
        </Data>
        """

        with respx.mock:
            respx.get("https://api.screenscraper.fr/api2/jeuRecherche.php").respond(
                200,
                content=xml
            )

            results = await client.search_game(rom_info)

            assert len(results) == 2
            assert results[0]['name'] == "Alpha Quest"
            assert results[1]['name'] == "Alpha Quest 2"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_game_no_results(base_config, throttle, tmp_path):
    """Test search_game with no results."""
    async with httpx.AsyncClient() as http_client:
        client = ScreenScraperClient(
            config=base_config,
            throttle_manager=throttle,
            client=http_client,
            cache=None
        )

        # Create ROMInfo for the search
        rom_info = ROMInfo(
            path=tmp_path / "NonexistentGame.nes",
            filename="NonexistentGame.nes",
            basename="NonexistentGame",
            rom_type=ROMType.STANDARD,
            system="nes",
            query_filename="NonexistentGame",
            file_size=32768,
            hash_value="ABC123"
        )

        xml = b"""
        <Data>
          <ssuser>
            <id>1</id><niveau>1</niveau><maxthreads>3</maxthreads>
          </ssuser>
          <jeux></jeux>
        </Data>
        """

        with respx.mock:
            respx.get("https://api.screenscraper.fr/api2/jeuRecherche.php").respond(
                200,
                content=xml
            )

            results = await client.search_game(rom_info)

            assert results == []


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_game_unknown_platform(base_config, throttle, tmp_path):
    """Test search_game with unknown platform."""
    async with httpx.AsyncClient() as http_client:
        client = ScreenScraperClient(
            config=base_config,
            throttle_manager=throttle,
            client=http_client,
            cache=None
        )

        # Create ROMInfo with unknown platform
        rom_info = ROMInfo(
            path=tmp_path / "Test.bin",
            filename="Test.bin",
            basename="Test",
            rom_type=ROMType.STANDARD,
            system="unknown_platform",
            query_filename="Test",
            file_size=32768,
            hash_value="ABC123"
        )

        with pytest.raises(SkippableAPIError, match="Platform not mapped"):
            await client.search_game(rom_info)


# ============================================================================
# Tests for get_user_limits
# ============================================================================

@pytest.mark.unit
def test_get_user_limits_not_initialized(base_config, throttle):
    """Test get_user_limits when not initialized."""
    client = ScreenScraperClient(
        config=base_config,
        throttle_manager=throttle,
        client=None,
        cache=None
    )

    assert client.get_user_limits() is None


@pytest.mark.unit
@pytest.mark.asyncio
async def test_get_user_limits_after_get_user_info(base_config, throttle):
    """Test get_user_limits returns stored limits."""
    async with httpx.AsyncClient() as http_client:
        client = ScreenScraperClient(
            config=base_config,
            throttle_manager=throttle,
            client=http_client,
            cache=None
        )

        xml = b"""
        <Data>
          <ssuser>
            <id>testuser</id>
            <niveau>1</niveau>
            <maxthreads>4</maxthreads>
            <maxrequestspermin>80</maxrequestspermin>
          </ssuser>
        </Data>
        """

        with respx.mock:
            respx.get("https://api.screenscraper.fr/api2/ssuserInfos.php").respond(
                200,
                content=xml
            )

            await client.get_user_info()

            limits = client.get_user_limits()
            assert limits is not None
            assert limits['maxthreads'] == 4
            assert limits['maxrequestspermin'] == 80


# ============================================================================
# Tests for cache integration scenarios
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_query_game_cache_miss_then_hit(base_config, throttle, test_rom_info, tmp_path):
    """Test cache miss followed by cache hit."""
    cache = MetadataCache(gamelist_directory=tmp_path)

    async with httpx.AsyncClient() as http_client:
        client = ScreenScraperClient(
            config=base_config,
            throttle_manager=throttle,
            client=http_client,
            cache=cache
        )

        xml = b"""
        <Data>
          <ssuser>
            <id>1</id><niveau>1</niveau><maxthreads>3</maxthreads>
            <maxrequestspermin>60</maxrequestspermin>
          </ssuser>
          <jeu id="99">
            <noms><nom region="us">TestGame</nom></noms>
            <systeme>nes</systeme>
          </jeu>
        </Data>
        """

        with respx.mock:
            mock_route = respx.get("https://api.screenscraper.fr/api2/jeuInfos.php").respond(
                200,
                content=xml
            )

            # First call - cache miss
            result1 = await client.query_game(test_rom_info)
            assert result1['name'] == "TestGame"
            assert mock_route.called

            # Reset mock
            mock_route.reset()

            # Second call - cache hit
            result2 = await client.query_game(test_rom_info)
            assert result2['name'] == "TestGame"
            assert not mock_route.called  # Should not call API again


# ============================================================================
# Tests for _build_redacted_url edge cases
# ============================================================================

@pytest.mark.unit
def test_build_redacted_url_handles_empty_params(base_config, throttle):
    """Test _build_redacted_url with minimal params."""
    client = ScreenScraperClient(
        config=base_config,
        throttle_manager=throttle,
        client=None,
        cache=None
    )

    url = "https://api.test.com/endpoint"
    params = {
        'devpassword': 'secret',
        'sspassword': 'pass',
        'other': 'value'
    }

    redacted = client._build_redacted_url(url, params)

    assert 'secret' not in redacted
    assert 'sspassword=pass' not in redacted  # Check the value isn't exposed
    assert 'devpassword=secret' not in redacted
    assert 'redacted' in redacted
    assert 'other=value' in redacted
