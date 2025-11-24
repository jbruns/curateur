from pathlib import Path

import pytest

from curateur.scanner.disc_handler import (
    is_disc_subdirectory,
    get_contained_file,
    validate_disc_subdirectory,
    DiscSubdirError,
)


@pytest.mark.unit
def test_disc_subdirectory_detection_and_validation(tmp_path):
    disc_dir = tmp_path / "Game (Disc 1).cue"
    disc_dir.mkdir()
    contained = disc_dir / "Game (Disc 1).cue"
    contained.write_text("cue content")

    assert is_disc_subdirectory(disc_dir, [".cue", ".gdi"]) is True
    assert get_contained_file(disc_dir) == contained
    assert validate_disc_subdirectory(disc_dir, [".cue"]) == contained


@pytest.mark.unit
def test_disc_subdirectory_invalid(tmp_path):
    bad_dir = tmp_path / "NotADisc"
    bad_dir.mkdir()
    with pytest.raises(DiscSubdirError):
        validate_disc_subdirectory(bad_dir, [".cue"])
