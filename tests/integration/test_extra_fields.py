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
        
        assert len(entries) == 1, f"Expected 1 entry, got {len(entries)}"
        
        mario = entries[0]
        
        # Check that extra fields were captured
        assert 'sortname' in mario.extra_fields, "sortname not in extra_fields"
        assert mario.extra_fields['sortname'] == 'Mario Bros., Super', \
            f"Wrong sortname value: {mario.extra_fields['sortname']}"
        print(f"  ✓ Parsed sortname: '{mario.extra_fields['sortname']}'")
        
        assert 'kidgame' in mario.extra_fields, "kidgame not in extra_fields"
        print(f"  ✓ Parsed kidgame: '{mario.extra_fields['kidgame']}'")
        
        assert 'altemulator' in mario.extra_fields, "altemulator not in extra_fields"
        print(f"  ✓ Parsed altemulator: '{mario.extra_fields['altemulator']}'")
        
        assert 'custom-field' in mario.extra_fields, "custom-field not in extra_fields"
        print(f"  ✓ Parsed custom-field: '{mario.extra_fields['custom-field']}'")
        
        # Ensure known fields are NOT in extra_fields
        assert 'name' not in mario.extra_fields and 'desc' not in mario.extra_fields, \
            "Known fields incorrectly in extra_fields"
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
        
        assert len(merged) == 1, f"Expected 1 merged entry, got {len(merged)}"
        
        merged_mario = merged[0]
        
        # Check that extra fields were preserved
        assert 'sortname' in merged_mario.extra_fields, "sortname not preserved after merge"
        assert merged_mario.extra_fields['sortname'] == 'Mario Bros., Super', \
            "sortname value changed after merge"
        print(f"  ✓ Extra fields preserved through merge")
        
        # Check that scraped metadata was updated
        assert merged_mario.desc == "Updated description from scraper", \
            f"Description not updated: {merged_mario.desc}"
        assert merged_mario.rating == 0.95, f"Rating not updated: {merged_mario.rating}"
        print(f"  ✓ Scraped metadata updated")
        
        # Check that user fields were preserved
        assert merged_mario.favorite, "Favorite flag not preserved"
        assert merged_mario.playcount == 5, f"Playcount not preserved: {merged_mario.playcount}"
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
        assert sortname_elem is not None and sortname_elem.text == "Mario Bros., Super", \
            "sortname not in output XML"
        print(f"  ✓ sortname in output XML: '{sortname_elem.text}'")
        
        kidgame_elem = game.find("kidgame")
        assert kidgame_elem is not None and kidgame_elem.text == "true", \
            "kidgame not in output XML"
        print(f"  ✓ kidgame in output XML: '{kidgame_elem.text}'")
        
        altemulator_elem = game.find("altemulator")
        assert altemulator_elem is not None, "altemulator not in output XML"
        print(f"  ✓ altemulator in output XML: '{altemulator_elem.text}'")
        
        custom_elem = game.find("custom-field")
        assert custom_elem is not None, "custom-field not in output XML"
        print(f"  ✓ custom-field in output XML: '{custom_elem.text}'")
        
        # Verify that playcount is NOT in the output (we don't write it)
        playcount_elem = game.find("playcount")
        assert playcount_elem is None, "playcount should not be in output XML"
        print(f"  ✓ playcount correctly omitted from output")


def main():
    """Run extra fields preservation test."""
    print("=" * 60)
    print("curateur - Extra Fields Preservation Test")
    print("=" * 60)
    
    try:
        test_extra_fields_preservation()
        print("\n" + "=" * 60)
        print("✓ Extra fields preservation test PASSED")
        print("=" * 60)
        return 0
    except Exception as e:
        print("\n" + "=" * 60)
        print(f"✗ Extra fields preservation test FAILED: {e}")
        print("=" * 60)
        return 1


if __name__ == '__main__':
    sys.exit(main())
