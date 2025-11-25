from pathlib import Path

from curateur.gamelist.path_handler import PathHandler


def test_path_handler_relative_paths(tmp_path):
    rom_dir = tmp_path / "roms"
    media_dir = tmp_path / "media"
    gamelist_dir = tmp_path / "gamelists"
    rom_dir.mkdir()
    media_dir.mkdir()
    gamelist_dir.mkdir()

    handler = PathHandler(rom_dir, media_dir, gamelist_dir)

    rom = rom_dir / "Alpha.nes"
    rom.write_text("data")
    rel_rom = handler.get_relative_rom_path(rom)
    assert rel_rom == "./Alpha.nes"
    assert handler.resolve_rom_path(rel_rom) == rom

    media_path = media_dir / "covers" / "Alpha.png"
    media_path.parent.mkdir(parents=True, exist_ok=True)
    media_path.write_text("img")

    rel_media = handler.get_relative_media_path(media_path)
    assert rel_media.startswith("./")


def test_path_handler_media_and_basename(tmp_path):
    handler = PathHandler(tmp_path / "roms", tmp_path / "media", tmp_path / "gamelists")

    assert handler.normalize_path("a\\b\\c") == "a/b/c"
    assert handler.get_rom_basename("./Game.nes") == "Game"
    assert handler.get_rom_basename("./Game (Disc 1).cue") == "Game (Disc 1).cue"

    disc_dir = tmp_path / "roms" / "Game (Disc 1).cue"
    disc_dir.mkdir(parents=True)
    assert handler.get_media_basename(disc_dir) == "Game (Disc 1).cue"

    m3u = tmp_path / "roms" / "Game.m3u"
    m3u.write_text("Track.bin")
    assert handler.get_media_basename(m3u) == "Game"

    disc_file = disc_dir / "Game (Disc 1).cue"
    disc_file.write_text("cue")
    # Mode 1: convert provided media path
    rel_media = handler.calculate_media_path_from_gamelist(disc_file)
    # Disc file is outside media dir, so falls back to absolute path
    assert "Game (Disc 1).cue" in rel_media

    # Relative media inside media dir should be ./ path
    media_dir = tmp_path / "media"
    media_dir.mkdir(exist_ok=True)
    handler_media = PathHandler(tmp_path / "roms", media_dir, tmp_path / "gamelists")
    media_file = media_dir / "covers" / "Game.png"
    media_file.parent.mkdir(parents=True, exist_ok=True)
    media_file.write_text("img")
    rel_media2 = handler_media.get_relative_media_path(media_file)
    assert rel_media2.startswith("./")

    # Mode 2: calculate expected media path from ROM relative path
    rel_media3 = handler_media.calculate_media_path_from_gamelist(
        media_path=Path("./Game.nes"),
        rom_relative_path="./Game.nes",
        media_type="covers",
    )
    assert rel_media3.endswith(".png")
