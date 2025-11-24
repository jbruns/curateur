import pytest
from pathlib import Path

from curateur.gamelist.parser import GamelistParser


@pytest.mark.unit
def test_parse_gamelist_extracts_entries(tmp_path, data_dir):
    parser = GamelistParser()
    src = data_dir / "gamelist_valid.xml"
    gamelist_path = tmp_path / "gamelist.xml"
    gamelist_path.write_text(src.read_text())

    entries = parser.parse_gamelist(gamelist_path)

    assert len(entries) == 2
    alpha = entries[0]
    assert alpha.path == "./Alpha.zip"
    assert alpha.name == "Alpha"
    assert alpha.screenscraper_id == "123"
    assert alpha.favorite is True
    assert alpha.playcount == 5
    assert alpha.extra_fields.get("sortname") == "Alpha, The"


@pytest.mark.unit
def test_parse_gamelist_missing_file_raises():
    parser = GamelistParser()
    with pytest.raises(FileNotFoundError):
        parser.parse_gamelist(Path("/tmp/missing/gamelist.xml"))
