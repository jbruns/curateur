"""Tests for parser module."""
import pytest
from pathlib import Path
from lxml import etree
from curateur.gamelist.parser import GamelistParser, GamelistMerger
from curateur.gamelist.game_entry import GameEntry


@pytest.mark.unit
class TestGamelistParser:
    """Test GamelistParser."""
    
    def test_parse_valid_complete_gamelist(self, fixture_path):
        """Test parsing valid gamelist with complete entries."""
        parser = GamelistParser()
        gamelist_path = fixture_path / 'valid' / 'complete.xml'
        
        entries = parser.parse_gamelist(gamelist_path)
        
        assert len(entries) == 2
        assert all(isinstance(e, GameEntry) for e in entries)
        
        # Check first entry
        mario = entries[0]
        assert mario.path == "./Super Mario Bros.nes"
        assert mario.name == "Super Mario Bros."
        assert mario.screenscraper_id == "12345"
        assert mario.desc.startswith("A classic platformer")
        assert mario.rating == 0.95
        assert mario.releasedate == "19850913T000000"
        assert mario.developer == "Nintendo"
        assert mario.publisher == "Nintendo"
        assert mario.genre == "Platformer"
        assert mario.players == "1-2"
        assert mario.favorite is True
        assert mario.playcount == 42
        assert mario.lastplayed == "20251115T143000"
        # ES-DE infers media from directory structure, not gamelist.xml
        assert mario.image is None
        assert mario.thumbnail is None
        assert mario.video is None
    
    def test_parse_valid_minimal_gamelist(self, fixture_path):
        """Test parsing gamelist with minimal required fields."""
        parser = GamelistParser()
        gamelist_path = fixture_path / 'valid' / 'minimal.xml'
        
        entries = parser.parse_gamelist(gamelist_path)
        
        assert len(entries) == 1
        assert entries[0].path == "./Game.nes"
        assert entries[0].name == "Test Game"
        assert entries[0].screenscraper_id is None
    
    def test_parse_gamelist_with_html_entities(self, fixture_path):
        """Test parsing gamelist with HTML entities."""
        parser = GamelistParser()
        gamelist_path = fixture_path / 'valid' / 'with_html_entities.xml'
        
        entries = parser.parse_gamelist(gamelist_path)
        
        assert len(entries) == 1
        entry = entries[0]
        assert entry.name == 'Mario & Luigi: Partners "Forever"'
        assert entry.desc == "A game with <special> characters & symbols."
        assert entry.developer == "Company & Co."
        assert entry.publisher == "Test 'Publisher'"
    
    def test_parse_gamelist_with_extra_fields(self, fixture_path):
        """Test parsing gamelist with unknown custom fields."""
        parser = GamelistParser()
        gamelist_path = fixture_path / 'partial' / 'extra_fields.xml'
        
        entries = parser.parse_gamelist(gamelist_path)
        
        assert len(entries) == 1
        entry = entries[0]
        assert 'customfield1' in entry.extra_fields
        assert 'customfield2' in entry.extra_fields
        assert 'userrating' in entry.extra_fields
        assert entry.extra_fields['customfield1'] == 'Custom Value 1'
    
    def test_parse_gamelist_no_media(self, fixture_path):
        """Test parsing gamelist without media paths."""
        parser = GamelistParser()
        gamelist_path = fixture_path / 'partial' / 'no_media.xml'
        
        entries = parser.parse_gamelist(gamelist_path)
        
        assert len(entries) == 1
        entry = entries[0]
        assert entry.image is None
        assert entry.thumbnail is None
        assert entry.video is None
    
    def test_parse_malformed_xml(self, fixture_path):
        """Test parsing malformed XML raises error."""
        parser = GamelistParser()
        gamelist_path = fixture_path / 'invalid' / 'malformed.xml'
        
        with pytest.raises(etree.XMLSyntaxError):
            parser.parse_gamelist(gamelist_path)
    
    def test_parse_invalid_root_element(self, fixture_path):
        """Test parsing XML with wrong root element."""
        parser = GamelistParser()
        gamelist_path = fixture_path / 'invalid' / 'invalid_root.xml'
        
        # Should still parse but may return empty or handle gracefully
        # Actual behavior depends on implementation
        entries = parser.parse_gamelist(gamelist_path)
        # The implementation might return empty list or raise error
        assert isinstance(entries, list)
    
    def test_parse_not_xml_file(self, fixture_path):
        """Test parsing non-XML file raises error."""
        parser = GamelistParser()
        not_xml_path = fixture_path / 'invalid' / 'not_xml.txt'
        
        with pytest.raises(etree.XMLSyntaxError):
            parser.parse_gamelist(not_xml_path)
    
    def test_parse_nonexistent_file(self, tmp_path):
        """Test parsing nonexistent file raises error."""
        parser = GamelistParser()
        nonexistent = tmp_path / "does_not_exist.xml"
        
        with pytest.raises(FileNotFoundError):
            parser.parse_gamelist(nonexistent)


