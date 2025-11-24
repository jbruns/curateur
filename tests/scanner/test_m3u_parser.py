from pathlib import Path

import pytest

from curateur.scanner.m3u_parser import parse_m3u, get_disc1_file, M3UError


@pytest.mark.unit
def test_parse_m3u_resolves_relative_disc_paths(tmp_path, data_dir):
    # Create disc files
    (tmp_path / "Track01.bin").write_bytes(b"disc1")
    (tmp_path / "Track02.bin").write_bytes(b"disc2")

    m3u = tmp_path / "game.m3u"
    m3u.write_text((data_dir / "scanner" / "sample.m3u").read_text())

    discs = parse_m3u(m3u)
    assert discs[0].name == "Track01.bin"
    assert discs[0].exists()
    assert len(discs) == 2

    disc1 = get_disc1_file(m3u)
    assert disc1.name == "Track01.bin"


@pytest.mark.unit
def test_parse_m3u_missing_file_raises(tmp_path):
    with pytest.raises(M3UError):
        parse_m3u(tmp_path / "missing.m3u")
