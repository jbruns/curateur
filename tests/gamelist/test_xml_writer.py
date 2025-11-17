"""Tests for xml_writer module."""
import pytest
from pathlib import Path
from lxml import etree
from curateur.gamelist.xml_writer import GamelistWriter
from curateur.gamelist.game_entry import GameEntry, GamelistMetadata
from curateur.gamelist.parser import GamelistParser


@pytest.mark.unit
class TestGamelistWriter:
    """Test GamelistWriter."""
    
    def test_write_gamelist_basic(self, tmp_path, sample_metadata):
        """Test writing basic gamelist."""
        writer = GamelistWriter(sample_metadata)
        entries = [
            GameEntry(path="./Game.nes", name="Test Game")
        ]
        
        output_path = tmp_path / "gamelist.xml"
        writer.write_gamelist(entries, output_path)
        
        assert output_path.exists()
        assert output_path.stat().st_size > 0
    
    def test_write_gamelist_complete_entry(self, tmp_path, sample_metadata, sample_game_entry_with_media):
        """Test writing gamelist with complete entry (media paths not written to XML)."""
        writer = GamelistWriter(sample_metadata)
        entries = [sample_game_entry_with_media]
        
        output_path = tmp_path / "gamelist.xml"
        writer.write_gamelist(entries, output_path)
        
        # Parse it back to verify
        parser = GamelistParser()
        parsed = parser.parse_gamelist(output_path)
        
        assert len(parsed) == 1
        entry = parsed[0]
        assert entry.name == "Test Game"
        assert entry.screenscraper_id == "12345"
        assert entry.rating == 0.85
        # Media paths should not be in the XML output (ES-DE infers from directory structure)
        assert entry.image is None
        assert entry.thumbnail is None
        assert entry.video is None
    
    def test_write_gamelist_with_provider(self, tmp_path, sample_metadata):
        """Test gamelist includes provider metadata."""
        writer = GamelistWriter(sample_metadata)
        entries = [GameEntry(path="./Game.nes", name="Game")]
        
        output_path = tmp_path / "gamelist.xml"
        writer.write_gamelist(entries, output_path)
        
        # Parse and check provider
        tree = etree.parse(str(output_path))
        root = tree.getroot()
        
        provider = root.find('provider')
        assert provider is not None
        assert provider.find('System').text == "Nintendo Entertainment System"
        assert provider.find('software').text == "curateur"
        assert provider.find('database').text == "ScreenScraper.fr"
        assert provider.find('web').text == "http://www.screenscraper.fr"
    
    def test_write_gamelist_rating_format(self, tmp_path, sample_metadata):
        """Test rating is formatted without trailing zeros."""
        writer = GamelistWriter(sample_metadata)
        entries = [
            GameEntry(path="./Game1.nes", name="Game 1", rating=0.85),
            GameEntry(path="./Game2.nes", name="Game 2", rating=0.9),
            GameEntry(path="./Game3.nes", name="Game 3", rating=1.0)
        ]
        
        output_path = tmp_path / "gamelist.xml"
        writer.write_gamelist(entries, output_path)
        
        # Read raw content to check formatting
        content = output_path.read_text()
        
        assert "<rating>0.85</rating>" in content
        assert "<rating>0.9</rating>" in content
        assert "<rating>1</rating>" in content or "<rating>1.0</rating>" in content
    
    def test_write_gamelist_utf8_encoding(self, tmp_path, sample_metadata):
        """Test gamelist is written with UTF-8 encoding."""
        writer = GamelistWriter(sample_metadata)
        entries = [
            GameEntry(path="./Game.nes", name="Test Game", desc="Description with special chars: é, ñ, 中文")
        ]
        
        output_path = tmp_path / "gamelist.xml"
        writer.write_gamelist(entries, output_path)
        
        # Read as bytes and check encoding declaration
        content_bytes = output_path.read_bytes()
        assert b'encoding="UTF-8"' in content_bytes or b"encoding='UTF-8'" in content_bytes
        
        # Verify it can be read back properly
        content_text = output_path.read_text(encoding='utf-8')
        assert "é, ñ, 中文" in content_text
    
    def test_write_gamelist_pretty_printed(self, tmp_path, sample_metadata):
        """Test gamelist is pretty-printed with indentation."""
        writer = GamelistWriter(sample_metadata)
        entries = [GameEntry(path="./Game.nes", name="Game")]
        
        output_path = tmp_path / "gamelist.xml"
        writer.write_gamelist(entries, output_path)
        
        content = output_path.read_text()
        
        # Should have indentation (tabs or spaces)
        assert "\t" in content or "  " in content
        # Should have newlines between elements
        assert content.count("\n") > 5
    
    def test_write_gamelist_empty_hash_element(self, tmp_path, sample_metadata):
        """Test gamelist includes empty hash element for ES-DE compatibility."""
        writer = GamelistWriter(sample_metadata)
        entries = [GameEntry(path="./Game.nes", name="Game")]
        
        output_path = tmp_path / "gamelist.xml"
        writer.write_gamelist(entries, output_path)
        
        content = output_path.read_text()
        # lxml may write as <hash/>, <hash />, or <hash></hash> - all valid
        assert "<hash" in content and ("</hash>" in content or "/>" in content)
    
    def test_write_gamelist_with_user_fields(self, tmp_path, sample_metadata):
        """Test writing gamelist with user-editable fields."""
        writer = GamelistWriter(sample_metadata)
        entries = [
            GameEntry(
                path="./Game.nes",
                name="Game",
                favorite=True,
                playcount=42,
                lastplayed="20251115T143000",
                hidden=False,
                extra_fields={'kidgame': 'true'}
            )
        ]
        
        output_path = tmp_path / "gamelist.xml"
        writer.write_gamelist(entries, output_path)
        
        content = output_path.read_text()
        assert "<favorite>true</favorite>" in content
        assert "<playcount>42</playcount>" in content
        assert "<lastplayed>20251115T143000</lastplayed>" in content
        # kidgame from extra_fields
        assert "<kidgame>true</kidgame>" in content
    
    def test_write_gamelist_with_extra_fields(self, tmp_path, sample_metadata):
        """Test writing gamelist preserves extra fields."""
        writer = GamelistWriter(sample_metadata)
        entries = [
            GameEntry(
                path="./Game.nes",
                name="Game",
                extra_fields={'customfield': 'custom value', 'userrating': '5'}
            )
        ]
        
        output_path = tmp_path / "gamelist.xml"
        writer.write_gamelist(entries, output_path)
        
        content = output_path.read_text()
        assert "<customfield>custom value</customfield>" in content
        assert "<userrating>5</userrating>" in content
    
    def test_write_gamelist_xml_well_formed(self, tmp_path, sample_metadata):
        """Test written gamelist is well-formed XML."""
        writer = GamelistWriter(sample_metadata)
        entries = [
            GameEntry(path="./Game.nes", name="Game", desc="Description")
        ]
        
        output_path = tmp_path / "gamelist.xml"
        writer.write_gamelist(entries, output_path)
        
        # Should be able to parse without errors
        tree = etree.parse(str(output_path))
        root = tree.getroot()
        
        assert root.tag == "gameList"
        assert writer.validate_output(output_path) is True
    
    def test_write_gamelist_html_entity_escaping(self, tmp_path, sample_metadata):
        """Test HTML entities are properly escaped in output."""
        writer = GamelistWriter(sample_metadata)
        entries = [
            GameEntry(
                path="./Game.nes",
                name='Mario & Luigi: Partners "Forever"',
                desc="A game with <special> characters & symbols."
            )
        ]
        
        output_path = tmp_path / "gamelist.xml"
        writer.write_gamelist(entries, output_path)
        
        content = output_path.read_text()
        
        # lxml auto-escapes these in text content
        assert "&amp;" in content
        assert "&lt;" in content
        assert "&gt;" in content
        # Quotes in text content typically aren't escaped unless in attributes
    
    def test_validate_output_valid(self, tmp_path, sample_metadata):
        """Test validation passes for valid gamelist."""
        writer = GamelistWriter(sample_metadata)
        entries = [GameEntry(path="./Game.nes", name="Game")]
        
        output_path = tmp_path / "gamelist.xml"
        writer.write_gamelist(entries, output_path)
        
        assert writer.validate_output(output_path) is True
    
    def test_validate_output_malformed(self, fixture_path):
        """Test validation fails for malformed gamelist."""
        writer = GamelistWriter(GamelistMetadata(
            system="Test",
            software="curateur",
            database="ScreenScraper.fr",
            web="http://www.screenscraper.fr"
        ))
        
        malformed_path = fixture_path / 'invalid' / 'malformed.xml'
        
        assert writer.validate_output(malformed_path) is False


