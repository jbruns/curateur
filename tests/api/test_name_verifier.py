import pytest

from curateur.api.name_verifier import (
    verify_name_match,
    normalize_name,
    calculate_similarity,
    check_word_overlap,
    format_verification_result,
)


@pytest.mark.unit
def test_normalize_name_removes_noise():
    assert normalize_name("The Game (USA) [!].zip") == "game"


@pytest.mark.unit
def test_verify_name_match_thresholds():
    is_match, score, reason = verify_name_match(
        "Super Mario Bros. 3 (USA).zip", "Super Mario Bros. 3", threshold_mode="strict"
    )
    assert is_match is True
    assert score > 0.8
    assert "Similarity" in reason or "overlap" in reason.lower()

    is_match, score, reason = verify_name_match(
        "Offbeat Title (USA).zip", "Completely Different", threshold_mode="strict"
    )
    assert is_match is False
    assert score < 0.5
    assert "Similarity below" in reason


@pytest.mark.unit
def test_check_word_overlap_accepts_abbreviations():
    assert check_word_overlap("Super Mario Bros 3", "Mario Bros 3 (USA)") is True


@pytest.mark.unit
def test_format_verification_result_includes_similarity():
    msg = format_verification_result("foo.nes", "Foo", True, 0.9, "Similarity above threshold")
    assert "Similarity" in msg
    assert "✓" in msg
