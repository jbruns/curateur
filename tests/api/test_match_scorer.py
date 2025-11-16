"""Tests for match confidence scoring."""

import pytest
from curateur.api.match_scorer import (
    calculate_match_confidence,
    _score_filename_similarity,
    _score_region_match,
    _score_file_size,
    _score_media_availability,
    _score_user_rating,
    _normalize_name,
)


class TestFilenameNormalization:
    """Test filename normalization for matching."""
    
    def test_remove_rom_tags(self):
        """Remove common ROM tags from filenames."""
        assert _normalize_name("Mario Bros (USA)") == "mario bros"
        assert _normalize_name("Zelda [!]") == "zelda"
        assert _normalize_name("Sonic (Rev 1)") == "sonic"
        
    def test_remove_punctuation(self):
        """Remove punctuation but keep alphanumeric."""
        assert _normalize_name("Super Mario Bros.") == "super mario bros"
        assert _normalize_name("F-Zero") == "fzero"
        
    def test_normalize_whitespace(self):
        """Collapse multiple spaces."""
        assert _normalize_name("Game   Name") == "game name"
        assert _normalize_name("  Title  ") == "title"


class TestFilenameSimilarity:
    """Test filename similarity scoring."""
    
    def test_exact_match(self):
        """Exact filename match should score high."""
        rom_info = {'path': '/roms/mario.nes', 'size': 40960}
        game_data = {'names': {'us': 'mario'}}
        score = _score_filename_similarity(rom_info, game_data)
        assert score > 0.9
    
    def test_close_match(self):
        """Close match should score well."""
        rom_info = {'path': '/roms/super-mario-bros.nes', 'size': 40960}
        game_data = {'names': {'us': 'Super Mario Bros.'}}
        score = _score_filename_similarity(rom_info, game_data)
        assert score > 0.8
    
    def test_no_match(self):
        """Completely different names should score low."""
        rom_info = {'path': '/roms/mario.nes', 'size': 40960}
        game_data = {'names': {'us': 'Zelda'}}
        score = _score_filename_similarity(rom_info, game_data)
        assert score < 0.3
    
    def test_multiple_regions(self):
        """Should find best match across all regions."""
        rom_info = {'path': '/roms/mario.nes', 'size': 40960}
        game_data = {'names': {
            'jp': '日本語タイトル',
            'us': 'Mario Bros',
            'eu': 'Mario Bros.'
        }}
        score = _score_filename_similarity(rom_info, game_data)
        assert score > 0.65  # Should match 'mario' in us/eu names


class TestRegionMatch:
    """Test region matching scoring."""
    
    def test_first_preferred_region(self):
        """First preferred region should score 1.0."""
        game_data = {'names': {'us': 'Game', 'eu': 'Game'}}
        preferred = ['us', 'eu', 'jp']
        score = _score_region_match(game_data, preferred)
        assert score == 1.0
    
    def test_second_preferred_region(self):
        """Second preferred region should score 0.8."""
        game_data = {'names': {'eu': 'Game', 'jp': 'ゲーム'}}
        preferred = ['us', 'eu', 'jp']
        score = _score_region_match(game_data, preferred)
        assert score == 0.8
    
    def test_no_preferred_region(self):
        """Game without preferred regions should score low."""
        game_data = {'names': {'jp': 'ゲーム'}}
        preferred = ['us', 'eu']
        score = _score_region_match(game_data, preferred)
        assert score == 0.1


class TestFileSizeMatch:
    """Test file size matching scoring."""
    
    def test_exact_size_match(self):
        """Exact size match should score 1.0."""
        rom_info = {'size': 40960}
        game_data = {'romsize': '40960'}
        score = _score_file_size(rom_info, game_data)
        assert score == 1.0
    
    def test_close_size_match(self):
        """Close size match (<5% diff) should score 0.9."""
        rom_info = {'size': 40960}
        game_data = {'romsize': '41000'}  # ~1% difference
        score = _score_file_size(rom_info, game_data)
        assert score == 0.9
    
    def test_size_unknown(self):
        """Unknown size should score 0.5 (neutral)."""
        rom_info = {'size': 40960}
        game_data = {}
        score = _score_file_size(rom_info, game_data)
        assert score == 0.5
    
    def test_large_difference(self):
        """Large size difference should score low."""
        rom_info = {'size': 40960}
        game_data = {'romsize': '100000'}  # >100% difference
        score = _score_file_size(rom_info, game_data)
        assert score == 0.2


