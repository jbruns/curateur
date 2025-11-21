"""
Tests for ScreenScraper API client.

Tests ScreenScraperClient using respx library for HTTP mocking,
covering initialization, query_game(), error handling, rate limiting,
and name verification integration.
"""

import pytest
import pytest_asyncio
import respx
import httpx
from pathlib import Path
from unittest.mock import Mock, patch

from curateur.api.client import ScreenScraperClient
from curateur.api.error_handler import FatalAPIError, SkippableAPIError, RetryableAPIError, APIError
from curateur.scanner.rom_types import ROMInfo, ROMType


# Fixture paths
FIXTURES_DIR = Path(__file__).parent.parent / 'fixtures' / 'api'
ERROR_FIXTURES = FIXTURES_DIR / 'errors'
PARTIAL_FIXTURES = FIXTURES_DIR / 'partial'


# Test configuration
TEST_CONFIG = {
    'screenscraper': {
        'devid': 'test_dev_id',
        'devpassword': 'test_dev_password',
        'softname': 'curateur_test',
        'user_id': 'test_user',
        'user_password': 'test_password'
    },
    'api': {
        'request_timeout': 30,
        'max_retries': 3,
        'retry_backoff_seconds': 1
    },
    'scraping': {
        'name_verification': 'normal'
    }
}


@pytest_asyncio.fixture
async def api_client():
    """Create API client with test configuration."""
    from curateur.api.throttle import ThrottleManager, RateLimit
    
    # Create a throttle manager for the client
    throttle_manager = ThrottleManager(RateLimit(calls=20, window_seconds=60))
    
    # Create an httpx.AsyncClient (tests will mock HTTP calls anyway)
    async with httpx.AsyncClient() as client:
        yield ScreenScraperClient(TEST_CONFIG, throttle_manager=throttle_manager, client=client)


@pytest.fixture
def sample_rom_info():
    """Create sample ROM info for testing."""
    return ROMInfo(
        path=Path("/fake/roms/Super Mario Bros. (World).nes"),
        filename="Super Mario Bros. (World).nes",
        basename="Super Mario Bros. (World)",
        rom_type=ROMType.STANDARD,
        system="nes",
        query_filename="Super Mario Bros. (World).nes",
        file_size=40976,
        hash_type="crc32",
        hash_value="3337ec46"
    )


class TestClientInitialization:
    """Test API client initialization."""
    
    def test_init_with_credentials(self):
        """Test client initializes with credentials from config."""
        from curateur.api.throttle import ThrottleManager, RateLimit
        throttle_manager = ThrottleManager(RateLimit(calls=20, window_seconds=60))
        client = ScreenScraperClient(TEST_CONFIG, throttle_manager=throttle_manager)
        
        assert client.devid == 'test_dev_id'
        assert client.devpassword == 'test_dev_password'
        assert client.softname == 'curateur_test'
        assert client.ssid == 'test_user'
        assert client.sspassword == 'test_password'
    
    def test_init_with_timeouts(self):
        """Test client initializes with timeout settings."""
        from curateur.api.throttle import ThrottleManager, RateLimit
        throttle_manager = ThrottleManager(RateLimit(calls=20, window_seconds=60))
        client = ScreenScraperClient(TEST_CONFIG, throttle_manager=throttle_manager)
        
        assert client.request_timeout == 30
        assert client.max_retries == 3
        assert client.retry_backoff == 1
    
    def test_init_with_name_verification(self):
        """Test client initializes with name verification setting."""
        from curateur.api.throttle import ThrottleManager, RateLimit
        throttle_manager = ThrottleManager(RateLimit(calls=20, window_seconds=60))
        client = ScreenScraperClient(TEST_CONFIG, throttle_manager=throttle_manager)
        
        assert client.name_verification == 'normal'
    
    def test_init_creates_throttle_manager(self):
        """Test client initializes with throttle manager."""
        from curateur.api.throttle import ThrottleManager, RateLimit
        throttle_manager = ThrottleManager(RateLimit(calls=20, window_seconds=60))
        client = ScreenScraperClient(TEST_CONFIG, throttle_manager=throttle_manager)
        
        assert client.throttle_manager is not None
        assert not client._rate_limits_initialized


