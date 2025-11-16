"""
Milestone 2 Phase A Integration Tests

Tests for Skip Mode, Integrity Validation, and Mismatch Cleaning functionality.
"""

import pytest
from pathlib import Path
from lxml import etree
import tempfile
import shutil
from typing import Dict, List

from curateur.workflow.skip_manager import SkipManager, SkipAction
from curateur.gamelist.integrity_validator import IntegrityValidator, ValidationResult
from curateur.media.mismatch_cleaner import MismatchCleaner
from curateur.workflow.media_handler import MediaOnlyHandler


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_dir():
    """Create temporary directory for tests"""
    temp = tempfile.mkdtemp()
    yield Path(temp)
    shutil.rmtree(temp)


@pytest.fixture
def sample_config():
    """Sample configuration"""
    return {
        'scraping': {
            'skip_scraped': True,
            'update_mode': False,
            'gamelist_integrity_threshold': 0.95,
            'media_types': ['screenshot', 'titlescreen', 'marquee'],
        },
        'media': {
            'enabled_types': ['screenshot', 'titlescreen', 'marquee'],
            'skip_existing_media': True,
        }
    }


@pytest.fixture
def sample_gamelist_entry():
    """Sample gamelist.xml entry"""
    return {
        'path': './Super Mario Bros.nes',
        'name': 'Super Mario Bros.',
        'desc': 'A classic platformer',
        'rating': '0.95',
        'releasedate': '19850913T000000',
        'developer': 'Nintendo',
        'publisher': 'Nintendo',
        'genre': 'Platformer',
        'players': '2',
        'hash': 'abc123',
    }


@pytest.fixture
def mock_media_checker():
    """Mock media checker for testing"""
    class MockMediaChecker:
        def __init__(self):
            self.existing_media = {}  # {rom_basename: {system: [media_types]}}
            
        def media_exists(self, rom_basename, system_name, media_type):
            return media_type in self.existing_media.get(rom_basename, {}).get(system_name, [])
        
        def set_present_media(self, rom_basename, system_name, media_types):
            """Helper to set up test data"""
            if rom_basename not in self.existing_media:
                self.existing_media[rom_basename] = {}
            self.existing_media[rom_basename][system_name] = media_types
    
    return MockMediaChecker()


@pytest.fixture
def mock_gamelist_parser():
    """Mock gamelist parser for testing"""
    class MockGamelistParser:
        def __init__(self):
            self.entries = {}  # {rom_basename: {system: entry_dict}}
            
        def find_entry(self, rom_basename, system_name):
            """Find entry by basename and system"""
            return self.entries.get(rom_basename, {}).get(system_name)
        
        def set_entry(self, rom_basename, system_name, entry_dict):
            """Helper to set up test data"""
            if rom_basename not in self.entries:
                self.entries[rom_basename] = {}
            self.entries[rom_basename][system_name] = entry_dict
    
    return MockGamelistParser()


# ============================================================================
# Skip Manager Tests
# ============================================================================

