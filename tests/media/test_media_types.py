import pytest

from curateur.media.media_types import (
    get_directory_for_media_type,
    is_supported_media_type,
    convert_directory_names_to_media_types,
    to_singular,
    to_plural,
)


@pytest.mark.unit
def test_get_directory_for_media_type_and_singular_plural():
    assert get_directory_for_media_type("ss") == "screenshots"
    assert to_singular("covers") == "cover"
    assert to_plural("cover") == "covers"


@pytest.mark.unit
def test_convert_directory_names_to_media_types_filters_unknowns():
    assert convert_directory_names_to_media_types(["covers", "unknown"]) == ["box-2D"]
    assert is_supported_media_type("box-2D") is True
    assert is_supported_media_type("bogus") is False
