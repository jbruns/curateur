from pathlib import Path

import pytest

from curateur.scanner.rom_scanner import scan_system, _process_entry
from curateur.scanner.rom_types import ROMType
from curateur.config.es_systems import SystemDefinition


def _make_system(tmp_path: Path) -> SystemDefinition:
    return SystemDefinition(
        name="nes",
        fullname="NES",
        path=str(tmp_path),
        extensions=[".nes", ".zip", ".m3u", ".cue"],
        platform="nes",
    )


@pytest.mark.unit
def test_process_entry_skips_non_matching_extensions(tmp_path):
    system = _make_system(tmp_path)
    file_path = tmp_path / "readme.txt"
    file_path.write_text("ignore")

    assert _process_entry(file_path, system, crc_size_limit=1) is None


@pytest.mark.unit
def test_process_standard_rom(tmp_path):
    system = _make_system(tmp_path)
    rom = tmp_path / "Alpha.nes"
    rom.write_bytes(b"data")

    info = _process_entry(rom, system, crc_size_limit=10)
    assert info.rom_type == ROMType.STANDARD
    assert info.filename == "Alpha.nes"
    assert info.basename == "Alpha"
    assert info.file_size == 4
    assert info.crc_size_limit == 10


@pytest.mark.unit
def test_process_m3u_and_disc_subdir(tmp_path):
    system = _make_system(tmp_path)

    # M3U setup
    m3u = tmp_path / "Game.m3u"
    m3u.write_text("Disc1.bin")
    (tmp_path / "Disc1.bin").write_bytes(b"disc")

    info_m3u = _process_entry(m3u, system, crc_size_limit=0)
    assert info_m3u.rom_type == ROMType.M3U_PLAYLIST
    assert info_m3u.basename == "Game"

    # Disc subdir setup
    disc_dir = tmp_path / "Game (Disc 1).cue"
    disc_dir.mkdir()
    contained = disc_dir / "Game (Disc 1).cue"
    contained.write_bytes(b"discdata")

    info_disc = _process_entry(disc_dir, system, crc_size_limit=0)
    assert info_disc.rom_type == ROMType.DISC_SUBDIR
    assert info_disc.contained_file == contained


@pytest.mark.unit
def test_scan_system_filters_conflicts(tmp_path):
    system_path = tmp_path / "nes"
    system_path.mkdir()
    # Conflict: both M3U and disc subdir with same basename
    m3u = system_path / "Game.m3u"
    m3u.write_text("Disc1.bin")
    (system_path / "Disc1.bin").write_bytes(b"x")

    disc_dir = system_path / "Game (Disc 1).cue"
    disc_dir.mkdir()
    (disc_dir / "Game (Disc 1).cue").write_text("cue")

    system = SystemDefinition(
        name="nes",
        fullname="NES",
        path=str(system_path),
        extensions=[".nes", ".zip", ".m3u", ".cue"],
        platform="nes",
    )

    roms = scan_system(system, rom_root=tmp_path, crc_size_limit=0)
    # Conflict logic removes the M3U entry; disc subdir remains
    assert len(roms) == 1
    assert roms[0].rom_type.name == "DISC_SUBDIR"
