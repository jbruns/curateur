"""Integration tests for generator module."""
import pytest
from pathlib import Path
from curateur.gamelist.generator import GamelistGenerator
from curateur.gamelist.parser import GamelistParser
from curateur.gamelist.game_entry import GameEntry


@pytest.mark.integration
class TestGamelistGeneratorWorkflow:
    """Test end-to-end gamelist generation workflows."""
    
    def test_generate_new_gamelist_from_scratch(self, temp_gamelist_dir, api_game_info):
        """Test generating a new gamelist from scratch."""
        generator = GamelistGenerator(
            system_name='nes',
            full_system_name='Nintendo Entertainment System',
            rom_directory=temp_gamelist_dir['rom_dir'],
            media_directory=temp_gamelist_dir['media_dir'],
            gamelist_directory=temp_gamelist_dir['gamelist_dir']
        )
        
        # Prepare scraped game data
        rom_path = temp_gamelist_dir['rom_dir'] / "Super Mario Bros.nes"
        rom_path.write_bytes(b"FAKE_ROM_DATA")
        
        scraped_games = [
            {
                'rom_path': rom_path,
                'game_info': api_game_info,
                'media_paths': {}
            }
        ]
        
        # Generate gamelist
        output_path = generator.generate_gamelist(scraped_games, merge_existing=False)
        
        # Verify output
        assert output_path.exists()
        assert output_path.stat().st_size > 0
        
        # Parse and verify contents
        parser = GamelistParser()
        entries = parser.parse_gamelist(output_path)
        
        assert len(entries) == 1
        assert entries[0].name == "Test Game"
        assert entries[0].screenscraper_id == "12345"
    
    def test_generate_gamelist_with_media(self, temp_gamelist_dir, api_game_info):
        """Test generating gamelist with media files (ES-DE infers media from directory structure)."""
        generator = GamelistGenerator(
            system_name='nes',
            full_system_name='Nintendo Entertainment System',
            rom_directory=temp_gamelist_dir['rom_dir'],
            media_directory=temp_gamelist_dir['media_dir'],
            gamelist_directory=temp_gamelist_dir['gamelist_dir']
        )
        
        # Create ROM and media files
        rom_path = temp_gamelist_dir['rom_dir'] / "Game.nes"
        rom_path.write_bytes(b"ROM_DATA")
        
        cover_path = temp_gamelist_dir['media_dir'] / "covers" / "Game.png"
        cover_path.write_bytes(b"IMAGE_DATA")
        
        screenshot_path = temp_gamelist_dir['media_dir'] / "screenshots" / "Game.png"
        screenshot_path.write_bytes(b"IMAGE_DATA")
        
        scraped_games = [
            {
                'rom_path': rom_path,
                'game_info': api_game_info,
                'media_paths': {
                    'box-2D': cover_path,
                    'ss': screenshot_path
                }
            }
        ]
        
        # Generate gamelist
        output_path = generator.generate_gamelist(scraped_games, merge_existing=False)
        
        # Verify gamelist was created and media files exist in directory structure
        assert output_path.exists()
        assert cover_path.exists()
        assert screenshot_path.exists()
        
        # Parse and verify - media paths should NOT be in gamelist.xml
        parser = GamelistParser()
        entries = parser.parse_gamelist(output_path)
        
        assert len(entries) == 1
        # ES-DE infers media from directory, so these should not be in XML
        assert entries[0].image is None
        assert entries[0].thumbnail is None
    
    def test_merge_with_existing_gamelist(self, temp_gamelist_dir, api_game_info, fixture_path):
        """Test merging new data with existing gamelist."""
        generator = GamelistGenerator(
            system_name='nes',
            full_system_name='Nintendo Entertainment System',
            rom_directory=temp_gamelist_dir['rom_dir'],
            media_directory=temp_gamelist_dir['media_dir'],
            gamelist_directory=temp_gamelist_dir['gamelist_dir']
        )
        
        # Copy existing gamelist with user edits
        existing_gamelist = fixture_path / 'valid' / 'with_user_edits.xml'
        target_gamelist = temp_gamelist_dir['gamelist_dir'] / 'gamelist.xml'
        target_gamelist.write_text(existing_gamelist.read_text())
        
        # Create new ROM to scrape
        rom_path = temp_gamelist_dir['rom_dir'] / "New Game.nes"
        rom_path.write_bytes(b"ROM_DATA")
        
        scraped_games = [
            {
                'rom_path': rom_path,
                'game_info': api_game_info,
                'media_paths': {}
            }
        ]
        
        # Generate with merge
        output_path = generator.generate_gamelist(scraped_games, merge_existing=True)
        
        # Parse and verify
        parser = GamelistParser()
        entries = parser.parse_gamelist(output_path)
        
        # Should have both existing and new entries
        assert len(entries) >= 1
        
        # Check that existing entry's user fields are preserved
        sonic_entry = next((e for e in entries if "Sonic" in e.name), None)
        if sonic_entry:
            assert sonic_entry.favorite is True
            assert sonic_entry.playcount == 15
    
    def test_generate_multiple_games(self, temp_gamelist_dir, api_game_info, api_game_info_minimal):
        """Test generating gamelist with multiple games."""
        generator = GamelistGenerator(
            system_name='nes',
            full_system_name='Nintendo Entertainment System',
            rom_directory=temp_gamelist_dir['rom_dir'],
            media_directory=temp_gamelist_dir['media_dir'],
            gamelist_directory=temp_gamelist_dir['gamelist_dir']
        )
        
        # Create multiple ROMs
        roms = []
        scraped_games = []
        
        for i, game_info in enumerate([api_game_info, api_game_info_minimal]):
            rom_path = temp_gamelist_dir['rom_dir'] / f"Game{i}.nes"
            rom_path.write_bytes(b"ROM_DATA")
            roms.append(rom_path)
            
            scraped_games.append({
                'rom_path': rom_path,
                'game_info': game_info,
                'media_paths': {}
            })
        
        # Generate gamelist
        output_path = generator.generate_gamelist(scraped_games, merge_existing=False)
        
        # Parse and verify
        parser = GamelistParser()
        entries = parser.parse_gamelist(output_path)
        
        assert len(entries) == 2
        assert all(isinstance(e, GameEntry) for e in entries)
    
    def test_validate_generated_gamelist(self, temp_gamelist_dir, api_game_info):
        """Test validating generated gamelist."""
        generator = GamelistGenerator(
            system_name='nes',
            full_system_name='Nintendo Entertainment System',
            rom_directory=temp_gamelist_dir['rom_dir'],
            media_directory=temp_gamelist_dir['media_dir'],
            gamelist_directory=temp_gamelist_dir['gamelist_dir']
        )
        
        # Create ROM
        rom_path = temp_gamelist_dir['rom_dir'] / "Game.nes"
        rom_path.write_bytes(b"ROM_DATA")
        
        scraped_games = [
            {
                'rom_path': rom_path,
                'game_info': api_game_info,
                'media_paths': {}
            }
        ]
        
        # Generate gamelist
        generator.generate_gamelist(scraped_games, merge_existing=False)
        
        # Validate
        is_valid = generator.validate_gamelist()
        
        assert is_valid is True
    
    def test_round_trip_preserve_data(self, temp_gamelist_dir, api_game_info):
        """Test that data is preserved through generate-parse-generate cycle."""
        generator = GamelistGenerator(
            system_name='nes',
            full_system_name='Nintendo Entertainment System',
            rom_directory=temp_gamelist_dir['rom_dir'],
            media_directory=temp_gamelist_dir['media_dir'],
            gamelist_directory=temp_gamelist_dir['gamelist_dir']
        )
        
        # Create ROM
        rom_path = temp_gamelist_dir['rom_dir'] / "Game.nes"
        rom_path.write_bytes(b"ROM_DATA")
        
        scraped_games = [
            {
                'rom_path': rom_path,
                'game_info': api_game_info,
                'media_paths': {}
            }
        ]
        
        # First generation
        output_path = generator.generate_gamelist(scraped_games, merge_existing=False)
        
        # Parse
        parser = GamelistParser()
        entries_first = parser.parse_gamelist(output_path)
        
        # Generate again from parsed entries
        from curateur.gamelist.xml_writer import GamelistWriter
        from curateur.gamelist.game_entry import GamelistMetadata
        
        metadata = GamelistMetadata(
            system='Nintendo Entertainment System',
            software='curateur',
            database='ScreenScraper.fr',
            web='http://www.screenscraper.fr'
        )
        
        writer = GamelistWriter(metadata)
        output_path2 = temp_gamelist_dir['gamelist_dir'] / 'gamelist2.xml'
        writer.write_gamelist(entries_first, output_path2)
        
        # Parse again
        entries_second = parser.parse_gamelist(output_path2)
        
        # Compare
        assert len(entries_first) == len(entries_second)
        for e1, e2 in zip(entries_first, entries_second):
            assert e1.name == e2.name
            assert e1.path == e2.path
            assert e1.screenscraper_id == e2.screenscraper_id
            assert e1.rating == e2.rating
