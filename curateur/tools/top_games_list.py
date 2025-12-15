#!/usr/bin/env python3
"""Command-line tool to fetch games from RAWG API sorted by Metacritic score."""

import sys
import argparse
import logging
import requests
import csv
from typing import Optional, List, Dict
from urllib.parse import urljoin
from io import StringIO

# Setup logging - output to stderr to avoid interfering with CSV output
logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)

logger = logging.getLogger(__name__)

RAWG_BASE_URL = "https://api.rawg.io/"


def fetch_platform_mapping(api_key: str) -> Dict[str, int]:
    """
    Fetch platform list from RAWG API and create a mapping of name/slug to ID.

    Args:
        api_key: RAWG API key

    Returns:
        Dictionary mapping platform names and slugs (lowercase) to platform IDs
    """
    platform_map = {}
    page = 1

    while True:
        params = {"key": api_key, "page": page, "page_size": 40}

        url = urljoin(RAWG_BASE_URL, "/api/platforms")

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching platforms from RAWG API: {e}")
            sys.exit(1)
        except ValueError as e:
            logger.error(f"Error parsing JSON response: {e}")
            sys.exit(1)

        results = data.get("results", [])

        if not results:
            break

        for platform in results:
            platform_id = platform.get("id")
            platform_name = platform.get("name", "").lower()
            platform_slug = platform.get("slug", "").lower()

            if platform_id:
                if platform_name:
                    platform_map[platform_name] = platform_id
                if platform_slug:
                    platform_map[platform_slug] = platform_id

        # Check if there's a next page
        if not data.get("next"):
            break

        page += 1

    return platform_map


def resolve_platform_id(
    platform_query: str, api_key: str, verbose: bool = False
) -> int:
    """
    Resolve a platform name or slug to a platform ID.

    Args:
        platform_query: Platform name, slug, or ID
        api_key: RAWG API key
        verbose: Enable verbose logging

    Returns:
        Platform ID

    Raises:
        SystemExit: If platform cannot be resolved
    """
    # Check if it's already an integer ID
    try:
        return int(platform_query)
    except ValueError:
        pass

    # Fetch platform mapping
    if verbose:
        logger.info("Fetching platform list from RAWG API...")

    platform_map = fetch_platform_mapping(api_key)

    # Try to find the platform
    platform_query_lower = platform_query.lower()

    if platform_query_lower in platform_map:
        platform_id = platform_map[platform_query_lower]
        if verbose:
            logger.info(f"Resolved platform '{platform_query}' to ID: {platform_id}")
        return platform_id

    # Platform not found
    logger.error(f"Platform '{platform_query}' not found")
    logger.error(f"Available platforms: {', '.join(sorted(set(platform_map.keys())))}")
    sys.exit(1)


def create_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser for RAWG games command."""
    parser = argparse.ArgumentParser(
        prog="top_games_list",
        description="Fetch games from RAWG API sorted by Metacritic score",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch games for PlayStation 2
  top_games_list --api-key YOUR_API_KEY --platform "playstation2"

  # Fetch games for PC with custom page size
  top_games_list --api-key YOUR_API_KEY --platform "pc" --page-size 50

  # Fetch games and limit results
  top_games_list --api-key YOUR_API_KEY --platform "xbox" --limit 10
        """,
    )

    parser.add_argument(
        "--api-key",
        type=str,
        required=True,
        help="RAWG API key (get one from https://rawg.io/apidocs)",
    )

    parser.add_argument(
        "--platform",
        type=str,
        required=True,
        help='Platform name, slug, or ID (e.g., "PlayStation 2", "playstation2", "pc", "xbox", or numeric ID)',
    )

    parser.add_argument(
        "--page-size",
        type=int,
        default=40,
        help="Number of results per page (default: 40)",
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of games to fetch (default: all results)",
    )

    parser.add_argument(
        "--min-metacritic",
        type=int,
        default=None,
        help="Minimum Metacritic score filter (e.g., 80)",
    )

    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    return parser


def fetch_games(
    api_key: str,
    platform: str,
    page_size: int = 40,
    limit: Optional[int] = None,
    min_metacritic: Optional[int] = None,
    verbose: bool = False,
) -> List[Dict]:
    """
    Fetch games from RAWG API sorted by Metacritic score (descending).

    Args:
        api_key: RAWG API key
        platform: Platform name or ID
        page_size: Number of results per page
        limit: Maximum number of games to fetch
        min_metacritic: Minimum Metacritic score filter
        verbose: Enable verbose logging

    Returns:
        List of game dictionaries
    """
    games = []
    page = 1
    total_fetched = 0

    while True:
        # Build query parameters
        params = {
            "key": api_key,
            "platforms": platform,
            "ordering": "-metacritic",
            "page": page,
            "page_size": page_size,
        }

        # Add metacritic filter if specified
        if min_metacritic:
            params["metacritic"] = f"{min_metacritic},100"

        # Make request
        url = urljoin(RAWG_BASE_URL, "/api/games")

        if verbose:
            logger.info(f"Fetching page {page}...")

        try:
            response = requests.get(url, params=params)
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching data from RAWG API: {e}")
            sys.exit(1)
        except ValueError as e:
            logger.error(f"Error parsing JSON response: {e}")
            sys.exit(1)

        # Extract results
        results = data.get("results", [])

        if not results:
            break

        for game in results:
            games.append(game)
            total_fetched += 1

            if limit and total_fetched >= limit:
                return games

        # Check if there's a next page
        if not data.get("next"):
            break

        page += 1

    return games


def format_game_as_csv_row(game: Dict) -> str:
    """
    Format game information as a CSV row.

    Args:
        game: Game dictionary from API

    Returns:
        CSV formatted string
    """
    output = StringIO()
    writer = csv.writer(output)

    name = game.get("name", "")
    metacritic = game.get("metacritic", "")
    released = game.get("released", "")

    writer.writerow([name, metacritic, released])
    return output.getvalue().strip()


def main():
    """Main entry point for the RAWG games command."""
    parser = create_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Resolve platform to ID
    platform_id = resolve_platform_id(
        platform_query=args.platform, api_key=args.api_key, verbose=args.verbose
    )

    logger.info(f"Fetching games for platform: {args.platform} (ID: {platform_id})")
    logger.info(f"Ordering by Metacritic score (descending)")

    if args.min_metacritic:
        logger.info(f"Filtering for Metacritic >= {args.min_metacritic}")

    # Fetch games
    games = fetch_games(
        api_key=args.api_key,
        platform=str(platform_id),
        page_size=args.page_size,
        limit=args.limit,
        min_metacritic=args.min_metacritic,
        verbose=args.verbose,
    )

    if not games:
        logger.warning("No games found matching the criteria")
        return 0

    logger.info(f"\nFound {len(games)} games\n")

    # Print CSV header
    print("title,metacritic_score,release_date")

    # Display games as CSV rows
    for game in games:
        print(format_game_as_csv_row(game))

    logger.info(f"\nTotal games: {len(games)}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