@pytest.mark.asyncio
class TestQueryGameSuccess:
    """Test successful game queries."""
    
    async def test_query_game_basic(self, api_client, sample_rom_info, respx_mock):
        """Test basic successful game query."""
        # Create success response XML
        response_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<Data>
  <ssuser>
    <id>12345</id>
    <niveau>1</niveau>
    <maxthreads>1</maxthreads>
    <maxrequestspermin>20</maxrequestspermin>
    <maxrequestsperday>10000</maxrequestsperday>
    <requeststoday>42</requeststoday>
  </ssuser>
  <jeu id="1234">
    <noms>
      <nom region="us" langue="en">Super Mario Bros.</nom>
      <nom region="wor" langue="en">Super Mario Bros.</nom>
    </noms>
    <genres>
      <genre id="7" principale="1">
        <noms><nom langue="en">Platform</nom></noms>
      </genre>
    </genres>
    <developpeur><nom>Nintendo</nom></developpeur>
    <editeur><nom>Nintendo</nom></editeur>
  </jeu>
</Data>'''
        
        # Mock the API request
        route = respx_mock.get('https://api.screenscraper.fr/api2/jeuInfos.php').mock(
            return_value=httpx.Response(200, content=response_xml)
        )
        
        # Execute query
        result = await api_client.query_game(sample_rom_info)
        
        # Verify result
        assert result is not None
        assert result['id'] == '1234'
        assert result['name'] == 'Super Mario Bros.'
        assert 'genres' in result
        
        # Verify request was made with correct parameters
        assert route.called
        request = route.calls[0].request
        assert 'devid=test_dev_id' in str(request.url)
        assert 'devpassword=test_dev_password' in str(request.url)
        assert 'systemeid=3' in str(request.url)  # NES system ID
        assert 'romnom=Super+Mario+Bros.+%28World%29.nes' in str(request.url)
        assert 'romtaille=40976' in str(request.url)
        assert 'crc=3337ec46' in str(request.url)
    
    async def test_query_game_rate_limit_initialization(self, api_client, sample_rom_info, respx_mock):
        """Test that rate limits are initialized from first API response."""
        response_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<Data>
  <ssuser>
    <id>12345</id>
    <maxrequestspermin>60</maxrequestspermin>
  </ssuser>
  <jeu id="1234">
    <noms><nom region="us">Super Mario Bros.</nom></noms>
  </jeu>
</Data>'''
        
        respx_mock.get('https://api.screenscraper.fr/api2/jeuInfos.php').mock(
            return_value=httpx.Response(200, content=response_xml)
        )
        
        # Before query, rate limits not initialized
        assert not api_client._rate_limits_initialized
        
        # Execute query
        await api_client.query_game(sample_rom_info)
        
        # After query, rate limits should be initialized
        assert api_client._rate_limits_initialized


