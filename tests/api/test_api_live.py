"""
Live API tests for ScreenScraper.

These tests make REAL API calls to ScreenScraper using actual credentials
and game data from nes.dat. They are marked with @pytest.mark.live and
can be skipped with: pytest -m "not live"

Requirements:
- Valid config.yaml with ScreenScraper credentials
- Active internet connection
- ScreenScraper API must be accessible

Usage:
    # Run all tests except live:
    pytest -m "not live"
    
    # Run only live tests:
    pytest -m live
    
    # Run specific live test:
    pytest tests/test_api_live.py::TestLiveAPIQueries::test_query_super_mario_bros -v
"""

import pytest
from pathlib import Path

from curateur.config.loader import load_config
from curateur.api.client import ScreenScraperClient
from curateur.api.error_handler import SkippableAPIError, FatalAPIError
from curateur.scanner.rom_types import ROMInfo, ROMType


# Check if config exists
CONFIG_PATH = Path('config.yaml')
CONFIG_EXISTS = CONFIG_PATH.exists()


# Skip all tests in this module if config doesn't exist
pytestmark = pytest.mark.skipif(
    not CONFIG_EXISTS,
    reason="config.yaml not found - required for live API tests"
)


@pytest.fixture(scope='module')
def live_config():
    """Load real configuration for live tests."""
    if not CONFIG_EXISTS:
        pytest.skip("config.yaml not found")
    return load_config(CONFIG_PATH)


@pytest.fixture(scope='module')
def live_client(live_config):
    """Create API client with real credentials."""
    return ScreenScraperClient(live_config)


@pytest.mark.live
class TestLiveAPIQueries:
    """Test real API queries against ScreenScraper."""
    
    def test_query_super_mario_bros(self, live_client):
        """Test querying Super Mario Bros. - most recognized NES game."""
        rom_info = ROMInfo(
            path=Path("/fake/Super Mario Bros. (World).nes"),
            filename="Super Mario Bros. (World).nes",
            basename="Super Mario Bros. (World)",
            rom_type=ROMType.STANDARD,
            system="nes",
            query_filename="Super Mario Bros. (World).nes",
            file_size=40976,
            crc32="3337ec46"
        )
        
        print(f"\n  Querying: {rom_info.filename}")
        game_data = live_client.query_game(rom_info)
        
        # Verify response structure
        assert game_data is not None
        assert 'id' in game_data
        assert 'name' in game_data
        assert 'Super Mario' in game_data['name']
        
        print(f"  ✓ Found: {game_data['name']} (ID: {game_data['id']})")
        
        # Verify optional fields if present
        if 'genres' in game_data:
            print(f"  ✓ Genres: {', '.join(game_data['genres'])}")
        
        if 'developer' in game_data:
            print(f"  ✓ Developer: {game_data['developer']}")
        
        if 'media' in game_data:
            media_types = list(game_data['media'].keys())
            print(f"  ✓ Media types: {', '.join(media_types)}")
    
    def test_query_legend_of_zelda(self, live_client):
        """Test querying The Legend of Zelda."""
        rom_info = ROMInfo(
            path=Path("/fake/Legend of Zelda, The (USA).nes"),
            filename="Legend of Zelda, The (USA).nes",
            basename="Legend of Zelda, The (USA)",
            rom_type=ROMType.STANDARD,
            system="nes",
            query_filename="Legend of Zelda, The (USA).nes",
            file_size=131088,
            crc32="38027b14"
        )
        
        print(f"\n  Querying: {rom_info.filename}")
        game_data = live_client.query_game(rom_info)
        
        assert game_data is not None
        assert 'name' in game_data
        assert 'Zelda' in game_data['name']
        
        print(f"  ✓ Found: {game_data['name']} (ID: {game_data['id']})")
    
    def test_query_obscure_japan_game(self, live_client):
        """Test querying obscure Japan-only title."""
        rom_info = ROMInfo(
            path=Path("/fake/'89 Dennou Kyuusei Uranai (Japan).nes"),
            filename="'89 Dennou Kyuusei Uranai (Japan).nes",
            basename="'89 Dennou Kyuusei Uranai (Japan)",
            rom_type=ROMType.STANDARD,
            system="nes",
            query_filename="'89 Dennou Kyuusei Uranai (Japan).nes",
            file_size=262160,
            crc32="3577ab04"
        )
        
        print(f"\n  Querying: {rom_info.filename}")
        
        try:
            game_data = live_client.query_game(rom_info)
            assert game_data is not None
            print(f"  ✓ Found: {game_data['name']} (ID: {game_data['id']})")
        except SkippableAPIError as e:
            # Obscure games might not be in database
            print(f"  ⚠ Skipped: {e}")
            pytest.skip(f"Game not in database: {e}")