@pytest.mark.unit
class TestGamelistWriterHelpers:
    """Test GamelistWriter helper methods."""
    
    def test_create_provider_element(self, sample_metadata):
        """Test creating provider XML element."""
        writer = GamelistWriter(sample_metadata)
        provider = writer._create_provider_element()
        
        assert provider.tag == "provider"
        assert provider.find('System').text == "Nintendo Entertainment System"
        assert provider.find('software').text == "curateur"
    
    def test_create_game_element_basic(self, sample_metadata):
        """Test creating game XML element."""
        writer = GamelistWriter(sample_metadata)
        entry = GameEntry(path="./Game.nes", name="Test Game")
        
        game_elem = writer._create_game_element(entry)
        
        assert game_elem.tag == "game"
        assert game_elem.find('path').text == "./Game.nes"
        assert game_elem.find('name').text == "Test Game"
    
    def test_create_game_element_with_id(self, sample_metadata):
        """Test game element includes id attribute."""
        writer = GamelistWriter(sample_metadata)
        entry = GameEntry(
            path="./Game.nes",
            name="Game",
            screenscraper_id="12345"
        )
        
        game_elem = writer._create_game_element(entry)
        
        assert game_elem.get('id') == "12345"
        assert game_elem.get('source') == "ScreenScraper.fr"
    
    def test_add_element_with_text(self, sample_metadata):
        """Test adding child element with text."""
        writer = GamelistWriter(sample_metadata)
        parent = etree.Element('parent')
        
        writer._add_element(parent, 'child', 'text value')
        
        assert parent.find('child').text == "text value"
    
    def test_add_element_skip_none(self, sample_metadata):
        """Test adding element with None value creates empty element."""
        writer = GamelistWriter(sample_metadata)
        parent = etree.Element('parent')
        
        writer._add_element(parent, 'child', None)
        
        # _add_element creates element with None text (empty element)
        child = parent.find('child')
        assert child is not None
        assert child.text is None
    
    def test_add_element_skip_empty_string(self, sample_metadata):
        """Test adding element with empty string."""
        writer = GamelistWriter(sample_metadata)
        parent = etree.Element('parent')
        
        writer._add_element(parent, 'child', '')
        
        # _add_element creates element even with empty text
        child = parent.find('child')
        assert child is not None
        assert child.text == ''
