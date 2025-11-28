from pathlib import Path

import pytest

from curateur.gamelist.generator import GamelistGenerator


@pytest.mark.unit
def test_generate_gamelist_writes_entries(tmp_path):
    rom_dir = tmp_path / "roms"
    media_dir = tmp_path / "media"
    gamelist_dir = tmp_path / "gamelist"
    rom_dir.mkdir()
    media_dir.mkdir()
    gamelist_dir.mkdir()

    rom_path = rom_dir / "Alpha.nes"
    rom_path.write_text("rom")

    generator = GamelistGenerator(
        system_name="nes",
        full_system_name="Nintendo",
        rom_directory=rom_dir,
        media_directory=media_dir,
        gamelist_directory=gamelist_dir,
    )

    scraped_games = [
        {
            "rom_path": rom_path,
            "game_info": {
                "id": "1",
                "names": {"us": "Alpha"},
                "descriptions": {"en": "desc"},
                "rating": 10,
                "release_dates": {"us": "1990-01-01"},
                "developer": "Dev",
                "publisher": "Pub",
                "genres": ["Action"],
                "players": "1",
            },
            "media_paths": {},
        }
    ]

    result = generator.generate_gamelist(scraped_games, validate=False)
    assert generator.gamelist_path.exists()
    content = generator.gamelist_path.read_text()
    assert "Alpha" in content
    assert result is None  # validate=False


@pytest.mark.unit
def test_extract_media_paths_maps_known_types(tmp_path):
    rom_dir = tmp_path / "roms"
    media_dir = tmp_path / "media"
    gamelist_dir = tmp_path / "gamelist"
    rom_dir.mkdir()
    media_dir.mkdir()
    gamelist_dir.mkdir()

    cover = media_dir / "covers" / "Alpha.png"
    cover.parent.mkdir(parents=True, exist_ok=True)
    cover.write_text("img")
    ss = media_dir / "screenshots" / "Alpha.png"
    ss.parent.mkdir(parents=True, exist_ok=True)
    ss.write_text("img")
    video = media_dir / "videos" / "Alpha.mp4"
    video.parent.mkdir(parents=True, exist_ok=True)
    video.write_text("vid")

    generator = GamelistGenerator(
        system_name="nes",
        full_system_name="Nintendo",
        rom_directory=rom_dir,
        media_directory=media_dir,
        gamelist_directory=gamelist_dir,
    )

    rel = generator._extract_media_paths(
        {"box-2D": cover, "ss": ss, "video": video},
        rom_path=rom_dir / "Alpha.nes",
    )
    assert rel["cover"].startswith("./")
    assert rel["screenshot"].startswith("./")
    assert rel["video"].startswith("./")


@pytest.mark.unit
def test_generate_gamelist_merges_existing(tmp_path):
    rom_dir = tmp_path / "roms"
    media_dir = tmp_path / "media"
    gamelist_dir = tmp_path / "gamelist"
    rom_dir.mkdir()
    media_dir.mkdir()
    gamelist_dir.mkdir()

    rom_path = rom_dir / "Alpha.nes"
    rom_path.write_text("rom")
    existing = gamelist_dir / "gamelist.xml"
    existing.write_text(
        """<gameList><game><path>./Alpha.nes</path><name>Old Alpha</name><favorite>true</favorite></game></gameList>"""
    )

    generator = GamelistGenerator(
        system_name="nes",
        full_system_name="Nintendo",
        rom_directory=rom_dir,
        media_directory=media_dir,
        gamelist_directory=gamelist_dir,
        merge_strategy="refresh_metadata",  # Update scraped fields, preserve user fields
    )

    scraped_games = [
        {
            "rom_path": rom_path,
            "game_info": {"id": "1", "names": {"us": "New Alpha"}, "players": "1"},
            "media_paths": {},
        }
    ]

    generator.generate_gamelist(scraped_games, validate=False, merge_existing=True)
    content = existing.read_text()
    # New name merged, favorite preserved
    assert "<name>New Alpha</name>" in content
    assert "<favorite>true</favorite>" in content


@pytest.mark.unit
def test_auto_favorite_applies_to_new_gamelist(tmp_path):
    """Test that auto-favorite works when creating a brand new gamelist (no existing gamelist.xml)"""
    rom_dir = tmp_path / "roms"
    media_dir = tmp_path / "media"
    gamelist_dir = tmp_path / "gamelist"
    rom_dir.mkdir()
    media_dir.mkdir()
    gamelist_dir.mkdir()

    rom_path = rom_dir / "HighRated.nes"
    rom_path.write_text("rom")

    generator = GamelistGenerator(
        system_name="nes",
        full_system_name="Nintendo",
        rom_directory=rom_dir,
        media_directory=media_dir,
        gamelist_directory=gamelist_dir,
        merge_strategy="refresh_metadata",
        auto_favorite_enabled=True,
        auto_favorite_threshold=0.9,
    )

    scraped_games = [
        {
            "rom_path": rom_path,
            "game_info": {
                "id": "1",
                "names": {"us": "HighRated Game"},
                "rating": 19.0,  # ScreenScraper 0-20 scale, becomes 0.95 in ES-DE
            },
            "media_paths": {},
        }
    ]

    # Generate brand new gamelist (no existing file)
    generator.generate_gamelist(scraped_games, validate=False, merge_existing=False)

    # Read generated gamelist
    content = generator.gamelist_path.read_text()

    # Should have auto-favorited the high-rated game
    assert "<name>HighRated Game</name>" in content
    assert "<rating>0.95</rating>" in content
    assert "<favorite>true</favorite>" in content


@pytest.mark.unit
def test_auto_favorite_respects_preserve_user_edits_on_new_gamelist(tmp_path):
    """Test that preserve_user_edits strategy blocks auto-favorite even on new gamelists"""
    rom_dir = tmp_path / "roms"
    media_dir = tmp_path / "media"
    gamelist_dir = tmp_path / "gamelist"
    rom_dir.mkdir()
    media_dir.mkdir()
    gamelist_dir.mkdir()

    rom_path = rom_dir / "HighRated.nes"
    rom_path.write_text("rom")

    generator = GamelistGenerator(
        system_name="nes",
        full_system_name="Nintendo",
        rom_directory=rom_dir,
        media_directory=media_dir,
        gamelist_directory=gamelist_dir,
        merge_strategy="preserve_user_edits",  # Should block auto-favorite
        auto_favorite_enabled=True,
        auto_favorite_threshold=0.9,
    )

    scraped_games = [
        {
            "rom_path": rom_path,
            "game_info": {
                "id": "1",
                "names": {"us": "HighRated Game"},
                "rating": 19.0,  # 0.95 in ES-DE scale
            },
            "media_paths": {},
        }
    ]

    # Generate brand new gamelist
    generator.generate_gamelist(scraped_games, validate=False, merge_existing=False)

    # Read generated gamelist
    content = generator.gamelist_path.read_text()

    # Should NOT have auto-favorited (preserve_user_edits blocks it)
    assert "<name>HighRated Game</name>" in content
    assert "<rating>0.95</rating>" in content
    assert "<favorite>true</favorite>" not in content
