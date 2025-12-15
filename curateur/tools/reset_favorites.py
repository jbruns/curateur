#!/usr/bin/env python3
"""
Reset favorite flags in gamelist.xml based on rating threshold.

This script updates the <favorite> element for all games in a gamelist.xml file
based on their rating. Games with ratings at or above the threshold will be
marked as favorites, while games below the threshold will have their favorite
flag removed.

Usage:
    python -m curateur.tools.reset_favorites /path/to/gamelist.xml --threshold 0.8
"""

import argparse
import sys
from pathlib import Path
from typing import Optional
from lxml import etree


def reset_favorites(
    gamelist_path: Path, rating_threshold: float, dry_run: bool = False
) -> tuple[int, int, int]:
    """
    Reset favorite flags based on rating threshold.

    Args:
        gamelist_path: Path to gamelist.xml file
        rating_threshold: Minimum rating for favorite (0.0 to 1.0)
        dry_run: If True, don't write changes

    Returns:
        Tuple of (favorites_added, favorites_removed, games_without_rating)
    """
    if not gamelist_path.exists():
        raise FileNotFoundError(f"Gamelist not found: {gamelist_path}")

    # Parse XML
    parser = etree.XMLParser(remove_blank_text=True)
    tree = etree.parse(str(gamelist_path), parser)
    root = tree.getroot()

    favorites_added = 0
    favorites_removed = 0
    games_without_rating = 0

    # Process each game entry
    for game in root.findall("game"):
        # Get rating element
        rating_elem = game.find("rating")

        if rating_elem is None or not rating_elem.text:
            # No rating - remove favorite if it exists
            favorite_elem = game.find("favorite")
            if favorite_elem is not None:
                game.remove(favorite_elem)
                favorites_removed += 1
            games_without_rating += 1
            continue

        try:
            rating = float(rating_elem.text)
        except ValueError:
            # Invalid rating - treat as no rating
            favorite_elem = game.find("favorite")
            if favorite_elem is not None:
                game.remove(favorite_elem)
                favorites_removed += 1
            games_without_rating += 1
            continue

        # Check if rating meets threshold
        should_be_favorite = rating >= rating_threshold
        favorite_elem = game.find("favorite")

        if should_be_favorite:
            # Should be favorite
            if favorite_elem is None:
                # Add favorite element as last child
                favorite_elem = etree.Element("favorite")
                favorite_elem.text = "true"
                game.append(favorite_elem)
                favorites_added += 1
            elif favorite_elem.text != "true":
                # Update existing to true
                favorite_elem.text = "true"
                favorites_added += 1
        else:
            # Should not be favorite
            if favorite_elem is not None:
                game.remove(favorite_elem)
                favorites_removed += 1

    # Write changes if not dry run
    if not dry_run:
        tree.write(
            str(gamelist_path),
            encoding="utf-8",
            xml_declaration=True,
            pretty_print=True,
        )

    return favorites_added, favorites_removed, games_without_rating


def main():
    parser = argparse.ArgumentParser(
        description="Reset favorite flags in gamelist.xml based on rating threshold",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Set favorites for games rated 0.8 or higher
  python -m curateur.tools.reset_favorites /path/to/gamelist.xml --threshold 0.8

  # Preview changes without modifying the file
  python -m curateur.tools.reset_favorites /path/to/gamelist.xml --threshold 0.75 --dry-run

  # Use default threshold of 0.8
  python -m curateur.tools.reset_favorites /path/to/gamelist.xml

Notes:
  - Rating values range from 0.0 (worst) to 1.0 (best)
  - Games without ratings will not be marked as favorites
  - A backup of the original file is recommended before running
        """,
    )

    parser.add_argument("gamelist", type=Path, help="Path to gamelist.xml file")

    parser.add_argument(
        "--threshold",
        type=float,
        default=0.8,
        help="Minimum rating for favorite (0.0 to 1.0, default: 0.8)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without modifying the file",
    )

    args = parser.parse_args()

    # Validate threshold
    if not 0.0 <= args.threshold <= 1.0:
        print("Error: Threshold must be between 0.0 and 1.0", file=sys.stderr)
        return 1

    gamelist_path = args.gamelist.resolve()

    print(f"Gamelist: {gamelist_path}")
    print(f"Rating threshold: {args.threshold}")
    print()

    try:
        favorites_added, favorites_removed, games_without_rating = reset_favorites(
            gamelist_path, args.threshold, args.dry_run
        )
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    # Print summary
    print(f"Favorites added: {favorites_added}")
    print(f"Favorites removed: {favorites_removed}")
    print(f"Games without rating: {games_without_rating}")
    print()

    if args.dry_run:
        print("DRY RUN - No changes were made")
    else:
        print(f"✓ Updated {gamelist_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