class TestSkipManager:
    """Test Skip Manager decision logic"""
    
    def test_skip_existing_full_match(self, sample_config, mock_gamelist_parser, 
                                     mock_media_checker):
        """Test SKIP action when ROM exists with all media"""
        sample_config['scraping']['skip_scraped'] = True
        manager = SkipManager(sample_config, mock_gamelist_parser, mock_media_checker)
        
        # Setup: ROM exists in gamelist with all media
        rom_info = {'basename': 'Super Mario Bros', 'path': './Super Mario Bros.nes'}
        mock_gamelist_parser.set_entry('Super Mario Bros', 'nes', {'name': 'Super Mario Bros.', 'path': './Super Mario Bros.nes'})
        mock_media_checker.set_present_media('Super Mario Bros', 'nes', ['screenshot', 'titlescreen', 'marquee'])
        
        action, media_types, reuse = manager.determine_action(rom_info, 'nes')
        
        assert action == SkipAction.SKIP
        assert media_types == []
        assert reuse is False
    
    def test_media_only_partial_media(self, sample_config, mock_gamelist_parser, 
                                     mock_media_checker):
        """Test MEDIA_ONLY action when ROM exists but media incomplete"""
        sample_config['scraping']['skip_scraped'] = True
        manager = SkipManager(sample_config, mock_gamelist_parser, mock_media_checker)
        
        # Setup: ROM exists with partial media
        rom_info = {'basename': 'Zelda', 'path': './Zelda.nes'}
        mock_gamelist_parser.set_entry('Zelda', 'nes', {'name': 'The Legend of Zelda', 'path': './Zelda.nes'})
        mock_media_checker.set_present_media('Zelda', 'nes', ['screenshot'])  # Missing 2 types
        
        action, media_types, reuse = manager.determine_action(rom_info, 'nes')
        
        assert action == SkipAction.MEDIA_ONLY
        assert set(media_types) == {'titlescreen', 'marquee'}
        assert reuse is True
    
    def test_full_scrape_new_rom(self, sample_config, mock_gamelist_parser, 
                                mock_media_checker):
        """Test FULL_SCRAPE action for new ROM"""
        manager = SkipManager(sample_config, mock_gamelist_parser, mock_media_checker)
        
        # Setup: ROM not in gamelist
        rom_info = {'basename': 'Metroid', 'path': './Metroid.nes'}
        # No entry in mock_gamelist_parser.entries
        
        action, media_types, reuse = manager.determine_action(rom_info, 'nes')
        
        assert action == SkipAction.FULL_SCRAPE
        assert set(media_types) == {'screenshot', 'titlescreen', 'marquee'}
        assert reuse is False
    
    def test_update_mode_enabled(self, sample_config, mock_gamelist_parser, 
                                mock_media_checker):
        """Test UPDATE action when update_mode=True"""
        sample_config['scraping']['skip_scraped'] = False
        sample_config['scraping']['update_mode'] = True
        manager = SkipManager(sample_config, mock_gamelist_parser, mock_media_checker)
        
        # Setup: ROM exists in gamelist
        rom_info = {'basename': 'Castlevania', 'path': './Castlevania.nes'}
        mock_gamelist_parser.set_entry('Castlevania', 'nes', {'name': 'Castlevania', 'path': './Castlevania.nes'})
        mock_media_checker.set_present_media('Castlevania', 'nes', ['screenshot', 'titlescreen', 'marquee'])
        
        action, media_types, reuse = manager.determine_action(rom_info, 'nes')
        
        assert action == SkipAction.UPDATE
        assert media_types == ['screenshot', 'titlescreen', 'marquee']
        assert reuse is False
    
    def test_skip_disabled_forces_full_scrape(self, sample_config, mock_gamelist_parser,
                                             mock_media_checker):
        """Test FULL_SCRAPE when skip_scraped=False"""
        sample_config['scraping']['skip_scraped'] = False
        sample_config['scraping']['update_mode'] = False
        manager = SkipManager(sample_config, mock_gamelist_parser, mock_media_checker)
        
        # Setup: ROM exists but skip disabled
        rom_info = {'basename': 'Mega Man', 'path': './Mega Man.nes'}
        mock_gamelist_parser.set_entry('Mega Man', 'nes', {'name': 'Mega Man', 'path': './Mega Man.nes'})
        mock_media_checker.set_present_media('Mega Man', 'nes', ['screenshot'])
        
        action, media_types, reuse = manager.determine_action(rom_info, 'nes')
        
        assert action == SkipAction.FULL_SCRAPE
        assert set(media_types) == {'screenshot', 'titlescreen', 'marquee'}
        assert reuse is False


# ============================================================================
# Integrity Validator Tests
# ============================================================================

