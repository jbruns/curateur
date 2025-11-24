import pytest

from curateur.media.url_selector import MediaURLSelector


@pytest.mark.unit
def test_url_selector_picks_region_and_supported_types():
    selector = MediaURLSelector(
        preferred_regions=["us", "eu"],
        enabled_media_types=["box-2D", "ss"],
    )
    media_list = [
        {"type": "box-2D", "url": "cover-eu", "region": "eu"},
        {"type": "box-2D", "url": "cover-us", "region": "us"},
        {"type": "ss", "url": "shot", "region": "us"},
        {"type": "sstitle", "url": "title", "region": "us"},  # not enabled
    ]

    selected = selector.select_media_urls(media_list, "Game (USA).zip")

    assert selected["box-2D"]["url"] == "cover-us"
    assert selected["ss"]["url"] == "shot"
    assert "sstitle" not in selected
