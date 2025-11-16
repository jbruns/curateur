"""
Integration tests for API modules.

Tests end-to-end workflows combining multiple API components:
- ROM scanning → API query → response parsing → name verification
- Multi-game sequential queries with rate limiting
- Error recovery and retry logic
"""

import pytest
import responses
from pathlib import Path
from unittest.mock import patch

from curateur.api.client import ScreenScraperClient
from curateur.api.error_handler import SkippableAPIError
from curateur.scanner.rom_types import ROMInfo, ROMType


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


@pytest.fixture
def api_client():
    """Create API client for integration tests."""
    return ScreenScraperClient(TEST_CONFIG)


@pytest.mark.integration
class TestEndToEndWorkflow:
    """Test complete API workflow from ROM info to game data."""
    
    @responses.activate
    def test_complete_workflow_success(self, api_client):
        """Test complete workflow: ROMInfo → query → parse → verify → result."""
        # Create ROM info
        rom_info = ROMInfo(
            path=Path("/fake/roms/Super Mario Bros. (World).nes"),
            filename="Super Mario Bros. (World).nes",
            basename="Super Mario Bros. (World)",
            rom_type=ROMType.STANDARD,
            system="nes",
            query_filename="Super Mario Bros. (World).nes",
            file_size=40976,
            crc32="3337ec46"
        )
        
        # Mock complete successful response
        response_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<Data>
  <ssuser>
    <id>12345</id>
    <niveau>2</niveau>
    <maxthreads>2</maxthreads>
    <maxrequestspermin>60</maxrequestspermin>
    <maxrequestsperday>20000</maxrequestsperday>
    <requeststoday>100</requeststoday>
  </ssuser>
  <jeu id="1">
    <noms>
      <nom region="us" langue="en">Super Mario Bros.</nom>
      <nom region="wor" langue="en">Super Mario Bros.</nom>
    </noms>
    <synopsis>
      <synopsis langue="en">The classic platformer that started it all.</synopsis>
    </synopsis>
    <dates>
      <date region="us">1985-10-18</date>
      <date region="jp">1985-09-13</date>
    </dates>
    <genres>
      <genre id="7" principale="1">
        <noms><nom langue="en">Platform</nom></noms>
      </genre>
    </genres>
    <developpeur>Nintendo</developpeur>
    <editeur>Nintendo</editeur>
    <joueurs>1-2</joueurs>
    <note>18</note>
    <medias>
      <media type="box-2D" format="png" region="us">https://example.com/box.png</media>
      <media type="ss" format="jpg" region="wor">https://example.com/screenshot.jpg</media>
    </medias>
  </jeu>
</Data>'''.encode('utf-8')
        
        responses.add(
            responses.GET,
            'https://api.screenscraper.fr/api2/jeuInfos.php',
            body=response_xml,
            status=200
        )
        
        # Execute workflow
        game_data = api_client.query_game(rom_info)
        
        # Verify complete workflow results
        assert game_data is not None
        assert game_data['id'] == '1'
        assert game_data['name'] == 'Super Mario Bros.'
        assert 'names' in game_data
        assert len(game_data['names']) == 2  # us and wor only in mock response
        assert 'descriptions' in game_data
        assert 'release_dates' in game_data
        assert 'genres' in game_data
        assert 'Platform' in game_data['genres']
        assert game_data['developer'] == 'Nintendo'
        assert game_data['publisher'] == 'Nintendo'
        assert game_data['players'] == '1-2'
        assert game_data['rating'] == 18.0
        assert 'media' in game_data
        assert 'box-2D' in game_data['media']
        assert 'ss' in game_data['media']
        
        # Verify rate limiter was initialized
        assert api_client._rate_limits_initialized
    
    @responses.activate
    def test_workflow_with_minimal_response(self, api_client):
        """Test workflow handles minimal API response gracefully."""
        rom_info = ROMInfo(
            path=Path("/fake/roms/Obscure Game.nes"),
            filename="Obscure Game.nes",
            basename="Obscure Game",
            rom_type=ROMType.STANDARD,
            system="nes",
            query_filename="Obscure Game.nes",
            file_size=24592,
            crc32="12345678"
        )
        
        # Minimal response with just name
        response_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<Data>
  <ssuser>
    <id>12345</id>
    <maxrequestspermin>20</maxrequestspermin>
  </ssuser>
  <jeu id="999">
    <noms>
      <nom region="wor">Obscure Game</nom>
    </noms>
  </jeu>
</Data>'''
        
        responses.add(
            responses.GET,
            'https://api.screenscraper.fr/api2/jeuInfos.php',
            body=response_xml,
            status=200
        )
        
        # Execute workflow
        game_data = api_client.query_game(rom_info)
        
        # Verify minimal data is handled
        assert game_data is not None
        assert game_data['name'] == 'Obscure Game'
        assert 'descriptions' not in game_data
        assert 'media' not in game_data


