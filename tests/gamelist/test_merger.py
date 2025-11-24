import pytest

from curateur.gamelist.parser import GamelistMerger
from curateur.gamelist.game_entry import GameEntry


def _entry(path: str, name: str, **kwargs) -> GameEntry:
    return GameEntry(path=path, name=name, **kwargs)


@pytest.mark.unit
def test_merger_preserves_user_fields_and_extra():
    existing = _entry(
        "./Alpha.zip",
        "Alpha",
        favorite=True,
        playcount=10,
        lastplayed="20230101T000000",
        hidden=True,
        extra_fields={"sortname": "Alpha, The"},
    )
    new = _entry(
        "./Alpha.zip",
        "Alpha Updated",
        desc="New desc",
        rating=0.9,
        releasedate="19900101T000000",
    )

    merger = GamelistMerger()
    merged = merger.merge_entries([existing], [new])[0]

    assert merged.name == "Alpha Updated"
    assert merged.favorite is True
    assert merged.playcount == 10
    assert merged.lastplayed == "20230101T000000"
    assert merged.hidden is True
    assert merged.extra_fields["sortname"] == "Alpha, The"


@pytest.mark.unit
def test_merger_appends_new_entries_and_preserves_existing_not_in_new():
    existing = [_entry("./Alpha.zip", "Alpha")]
    new = [_entry("./Beta.zip", "Beta")]

    merger = GamelistMerger()
    merged = merger.merge_entries(existing, new)

    assert {e.name for e in merged} == {"Alpha", "Beta"}
