from pathlib import Path

import pytest

from curateur.scanner.hash_calculator import calculate_hash, format_file_size


@pytest.mark.unit
def test_calculate_hash_respects_size_limit(tmp_path):
    rom = tmp_path / "file.bin"
    rom.write_bytes(b"a" * 10)

    # With limit above size, returns hash
    h = calculate_hash(rom, algorithm="crc32", size_limit=100)
    assert h is not None

    # With limit below size, returns None
    assert calculate_hash(rom, size_limit=1) is None


@pytest.mark.unit
def test_calculate_hash_supports_md5_and_sha1(tmp_path):
    rom = tmp_path / "file.bin"
    rom.write_bytes(b"data")

    md5 = calculate_hash(rom, algorithm="md5", size_limit=0)
    sha1 = calculate_hash(rom, algorithm="sha1", size_limit=0)
    assert len(md5) == 32
    assert len(sha1) == 40


@pytest.mark.unit
@pytest.mark.parametrize(
    "size,expected",
    [
        (500, "500 B"),
        (1500, "1.5 KB"),
        (1024 * 1024, "1.0 MB"),
        (2 * 1024 * 1024 * 1024, "2.00 GB"),
    ],
)
def test_format_file_size(size, expected):
    assert format_file_size(size) == expected
