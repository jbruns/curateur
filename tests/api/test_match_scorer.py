import pytest

from curateur.api.match_scorer import calculate_match_confidence


@pytest.mark.unit
def test_calculate_match_confidence_weights_fields():
    rom_info = {"path": "games/Alpha Quest (USA).zip", "size": 1024}
    game_data = {
        "names": {"us": "Alpha Quest", "eu": "Alpha Quest"},
        "romsize": 1024,
        "note": 18,  # ~0.9 normalized
        "cover": {"url": "cover.png"},
        "screenshot": {"url": "shot.png"},
    }

    score = calculate_match_confidence(rom_info, game_data, preferred_regions=["us", "eu"])
    # High score because filename, region, and size all align
    assert score > 0.7


@pytest.mark.unit
def test_calculate_match_confidence_penalizes_region_mismatch():
    rom_info = {"path": "games/Alpha Quest (USA).zip", "size": 1024}
    game_data = {
        "names": {"jp": "Alpha Quest JP"},
        "romsize": 2048,  # size mismatch
        "note": 10,
    }

    score = calculate_match_confidence(rom_info, game_data, preferred_regions=["us", "eu"])
    assert score < 0.5