@pytest.mark.integration
class TestMultiGameSequence:
    """Test querying multiple games sequentially."""
    
    @responses.activate
    def test_query_multiple_games(self, api_client):
        """Test querying multiple games in sequence with rate limiting."""
        # Create multiple ROM infos
        roms = [
            ROMInfo(
                path=Path("/fake/Game1.nes"),
                filename="Game1.nes",
                basename="Game1",
                rom_type=ROMType.STANDARD,
                system="nes",
                query_filename="Game1.nes",
                file_size=40976,
                crc32="11111111"
            ),
            ROMInfo(
                path=Path("/fake/Game2.nes"),
                filename="Game2.nes",
                basename="Game2",
                rom_type=ROMType.STANDARD,
                system="nes",
                query_filename="Game2.nes",
                file_size=40976,
                crc32="22222222"
            ),
            ROMInfo(
                path=Path("/fake/Game3.nes"),
                filename="Game3.nes",
                basename="Game3",
                rom_type=ROMType.STANDARD,
                system="nes",
                query_filename="Game3.nes",
                file_size=40976,
                crc32="33333333"
            )
        ]
        
        # Mock responses for each game
        for i, rom in enumerate(roms, 1):
            response_xml = f'''<?xml version="1.0" encoding="UTF-8"?>
<Data>
  <ssuser>
    <id>12345</id>
    <maxrequestspermin>20</maxrequestspermin>
    <requeststoday>{i * 10}</requeststoday>
  </ssuser>
  <jeu id="{i}">
    <noms>
      <nom region="us">Game {i}</nom>
    </noms>
  </jeu>
</Data>'''.encode()
            
            responses.add(
                responses.GET,
                'https://api.screenscraper.fr/api2/jeuInfos.php',
                body=response_xml,
                status=200
            )
        
        # Query all games
        results = []
        for rom in roms:
            game_data = api_client.query_game(rom)
            results.append(game_data)
        
        # Verify all succeeded
        assert len(results) == 3
        assert results[0]['name'] == 'Game 1'
        assert results[1]['name'] == 'Game 2'
        assert results[2]['name'] == 'Game 3'
        
        # Verify rate limiter was updated only once (from first response)
        assert api_client._rate_limits_initialized


@pytest.mark.integration
class TestErrorRecovery:
    """Test error handling and recovery in workflows."""
    
    @responses.activate
    def test_workflow_handles_404_gracefully(self, api_client):
        """Test workflow handles game not found errors."""
        rom_info = ROMInfo(
            path=Path("/fake/Unknown Game.nes"),
            filename="Unknown Game.nes",
            basename="Unknown Game",
            rom_type=ROMType.STANDARD,
            system="nes",
            query_filename="Unknown Game.nes",
            file_size=1024,
            crc32="99999999"
        )
        
        # 404 response
        response_xml = '''<?xml version="1.0" encoding="UTF-8"?>
<Data>
  <ssuser>
    <id>12345</id>
    <maxrequestspermin>20</maxrequestspermin>
  </ssuser>
  <erreur>Erreur : Rom non trouvee</erreur>
</Data>'''.encode('utf-8')
        
        responses.add(
            responses.GET,
            'https://api.screenscraper.fr/api2/jeuInfos.php',
            body=response_xml,
            status=404
        )
        
        # Should raise SkippableAPIError
        with pytest.raises(SkippableAPIError):
            api_client.query_game(rom_info)
    
    @responses.activate
    def test_workflow_continues_after_skippable_error(self, api_client):
        """Test that workflow can continue after skippable errors."""
        roms = [
            ROMInfo(
                path=Path("/fake/Good Game.nes"),
                filename="Good Game.nes",
                basename="Good Game",
                rom_type=ROMType.STANDARD,
                system="nes",
                query_filename="Good Game.nes",
                file_size=40976,
                crc32="12345678"
            ),
            ROMInfo(
                path=Path("/fake/Bad Game.nes"),
                filename="Bad Game.nes",
                basename="Bad Game",
                rom_type=ROMType.STANDARD,
                system="nes",
                query_filename="Bad Game.nes",
                file_size=1024,
                crc32="99999999"
            ),
            ROMInfo(
                path=Path("/fake/Another Good Game.nes"),
                filename="Another Good Game.nes",
                basename="Another Good Game",
                rom_type=ROMType.STANDARD,
                system="nes",
                query_filename="Another Good Game.nes",
                file_size=40976,
                crc32="87654321"
            )
        ]
        
        # Success response for first game
        responses.add(
            responses.GET,
            'https://api.screenscraper.fr/api2/jeuInfos.php',
            body=b'''<?xml version="1.0"?>
<Data>
  <ssuser><id>1</id><maxrequestspermin>20</maxrequestspermin></ssuser>
  <jeu id="1"><noms><nom region="us">Good Game</nom></noms></jeu>
</Data>''',
            status=200
        )
        
        # 404 for second game
        responses.add(
            responses.GET,
            'https://api.screenscraper.fr/api2/jeuInfos.php',
            body=b'''<?xml version="1.0"?>
<Data>
  <ssuser><id>1</id><maxrequestspermin>20</maxrequestspermin></ssuser>
  <erreur>Rom non trouvee</erreur>
</Data>''',
            status=404
        )
        
        # Success for third game
        responses.add(
            responses.GET,
            'https://api.screenscraper.fr/api2/jeuInfos.php',
            body=b'''<?xml version="1.0"?>
<Data>
  <ssuser><id>1</id><maxrequestspermin>20</maxrequestspermin></ssuser>
  <jeu id="3"><noms><nom region="us">Another Good Game</nom></noms></jeu>
</Data>''',
            status=200
        )
        
        # Query games, handling errors
        results = []
        for rom in roms:
            try:
                game_data = api_client.query_game(rom)
                results.append(game_data)
            except SkippableAPIError:
                results.append(None)
        
        # Verify first and third succeeded, second failed
        assert len(results) == 3
        assert results[0] is not None
        assert results[0]['name'] == 'Good Game'
        assert results[1] is None  # Skipped
        assert results[2] is not None
        assert results[2]['name'] == 'Another Good Game'


