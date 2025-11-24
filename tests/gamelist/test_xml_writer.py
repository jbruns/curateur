from pathlib import Path

import pytest
from lxml import etree

from curateur.gamelist.xml_writer import GamelistWriter
from curateur.gamelist.game_entry import GameEntry, GamelistMetadata


@pytest.mark.unit
def test_xml_writer_writes_provider_and_entries(tmp_path):
    entries = [
        GameEntry(path="./Alpha.zip", name="Alpha", favorite=True, extra_fields={"sortname": "Alpha, The"}),
        GameEntry(path="./Beta.zip", name="Beta", rating=0.9),
    ]
    writer = GamelistWriter(GamelistMetadata(system="nes"))
    out = tmp_path / "gamelist.xml"

    writer.write_gamelist(entries, out)
    assert out.exists()
    assert writer.validate_output(out) is True

    tree = etree.parse(str(out))
    root = tree.getroot()
    provider = root.find("provider")
    assert provider is not None
    assert provider.findtext("System") == "nes"

    games = root.findall("game")
    assert len(games) == 2
    alpha = games[0]
    assert alpha.findtext("name") == "Alpha"
    # Extra field preserved
    assert alpha.findtext("sortname") == "Alpha, The"

    beta = games[1]
    # Rating serialized without trailing zeros
    assert beta.findtext("rating") == "0.9"
