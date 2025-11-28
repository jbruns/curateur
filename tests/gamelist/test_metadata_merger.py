import pytest

from curateur.gamelist.game_entry import GameEntry
from curateur.gamelist.metadata_merger import MetadataMerger


def _entry(path: str, name: str, **kwargs) -> GameEntry:
    return GameEntry(path=path, name=name, **kwargs)


@pytest.mark.unit
def test_refresh_metadata_updates_scraped_fields_only():
    existing = _entry(
        "./Alpha.zip",
        "Old Name",
        desc="Old desc",
        rating=0.5,
        releasedate="19900101T000000",
        developer="OldDev",
        favorite=True,
        playcount=3,
    )
    scraped = _entry(
        "./Alpha.zip",
        "New Name",
        desc="New desc",
        rating=0.9,
        releasedate="19910101T000000",
        developer="NewDev",
        favorite=False,
        playcount=0,
    )

    merger = MetadataMerger(merge_strategy="refresh_metadata")
    result = merger.merge_entries(existing, scraped)
    merged = result.merged_entry

    assert merged.name == "New Name"
    assert merged.desc == "New desc"
    assert merged.rating == 0.9
    assert merged.developer == "NewDev"
    # User fields preserved
    assert merged.favorite is True
    assert merged.playcount == 3
    assert "favorite" in result.preserved_fields
    assert "name" in result.updated_fields


@pytest.mark.unit
def test_auto_favorite_sets_flag_based_on_rating():
    existing = _entry("./Alpha.zip", "Alpha", favorite=False)
    scraped = _entry("./Alpha.zip", "Alpha", rating=0.95)

    merger = MetadataMerger(
        merge_strategy="refresh_metadata",
        auto_favorite_enabled=True,
        auto_favorite_threshold=0.9,
    )
    merged = merger.merge_entries(existing, scraped).merged_entry

    assert merged.favorite is True


@pytest.mark.unit
def test_rating_conversion_from_screenscraper():
    """Test that ScreenScraper ratings (0-20 scale) are correctly converted to ES-DE format (0-1 scale)"""
    from curateur.gamelist.game_entry import GameEntry

    # Simulate ScreenScraper API response with rating=18 (out of 20)
    game_info = {
        'id': '12345',
        'name': 'Test Game',
        'rating': 18.0,  # ScreenScraper's 0-20 scale
        'descriptions': {'en': 'Test description'},
        'release_dates': {'us': '2000-01-01'},
        'genres': ['Action'],
    }

    entry = GameEntry.from_api_response(
        game_info,
        rom_path='./TestGame.zip',
        media_paths={}
    )

    # Should be normalized to 0.9 (18/20 = 0.9)
    assert entry.rating == 0.9

    # Test edge cases
    game_info_perfect = {
        'id': '12346',
        'name': 'Perfect Game',
        'rating': 20.0,
    }
    entry_perfect = GameEntry.from_api_response(game_info_perfect, './Perfect.zip', {})
    assert entry_perfect.rating == 1.0

    game_info_zero = {
        'id': '12347',
        'name': 'Zero Game',
        'rating': 0.0,
    }
    entry_zero = GameEntry.from_api_response(game_info_zero, './Zero.zip', {})
    assert entry_zero.rating == 0.0
