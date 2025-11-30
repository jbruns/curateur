import pytest

from curateur.gamelist.metadata_merger import MetadataMerger
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

    merger = MetadataMerger(merge_strategy="refresh_metadata")
    merged = merger.merge_entry_lists([existing], [new])[0]

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

    merger = MetadataMerger()
    merged = merger.merge_entry_lists(existing, new)

    assert {e.name for e in merged} == {"Alpha", "Beta"}


@pytest.mark.unit
def test_auto_favorite_new_entries_above_threshold():
    """Test that new entries with ratings above threshold are auto-favorited"""
    existing = [_entry("./Alpha.zip", "Alpha", favorite=False)]
    new = [
        _entry("./Beta.zip", "Beta", rating=0.95, favorite=False),  # Above threshold
        _entry("./Gamma.zip", "Gamma", rating=0.8, favorite=False),  # Below threshold
    ]

    merger = MetadataMerger(
        merge_strategy="refresh_metadata",
        auto_favorite_enabled=True,
        auto_favorite_threshold=0.9
    )
    merged = merger.merge_entry_lists(existing, new)

    # Find the entries
    beta = next(e for e in merged if e.name == "Beta")
    gamma = next(e for e in merged if e.name == "Gamma")

    # Beta should be auto-favorited (0.95 >= 0.9)
    assert beta.favorite is True
    # Gamma should not be auto-favorited (0.8 < 0.9)
    assert gamma.favorite is False


@pytest.mark.unit
def test_auto_favorite_disabled_does_not_favorite_new_entries():
    """Test that auto-favorite disabled doesn't favorite new entries"""
    existing = []
    new = [_entry("./Beta.zip", "Beta", rating=0.95, favorite=False)]

    merger = MetadataMerger(
        merge_strategy="refresh_metadata",
        auto_favorite_enabled=False,
        auto_favorite_threshold=0.9
    )
    merged = merger.merge_entry_lists(existing, new)

    beta = merged[0]
    assert beta.favorite is False


@pytest.mark.unit
def test_auto_favorite_does_not_override_existing_entries():
    """Test that auto-favorite doesn't override user-set favorite on existing entries"""
    existing = [_entry("./Alpha.zip", "Alpha", rating=0.8, favorite=True)]  # User favorited despite low rating
    new = [_entry("./Alpha.zip", "Alpha", rating=0.95)]  # New scraped data with high rating

    merger = MetadataMerger(
        merge_strategy="refresh_metadata",
        auto_favorite_enabled=True,
        auto_favorite_threshold=0.9
    )
    merged = merger.merge_entry_lists(existing, new)

    # Should preserve user's favorite=True even though original rating was low
    assert merged[0].favorite is True


@pytest.mark.unit
def test_auto_favorite_upgrades_existing_entries_with_low_rating():
    """Test that auto-favorite sets flag on existing entries when rating increases above threshold"""
    existing = [_entry("./Alpha.zip", "Alpha", rating=0.5, favorite=False)]  # Low rating, not favorited
    new = [_entry("./Alpha.zip", "Alpha", rating=0.95)]  # Updated with high rating

    merger = MetadataMerger(
        merge_strategy="refresh_metadata",
        auto_favorite_enabled=True,
        auto_favorite_threshold=0.9
    )
    merged = merger.merge_entry_lists(existing, new)

    # Should auto-favorite since rating increased above threshold
    assert merged[0].favorite is True


@pytest.mark.unit
def test_preserve_user_edits_blocks_auto_favorite():
    """Test that preserve_user_edits strategy prevents auto-favorite from modifying entries"""
    existing = [_entry("./Alpha.zip", "Alpha", rating=0.5, favorite=False)]
    new_entries = [
        _entry("./Alpha.zip", "Alpha", rating=0.95),  # Updated existing with high rating
        _entry("./Beta.zip", "Beta", rating=0.95, favorite=False),  # New entry with high rating
    ]

    merger = MetadataMerger(
        merge_strategy="preserve_user_edits",
        auto_favorite_enabled=True,
        auto_favorite_threshold=0.9
    )
    merged = merger.merge_entry_lists(existing, new_entries)

    alpha = next(e for e in merged if e.name == "Alpha")
    beta = next(e for e in merged if e.name == "Beta")

    # Neither should be auto-favorited when strategy is preserve_user_edits
    assert alpha.favorite is False
    assert beta.favorite is False


@pytest.mark.unit
def test_refresh_metadata_allows_auto_favorite():
    """Test that refresh_metadata strategy allows auto-favorite"""
    existing = [_entry("./Alpha.zip", "Alpha", rating=0.5, favorite=False)]
    new_entries = [
        _entry("./Alpha.zip", "Alpha", rating=0.95),  # Updated existing with high rating
        _entry("./Beta.zip", "Beta", rating=0.95, favorite=False),  # New entry with high rating
    ]

    merger = MetadataMerger(
        merge_strategy="refresh_metadata",
        auto_favorite_enabled=True,
        auto_favorite_threshold=0.9
    )
    merged = merger.merge_entry_lists(existing, new_entries)

    alpha = next(e for e in merged if e.name == "Alpha")
    beta = next(e for e in merged if e.name == "Beta")

    # Both should be auto-favorited with refresh_metadata strategy
    assert alpha.favorite is True
    assert beta.favorite is True


@pytest.mark.unit
def test_reset_all_allows_auto_favorite():
    """Test that reset_all strategy allows auto-favorite"""
    existing = []
    new_entries = [_entry("./Beta.zip", "Beta", rating=0.95, favorite=False)]

    merger = MetadataMerger(
        merge_strategy="reset_all",
        auto_favorite_enabled=True,
        auto_favorite_threshold=0.9
    )
    merged = merger.merge_entry_lists(existing, new_entries)

    # Should be auto-favorited with reset_all strategy
    assert merged[0].favorite is True
