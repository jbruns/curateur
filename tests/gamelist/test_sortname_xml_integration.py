"""
Integration tests for sortname in XML output.

Tests that sortname is correctly written to gamelist.xml files.
"""

import pytest
from pathlib import Path
from curateur.gamelist.generator import GamelistGenerator


def _parse_gamelist(gamelist_path):
    """Helper to parse gamelist.xml and return dict of games"""
    from lxml import etree
    tree = etree.parse(str(gamelist_path))
    root = tree.getroot()

    games = {}
    for game in root.findall('game'):
        path = game.find('path').text
        games[path] = {}
        for child in game:
            if child.tag != 'path':
                games[path][child.tag] = child.text

    return games


@pytest.mark.unit
def test_sortname_written_to_xml_when_enabled(tmp_path):
    """Test that sortname is written to gamelist.xml when feature is enabled"""
    rom_dir = tmp_path / "roms"
    media_dir = tmp_path / "media"
    gamelist_dir = tmp_path / "gamelist"
    rom_dir.mkdir()
    media_dir.mkdir()
    gamelist_dir.mkdir()

    generator = GamelistGenerator(
        system_name="nes",
        full_system_name="Nintendo",
        rom_directory=rom_dir,
        media_directory=media_dir,
        gamelist_directory=gamelist_dir,
        auto_sortname_enabled=True
    )

    scraped_games = [
        {
            "rom_path": rom_dir / "zelda.nes",
            "game_info": {
                "id": "1",
                "names": {"us": "The Legend of Zelda"},
                "rating": 19.0,
            },
            "media_paths": {},
        },
        {
            "rom_path": rom_dir / "mario.nes",
            "game_info": {
                "id": "2",
                "names": {"us": "Super Mario Bros"},
                "rating": 18.0,
            },
            "media_paths": {},
        },
    ]

    generator.generate_gamelist(scraped_games, validate=False)

    games = _parse_gamelist(generator.gamelist_path)

    # Zelda should have sortname (starts with "The")
    assert "./zelda.nes" in games
    assert games["./zelda.nes"]["name"] == "The Legend of Zelda"
    assert games["./zelda.nes"]["sortname"] == "Legend of Zelda, The"

    # Mario should NOT have sortname (no article)
    assert "./mario.nes" in games
    assert games["./mario.nes"]["name"] == "Super Mario Bros"
    assert "sortname" not in games["./mario.nes"]


@pytest.mark.unit
def test_sortname_not_written_when_disabled(tmp_path):
    """Test that sortname is not written to gamelist.xml when feature is disabled"""
    rom_dir = tmp_path / "roms"
    media_dir = tmp_path / "media"
    gamelist_dir = tmp_path / "gamelist"
    rom_dir.mkdir()
    media_dir.mkdir()
    gamelist_dir.mkdir()

    generator = GamelistGenerator(
        system_name="nes",
        full_system_name="Nintendo",
        rom_directory=rom_dir,
        media_directory=media_dir,
        gamelist_directory=gamelist_dir,
        auto_sortname_enabled=False
    )

    scraped_games = [
        {
            "rom_path": rom_dir / "zelda.nes",
            "game_info": {
                "id": "1",
                "names": {"us": "The Legend of Zelda"},
                "rating": 19.0,
            },
            "media_paths": {},
        },
    ]

    generator.generate_gamelist(scraped_games, validate=False)

    games = _parse_gamelist(generator.gamelist_path)

    # Zelda should NOT have sortname (feature disabled)
    assert "./zelda.nes" in games
    assert games["./zelda.nes"]["name"] == "The Legend of Zelda"
    assert "sortname" not in games["./zelda.nes"]


@pytest.mark.unit
def test_sortname_with_various_articles(tmp_path):
    """Test sortname generation with A, An, and The"""
    rom_dir = tmp_path / "roms"
    media_dir = tmp_path / "media"
    gamelist_dir = tmp_path / "gamelist"
    rom_dir.mkdir()
    media_dir.mkdir()
    gamelist_dir.mkdir()

    generator = GamelistGenerator(
        system_name="nes",
        full_system_name="Nintendo",
        rom_directory=rom_dir,
        media_directory=media_dir,
        gamelist_directory=gamelist_dir,
        auto_sortname_enabled=True
    )

    scraped_games = [
        {
            "rom_path": rom_dir / "game1.nes",
            "game_info": {
                "id": "1",
                "names": {"us": "The Last of Us"},
            },
            "media_paths": {},
        },
        {
            "rom_path": rom_dir / "game2.nes",
            "game_info": {
                "id": "2",
                "names": {"us": "A Boy and His Blob"},
            },
            "media_paths": {},
        },
        {
            "rom_path": rom_dir / "game3.nes",
            "game_info": {
                "id": "3",
                "names": {"us": "An American Tail"},
            },
            "media_paths": {},
        },
    ]

    generator.generate_gamelist(scraped_games, validate=False)

    games = _parse_gamelist(generator.gamelist_path)

    assert games["./game1.nes"]["sortname"] == "Last of Us, The"
    assert games["./game2.nes"]["sortname"] == "Boy and His Blob, A"
    assert games["./game3.nes"]["sortname"] == "American Tail, An"
