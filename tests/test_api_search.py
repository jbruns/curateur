"""Tests for ScreenScraper search endpoint (jeuRecherche.php)."""

import pytest
import responses
from pathlib import Path
from typing import Dict, Any

from curateur.api.client import ScreenScraperClient
from curateur.api.error_handler import SkippableAPIError
from curateur.api.response_parser import (
    validate_response,
    parse_game_info,
    parse_search_results,
    extract_error_message
)


@pytest.fixture
def api_config():
    """Configuration for API client tests."""
    return {
        'screenscraper': {
            'devid': 'test_dev',
            'devpassword': 'test_pass',
            'softname': 'test_soft',
            'user_id': 'test_user',
            'user_password': 'test_pw'
        },
        'api': {
            'request_timeout': 30,
            'max_retries': 3,
            'retry_backoff': 1.0
        }
    }


@pytest.fixture
def api_client(api_config):
    """Create API client for testing."""
    return ScreenScraperClient(api_config)


class TestSearchResponseParsing:
    """Test parsing of search endpoint responses."""
    
    def test_parse_multiple_search_results(self):
        """Test parsing response with multiple game results."""
        fixture_path = Path(__file__).parent / 'fixtures' / 'api' / 'jeuRecherche.xml'
        xml_data = fixture_path.read_bytes()
        
        # Validate response structure
        root = validate_response(xml_data)
        assert root is not None
        
        # Parse all search results
        games = parse_search_results(root)
        assert len(games) > 0
        
        # Check first game
        first_game = games[0]
        assert first_game['id'] == '3'
        assert 'Sonic The Hedgehog 2' in first_game['name']
        assert first_game['system'] == 'Megadrive'
        assert first_game['developer'] == 'SEGA'
        assert first_game['publisher'] == 'SEGA'
        
        # Check second game
        second_game = games[1]
        assert second_game['id'] == '5'
        assert 'Sonic The Hedgehog' in second_game['name']
        assert second_game['system'] == 'Megadrive'
    
    def test_parse_single_search_result(self):
        """Test parsing response with single game result."""
        xml_data = b'''<?xml version="1.0" encoding="UTF-8"?>
<Data>
  <serveurs>
    <maxthreads>1</maxthreads>
  </serveurs>
  <ssuser>
    <id>test</id>
    <maxthreads>1</maxthreads>
    <maxrequestspermin>20</maxrequestspermin>
    <maxrequestsperday>10000</maxrequestsperday>
    <requeststoday>50</requeststoday>
  </ssuser>
  <jeux>
    <jeu id="123">
      <noms>
        <nom region="us">Super Mario Bros.</nom>
      </noms>
      <systeme id="2">Nintendo Entertainment System (NES)</systeme>
      <developpeur>Nintendo</developpeur>
      <editeur>Nintendo</editeur>
    </jeu>
  </jeux>
</Data>'''
        
        root = validate_response(xml_data)
        games = parse_search_results(root)
        
        assert len(games) == 1
        game = games[0]
        assert game['id'] == '123'
        assert game['name'] == 'Super Mario Bros.'
    
    def test_parse_empty_search_results(self):
        """Test parsing response with no results."""
        xml_data = b'''<?xml version="1.0" encoding="UTF-8"?>
<Data>
  <serveurs>
    <maxthreads>1</maxthreads>
  </serveurs>
  <ssuser>
    <id>test</id>
    <maxthreads>1</maxthreads>
    <maxrequestspermin>20</maxrequestspermin>
    <maxrequestsperday>10000</maxrequestsperday>
    <requeststoday>50</requeststoday>
  </ssuser>
  <jeux>
  </jeux>
</Data>'''
        
        root = validate_response(xml_data)
        games = parse_search_results(root)
        assert len(games) == 0
    
    def test_parse_search_with_incomplete_metadata(self):
        """Test parsing search results with incomplete game metadata."""
        xml_data = b'''<?xml version="1.0" encoding="UTF-8"?>
<Data>
  <serveurs><maxthreads>1</maxthreads></serveurs>
  <ssuser>
    <id>test</id>
    <maxthreads>1</maxthreads>
    <maxrequestspermin>20</maxrequestspermin>
    <maxrequestsperday>10000</maxrequestsperday>
    <requeststoday>50</requeststoday>
  </ssuser>
  <jeux>
    <jeu id="456">
      <noms>
        <nom region="us">Obscure Game</nom>
      </noms>
      <systeme id="2">NES</systeme>
    </jeu>
  </jeux>
</Data>'''
        
        root = validate_response(xml_data)
        games = parse_search_results(root)
        game = games[0]
        
        assert game['id'] == '456'
        assert game['name'] == 'Obscure Game'
        assert game['system'] == 'NES'
        # Missing fields should not be present or be None
        assert game.get('developer') is None
        assert game.get('publisher') is None
        assert game.get('media') is None or game['media'] == {}


