"""Name verification with fuzzy matching for ROM identification."""

import re
from difflib import SequenceMatcher
from typing import Optional, Tuple


# Verification threshold levels
VERIFICATION_THRESHOLDS = {
    "strict": 0.8,  # 80% similarity required
    "normal": 0.6,  # 60% similarity required (default)
    "lenient": 0.4,  # 40% similarity required
    "disabled": 0.0,  # Accept any match
}


def normalize_name(name: str) -> str:
    """
    Normalize a game name for comparison.

    Removes common noise words, normalizes whitespace, converts to lowercase.

    Args:
        name: Game name to normalize

    Returns:
        Normalized name
    """
    if not name:
        return ""

    # Convert to lowercase
    result = name.lower()

    # Remove file extensions
    for ext in [".zip", ".7z", ".rar", ".nes", ".snes", ".bin", ".cue", ".gdi", ".iso"]:
        if result.endswith(ext):
            result = result[: -len(ext)]

    # Remove common region/version indicators in parentheses/brackets
    # e.g., "(USA)", "[!]", "(Rev 1)", etc.
    result = re.sub(r"\s*[\(\[].*?[\)\]]", "", result)

    # Remove "The" at the beginning
    result = re.sub(r"^the\s+", "", result)

    # Remove special characters and normalize whitespace
    result = re.sub(r"[^a-z0-9\s]", " ", result)
    result = re.sub(r"\s+", " ", result)
    result = result.strip()

    return result


def calculate_similarity(name1: str, name2: str) -> float:
    """
    Calculate similarity score between two names.

    Uses SequenceMatcher for fuzzy string matching.

    Args:
        name1: First name
        name2: Second name

    Returns:
        Similarity score between 0.0 and 1.0
    """
    norm1 = normalize_name(name1)
    norm2 = normalize_name(name2)

    if not norm1 or not norm2:
        return 0.0

    # Use SequenceMatcher for Gestalt pattern matching
    matcher = SequenceMatcher(None, norm1, norm2)
    return matcher.ratio()


def check_word_overlap(name1: str, name2: str) -> bool:
    """
    Check if names have significant word overlap.

    This can catch cases where similarity is low but the names clearly
    refer to the same game (e.g., "SMB3" vs "Super Mario Bros. 3").

    Args:
        name1: First name
        name2: Second name

    Returns:
        True if significant word overlap detected
    """
    words1 = set(normalize_name(name1).split())
    words2 = set(normalize_name(name2).split())

    # Remove very short words (less than 3 chars)
    words1 = {w for w in words1 if len(w) >= 3}
    words2 = {w for w in words2 if len(w) >= 3}

    if not words1 or not words2:
        return False

    # Check for overlap
    overlap = words1 & words2

    # If more than 50% of words match, consider it a match
    overlap_ratio1 = len(overlap) / len(words1)
    overlap_ratio2 = len(overlap) / len(words2)

    return overlap_ratio1 >= 0.5 or overlap_ratio2 >= 0.5


def verify_name_match(
    rom_filename: str, api_game_name: str, threshold_mode: str = "normal"
) -> Tuple[bool, float, str]:
    """
    Verify that API response matches the ROM filename.

    Args:
        rom_filename: ROM filename (e.g., "Zelda (USA).zip")
        api_game_name: Game name from API response
        threshold_mode: Verification mode (strict, normal, lenient, disabled)

    Returns:
        Tuple of (is_match, similarity_score, reason)
    """
    # Get threshold
    threshold = VERIFICATION_THRESHOLDS.get(threshold_mode, 0.6)

    # Calculate similarity
    similarity = calculate_similarity(rom_filename, api_game_name)

    # Check if similarity meets threshold
    if similarity >= threshold:
        return True, similarity, "Similarity above threshold"

    # If similarity is low but there's word overlap, accept it
    if check_word_overlap(rom_filename, api_game_name):
        return True, similarity, "Word overlap detected"

    # No match
    return False, similarity, "Similarity below threshold, no word overlap"


def format_verification_result(
    rom_filename: str,
    api_game_name: str,
    is_match: bool,
    similarity: float,
    reason: str,
) -> str:
    """
    Format verification result for logging.

    Args:
        rom_filename: ROM filename
        api_game_name: API game name
        is_match: Whether match was accepted
        similarity: Similarity score
        reason: Reason for decision

    Returns:
        Formatted string
    """
    status = "✓" if is_match else "✗"

    lines = [
        f"{status} Name verification:",
        f"  ROM: {rom_filename}",
        f"  API: {api_game_name}",
        f"  Similarity: {similarity*100:.0f}% ({reason})",
    ]

    return "\n".join(lines)