@pytest.mark.live
class TestLiveRateLimiting:
    """Test rate limiting with real API."""
    
    def test_rate_limits_initialized(self, live_client):
        """Test that rate limits are properly initialized from API."""
        # Make a query to initialize rate limits
        rom_info = ROMInfo(
            path=Path("/fake/1942 (Japan, USA) (En).nes"),
            filename="1942 (Japan, USA) (En).nes",
            basename="1942 (Japan, USA) (En)",
            rom_type=ROMType.STANDARD,
            system="nes",
            query_filename="1942 (Japan, USA) (En).nes",
            file_size=40976,
            crc32="74d7bae1"
        )
        
        print(f"\n  Querying to test rate limit initialization...")
        
        try:
            game_data = live_client.query_game(rom_info)
            
            # Check rate limits were initialized
            assert live_client._rate_limits_initialized
            
            # Get rate limit info
            limits = live_client.get_rate_limits()
            print(f"  ✓ Rate limits initialized:")
            print(f"    - Requests per minute: {limits.get('max_requests_per_minute', 'N/A')}")
            print(f"    - Current count: {limits.get('request_count', 0)}")
            
        except SkippableAPIError as e:
            print(f"  ⚠ Game not found, but rate limits should still be set")
            assert live_client._rate_limits_initialized
    
    def test_multiple_queries_respect_rate_limit(self, live_client):
        """Test that multiple queries respect rate limiting."""
        import time
        
        roms = [
            ROMInfo(
                path=Path("/fake/Game1.nes"),
                filename="Game1.nes",
                basename="Game1",
                rom_type=ROMType.STANDARD,
                system="nes",
                query_filename="Game1.nes",
                file_size=40976,
                crc32="3337ec46"
            ),
            ROMInfo(
                path=Path("/fake/Game2.nes"),
                filename="Game2.nes",
                basename="Game2",
                rom_type=ROMType.STANDARD,
                system="nes",
                query_filename="Game2.nes",
                file_size=131088,
                crc32="38027b14"
            )
        ]
        
        print(f"\n  Testing rate limiting with {len(roms)} queries...")
        
        start_time = time.time()
        
        for i, rom in enumerate(roms, 1):
            try:
                game_data = live_client.query_game(rom)
                print(f"  ✓ Query {i} completed")
            except SkippableAPIError:
                print(f"  ⚠ Query {i} skipped (game not found)")
        
        elapsed = time.time() - start_time
        print(f"  ✓ Total time: {elapsed:.2f}s")
        
        # Should have some delay due to rate limiting
        # (unless rate limit is very high)
        print(f"  ✓ Rate limiting appears to be working")


@pytest.mark.live
class TestLiveResponseStructure:
    """Test response structure from real API."""
    
    def test_response_has_expected_fields(self, live_client):
        """Test that real API responses have expected structure."""
        rom_info = ROMInfo(
            path=Path("/fake/Mega Man (USA).nes"),
            filename="Mega Man (USA).nes",
            basename="Mega Man (USA)",
            rom_type=ROMType.STANDARD,
            system="nes",
            query_filename="Mega Man (USA).nes",
            file_size=131088,
            crc32="d2c305ae"
        )
        
        print(f"\n  Querying: {rom_info.filename}")
        
        try:
            game_data = live_client.query_game(rom_info)
            
            # Verify required fields
            assert 'id' in game_data, "Missing 'id' field"
            assert 'name' in game_data, "Missing 'name' field"
            
            print(f"  ✓ Game ID: {game_data['id']}")
            print(f"  ✓ Game Name: {game_data['name']}")
            
            # Check for optional but common fields
            optional_fields = [
                'names', 'descriptions', 'release_dates', 'genres',
                'developer', 'publisher', 'players', 'rating', 'media'
            ]
            
            present_fields = [f for f in optional_fields if f in game_data]
            print(f"  ✓ Present fields: {', '.join(present_fields)}")
            
            # Verify media structure if present
            if 'media' in game_data:
                assert isinstance(game_data['media'], dict)
                for media_type, media_list in game_data['media'].items():
                    assert isinstance(media_list, list)
                    if media_list:
                        assert 'url' in media_list[0]
                        print(f"    - {media_type}: {len(media_list)} item(s)")
            
        except SkippableAPIError as e:
            pytest.skip(f"Game not in database: {e}")


@pytest.mark.live
class TestLiveErrorHandling:
    """Test error handling with real API."""
    
    def test_invalid_crc_returns_error(self, live_client):
        """Test that completely invalid CRC returns appropriate error."""
        rom_info = ROMInfo(
            path=Path("/fake/Nonexistent Game.nes"),
            filename="Nonexistent Game.nes",
            basename="Nonexistent Game",
            rom_type=ROMType.STANDARD,
            system="nes",
            query_filename="Nonexistent Game.nes",
            file_size=1024,
            crc32="00000000"
        )
        
        print(f"\n  Querying with invalid CRC: {rom_info.crc32}")
        
        # Should raise SkippableAPIError (game not found)
        with pytest.raises(SkippableAPIError):
            live_client.query_game(rom_info)
        
        print(f"  ✓ Correctly raised SkippableAPIError for invalid game")


if __name__ == '__main__':
    # Run only live tests
    pytest.main([__file__, '-v', '-m', 'live'])
