#!/usr/bin/env python3
"""
Test preservation of unknown XML fields.

Verifies that curateur preserves fields it doesn't manage.
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
)


def test_extra_fields_preservation():
    """Test that unknown XML fields are preserved through parse->merge->write cycle."""
    print("Testing extra fields preservation...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        gamelist_path = Path(tmpdir) / "gamelist.xml"
        
        # Create a gamelist with known and unknown fields
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
        <rating>0.9</rating>
        <developer>Nintendo</developer>
        <sortname>Mario Bros., Super</sortname>
        <kidgame>true</kidgame>
        <favorite>true</favorite>
        <playcount>5</playcount>
        <altemulator>Special Emulator</altemulator>
        <custom-field>User custom data</custom-field>
    </game>
</gameList>'''
        
        gamelist_path.write_text(xml_content)
        
        # Parse the gamelist
        parser = GamelistParser()
        entries = parser.parse_gamelist(gamelist_path)
        
        if len(entries) != 1:
            print(f"  ✗ Expected 1 entry, got {len(entries)}")
            return False
        
        mario = entries[0]
        
        # Check that extra fields were captured
        if 'sortname' not in mario.extra_fields:
            print(f"  ✗ sortname not in extra_fields")
            return False
        
        if mario.extra_fields['sortname'] != 'Mario Bros., Super':
            print(f"  ✗ Wrong sortname value: {mario.extra_fields['sortname']}")
            return False
        
        print(f"  ✓ Parsed sortname: '{mario.extra_fields['sortname']}'")
        
        if 'kidgame' not in mario.extra_fields:
            print(f"  ✗ kidgame not in extra_fields")
            return False
        
        print(f"  ✓ Parsed kidgame: '{mario.extra_fields['kidgame']}'")
        
        if 'altemulator' not in mario.extra_fields:
            print(f"  ✗ altemulator not in extra_fields")
            return False
        
        print(f"  ✓ Parsed altemulator: '{mario.extra_fields['altemulator']}'")
        
        if 'custom-field' not in mario.extra_fields:
            print(f"  ✗ custom-field not in extra_fields")
            return False
        
        print(f"  ✓ Parsed custom-field: '{mario.extra_fields['custom-field']}'")
        
        # Ensure known fields are NOT in extra_fields
        if 'name' in mario.extra_fields or 'desc' in mario.extra_fields:
            print(f"  ✗ Known fields incorrectly in extra_fields")
            return False
        
        print(f"  ✓ Known fields not in extra_fields")
        
        # Now simulate a merge with new scraped data
        new_entry = GameEntry(
            path="./Mario.nes",
            name="Super Mario Bros.",  # Updated name
            desc="Updated description from scraper",
            rating=0.95,  # Updated rating
            developer="Nintendo",
            publisher="Nintendo",  # New field
            genre="Platform"  # New field
        )
        
        merger = GamelistMerger()
        merged = merger.merge_entries(entries, [new_entry])
        
        if len(merged) != 1:
            print(f"  ✗ Expected 1 merged entry, got {len(merged)}")
            return False
        
        merged_mario = merged[0]
        
        # Check that extra fields were preserved
        if 'sortname' not in merged_mario.extra_fields:
            print(f"  ✗ sortname not preserved after merge")
            return False
        
        if merged_mario.extra_fields['sortname'] != 'Mario Bros., Super':
            print(f"  ✗ sortname value changed after merge")
            return False
        
        print(f"  ✓ Extra fields preserved through merge")
        
        # Check that scraped metadata was updated
        if merged_mario.desc != "Updated description from scraper":
            print(f"  ✗ Description not updated: {merged_mario.desc}")
            return False
        
        if merged_mario.rating != 0.95:
            print(f"  ✗ Rating not updated: {merged_mario.rating}")
            return False
        
        print(f"  ✓ Scraped metadata updated")
        
        # Check that user fields were preserved
        if not merged_mario.favorite:
            print(f"  ✗ Favorite flag not preserved")
            return False
        
        if merged_mario.playcount != 5:
            print(f"  ✗ Playcount not preserved")
            return False
        
        print(f"  ✓ User fields preserved")
        
        # Write the merged gamelist
        output_path = Path(tmpdir) / "output.xml"
        metadata = GamelistMetadata(system="Nintendo Entertainment System")
        writer = GamelistWriter(metadata)
        writer.write_gamelist(merged, output_path)
        
        # Parse the output and verify extra fields are present
        tree = etree.parse(str(output_path))
        root = tree.getroot()
        game = root.find(".//game")
        
        # Check for extra fields in XML
        sortname_elem = game.find("sortname")
        if sortname_elem is None or sortname_elem.text != "Mario Bros., Super":
            print(f"  ✗ sortname not in output XML")
            return False
        
        print(f"  ✓ sortname in output XML: '{sortname_elem.text}'")
        
        kidgame_elem = game.find("kidgame")
        if kidgame_elem is None or kidgame_elem.text != "true":
            print(f"  ✗ kidgame not in output XML")
            return False
        
        print(f"  ✓ kidgame in output XML: '{kidgame_elem.text}'")
        
        altemulator_elem = game.find("altemulator")
        if altemulator_elem is None:
            print(f"  ✗ altemulator not in output XML")
            return False
        
        print(f"  ✓ altemulator in output XML: '{altemulator_elem.text}'")
        
        custom_elem = game.find("custom-field")
        if custom_elem is None:
            print(f"  ✗ custom-field not in output XML")
            return False
        
        print(f"  ✓ custom-field in output XML: '{custom_elem.text}'")
        
        # Verify that playcount is NOT in the output (we don't write it)
        playcount_elem = game.find("playcount")
        if playcount_elem is not None:
            print(f"  ✗ playcount should not be in output XML")
            return False
        
        print(f"  ✓ playcount correctly omitted from output")
        
        return True


def main():
    """Run extra fields preservation test."""
    print("=" * 60)
    print("curateur - Extra Fields Preservation Test")
    print("=" * 60)
    
    if test_extra_fields_preservation():
        print("\n" + "=" * 60)
        print("✓ Extra fields preservation test PASSED")
        print("=" * 60)
        return 0
    else:
        print("\n" + "=" * 60)
        print("✗ Extra fields preservation test FAILED")
        print("=" * 60)
        return 1


if __name__ == '__main__':
    sys.exit(main())
