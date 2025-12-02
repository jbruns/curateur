"""Parser for MAME INI files (bestgames.ini, genre.ini, multiplayer.ini, etc.).

These INI files use a folder-based structure to categorize games.
"""

import logging
import re
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class INIParser:
    """Parser for MAME folder INI files."""

    def __init__(self, ini_path: Path):
        """Initialize parser with path to INI file.
        
        Args:
            ini_path: Path to INI file
        """
        self.ini_path = ini_path
        self.categories: Dict[str, List[str]] = {}

    def parse(self) -> Dict[str, List[str]]:
        """Parse INI file and return category mappings.
        
        Returns:
            Dictionary mapping category name to list of shortnames
            
        Raises:
            FileNotFoundError: If INI file doesn't exist
        """
        if not self.ini_path.exists():
            raise FileNotFoundError(f"INI file not found: {self.ini_path}")

        logger.info(f"Parsing INI file: {self.ini_path.name}")

        current_category = None
        shortnames_found = 0

        with open(self.ini_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith(';'):
                    continue
                
                # Check for category header [CategoryName]
                if line.startswith('[') and line.endswith(']'):
                    current_category = line[1:-1]
                    if current_category not in self.categories:
                        self.categories[current_category] = []
                    continue
                
                # If we're in a category, treat line as shortname
                if current_category:
                    # Skip special folder settings
                    if '=' in line:
                        continue
                    
                    # Add shortname (normalized to lowercase)
                    shortname = line.lower()
                    self.categories[current_category].append(shortname)
                    shortnames_found += 1

        logger.info(f"  - Found {len(self.categories)} categories")
        logger.info(f"  - Found {shortnames_found} game entries")

        return self.categories

    def get_categories_for_game(self, shortname: str) -> List[str]:
        """Get all categories that contain this game.
        
        Args:
            shortname: Game shortname
            
        Returns:
            List of category names
        """
        shortname = shortname.lower()
        return [
            category
            for category, games in self.categories.items()
            if shortname in games
        ]

    def get_games_in_category(self, category: str) -> List[str]:
        """Get all games in a specific category.
        
        Args:
            category: Category name
            
        Returns:
            List of game shortnames
        """
        return self.categories.get(category, [])


class BestGamesParser(INIParser):
    """Parser for bestgames.ini with rating extraction."""

    # Rating tier mappings (category name pattern -> rating value)
    # Patterns are ordered from highest to lowest to match correctly
    RATING_TIERS = {
        r'\b90\s+to\s+100\b': 0.95,
        r'\b80\s+to\s+90\b': 0.85,
        r'\b70\s+to\s+80\b': 0.75,
        r'\b60\s+to\s+70\b': 0.65,
        r'\b50\s+to\s+60\b': 0.55,
        r'\b40\s+to\s+50\b': 0.45,
        r'\b30\s+to\s+40\b': 0.35,
        r'\b20\s+to\s+30\b': 0.25,
        r'\b10\s+to\s+20\b': 0.15,
        r'\b0\s+to\s+10\b': 0.05,
    }

    def get_rating(self, shortname: str) -> Optional[float]:
        """Get rating for a game based on its category.
        
        Args:
            shortname: Game shortname
            
        Returns:
            Rating as float 0.0-1.0, or None if not found
        """
        categories = self.get_categories_for_game(shortname)
        
        for category in categories:
            # Try to match category name to rating tier
            for pattern, rating in self.RATING_TIERS.items():
                if re.search(pattern, category, re.IGNORECASE):
                    return rating
        
        return None

    def get_ratings_map(self) -> Dict[str, float]:
        """Get ratings for all games in the INI file.
        
        Returns:
            Dictionary mapping shortname to rating
        """
        ratings = {}
        
        for category, games in self.categories.items():
            # Find rating for this category
            rating = None
            for pattern, rating_value in self.RATING_TIERS.items():
                if re.search(pattern, category, re.IGNORECASE):
                    rating = rating_value
                    break
            
            # Assign rating to all games in category
            if rating is not None:
                for game in games:
                    ratings[game] = rating
        
        return ratings


class GenreParser(INIParser):
    """Parser for genre.ini."""

    def get_genre(self, shortname: str) -> Optional[str]:
        """Get genre for a game.
        
        Args:
            shortname: Game shortname
            
        Returns:
            Genre string or None if not found
        """
        categories = self.get_categories_for_game(shortname)
        
        # Filter out special categories
        ignore_categories = {'ROOT_FOLDER', 'FOLDER_SETTINGS'}
        genres = [c for c in categories if c not in ignore_categories]
        
        # Return first genre found
        return genres[0] if genres else None


class MultiplayerParser(INIParser):
    """Parser for multiplayer.ini with player count extraction."""

    def get_players(self, shortname: str) -> Optional[str]:
        """Get player count for a game.
        
        Args:
            shortname: Game shortname
            
        Returns:
            Player count as integer string (e.g., "1", "2", "4") or None if not found
        """
        categories = self.get_categories_for_game(shortname)
        
        # Extract player count from category name
        # For alternating/simultaneous patterns like "[8P alt / 2P sim]", prefer simultaneous count
        for category in categories:
            # Check for "XP sim" pattern (simultaneous play)
            sim_match = re.search(r'(\d+)P\s+sim', category, re.IGNORECASE)
            if sim_match:
                return sim_match.group(1)
            
            # Check for "XP alt" pattern (alternating play)
            alt_match = re.search(r'(\d+)P\s+alt', category, re.IGNORECASE)
            if alt_match:
                return alt_match.group(1)
            
            # Check for simple "XP" pattern
            simple_match = re.search(r'(\d+)P(?!\s+(?:sim|alt))', category, re.IGNORECASE)
            if simple_match:
                return simple_match.group(1)
        
        return None


class GameOrNoGameParser(INIParser):
    """Parser for Game or No Game.ini to filter actual games."""

    def get_games(self) -> Set[str]:
        """Get set of all shortnames in the [Game] category.
        
        Returns:
            Set of game shortnames
        """
        games = self.get_games_in_category('Game')
        return set(games)

    def is_game(self, shortname: str) -> bool:
        """Check if shortname is in the [Game] category.
        
        Args:
            shortname: Game shortname
            
        Returns:
            True if in [Game] category, False otherwise
        """
        games = self.get_games()
        return shortname.lower() in games
