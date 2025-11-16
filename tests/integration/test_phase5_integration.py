#!/usr/bin/env python3
"""
Phase 5 Integration Test - Gamelist Generator

Tests all gamelist generation components with XML parsing and merging.
"""

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from lxml import etree
from curateur.gamelist import (
    GameEntry,
    GamelistMetadata,
    GamelistWriter,
    GamelistParser,
    GamelistMerger,
    PathHandler,
    GamelistGenerator,
)


def test_game_entry_creation():
    """Test GameEntry creation and HTML entity decoding."""
    print("Testing game entry creation...")
    
    # Test basic entry
    entry = GameEntry(
        path="./Game.zip",
        name="Test Game"
    )
    
    if entry.path == "./Game.zip" and entry.name == "Test Game":
        print(f"  ✓ Basic entry created")
    else:
        print(f"  ✗ Basic entry creation failed")
        assert False, "Test failed"
    
    # Test HTML entity decoding
    entry_with_entities = GameEntry(
        path="./Pokemon.zip",
        name="Pok&eacute;mon Red",
        desc="A game about Pok&eacute;mon",
        developer="Nintendo &amp; Game Freak"
    )
    
    if entry_with_entities.name == "Pokémon Red":
        print(f"  ✓ HTML entity decoded in name: '{entry_with_entities.name}'")
    else:
        print(f"  ✗ HTML entity decoding failed: '{entry_with_entities.name}'")
        assert False, "Test failed"
    
    if "Pokémon" in entry_with_entities.desc:
        print(f"  ✓ HTML entity decoded in description")
    else:
        print(f"  ✗ HTML entity decoding failed in description")
        assert False, "Test failed"
    
    if entry_with_entities.developer == "Nintendo & Game Freak":
        print(f"  ✓ HTML entity decoded in developer")
    else:
        print(f"  ✗ HTML entity decoding failed: '{entry_with_entities.developer}'")
        assert False, "Test failed"
    


def test_game_entry_from_api():
    """Test GameEntry creation from API response."""
    print("\nTesting GameEntry from API response...")
    
    # Mock API response
    api_response = {
        'id': '12345',
        'names': {'us': 'Super Mario Bros.', 'eu': 'Super Mario Bros'},
        'descriptions': {'us': 'A classic platformer'},
        'rating': '4.5',  # 0-5 scale
        'release_dates': {'us': '1985-10-18'},
        'genres': ['Platform', 'Action'],
        'developer': 'Nintendo',
        'publisher': 'Nintendo',
        'players': '2'
    }
    
    media_paths = {
        'box-2D': './covers/Mario.jpg',
        'screenshot': './screenshots/Mario.png'
    }
    
    entry = GameEntry.from_api_response(
        api_response,
        './Mario.nes',
        media_paths
    )
    
    if entry.name == 'Super Mario Bros.':
        print(f"  ✓ Name extracted: '{entry.name}'")
    else:
        print(f"  ✗ Name extraction failed: '{entry.name}'")
        assert False, "Test failed"
    
    if entry.rating == 0.9:  # 4.5/5 = 0.9
        print(f"  ✓ Rating converted: {entry.rating}")
    else:
        print(f"  ✗ Rating conversion failed: {entry.rating}")
        assert False, "Test failed"
    
    if entry.releasedate == '19851018T000000':
        print(f"  ✓ Release date formatted: {entry.releasedate}")
    else:
        print(f"  ✗ Release date formatting failed: {entry.releasedate}")
        assert False, "Test failed"
    
    if entry.genre == 'Platform-Action':
        print(f"  ✓ Genres joined: '{entry.genre}'")
    else:
        print(f"  ✗ Genre joining failed: '{entry.genre}'")
        assert False, "Test failed"
    