@pytest.mark.asyncio
class TestQueryGameErrors:
    """Test error handling in game queries."""
    
    async def test_query_game_not_found(self, api_client, sample_rom_info, respx_mock):
        """Test handling of 404 game not found error."""
        xml_path = ERROR_FIXTURES / '404_not_found.xml'
        response_xml = xml_path.read_bytes()
        
        respx_mock.get('https://api.screenscraper.fr/api2/jeuInfos.php').mock(
            return_value=httpx.Response(404, content=response_xml)
        )
        
        with pytest.raises(SkippableAPIError):
            await api_client.query_game(sample_rom_info)
    
    async def test_query_game_invalid_credentials(self, api_client, sample_rom_info, respx_mock):
        """Test handling of 403 invalid credentials error."""
        xml_path = ERROR_FIXTURES / '403_invalid_creds.xml'
        response_xml = xml_path.read_bytes()
        
        respx_mock.get('https://api.screenscraper.fr/api2/jeuInfos.php').mock(
            return_value=httpx.Response(403, content=response_xml)
        )
        
        # 403 authentication errors cause sys.exit(1) in production
        with pytest.raises(SystemExit) as exc_info:
            await api_client.query_game(sample_rom_info)
        assert exc_info.value.code == 1
    
    async def test_query_game_api_closed(self, api_client, sample_rom_info, respx_mock):
        """Test handling of 423 API closed error."""
        xml_path = ERROR_FIXTURES / '423_api_closed.xml'
        response_xml = xml_path.read_bytes()
        
        respx_mock.get('https://api.screenscraper.fr/api2/jeuInfos.php').mock(
            return_value=httpx.Response(423, content=response_xml)
        )
        
        with pytest.raises(FatalAPIError):
            await api_client.query_game(sample_rom_info)
    
    async def test_query_game_thread_limit(self, api_client, sample_rom_info, respx_mock, mocker):
        """Test handling of 429 thread limit error."""
        xml_path = ERROR_FIXTURES / '429_thread_limit.xml'
        response_xml = xml_path.read_bytes()
        
        respx_mock.get('https://api.screenscraper.fr/api2/jeuInfos.php').mock(
            return_value=httpx.Response(429, content=response_xml)
        )
        
        # 429 errors trigger RetryableAPIError and retry logic
        # Patch sleep to make retries instant in tests
        async def instant_sleep(*args, **kwargs):
            pass
        mocker.patch('asyncio.sleep', side_effect=instant_sleep)
        
        # After retries are exhausted, API client converts to SkippableAPIError
        with pytest.raises(SkippableAPIError, match="API error"):
            await api_client.query_game(sample_rom_info)
    
    async def test_query_game_quota_exceeded(self, api_client, sample_rom_info, respx_mock):
        """Test handling of 430 quota exceeded error."""
        xml_path = ERROR_FIXTURES / '430_quota_exceeded.xml'
        response_xml = xml_path.read_bytes()
        
        respx_mock.get('https://api.screenscraper.fr/api2/jeuInfos.php').mock(
            return_value=httpx.Response(430, content=response_xml)
        )
        
        with pytest.raises(FatalAPIError):
            await api_client.query_game(sample_rom_info)
    
    async def test_query_game_timeout(self, api_client, sample_rom_info, respx_mock, mocker):
        """Test handling of request timeout."""
        respx_mock.get('https://api.screenscraper.fr/api2/jeuInfos.php').mock(
            side_effect=httpx.TimeoutException("Timeout")
        )
        
        # Timeouts trigger retries and eventually raise error
        # Patch sleep to make retries instant in tests
        async def instant_sleep(*args, **kwargs):
            pass
        mocker.patch('asyncio.sleep', side_effect=instant_sleep)
        
        with pytest.raises((httpx.TimeoutException, APIError)):
            await api_client.query_game(sample_rom_info)


@pytest.mark.asyncio
class TestNameVerification:
    """Test name verification integration."""
    
    async def test_query_game_name_mismatch(self, api_client, respx_mock):
        """Test that name verification rejects mismatched names."""
        rom_info = ROMInfo(
            path=Path("/fake/roms/Zelda.nes"),
            filename="Zelda.nes",
            basename="Zelda",
            rom_type=ROMType.STANDARD,
            system="nes",
            query_filename="Zelda.nes",
            file_size=131088,
            hash_type="crc32",
            hash_value="38027b14"
        )
        
        # Response with completely different game name
        response_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<Data>
  <ssuser>
    <id>12345</id>
    <maxrequestspermin>20</maxrequestspermin>
  </ssuser>
  <jeu id="1234">
    <noms>
      <nom region="us">Super Mario Bros.</nom>
    </noms>
  </jeu>
