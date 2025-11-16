"""
Tests for API response parser module.

Tests response_parser.py functions with real XML fixtures from ScreenScraper,
covering success cases, error cases, partial data, and malformed responses.
"""

import pytest
from pathlib import Path
from lxml import etree

from curateur.api.response_parser import (
    validate_response,
    parse_game_info,
    parse_user_info,
    parse_media_urls,
    decode_html_entities,
    extract_error_message,
    ResponseError
)


# Fixture paths
FIXTURES_DIR = Path(__file__).parent.parent / 'fixtures' / 'api'
ERROR_FIXTURES = FIXTURES_DIR / 'errors'
PARTIAL_FIXTURES = FIXTURES_DIR / 'partial'
MALFORMED_FIXTURES = FIXTURES_DIR / 'malformed'


class TestValidateResponse:
    """Test XML response validation."""
    
    def test_valid_error_response(self):
        """Test validation with valid error response."""
        xml_path = ERROR_FIXTURES / '404_not_found.xml'
        content = xml_path.read_bytes()
        
        root = validate_response(content, expected_format='xml')
        
        assert root is not None
        assert root.tag == 'Data'
    
    def test_empty_response(self):
        """Test validation fails on empty response."""
        with pytest.raises(ResponseError, match="Empty response body"):
            validate_response(b'')
    
    def test_invalid_xml(self):
        """Test validation fails on malformed XML."""
        xml_path = MALFORMED_FIXTURES / 'not_xml.xml'
        content = xml_path.read_bytes()
        
        with pytest.raises(ResponseError, match="Malformed XML"):
            validate_response(content)
    
    def test_invalid_root_element(self):
        """Test validation fails on incorrect root element."""
        xml_path = MALFORMED_FIXTURES / 'invalid_root.xml'
        content = xml_path.read_bytes()
        
        with pytest.raises(ResponseError, match="Invalid root element"):
            validate_response(content)


class TestParseGameInfo:
    """Test game information parsing."""
    
    def test_minimal_metadata(self):
        """Test parsing game with minimal metadata."""
        xml_path = PARTIAL_FIXTURES / 'minimal_metadata.xml'
        content = xml_path.read_bytes()
        root = etree.fromstring(content)
        
        game_data = parse_game_info(root)
        
        assert 'id' in game_data
        assert game_data['id'] == '12345'
        assert 'name' in game_data
        assert game_data['name'] == 'Test Game'
        assert 'names' in game_data
        assert 'wor' in game_data['names']
    
    def test_game_with_no_media(self):
        """Test parsing game without media section."""
        xml_path = PARTIAL_FIXTURES / 'no_media.xml'
        content = xml_path.read_bytes()
        root = etree.fromstring(content)
        
        game_data = parse_game_info(root)
        
        assert 'id' in game_data
        assert game_data['name'] == 'Game Without Media'
        assert 'genres' in game_data
        assert 'Action' in game_data['genres']
        assert 'developer' in game_data
        assert game_data['developer'] == 'Test Developer'
        assert 'publisher' in game_data
        assert game_data['publisher'] == 'Test Publisher'
        assert 'players' in game_data
        assert game_data['players'] == '1-2'
        assert 'rating' in game_data
        assert game_data['rating'] == 7.5
        # No media key should exist
        assert 'media' not in game_data
    
    def test_missing_jeu_element(self):
        """Test parsing fails when <jeu> element is missing."""
        xml_path = MALFORMED_FIXTURES / 'missing_jeu.xml'
        content = xml_path.read_bytes()
        root = etree.fromstring(content)
        
        with pytest.raises(ResponseError, match="Game not found"):
            parse_game_info(root)
    
    def test_name_priority_us_over_wor(self):
        """Test that 'us' region name is preferred over 'wor'."""
        xml_content = b'''<?xml version="1.0"?>
<Data>
  <jeu id="999">
    <noms>
      <nom region="wor" langue="en">World Name</nom>
      <nom region="us" langue="en">US Name</nom>
      <nom region="jp" langue="ja">JP Name</nom>
    </noms>
  </jeu>
</Data>'''
        
        root = etree.fromstring(xml_content)
        game_data = parse_game_info(root)
        
        assert game_data['name'] == 'US Name'
        assert 'us' in game_data['names']
        assert 'wor' in game_data['names']
        assert 'jp' in game_data['names']
    
    def test_name_fallback_to_wor(self):
        """Test that 'wor' region name is used when 'us' not available."""
        xml_content = b'''<?xml version="1.0"?>
<Data>
  <jeu id="999">
    <noms>
      <nom region="wor" langue="en">World Name</nom>
      <nom region="eu" langue="en">EU Name</nom>
    </noms>
  </jeu>
</Data>'''
        
        root = etree.fromstring(xml_content)
        game_data = parse_game_info(root)
        
        assert game_data['name'] == 'World Name'
    
    def test_name_fallback_to_first_available(self):
        """Test that first available name is used when no us/wor."""
        xml_content = b'''<?xml version="1.0"?>
<Data>
  <jeu id="999">
    <noms>
      <nom region="jp" langue="ja">Japanese Name</nom>
      <nom region="eu" langue="en">European Name</nom>
    </noms>
  </jeu>
</Data>'''
        
        root = etree.fromstring(xml_content)
        game_data = parse_game_info(root)
        
        # Should get one of them (dict ordering)
        assert game_data['name'] in ['Japanese Name', 'European Name']