def test_xml_writer():
    """Test XML writer."""
    print("\nTesting XML writer...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        output_path = Path(tmpdir) / "gamelist.xml"
        
        metadata = GamelistMetadata(system="Nintendo Entertainment System", software="curateur")
        writer = GamelistWriter(metadata)
        
        entries = [
            GameEntry(
                path="./Mario.nes",
                name="Super Mario Bros.",
                screenscraper_id="1234",
                desc="Classic platformer",
                rating=0.9,
                developer="Nintendo"
            ),
            GameEntry(
                path="./Zelda.nes",
                name="The Legend of Zelda",
                screenscraper_id="5678",
                favorite=True
            )
        ]
        
        writer.write_gamelist(entries, output_path)
        
        if not output_path.exists():
            print(f"  ✗ Gamelist file not created")
            return False
        
        print(f"  ✓ Gamelist file created")
        
        # Validate XML structure
        tree = etree.parse(str(output_path))
        root = tree.getroot()
        
        if root.tag != "gameList":
            print(f"  ✗ Wrong root tag: {root.tag}")
            return False
        
        print(f"  ✓ Root element is gameList")
        
        # Check provider
        provider = root.find("provider")
        if provider is None:
            print(f"  ✗ No provider element")
            return False
        
        print(f"  ✓ Provider element present")
        
        # Check games
        games = root.findall("game")
        if len(games) != 2:
            print(f"  ✗ Expected 2 games, found {len(games)}")
            return False
        
        print(f"  ✓ Both games present")
        
        # Check first game
        game1 = games[0]
        if game1.get('id') != '1234':
            print(f"  ✗ Wrong game ID: {game1.get('id')}")
            return False
        
        if game1.find('name').text != 'Super Mario Bros.':
            print(f"  ✗ Wrong game name")
            return False
        
        print(f"  ✓ Game metadata correct")
        
        # Validate with writer's validator
        assert writer.validate_output(output_path), "XML validation failed"
        print(f"  ✓ XML validation passed")


def test_xml_parser():
    """Test XML parser."""
    print("\nTesting XML parser...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        gamelist_path = Path(tmpdir) / "gamelist.xml"
        
        # Create a test gamelist
        xml_content = '''<?xml version="1.0"?>
<gameList>
    <provider>
        <System>Nintendo Entertainment System</System>
        <software>curateur</software>
        <database>ScreenScraper.fr</database>
        <web>http://www.screenscraper.fr</web>
    </provider>
    <game id="1234" source="ScreenScraper.fr">
        <path>./Mario.nes</path>
        <name>Super Mario Bros.</name>
        <desc>Classic platformer</desc>
        <rating>0.900000</rating>
        <developer>Nintendo</developer>
        <favorite>true</favorite>
        <playcount>5</playcount>
    </game>
    <game id="5678">
        <path>./Zelda.nes</path>
        <name>The Legend of Zelda</name>
    </game>
</gameList>'''
        
        gamelist_path.write_text(xml_content)
        
        parser = GamelistParser()
        entries = parser.parse_gamelist(gamelist_path)
        
        if len(entries) != 2:
            print(f"  ✗ Expected 2 entries, got {len(entries)}")
            return False
        
        print(f"  ✓ Parsed 2 entries")
        
        # Check first entry
        mario = entries[0]
        if mario.name != "Super Mario Bros.":
            print(f"  ✗ Wrong name: {mario.name}")
            return False
        
        if mario.rating != 0.9:
            print(f"  ✗ Wrong rating: {mario.rating}")
            return False
        
        if not mario.favorite:
            print(f"  ✗ Favorite flag not parsed")
            return False
        
        if mario.playcount != 5:
            print(f"  ✗ Wrong playcount: {mario.playcount}")
            return False
        
        print(f"  ✓ Entry fields parsed correctly")
        


def test_gamelist_merger():
    """Test gamelist merging."""
    print("\nTesting gamelist merger...")
    
    # Existing entries (with user data)
    existing = [
        GameEntry(
            path="./Mario.nes",
            name="Super Mario Bros",
            screenscraper_id="1234",
            desc="Old description",
            favorite=True,
            playcount=10
        ),
        GameEntry(
            path="./OldGame.nes",
            name="Old Game",
            favorite=True
        )
    ]
    
    # New scraped entries
    new = [
        GameEntry(
            path="./Mario.nes",
            name="Super Mario Bros.",
            screenscraper_id="1234",
            desc="New description from API",
            rating=0.9,
            developer="Nintendo"
        ),
        GameEntry(
            path="./Zelda.nes",
            name="The Legend of Zelda",
            screenscraper_id="5678"
        )
    ]
    
    merger = GamelistMerger()
    merged = merger.merge_entries(existing, new)
    
    if len(merged) != 3:
        print(f"  ✗ Expected 3 entries, got {len(merged)}")
        assert False, "Test failed"
    
    print(f"  ✓ Merged to 3 entries")
    
    # Find Mario entry
    mario = next((e for e in merged if 'Mario' in e.name), None)
    if not mario:
        print(f"  ✗ Mario entry not found")
        assert False, "Test failed"
    
    # Check metadata updated
    if mario.desc != "New description from API":
        print(f"  ✗ Description not updated: {mario.desc}")
        assert False, "Test failed"
    
    print(f"  ✓ Metadata updated from new scrape")
    
    # Check user data preserved
    if not mario.favorite or mario.playcount != 10:
        print(f"  ✗ User data not preserved (favorite={mario.favorite}, playcount={mario.playcount})")
        assert False, "Test failed"
    
    print(f"  ✓ User data preserved")
    
    # Check old entry preserved
    old_game = next((e for e in merged if 'OldGame' in e.path), None)
    if not old_game:
        print(f"  ✗ Old entry not preserved")
        assert False, "Test failed"
    
    print(f"  ✓ Existing entries preserved")
    


def test_path_handler():
    """Test path handling."""
    print("\nTesting path handler...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        rom_dir = base / "roms" / "nes"
        media_dir = base / "downloaded_media" / "nes"
        gamelist_dir = base / "gamelists" / "nes"
        
        rom_dir.mkdir(parents=True)
        media_dir.mkdir(parents=True)
        gamelist_dir.mkdir(parents=True)
        
        handler = PathHandler(rom_dir, media_dir, gamelist_dir)
        
        # Test ROM path
        rom_path = rom_dir / "Mario.nes"
        rel_rom = handler.get_relative_rom_path(rom_path)
        
        if rel_rom == "./Mario.nes":
            print(f"  ✓ ROM path: {rel_rom}")
        else:
            print(f"  ✗ Wrong ROM path: {rel_rom}")
            return False
        
        # Test basename extraction
        basename = handler.get_rom_basename("./Mario.nes")
        if basename == "Mario":
            print(f"  ✓ Basename: {basename}")
        else:
            print(f"  ✗ Wrong basename: {basename}")
            return False
        
        # Test disc subdir basename
        disc_basename = handler.get_rom_basename("./Game (Disc 1).cue")
        if disc_basename == "Game (Disc 1).cue":
            print(f"  ✓ Disc subdir basename: {disc_basename}")
        else:
            print(f"  ✗ Wrong disc basename: {disc_basename}")
            return False
        


def test_gamelist_generator():
    """Test full gamelist generation."""
    print("\nTesting gamelist generator...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        base = Path(tmpdir)
        rom_dir = base / "roms" / "nes"
        media_dir = base / "downloaded_media" / "nes"
        gamelist_dir = base / "gamelists" / "nes"
        
        rom_dir.mkdir(parents=True)
        media_dir.mkdir(parents=True)
        gamelist_dir.mkdir(parents=True)
        
        generator = GamelistGenerator(
            system_name="nes",
            full_system_name="Nintendo Entertainment System",
            rom_directory=rom_dir,
            media_directory=media_dir,
            gamelist_directory=gamelist_dir
        )
        
        # Prepare scraped data
        scraped_games = [
            {
                'rom_path': rom_dir / "Mario.nes",
                'game_info': {
                    'id': '1234',
                    'names': {'us': 'Super Mario Bros.'},
                    'genres': ['Platform'],
                    'developer': 'Nintendo'
                },
                'media_paths': {}
            }
        ]
        
        # Generate gamelist
        output = generator.generate_gamelist(scraped_games, merge_existing=False)
        
        if not output.exists():
            print(f"  ✗ Gamelist not created")
            return False
        
        print(f"  ✓ Gamelist created: {output}")
        
        # Validate
        if generator.validate_gamelist():
            print(f"  ✓ Gamelist validated")
        else:
            print(f"  ✗ Gamelist validation failed")
            return False
        


def main():
    """Run all Phase 5 tests."""
    print("=" * 60)
    print("curateur MVP Phase 5 - Gamelist Generator Test")
    print("=" * 60)
    
    tests = [
        test_game_entry_creation,
        test_game_entry_from_api,
        test_xml_writer,
        test_xml_parser,
        test_gamelist_merger,
        test_path_handler,
        test_gamelist_generator,
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("✓ Phase 5 integration test PASSED")
        print("=" * 60)
        return 0
    else:
        print("✗ Phase 5 integration test FAILED")
        print("=" * 60)
        return 1


if __name__ == '__main__':
    sys.exit(main())
