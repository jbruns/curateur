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

    # get_rom_basename handles normal files
    assert organizer.get_rom_basename("/roms/Game.zip") == "Game"
    assert organizer.get_rom_basename("/roms/Game.m3u") == "Game"

    # get_rom_basename handles disc subdirectories (actual directories with extensions)
    disc_subdir = tmp_path / "roms" / "Armada (USA).cue"
    disc_subdir.mkdir(parents=True)
    assert organizer.get_rom_basename(str(disc_subdir)) == "Armada (USA).cue"

    # Another disc subdir example
    disc_subdir2 = tmp_path / "roms" / "Game (Disc 1).cue"
    disc_subdir2.mkdir(parents=True)
    assert organizer.get_rom_basename(str(disc_subdir2)) == "Game (Disc 1).cue"

    # Test files INSIDE disc subdirectories
    disc_file = disc_subdir / "Armada (USA).cue"
    disc_file.touch()
    assert organizer.get_rom_basename(str(disc_file)) == "Armada (USA).cue"

    # Test file with disc number in name inside disc subdirectory
    disc_subdir3 = tmp_path / "roms" / "Baten Kaitos Origins (USA) (Disc 2).rvz"
    disc_subdir3.mkdir(parents=True)
    disc_file2 = disc_subdir3 / "Baten Kaitos Origins (USA) (Disc 2).rvz"
    disc_file2.touch()
    # Should return parent directory name (with .rvz), not strip it
    assert organizer.get_rom_basename(str(disc_file2)) == "Baten Kaitos Origins (USA) (Disc 2).rvz"

    # Test regular file with disc number in name (NOT in a disc subdirectory)
    regular_file = tmp_path / "roms" / "Final Fantasy VII (Disc 2).iso"
    regular_file.parent.mkdir(parents=True, exist_ok=True)
    regular_file.touch()
    # Should strip extension since it's a regular file
    assert organizer.get_rom_basename(str(regular_file)) == "Final Fantasy VII (Disc 2)"