class TestSearchResponseValidation:
    """Test validation of search responses."""
    
    def test_validate_search_response_structure(self):
        """Test validation accepts search response structure."""
        xml_data = b'''<?xml version="1.0" encoding="UTF-8"?>
<Data>
  <serveurs><maxthreads>1</maxthreads></serveurs>
  <ssuser><id>test</id></ssuser>
  <jeux></jeux>
</Data>'''
        
        root = validate_response(xml_data)
        assert root.tag == 'Data'
        assert root.find('jeux') is not None
    
    def test_validate_missing_jeux_container(self):
        """Test handling of missing jeux container."""
        xml_data = b'''<?xml version="1.0" encoding="UTF-8"?>
<Data>
  <serveurs><maxthreads>1</maxthreads></serveurs>
  <ssuser><id>test</id></ssuser>
</Data>'''
        
        root = validate_response(xml_data)
        jeux = root.find('jeux')
        assert jeux is None  # Should handle gracefully


class TestSearchIteratorPattern:
    """Test iterator pattern for processing search results."""
    
    def test_iterate_over_search_results(self):
        """Test iterating through multiple search results."""
        fixture_path = Path(__file__).parent / 'fixtures' / 'api' / 'jeuRecherche.xml'
        xml_data = fixture_path.read_bytes()
        
        root = validate_response(xml_data)
        games = parse_search_results(root)
        
        game_ids = [g['id'] for g in games]
        game_names = [g['name'] for g in games]
        
        # Should have multiple Sonic games
        assert len(game_ids) >= 3
        assert all('Sonic' in name for name in game_names)
        
        # IDs should be unique
        assert len(game_ids) == len(set(game_ids))
    
    def test_filter_search_results_by_system(self):
        """Test filtering search results by system."""
        fixture_path = Path(__file__).parent / 'fixtures' / 'api' / 'jeuRecherche.xml'
        xml_data = fixture_path.read_bytes()
        
        root = validate_response(xml_data)
        games = parse_search_results(root)
        
        megadrive_games = [g for g in games if g['system'] == 'Megadrive']
        
        # All games in fixture should be Megadrive
        assert len(megadrive_games) > 0
        assert all(g['system'] == 'Megadrive' for g in megadrive_games)


class TestSearchResultComparison:
    """Test comparing and ranking search results."""
    
    def test_compare_game_ratings(self):
        """Test extracting and comparing game ratings from search results."""
        fixture_path = Path(__file__).parent / 'fixtures' / 'api' / 'jeuRecherche.xml'
        xml_data = fixture_path.read_bytes()
        
        root = validate_response(xml_data)
        games = parse_search_results(root)
        
        ratings = [(g['name'], g['rating']) for g in games if 'rating' in g]
        
        # Should have ratings for multiple games
        assert len(ratings) > 0
        # Ratings should be numeric
        assert all(isinstance(r[1], (int, float)) for r in ratings)
    
    def test_identify_best_match_in_results(self):
        """Test identifying best matching game from search results."""
        xml_data = b'''<?xml version="1.0" encoding="UTF-8"?>
<Data>
  <serveurs><maxthreads>1</maxthreads></serveurs>
  <ssuser>
    <id>test</id>
    <maxthreads>1</maxthreads>
    <maxrequestspermin>20</maxrequestspermin>
    <maxrequestsperday>10000</maxrequestsperday>
    <requeststoday>50</requeststoday>
  </ssuser>
  <jeux>
    <jeu id="1">
      <noms><nom region="us">Super Mario Bros. 2</nom></noms>
      <systeme id="2">NES</systeme>
    </jeu>
    <jeu id="2">
      <noms><nom region="us">Super Mario Bros.</nom></noms>
      <systeme id="2">NES</systeme>
    </jeu>
    <jeu id="3">
      <noms><nom region="us">Super Mario Bros. 3</nom></noms>
      <systeme id="2">NES</systeme>
    </jeu>
  </jeux>
</Data>'''
        
        root = validate_response(xml_data)
        games = parse_search_results(root)
        
        search_term = "Super Mario Bros."
        best_match = None
        best_score = -1
        
        for game_data in games:
            # Simple exact match scoring
            if game_data['name'] == search_term:
                score = 100
            elif search_term in game_data['name']:
                score = 50
            else:
                score = 0
            
            if score > best_score:
                best_score = score
                best_match = game_data
        
        assert best_match is not None
        assert best_match['id'] == '2'
        assert best_match['name'] == search_term