class TestParseUserInfo:
    """Test user information parsing."""
    
    def test_parse_user_with_rate_limits(self):
        """Test parsing user info with rate limit data."""
        xml_path = ERROR_FIXTURES / '404_not_found.xml'
        content = xml_path.read_bytes()
        root = etree.fromstring(content)
        
        user_info = parse_user_info(root)
        
        assert 'id' in user_info
        assert user_info['id'] == 12345
        assert 'niveau' in user_info
        assert user_info['niveau'] == 1
        assert 'maxthreads' in user_info
        assert user_info['maxthreads'] == 1
        assert 'maxrequestspermin' in user_info
        assert user_info['maxrequestspermin'] == 20
        assert 'maxrequestsperday' in user_info
        assert user_info['maxrequestsperday'] == 10000
        assert 'requeststoday' in user_info
        assert user_info['requeststoday'] == 42
    
    def test_parse_user_quota_exceeded(self):
        """Test parsing user info when quota is exceeded."""
        xml_path = ERROR_FIXTURES / '430_quota_exceeded.xml'
        content = xml_path.read_bytes()
        root = etree.fromstring(content)
        
        user_info = parse_user_info(root)
        
        assert user_info['requeststoday'] == 10000
        assert user_info['maxrequestsperday'] == 10000
        # Should be at limit
        assert user_info['requeststoday'] >= user_info['maxrequestsperday']
    
    def test_parse_user_missing_ssuser(self):
        """Test parsing when <ssuser> element is missing."""
        xml_content = b'''<?xml version="1.0"?>
<Data>
  <jeu id="123">
    <noms><nom region="us">Test</nom></noms>
  </jeu>
</Data>'''
        
        root = etree.fromstring(xml_content)
        user_info = parse_user_info(root)
        
        assert user_info == {}


class TestDecodeHtmlEntities:
    """Test HTML entity decoding."""
    
    def test_decode_ampersand(self):
        """Test decoding &amp; to &."""
        text = "Mario &amp; Luigi"
        decoded = decode_html_entities(text)
        assert decoded == "Mario & Luigi"
    
    def test_decode_quotes(self):
        """Test decoding &quot; and &apos;."""
        text = "&quot;The Legend&apos;s Tale&quot;"
        decoded = decode_html_entities(text)
        assert decoded == '"The Legend\'s Tale"'
    
    def test_decode_lt_gt(self):
        """Test decoding &lt; and &gt;."""
        text = "Score &lt;100&gt;"
        decoded = decode_html_entities(text)
        assert decoded == "Score <100>"
    
    def test_decode_mixed_entities(self):
        """Test decoding multiple entities."""
        text = "&quot;Mario &amp; Sonic&quot; &lt;Adventure&gt;"
        decoded = decode_html_entities(text)
        assert decoded == '"Mario & Sonic" <Adventure>'
    
    def test_decode_empty_string(self):
        """Test decoding empty string."""
        assert decode_html_entities("") == ""
    
    def test_decode_none(self):
        """Test decoding None."""
        assert decode_html_entities(None) is None