class TestIntegrityValidator:
    """Test Integrity Validator functionality"""
    
    def test_validation_success_all_present(self, sample_config):
        """Test validation passes when all ROMs present"""
        validator = IntegrityValidator(sample_config)
        
        gamelist_entries = [
            {'path': './game1.nes', 'name': 'Game 1'},
            {'path': './game2.nes', 'name': 'Game 2'},
            {'path': './game3.nes', 'name': 'Game 3'},
        ]
        
        scanned_roms = [
            {'basename': 'game1'},
            {'basename': 'game2'},
            {'basename': 'game3'},
        ]
        
        result = validator.validate_gamelist(gamelist_entries, scanned_roms)
        
        assert result.is_valid is True
        assert result.ratio == 1.0
        assert len(result.missing_roms) == 0
    
    def test_validation_failure_below_threshold(self, sample_config):
        """Test validation fails when ratio below threshold"""
        validator = IntegrityValidator(sample_config)
        
        gamelist_entries = [
            {'path': './game1.nes', 'name': 'Game 1'},
            {'path': './game2.nes', 'name': 'Game 2'},
            {'path': './game3.nes', 'name': 'Game 3'},
            {'path': './game4.nes', 'name': 'Game 4'},
        ]
        
        scanned_roms = [
            {'basename': 'game1'},
            {'basename': 'game2'},
            # game3 and game4 missing (50% ratio, below 95% threshold)
        ]
        
        result = validator.validate_gamelist(gamelist_entries, scanned_roms)
        
        assert result.is_valid is False
        assert result.ratio == 0.5
        assert len(result.missing_roms) == 2
        assert any(e['path'] == './game3.nes' for e in result.missing_roms)
        assert any(e['path'] == './game4.nes' for e in result.missing_roms)
    
    def test_validation_edge_case_at_threshold(self, sample_config):
        """Test validation at exact threshold boundary"""
        validator = IntegrityValidator(sample_config)
        
        # 19/20 = 95% (exactly at threshold)
        gamelist_entries = [{'path': f'./game{i}.nes', 'name': f'Game {i}'} 
                           for i in range(1, 21)]
        scanned_roms = [{'basename': f'game{i}'} for i in range(1, 20)]  # Missing game20
        
        result = validator.validate_gamelist(gamelist_entries, scanned_roms)
        
        assert result.is_valid is True  # 95% meets threshold
        assert result.ratio == 0.95
        assert len(result.missing_roms) == 1
    
    def test_cleanup_execution(self, sample_config, temp_dir):
        """Test cleanup removes entries and moves media"""
        validator = IntegrityValidator(sample_config)
        
        # Create test structure
        gamelist_path = temp_dir / "gamelist.xml"
        media_root = temp_dir / "media"
        system_media = media_root / "nes" / "screenshot"
        system_media.mkdir(parents=True)
        
        # Create gamelist with 2 entries
        gamelist_xml = """<?xml version="1.0" encoding="utf-8"?>
<gameList>
    <game>
        <path>./game1.nes</path>
        <name>Game 1</name>
    </game>
    <game>
        <path>./game2.nes</path>
        <name>Game 2</name>
    </game>
</gameList>"""
        gamelist_path.write_text(gamelist_xml)
        
        # Create media file for missing ROM
        media_file = system_media / "game2.png"
        media_file.touch()
        
        # Create validation result
        validation_result = ValidationResult(
            is_valid=False,
            ratio=0.5,
            missing_roms=[{'path': './game2.nes', 'name': 'Game 2'}],
            orphaned_media={}
        )
        
        # Execute cleanup
        validator.execute_cleanup(validation_result, 'nes', media_root, gamelist_path)
        
        # Verify gamelist updated
        tree = etree.parse(str(gamelist_path))
        games = tree.findall('.//game')
        assert len(games) == 1
        assert games[0].find('path').text == './game1.nes'
        
        # Verify media moved to CLEANUP
        cleanup_file = media_root / "CLEANUP" / "nes" / "screenshot" / "game2.png"
        assert cleanup_file.exists()
        assert not media_file.exists()


# ============================================================================
# Mismatch Cleaner Tests
# ============================================================================

