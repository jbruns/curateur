from pathlib import Path

from curateur.media.organizer import MediaOrganizer


def test_media_organizer_builds_paths_and_relative(tmp_path):
    organizer = MediaOrganizer(tmp_path)
    path = organizer.get_media_path("nes", "box-2D", "Alpha", "jpg")

    assert path == tmp_path / "nes" / "covers" / "Alpha.jpg"

    organizer.ensure_directory_exists(path)
    path.write_text("data")
    assert organizer.file_exists(path) is True

    rel = organizer.get_relative_path(path, tmp_path)
    assert rel == "./nes/covers/Alpha.jpg"

    # get_rom_basename handles normal and disc-like names
    assert organizer.get_rom_basename("/roms/Game.zip") == "Game"
    assert organizer.get_rom_basename("/roms/Game (Disc 1).cue") == "Game (Disc 1).cue"