class TestExtractErrorMessage:
    """Test error message extraction."""
    
    def test_extract_404_error(self):
        """Test extracting 404 not found error."""
        xml_path = ERROR_FIXTURES / '404_not_found.xml'
        content = xml_path.read_bytes()
        root = etree.fromstring(content)
        
        error = extract_error_message(root)
        
        assert error is not None
        assert "Rom non trouvée" in error
    
    def test_extract_429_error(self):
        """Test extracting 429 thread limit error."""
        xml_path = ERROR_FIXTURES / '429_thread_limit.xml'
        content = xml_path.read_bytes()
        root = etree.fromstring(content)
        
        error = extract_error_message(root)
        
        assert error is not None
        assert "threads maximum" in error.lower()
    
    def test_extract_430_error(self):
        """Test extracting 430 quota exceeded error."""
        xml_path = ERROR_FIXTURES / '430_quota_exceeded.xml'
        content = xml_path.read_bytes()
        root = etree.fromstring(content)
        
        error = extract_error_message(root)
        
        assert error is not None
        assert "requetes journalieres" in error.lower()
    
    def test_extract_423_error(self):
        """Test extracting 423 API closed error."""
        xml_path = ERROR_FIXTURES / '423_api_closed.xml'
        content = xml_path.read_bytes()
        root = etree.fromstring(content)
        
        error = extract_error_message(root)
        
        assert error is not None
        assert "API fermée" in error
    
    def test_extract_403_error(self):
        """Test extracting 403 invalid credentials error."""
        xml_path = ERROR_FIXTURES / '403_invalid_creds.xml'
        content = xml_path.read_bytes()
        root = etree.fromstring(content)
        
        error = extract_error_message(root)
        
        assert error is not None
        assert "Identifiants invalides" in error
    
    def test_extract_401_error(self):
        """Test extracting 401 API closed for non-members error."""
        xml_path = ERROR_FIXTURES / '401_api_closed_nonmembers.xml'
        content = xml_path.read_bytes()
        root = etree.fromstring(content)
        
        error = extract_error_message(root)
        
        assert error is not None
        assert "non membres" in error.lower()
    
    def test_extract_no_error(self):
        """Test extraction when no error exists."""
        xml_content = b'''<?xml version="1.0"?>
<Data>
  <jeu id="123">
    <noms><nom region="us">Test</nom></noms>
  </jeu>
</Data>'''
        
        root = etree.fromstring(xml_content)
        error = extract_error_message(root)
        
        assert error is None


class TestParseMediaUrls:
    """Test media URL parsing."""
    
    def test_parse_media_with_attributes(self):
        """Test parsing media with type, format, region."""
        xml_content = b'''<?xml version="1.0"?>
<medias>
  <media type="box-2D" format="png" region="us">https://example.com/box.png</media>
  <media type="ss" format="jpg" region="wor">https://example.com/screenshot.jpg</media>
  <media type="box-2D" format="jpg" region="eu">https://example.com/box_eu.jpg</media>
</medias>'''
        
        medias_elem = etree.fromstring(xml_content)
        media_dict = parse_media_urls(medias_elem)
        
        assert 'box-2D' in media_dict
        assert len(media_dict['box-2D']) == 2
        assert media_dict['box-2D'][0]['url'] == 'https://example.com/box.png'
        assert media_dict['box-2D'][0]['format'] == 'png'
        assert media_dict['box-2D'][0]['region'] == 'us'
        
        assert 'ss' in media_dict
        assert len(media_dict['ss']) == 1
        assert media_dict['ss'][0]['url'] == 'https://example.com/screenshot.jpg'
    
    def test_parse_media_empty(self):
        """Test parsing empty media section."""
        xml_content = b'<medias></medias>'
        
        medias_elem = etree.fromstring(xml_content)
        media_dict = parse_media_urls(medias_elem)
        
        assert media_dict == {}
    
    def test_parse_media_no_type(self):
        """Test parsing media without type attribute (should skip)."""
        xml_content = b'''<?xml version="1.0"?>
<medias>
  <media format="png">https://example.com/no_type.png</media>
  <media type="box-2D">https://example.com/with_type.png</media>
</medias>'''
        
        medias_elem = etree.fromstring(xml_content)
        media_dict = parse_media_urls(medias_elem)
        
        # Only the media with type should be included
        assert 'box-2D' in media_dict
        assert len(media_dict) == 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