class TestMismatchCleaner:
    """Test Mismatch Cleaner functionality"""
    
    def test_scan_finds_disabled_types(self, temp_dir):
        """Test scan identifies disabled media types"""
        enabled_types = ['screenshot', 'titlescreen']
        cleaner = MismatchCleaner(enabled_types, {})
        
        # Create test structure with enabled and disabled types
        media_root = temp_dir
        system_media = media_root / "psx"
        
        (system_media / "screenshot").mkdir(parents=True)
        (system_media / "screenshot" / "game1.png").touch()
        
        (system_media / "titlescreen").mkdir(parents=True)
        (system_media / "titlescreen" / "game1.png").touch()
        
        # Create disabled type
        (system_media / "marquee").mkdir(parents=True)
        (system_media / "marquee" / "game1.png").touch()
        (system_media / "marquee" / "game2.png").touch()
        
        mismatches = cleaner.scan_for_mismatches(media_root, 'psx')
        
        assert 'marquee' in mismatches
        assert len(mismatches['marquee']) == 2
        assert 'screenshot' not in mismatches
        assert 'titlescreen' not in mismatches
    
    def test_cleanup_moves_files(self, temp_dir):
        """Test cleanup moves files to CLEANUP directory"""
        enabled_types = ['screenshot']
        cleaner = MismatchCleaner(enabled_types, {})
        
        media_root = temp_dir
        system_media = media_root / "nes"
        
        # Create disabled media type with files
        disabled_dir = system_media / "video"
        disabled_dir.mkdir(parents=True)
        file1 = disabled_dir / "game1.mp4"
        file2 = disabled_dir / "game2.mp4"
        file1.touch()
        file2.touch()
        
        mismatches = {'video': [file1, file2]}
        
        moved_count = cleaner.execute_cleanup(mismatches, media_root, 'nes')
        
        assert moved_count == 2
        
        # Verify files moved to CLEANUP
        cleanup_dir = media_root / "CLEANUP" / "nes" / "video"
        assert (cleanup_dir / "game1.mp4").exists()
        assert (cleanup_dir / "game2.mp4").exists()
        
        # Verify source files removed
        assert not file1.exists()
        assert not file2.exists()
    
    def test_no_mismatches_returns_empty(self, temp_dir):
        """Test scan returns empty when no mismatches"""
        enabled_types = ['screenshot', 'titlescreen', 'marquee']
        cleaner = MismatchCleaner(enabled_types, {})
        
        media_root = temp_dir
        system_media = media_root / "genesis"
        
        # Create only enabled types
        (system_media / "screenshot").mkdir(parents=True)
        (system_media / "screenshot" / "game1.png").touch()
        
        mismatches = cleaner.scan_for_mismatches(media_root, 'genesis')
        
        assert len(mismatches) == 0


# ============================================================================
# Media-Only Handler Tests
# ============================================================================

class TestMediaOnlyHandler:
    """Test Media-Only Handler functionality"""
    
    def test_determine_missing_media(self, sample_config, temp_dir):
        """Test identification of missing media types"""
        handler = MediaOnlyHandler(sample_config, None)
        
        media_root = temp_dir
        system_media = media_root / "snes"
        
        # Create partial media
        (system_media / "screenshot").mkdir(parents=True)
        (system_media / "screenshot" / "game1.png").touch()
        
        rom_info = {'basename': 'game1'}
        enabled_types = ['screenshot', 'titlescreen', 'marquee']
        
        missing = handler.determine_missing_media(
            rom_info, media_root, 'snes', enabled_types
        )
        
        assert 'screenshot' not in missing
        assert 'titlescreen' in missing
        assert 'marquee' in missing
    
    def test_all_media_present_returns_empty(self, sample_config, temp_dir):
        """Test returns empty list when all media present"""
        handler = MediaOnlyHandler(sample_config, None)
        
        media_root = temp_dir
        system_media = media_root / "n64"
        
        # Create all media types
        for media_type in ['screenshot', 'titlescreen', 'marquee']:
            type_dir = system_media / media_type
            type_dir.mkdir(parents=True)
            (type_dir / "game1.png").touch()
        
        rom_info = {'basename': 'game1'}
        enabled_types = ['screenshot', 'titlescreen', 'marquee']
        
        missing = handler.determine_missing_media(
            rom_info, media_root, 'n64', enabled_types
        )
        
        assert len(missing) == 0
    
    def test_extract_media_urls(self, sample_config):
        """Test extraction of media URLs from API response"""
        handler = MediaOnlyHandler(sample_config, None)
        
        api_response = {
            'response': {
                'jeu': {
                    'medias': [
                        {'type': 'ss', 'url': 'http://example.com/screenshot.png'},
                        {'type': 'sstitle', 'url': 'http://example.com/title.png'},
                        {'type': 'wheel', 'url': 'http://example.com/wheel.png'},
                    ]
                }
            }
        }
        
        media_types = ['screenshot', 'titlescreen', 'marquee']
        urls = handler._extract_media_urls(api_response, media_types)
        
        assert urls['screenshot'] == 'http://example.com/screenshot.png'
        assert urls['titlescreen'] == 'http://example.com/title.png'
        assert urls['marquee'] == 'http://example.com/wheel.png'