class TestSearchErrorHandling:
    """Test error handling for search endpoint."""
    
    def test_parse_search_error_response(self):
        """Test parsing error in search response."""
        xml_data = b'''<?xml version="1.0" encoding="UTF-8"?>
<Data>
  <ssuser>
    <id>test</id>
    <maxthreads>1</maxthreads>
    <maxrequestspermin>20</maxrequestspermin>
    <maxrequestsperday>10000</maxrequestsperday>
    <requeststoday>50</requeststoday>
  </ssuser>
  <erreur>No games found matching your criteria</erreur>
</Data>'''
        
        root = validate_response(xml_data)
        error_msg = extract_error_message(root)
        
        assert error_msg is not None
        assert "No games found" in error_msg
    
    def test_handle_malformed_game_in_results(self):
        """Test handling malformed game entry in search results."""
        xml_data = b'''<?xml version="1.0" encoding="UTF-8"?>
<Data>
  <serveurs><maxthreads>1</maxthreads></serveurs>
  <ssuser>
    <id>test</id>
    <maxthreads>1</maxthreads>
    <maxrequestspermin>20</maxrequestspermin>
    <maxrequestsperday>10000</maxrequestsperday>
    <requeststoday>50</requeststoday>
  </ssuser>
  <jeux>
    <jeu id="1">
      <noms><nom region="us">Good Game</nom></noms>
      <systeme id="2">NES</systeme>
    </jeu>
    <jeu>
      <!-- Missing ID - parser handles gracefully -->
      <noms><nom region="us">Bad Game</nom></noms>
    </jeu>
    <jeu id="3">
      <noms><nom region="us">Another Good Game</nom></noms>
      <systeme id="2">NES</systeme>
    </jeu>
  </jeux>
</Data>'''
        
        root = validate_response(xml_data)
        # parse_search_results already filters malformed entries
        valid_games = parse_search_results(root)
        
        # Parser is lenient - it parses all 3 games even without ID
        assert len(valid_games) == 3
        assert valid_games[0]['id'] == '1'
        assert valid_games[1].get('id') is None  # Missing ID
        assert valid_games[2]['id'] == '3'
        
        # Filter for games with IDs if needed
        games_with_ids = [g for g in valid_games if 'id' in g and g['id']]
        assert len(games_with_ids) == 2


class TestSearchWithMedia:
    """Test handling media URLs in search results."""
    
    def test_extract_media_from_search_results(self):
        """Test extracting media URLs from search results."""
        fixture_path = Path(__file__).parent / 'fixtures' / 'api' / 'jeuRecherche.xml'
        xml_data = fixture_path.read_bytes()
        
        root = validate_response(xml_data)
        games = parse_search_results(root)
        
        games_with_media = 0
        for game_data in games:
            if 'media' in game_data and game_data['media']:
                games_with_media += 1
                # Check for common media types
                media_types = set(game_data['media'].keys())
                # Search results should have box art, screenshots, etc.
                assert len(media_types) > 0
        
        # Multiple games should have media
        assert games_with_media > 0
    
    def test_count_media_types_in_results(self):
        """Test counting different media types across results."""
        fixture_path = Path(__file__).parent / 'fixtures' / 'api' / 'jeuRecherche.xml'
        xml_data = fixture_path.read_bytes()
        
        root = validate_response(xml_data)
        games = parse_search_results(root)
        
        all_media_types = set()
        for game_data in games:
            if 'media' in game_data:
                all_media_types.update(game_data['media'].keys())
        
        # Should have various media types
        assert len(all_media_types) > 5
        # Common types should be present
        common_types = {'box-2D', 'ss', 'wheel', 'video'}
        assert len(common_types & all_media_types) > 0


class TestSearchMetadata:
    """Test extracting metadata from search responses."""
    
    def test_extract_server_info_from_search(self):
        """Test extracting server information from search response."""
        fixture_path = Path(__file__).parent / 'fixtures' / 'api' / 'jeuRecherche.xml'
        xml_data = fixture_path.read_bytes()
        
        root = validate_response(xml_data)
        serveurs = root.find('serveurs')
        
        assert serveurs is not None
        # Check for server info fields
        assert serveurs.find('maxthreadformember') is not None
        assert serveurs.find('threadformember') is not None
    
    def test_extract_user_limits_from_search(self):
        """Test extracting user rate limits from search response."""
        fixture_path = Path(__file__).parent / 'fixtures' / 'api' / 'jeuRecherche.xml'
        xml_data = fixture_path.read_bytes()
        
        root = validate_response(xml_data)
        ssuser = root.find('ssuser')
        
        assert ssuser is not None
        # Rate limit fields should be present
        max_threads = ssuser.find('maxthreads')
        requests_today = ssuser.find('requeststoday')
        max_per_day = ssuser.find('maxrequestsperday')
        
        assert max_threads is not None
        assert requests_today is not None
        assert max_per_day is not None


# Note: Integration tests for search endpoint would go in test_api_integration.py
# Live tests for search endpoint would go in test_api_live.py
# This file focuses on response parsing and data extraction from search results
