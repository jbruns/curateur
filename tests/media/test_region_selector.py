import pytest

from curateur.media.region_selector import (
    detect_region_from_filename,
    select_best_region,
    get_media_for_region,
    should_use_region_filtering,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    "filename,expected",
    [
        ("Game (USA).zip", ["us"]),
        ("Game (Japan, USA).nes", ["jp", "us"]),
        ("Game (Europe) (En,Fr,De).zip", ["eu"]),
        ("Game.zip", []),
    ],
)
def test_detect_region_from_filename(filename, expected):
    assert detect_region_from_filename(filename) == expected


@pytest.mark.unit
def test_select_best_region_uses_preferred_and_filename_matches():
    available = ["jp", "us", "eu"]
    # Filename includes jp and us; preferred puts us first
    best = select_best_region(available, "Game (Japan, USA).nes", preferred_regions=["us", "eu", "jp"])
    assert best == "us"


@pytest.mark.unit
def test_get_media_for_region_returns_first_when_no_region():
    media_list = [
        {"type": "ss", "url": "a"},
        {"type": "ss", "url": "b", "region": "eu"},
    ]
    assert get_media_for_region(media_list, "ss", None)["url"] == "a"
    assert get_media_for_region(media_list, "ss", "eu")["url"] == "b"


@pytest.mark.unit
def test_should_use_region_filtering_skips_video_and_fanart():
    assert should_use_region_filtering("ss") is True
    assert should_use_region_filtering("video") is False