</Data>'''
        
        respx_mock.get('https://api.screenscraper.fr/api2/jeuInfos.php').mock(
            return_value=httpx.Response(200, content=response_xml)
        )
        
        with pytest.raises(SkippableAPIError, match="Name verification failed"):
            await api_client.query_game(rom_info)
    
    async def test_query_game_name_match(self, api_client, respx_mock):
        """Test that name verification accepts similar names."""
        rom_info = ROMInfo(
            path=Path("/fake/roms/Super Mario Bros..nes"),
            filename="Super Mario Bros..nes",
            basename="Super Mario Bros.",
            rom_type=ROMType.STANDARD,
            system="nes",
            query_filename="Super Mario Bros..nes",
            file_size=40976,
            hash_type="crc32",
            hash_value="3337ec46"
        )
        
        response_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<Data>
  <ssuser>
    <id>12345</id>
    <maxrequestspermin>20</maxrequestspermin>
  </ssuser>
  <jeu id="1234">
    <noms>
      <nom region="us">Super Mario Bros.</nom>
    </noms>
  </jeu>
</Data>'''
        
        respx_mock.get('https://api.screenscraper.fr/api2/jeuInfos.php').mock(
            return_value=httpx.Response(200, content=response_xml)
        )
        
        # Should succeed - names are similar enough
        result = await api_client.query_game(rom_info)
        assert result is not None
        assert result['name'] == 'Super Mario Bros.'


@pytest.mark.asyncio
class TestSystemMapping:
    """Test system ID mapping."""
    
    async def test_query_game_invalid_system(self, api_client):
        """Test that invalid system raises SkippableAPIError."""
        rom_info = ROMInfo(
            path=Path("/fake/test.rom"),
            filename="test.rom",
            basename="test",
            rom_type=ROMType.STANDARD,
            system="invalid_system",
            query_filename="test.rom",
            file_size=1024,
            hash_type="crc32",
            hash_value="12345678"
        )
        
        with pytest.raises(SkippableAPIError, match="Platform not mapped"):
            await api_client.query_game(rom_info)


class TestGetRateLimits:
    """Test rate limit getter."""
    
    @pytest.mark.asyncio
    async def test_get_rate_limits(self, api_client):
        """Test getting current rate limit information from throttle manager."""
        # Get stats for a specific endpoint from throttle manager
        stats = api_client.throttle_manager.get_stats('jeuInfos.php')
        
        assert isinstance(stats, dict)
        # Should have expected fields
        assert 'limit' in stats
        assert 'recent_calls' in stats
        assert 'window_seconds' in stats
        assert 'endpoint' in stats


@pytest.mark.asyncio
class TestURLConstruction:
    """Test URL and parameter construction."""
    
    async def test_query_includes_all_credentials(self, api_client, sample_rom_info, respx_mock):
        """Test that all credentials are included in request."""
        response_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<Data>
  <ssuser><id>1</id><maxrequestspermin>20</maxrequestspermin></ssuser>
  <jeu id="1"><noms><nom region="us">Super Mario Bros.</nom></noms></jeu>
</Data>'''
        
        route = respx_mock.get('https://api.screenscraper.fr/api2/jeuInfos.php').mock(
            return_value=httpx.Response(200, content=response_xml)
        )
        
        await api_client.query_game(sample_rom_info)
        
        request_url = str(route.calls[0].request.url)
        assert 'devid=test_dev_id' in request_url
        assert 'devpassword=test_dev_password' in request_url
        assert 'softname=curateur_test' in request_url
        assert 'ssid=test_user' in request_url
        assert 'sspassword=test_password' in request_url
        assert 'output=xml' in request_url
    
    async def test_query_includes_rom_parameters(self, api_client, sample_rom_info, respx_mock):
        """Test that ROM parameters are included in request."""
        response_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<Data>
  <ssuser><id>1</id><maxrequestspermin>20</maxrequestspermin></ssuser>
  <jeu id="1"><noms><nom region="us">Super Mario Bros.</nom></noms></jeu>
</Data>'''
        
        route = respx_mock.get('https://api.screenscraper.fr/api2/jeuInfos.php').mock(
            return_value=httpx.Response(200, content=response_xml)
        )
        
        await api_client.query_game(sample_rom_info)
        
        request_url = str(route.calls[0].request.url)
        assert 'systemeid=3' in request_url  # NES
        assert 'romnom=' in request_url
        assert 'romtaille=40976' in request_url
        assert 'crc=3337ec46' in request_url
        assert 'romtype=rom' in request_url


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
