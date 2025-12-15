"""Match confidence scoring for search results."""

import logging
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, Any, Optional


logger = logging.getLogger(__name__)


def calculate_match_confidence(
    rom_info: Dict[str, Any],
    game_data: Dict[str, Any],
    preferred_regions: list[str],
) -> float:
    """
    Calculate confidence score for search result match.

    Uses multi-factor scoring algorithm:
    - Filename similarity: 40%
    - Region match: 30%
    - File size match: 15%
    - Media availability: 10%
    - User rating: 5%

    Args:
        rom_info: ROM metadata from scanner (path, filename, size, crc32, system)
        game_data: Game metadata from ScreenScraper API
        preferred_regions: Ordered list of preferred region codes

    Returns:
        Confidence score between 0.0 and 1.0
    """
    scores = {
        "filename": _score_filename_similarity(rom_info, game_data),
        "region": _score_region_match(game_data, preferred_regions),
        "size": _score_file_size(rom_info, game_data),
        "media": _score_media_availability(game_data),
        "rating": _score_user_rating(game_data),
    }

    # Weighted average
    weights = {
        "filename": 0.40,
        "region": 0.30,
        "size": 0.15,
        "media": 0.10,
        "rating": 0.05,
    }

    total_score = sum(scores[key] * weights[key] for key in scores)

    logger.debug(
        f"Match scoring breakdown: filename={scores['filename']:.2f} ({weights['filename']*100:.0f}%), "
        f"region={scores['region']:.2f} ({weights['region']*100:.0f}%), "
        f"size={scores['size']:.2f} ({weights['size']*100:.0f}%), "
        f"media={scores['media']:.2f} ({weights['media']*100:.0f}%), "
        f"rating={scores['rating']:.2f} ({weights['rating']*100:.0f}%) "
        f"-> total={total_score:.2f}"
    )

    return total_score


def _score_filename_similarity(
    rom_info: Dict[str, Any], game_data: Dict[str, Any]
) -> float:
    """
    Score filename similarity (40% weight).

    Compares ROM filename against game names in all regions.
    Uses normalized string comparison (lowercase, no punctuation).

    Returns:
        Similarity score 0.0-1.0
    """
    rom_path = Path(rom_info.get("path", ""))
    rom_name = rom_path.stem.lower()  # Filename without extension

    # Normalize: remove common ROM tags and punctuation
    rom_name_clean = _normalize_name(rom_name)

    # Get all game names from different regions
    game_names = game_data.get("names", {})
    if not game_names:
        return 0.0

    # Find best matching name across all regions
    best_similarity = 0.0
    for region, name in game_names.items():
        name_clean = _normalize_name(name.lower())
        similarity = SequenceMatcher(None, rom_name_clean, name_clean).ratio()
        if similarity > best_similarity:
            best_similarity = similarity
            logger.debug(
                f"Filename match: '{rom_name_clean}' vs '{name_clean}' [{region}] = {similarity:.2f}"
            )

    return best_similarity


def _score_region_match(
    game_data: Dict[str, Any], preferred_regions: list[str]
) -> float:
    """
    Score region match (30% weight).

    Higher score if game has names/media in preferred regions.

    Returns:
        Region match score 0.0-1.0
    """
    game_names = game_data.get("names", {})
    if not game_names:
        return 0.0

    # Check if any preferred region is present
    available_regions = set(game_names.keys())

    for i, region in enumerate(preferred_regions):
        if region in available_regions:
            # Higher score for earlier regions in preference list
            # First preferred region = 1.0, second = 0.8, third = 0.6, etc.
            position_score = 1.0 - (i * 0.2)
            return max(position_score, 0.2)  # Minimum 0.2 if any match

    # Game exists but not in preferred regions
    return 0.1


def _score_file_size(rom_info: Dict[str, Any], game_data: Dict[str, Any]) -> float:
    """
    Score file size match (15% weight).

    Compares ROM file size against ScreenScraper's reported size.
    Returns 1.0 for exact match, declining score for differences.

    Returns:
        Size match score 0.0-1.0
    """
    rom_size = rom_info.get("size", 0)
    game_size = game_data.get("romsize")

    if not rom_size or not game_size:
        # Size unknown - neutral score
        return 0.5

    try:
        game_size = int(game_size)
    except (ValueError, TypeError):
        return 0.5

    if rom_size == game_size:
        return 1.0

    # Calculate size difference percentage
    size_diff = abs(rom_size - game_size)
    larger_size = max(rom_size, game_size)
    diff_percent = (size_diff / larger_size) * 100

    # Score decreases with difference: 0-5% = 0.9, 5-10% = 0.7, 10-20% = 0.5, >20% = 0.2
    if diff_percent < 5:
        return 0.9
    elif diff_percent < 10:
        return 0.7
    elif diff_percent < 20:
        return 0.5
    else:
        return 0.2


def _score_media_availability(game_data: Dict[str, Any]) -> float:
    """
    Score media availability (10% weight).

    Games with more media assets are more likely to be complete/accurate entries.

    Returns:
        Media availability score 0.0-1.0
    """
    media_count = 0
    media_types = ["cover", "screenshot", "titlescreen", "marquee", "box3d", "video"]

    for media_type in media_types:
        if media_type in game_data:
            media_data = game_data[media_type]
            # Check if media exists (not just empty dict)
            if isinstance(media_data, dict) and media_data:
                media_count += 1
            elif isinstance(media_data, list) and media_data:
                media_count += 1

    # Normalize to 0-1 range (having 3+ media types = 1.0)
    return min(media_count / 3.0, 1.0)


def _score_user_rating(game_data: Dict[str, Any]) -> float:
    """
    Score user rating (5% weight).

    Higher-rated games are more likely to be correct matches
    (well-documented, popular titles).

    Returns:
        Rating score 0.0-1.0
    """
    note = game_data.get("note")
    if not note:
        # No rating - neutral score
        return 0.5

    try:
        # ScreenScraper ratings are typically 0-20 scale
        rating = float(note)
        # Normalize to 0-1 range
        normalized = rating / 20.0
        return min(normalized, 1.0)
    except (ValueError, TypeError):
        return 0.5


def _normalize_name(name: str) -> str:
    """
    Normalize game name for comparison.

    Removes common ROM tags, punctuation, and extra whitespace.

    Args:
        name: Raw name string

    Returns:
        Normalized name
    """
    import re

    # Convert to lowercase first
    name = name.lower()

    # Remove common ROM tags in parentheses/brackets
    # Examples: (USA), [!], (Rev 1), etc.
    name = re.sub(r"\([^)]*\)", "", name)
    name = re.sub(r"\[[^\]]*\]", "", name)

    # Remove special characters except spaces and alphanumeric
    # Keep letters, numbers, and spaces
    name = re.sub(r"[^a-z0-9\s]", "", name)

    # Collapse multiple spaces
    name = re.sub(r"\s+", " ", name)

    return name.strip()