@pytest.mark.unit
class TestGamelistParserElementExtraction:
    """Test element extraction methods."""
    
    def test_get_text(self, fixture_path):
        """Test extracting text from XML element."""
        parser = GamelistParser()
        gamelist_path = fixture_path / 'valid' / 'complete.xml'
        
        tree = etree.parse(str(gamelist_path))
        root = tree.getroot()
        game_element = root.find('.//game')
        
        name = parser._get_text(game_element, 'name')
        assert name == "Super Mario Bros."
    
    def test_get_text_missing(self, fixture_path):
        """Test extracting missing element returns None."""
        parser = GamelistParser()
        gamelist_path = fixture_path / 'valid' / 'minimal.xml'
        
        tree = etree.parse(str(gamelist_path))
        root = tree.getroot()
        game_element = root.find('.//game')
        
        rating = parser._get_text(game_element, 'rating')
        assert rating is None
    
    def test_get_float(self, fixture_path):
        """Test extracting float value from element."""
        parser = GamelistParser()
        gamelist_path = fixture_path / 'valid' / 'complete.xml'
        
        tree = etree.parse(str(gamelist_path))
        root = tree.getroot()
        game_element = root.find('.//game')
        
        rating = parser._get_float(game_element, 'rating')
        assert rating == 0.95
        assert isinstance(rating, float)
    
    def test_get_float_invalid(self, fixture_path):
        """Test extracting invalid float returns None."""
        parser = GamelistParser()
        
        # Create a test element with invalid float
        game_element = etree.Element('game')
        rating_element = etree.SubElement(game_element, 'rating')
        rating_element.text = "not-a-number"
        
        rating = parser._get_float(game_element, 'rating')
        assert rating is None
    
    def test_get_int(self, fixture_path):
        """Test extracting integer value from element."""
        parser = GamelistParser()
        gamelist_path = fixture_path / 'valid' / 'complete.xml'
        
        tree = etree.parse(str(gamelist_path))
        root = tree.getroot()
        game_element = root.find('.//game')
        
        playcount = parser._get_int(game_element, 'playcount')
        assert playcount == 42
        assert isinstance(playcount, int)
    
    def test_get_bool_true(self, fixture_path):
        """Test extracting boolean true value."""
        parser = GamelistParser()
        gamelist_path = fixture_path / 'valid' / 'complete.xml'
        
        tree = etree.parse(str(gamelist_path))
        root = tree.getroot()
        game_element = root.find('.//game')
        
        favorite = parser._get_bool(game_element, 'favorite')
        assert favorite is True
    
    def test_get_bool_false(self, fixture_path):
        """Test extracting boolean false value."""
        parser = GamelistParser()
        gamelist_path = fixture_path / 'valid' / 'with_user_edits.xml'
        
        tree = etree.parse(str(gamelist_path))
        root = tree.getroot()
        game_element = root.find('.//game')
        
        hidden = parser._get_bool(game_element, 'hidden')
        assert hidden is False
    
    def test_get_bool_missing(self):
        """Test getting bool from missing element."""
        xml = '<root><other>value</other></root>'
        root = etree.fromstring(xml)
        parser = GamelistParser()
        
        favorite = parser._get_bool(root, 'favorite')
        
        # Missing bool returns None, not False
        assert favorite is None


