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