class TestMediaAvailability:
    """Test media availability scoring."""
    
    def test_multiple_media_types(self):
        """Game with multiple media types should score high."""
        game_data = {
            'cover': [{'url': 'http://example.com/cover.jpg'}],
            'screenshot': [{'url': 'http://example.com/ss.jpg'}],
            'titlescreen': {'url': 'http://example.com/title.jpg'}
        }
        score = _score_media_availability(game_data)
        assert score == 1.0  # 3 types = 1.0
    
    def test_single_media_type(self):
        """Game with one media type should score proportionally."""
        game_data = {
            'cover': [{'url': 'http://example.com/cover.jpg'}]
        }
        score = _score_media_availability(game_data)
        assert abs(score - 0.333) < 0.1
    
    def test_no_media(self):
        """Game with no media should score 0.0."""
        game_data = {}
        score = _score_media_availability(game_data)
        assert score == 0.0


class TestUserRating:
    """Test user rating scoring."""
    
    def test_high_rating(self):
        """High rating should score well."""
        game_data = {'note': '18'}  # 18/20 = 0.9
        score = _score_user_rating(game_data)
        assert abs(score - 0.9) < 0.01
    
    def test_low_rating(self):
        """Low rating should score proportionally."""
        game_data = {'note': '5'}  # 5/20 = 0.25
        score = _score_user_rating(game_data)
        assert abs(score - 0.25) < 0.01
    
    def test_no_rating(self):
        """No rating should score 0.5 (neutral)."""
        game_data = {}
        score = _score_user_rating(game_data)
        assert score == 0.5


class TestOverallConfidence:
    """Test complete confidence calculation."""
    
    def test_perfect_match(self):
        """Perfect match should score very high."""
        rom_info = {
            'path': '/roms/Super Mario Bros (USA).nes',
            'size': 40960,
            'crc32': 'ABCD1234',
            'system': 'nes'
        }
        
        game_data = {
            'names': {'us': 'Super Mario Bros', 'eu': 'Super Mario Bros.'},
            'romsize': '40960',
            'note': '19',
            'cover': [{'url': 'http://example.com/cover.jpg'}],
            'screenshot': [{'url': 'http://example.com/ss.jpg'}],
            'titlescreen': {'url': 'http://example.com/title.jpg'}
        }
        
        preferred_regions = ['us', 'eu', 'jp']
        score = calculate_match_confidence(rom_info, game_data, preferred_regions)
        
        # Should be high confidence (>0.9)
        assert score > 0.9
    
    def test_poor_match(self):
        """Poor match should score low."""
        rom_info = {
            'path': '/roms/mario.nes',
            'size': 40960,
            'crc32': 'ABCD1234',
            'system': 'nes'
        }
        
        game_data = {
            'names': {'jp': 'ゼルダの伝説'},
            'romsize': '100000',
            'note': '5'
        }
        
        preferred_regions = ['us', 'eu']
        score = calculate_match_confidence(rom_info, game_data, preferred_regions)
        
        # Should be low confidence (<0.4)
        assert score < 0.4
    
    def test_weighted_average(self):
        """Verify weighted average calculation."""
        # Mock individual scores
        rom_info = {
            'path': '/roms/test.nes',
            'size': 40960,
            'system': 'nes'
        }
        
        game_data = {
            'names': {'us': 'test'},  # Filename: 1.0 (40%)
            'romsize': '40960',  # Size: 1.0 (15%)
            'note': '20'  # Rating: 1.0 (5%)
            # Region: 1.0 (30%), Media: 0.0 (10%)
        }
        
        preferred_regions = ['us']
        score = calculate_match_confidence(rom_info, game_data, preferred_regions)
        
        # Expected: 0.4 + 0.3 + 0.15 + 0.0 + 0.05 = 0.9
        assert abs(score - 0.9) < 0.05