@pytest.mark.unit
class TestGamelistMerger:
    """Test GamelistMerger."""
    
    def test_merge_new_entry_added(self):
        """Test merging adds new entries from scraped list."""
        merger = GamelistMerger()
        
        existing = []
        scraped = [
            GameEntry(path="./NewGame.nes", name="New Game", screenscraper_id="123")
        ]
        
        merged = merger.merge_entries(existing, scraped)
        
        assert len(merged) == 1
        assert merged[0].name == "New Game"
    
    def test_merge_preserves_user_fields(self):
        """Test merging preserves user-editable fields from existing."""
        merger = GamelistMerger()
        
        existing = [
            GameEntry(
                path="./Game.nes",
                name="Old Name",
                desc="Old description",
                favorite=True,
                playcount=42,
                lastplayed="20251115T143000"
            )
        ]
        
        scraped = [
            GameEntry(
                path="./Game.nes",
                name="New Name",
                desc="New description from scraper",
                screenscraper_id="123"
            )
        ]
        
        merged = merger.merge_entries(existing, scraped)
        
        assert len(merged) == 1
        entry = merged[0]
        # User fields preserved
        assert entry.favorite is True
        assert entry.playcount == 42
        assert entry.lastplayed == "20251115T143000"
        # Scraped metadata updated
        assert entry.name == "New Name"
        assert entry.desc == "New description from scraper"
        assert entry.screenscraper_id == "123"
    
    def test_merge_keeps_existing_roms_only(self):
        """Test that ROMs only in existing list are kept."""
        merger = GamelistMerger()
        
        existing = [
            GameEntry(path="./ManualEntry.nes", name="Manual Entry"),
            GameEntry(path="./Game.nes", name="Game")
        ]
        
        scraped = [
            GameEntry(path="./Game.nes", name="Updated Game", screenscraper_id="123")
        ]
        
        merged = merger.merge_entries(existing, scraped)
        
        assert len(merged) == 2
        paths = [e.path for e in merged]
        assert "./ManualEntry.nes" in paths
        assert "./Game.nes" in paths
    
    def test_merge_single_entry(self):
        """Test merging single entry."""
        merger = GamelistMerger()
        
        existing_entry = GameEntry(
            path="./Game.nes",
            name="Old Name",
            favorite=True,
            playcount=10
        )
        
        scraped_entry = GameEntry(
            path="./Game.nes",
            name="New Name",
            desc="New description",
            rating=0.85,
            screenscraper_id="123"
        )
        
        merged_entry = merger._merge_single_entry(existing_entry, scraped_entry)
        
        # User fields preserved
        assert merged_entry.favorite is True
        assert merged_entry.playcount == 10
        # Scraped metadata updated
        assert merged_entry.name == "New Name"
        assert merged_entry.desc == "New description"
        assert merged_entry.rating == 0.85
        assert merged_entry.screenscraper_id == "123"
    
    def test_merge_preserves_extra_fields(self):
        """Test merging preserves extra fields from existing."""
        merger = GamelistMerger()
        
        existing_entry = GameEntry(
            path="./Game.nes",
            name="Game",
            extra_fields={'customfield': 'custom value'}
        )
        
        scraped_entry = GameEntry(
            path="./Game.nes",
            name="Updated Game",
            desc="New description"
        )
        
        merged_entry = merger._merge_single_entry(existing_entry, scraped_entry)
        
        assert merged_entry.extra_fields == {'customfield': 'custom value'}