@pytest.mark.integration
class TestNameVerificationIntegration:
    """Test name verification in complete workflow."""
    
    @responses.activate
    def test_workflow_rejects_name_mismatch(self, api_client):
        """Test that workflow properly rejects name mismatches."""
        # ROM filename suggests Zelda
        rom_info = ROMInfo(
            path=Path("/fake/Legend of Zelda (USA).nes"),
            filename="Legend of Zelda (USA).nes",
            basename="Legend of Zelda (USA)",
            rom_type=ROMType.STANDARD,
            system="nes",
            query_filename="Legend of Zelda (USA).nes",
            file_size=131088,
            crc32="38027b14"
        )
        
        # But API returns Mario data (wrong game)
        response_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<Data>
  <ssuser>
    <id>12345</id>
    <maxrequestspermin>20</maxrequestspermin>
  </ssuser>
  <jeu id="1">
    <noms>
      <nom region="us">Super Mario Bros.</nom>
    </noms>
  </jeu>
</Data>'''
        
        responses.add(
            responses.GET,
            'https://api.screenscraper.fr/api2/jeuInfos.php',
            body=response_xml,
            status=200
        )
        
        # Should reject due to name mismatch
        with pytest.raises(SkippableAPIError, match="Name verification failed"):
            api_client.query_game(rom_info)
    
    @responses.activate
    def test_workflow_accepts_similar_names(self, api_client):
        """Test that workflow accepts names with minor differences."""
        # ROM with region tags and special chars
        rom_info = ROMInfo(
            path=Path("/fake/Super Mario Bros. (USA) (Rev A) [!].nes"),
            filename="Super Mario Bros. (USA) (Rev A) [!].nes",
            basename="Super Mario Bros. (USA) (Rev A) [!]",
            rom_type=ROMType.STANDARD,
            system="nes",
            query_filename="Super Mario Bros. (USA) (Rev A) [!].nes",
            file_size=40976,
            crc32="3337ec46"
        )
        
        # API returns clean name
        response_xml = b'''<?xml version="1.0" encoding="UTF-8"?>
<Data>
  <ssuser>
    <id>12345</id>
    <maxrequestspermin>20</maxrequestspermin>
  </ssuser>
  <jeu id="1">
    <noms>
      <nom region="us">Super Mario Bros.</nom>
    </noms>
  </jeu>
</Data>'''
        
        responses.add(
            responses.GET,
            'https://api.screenscraper.fr/api2/jeuInfos.php',
            body=response_xml,
            status=200
        )
        
        # Should succeed - names are similar after normalization
        game_data = api_client.query_game(rom_info)
        assert game_data is not None
        assert game_data['name'] == 'Super Mario Bros.'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
