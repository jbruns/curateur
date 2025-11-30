from pathlib import Path

import pytest

from curateur.tools import organize_roms


def _write_es_systems(tmp_path: Path) -> Path:
    xml = tmp_path / "es_systems.xml"
    xml.write_text(
        """
<systemList>
  <system>
    <name>psx</name>
    <fullname>Sony PlayStation</fullname>
    <path>%ROMPATH%/psx</path>
    <extension>.cue .bin .iso .m3u</extension>
    <platform>psx</platform>
  </system>
</systemList>
""".strip()
    )
    return xml


@pytest.mark.unit
def test_multi_disc_cue_creates_multidisc_and_m3u(tmp_path):
    es_xml = _write_es_systems(tmp_path)
    system = organize_roms.load_system(es_xml, "psx")

    source = tmp_path / "source"
    source.mkdir()

    cue1 = source / "Alpha (Disc 1).cue"
    cue1.write_text('FILE "Alpha (Disc 1) (Track 1).bin" BINARY\n')
    (source / "Alpha (Disc 1) (Track 1).bin").write_bytes(b"disc1")

    cue2 = source / "Alpha (Disc 2).cue"
    cue2.write_text('FILE "Alpha (Disc 2) (Track 1).bin" BINARY\n')
    (source / "Alpha (Disc 2) (Track 1).bin").write_bytes(b"disc2")

    rom_root = tmp_path / "roms"

    organize_roms.organize(source, system, rom_root)

    target_system_dir = rom_root / "psx"
    m3u_path = target_system_dir / "Alpha.m3u"
    assert m3u_path.exists()
    m3u_lines = m3u_path.read_text().splitlines()
    assert m3u_lines == [
        "./.multidisc/Alpha (Disc 1).cue/Alpha (Disc 1).cue",
        "./.multidisc/Alpha (Disc 2).cue/Alpha (Disc 2).cue",
    ]

    disc1_dir = target_system_dir / ".multidisc" / "Alpha (Disc 1).cue"
    disc2_dir = target_system_dir / ".multidisc" / "Alpha (Disc 2).cue"
    assert (disc1_dir / "Alpha (Disc 1).cue").exists()
    assert (disc1_dir / "Alpha (Disc 1) (Track 1).bin").exists()
    assert (disc2_dir / "Alpha (Disc 2).cue").exists()
    assert (disc2_dir / "Alpha (Disc 2) (Track 1).bin").exists()


@pytest.mark.unit
def test_single_disc_cue_gets_disc_directory(tmp_path):
    es_xml = _write_es_systems(tmp_path)
    system = organize_roms.load_system(es_xml, "psx")

    source = tmp_path / "source"
    source.mkdir()
    cue = source / "Solo.cue"
    cue.write_text('FILE "Solo.bin" BINARY\n')
    (source / "Solo.bin").write_bytes(b"solo")

    rom_root = tmp_path / "roms"
    organize_roms.organize(source, system, rom_root)

    target_system_dir = rom_root / "psx"
    disc_dir = target_system_dir / "Solo.cue"
    assert (disc_dir / "Solo.cue").exists()
    assert (disc_dir / "Solo.bin").exists()
    # No playlist created for single disc
    assert not (target_system_dir / "Solo.m3u").exists()


@pytest.mark.unit
def test_iso_copied_without_disc_dir(tmp_path):
    es_xml = _write_es_systems(tmp_path)
    system = organize_roms.load_system(es_xml, "psx")

    source = tmp_path / "source"
    source.mkdir()
    iso = source / "Lone.iso"
    iso.write_bytes(b"iso-data")

    rom_root = tmp_path / "roms"
    organize_roms.organize(source, system, rom_root)

    target_system_dir = rom_root / "psx"
    assert (target_system_dir / "Lone.iso").exists()
    # .multidisc directory is not needed for single ISO
    assert not (target_system_dir / ".multidisc").exists()
