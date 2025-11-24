from pathlib import Path

import pytest

from curateur.gamelist.integrity_validator import IntegrityValidator
from curateur.gamelist.game_entry import GameEntry


def _entry(path: str) -> GameEntry:
    return GameEntry(path=path, name=Path(path).stem)


@pytest.mark.unit
def test_integrity_validator_detects_missing_roms(tmp_path):
    entries = [_entry("./Alpha.zip"), _entry("./Beta.zip")]
    rom_files = [tmp_path / "Alpha.zip"]
    rom_files[0].touch()

    validator = IntegrityValidator(threshold=0.5)
    result = validator.validate(entries, rom_files)

    assert result.is_valid is True  # 1/2 >= 0.5
    assert result.match_ratio == 0.5
    assert "./Beta.zip" in result.missing_roms


@pytest.mark.unit
def test_integrity_validator_handles_empty_entries():
    validator = IntegrityValidator()
    result = validator.validate([], [])

    assert result.is_valid is True
    assert result.match_ratio == 1.0
    assert result.missing_roms == []