# ============================================================================
# Integration Tests
# ============================================================================

class TestPhaseAIntegration:
    """Integration tests combining multiple components"""
    
    def test_skip_mode_with_integrity_validation(self, sample_config, temp_dir,
                                                 mock_gamelist_parser, mock_media_checker):
        """Test skip mode workflow with integrity validation"""
        validator = IntegrityValidator(sample_config)
        manager = SkipManager(sample_config, mock_gamelist_parser, mock_media_checker)
        
        # Simulate scenario: 3 ROMs in gamelist, 2 on disk
        gamelist_entries = [
            {'path': './game1.nes', 'name': 'Game 1'},
            {'path': './game2.nes', 'name': 'Game 2'},
            {'path': './game3.nes', 'name': 'Game 3'},
        ]
        
        scanned_roms = [
            {'basename': 'game1', 'path': './game1.nes'},
            {'basename': 'game2', 'path': './game2.nes'},
        ]
        
        # Validate integrity
        validation_result = validator.validate_gamelist(gamelist_entries, scanned_roms)
        assert validation_result.is_valid is False
        
        # Setup gamelist parser with remaining ROMs
        mock_gamelist_parser.set_entry('game1', 'nes', gamelist_entries[0])
        mock_gamelist_parser.set_entry('game2', 'nes', gamelist_entries[1])
        mock_media_checker.set_present_media('game1', 'nes', ['screenshot', 'titlescreen', 'marquee'])
        mock_media_checker.set_present_media('game2', 'nes', ['screenshot', 'titlescreen', 'marquee'])
        
        # Test skip decisions for valid ROMs
        for rom in scanned_roms:
            action, _, _ = manager.determine_action(rom, 'nes')
            assert action == SkipAction.SKIP
    
    def test_media_only_with_mismatch_cleanup(self, sample_config, temp_dir,
                                             mock_gamelist_parser, mock_media_checker):
        """Test media-only download with disabled type cleanup"""
        # Setup components
        enabled_types = ['screenshot', 'titlescreen']
        sample_config['media']['enabled_types'] = enabled_types
        sample_config['scraping']['media_types'] = enabled_types
        
        cleaner = MismatchCleaner(enabled_types, sample_config)
        handler = MediaOnlyHandler(sample_config, None)
        manager = SkipManager(sample_config, mock_gamelist_parser, mock_media_checker)
        
        # Create test structure
        media_root = temp_dir
        system_media = media_root / "gba"
        
        # Existing media: screenshot + disabled marquee
        (system_media / "screenshot").mkdir(parents=True)
        (system_media / "screenshot" / "game1.png").touch()
        
        (system_media / "marquee").mkdir(parents=True)  # Disabled
        marquee_file = system_media / "marquee" / "game1.png"
        marquee_file.touch()
        
        # Setup ROM with partial media
        rom_info = {'basename': 'game1', 'path': './game1.gba'}
        mock_gamelist_parser.set_entry('game1', 'gba', {'name': 'Game 1', 'path': './game1.gba'})
        mock_media_checker.set_present_media('game1', 'gba', ['screenshot'])  # Missing titlescreen
        
        # Test skip decision: should be MEDIA_ONLY
        action, media_types, reuse = manager.determine_action(rom_info, 'gba')
        assert action == SkipAction.MEDIA_ONLY
        assert 'titlescreen' in media_types
        assert reuse is True
        
        # Determine missing media
        missing = handler.determine_missing_media(
            rom_info, media_root, 'gba', enabled_types
        )
        assert 'titlescreen' in missing
        assert 'screenshot' not in missing
        
        # Clean mismatched media
        mismatches = cleaner.scan_for_mismatches(media_root, 'gba')
        assert 'marquee' in mismatches
        
        moved = cleaner.execute_cleanup(mismatches, media_root, 'gba')
        assert moved == 1
        assert not marquee_file.exists()
        assert (media_root / "CLEANUP" / "gba" / "marquee" / "game1.png").exists()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
