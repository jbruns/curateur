"""
Game data structures for gamelist generation.

Defines the data models for game entries and their components.
"""

import html
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
from datetime import datetime


@dataclass
class GameEntry:
    """
    Represents a game entry for gamelist.xml.
    
    All text fields are stored as decoded UTF-8 (HTML entities already decoded).
    lxml will handle XML escaping when writing.
    """
    # Required fields
    path: str  # Relative path to ROM (e.g., "./Game.zip")
    name: str  # Game name
    
    # ScreenScraper metadata
    screenscraper_id: Optional[str] = None
    
    # Optional metadata fields
    desc: Optional[str] = None
    rating: Optional[float] = None  # 0.0-1.0
    releasedate: Optional[str] = None  # YYYYMMDDTHHMMSS format
    developer: Optional[str] = None
    publisher: Optional[str] = None
    genre: Optional[str] = None
    players: Optional[str] = None
    
    # Media paths (relative to gamelist directory)
    image: Optional[str] = None  # Box art/cover
    thumbnail: Optional[str] = None  # Thumbnail
    marquee: Optional[str] = None
    video: Optional[str] = None
    
    # User-editable fields (preserved during merge)
    favorite: bool = False
    playcount: Optional[int] = None
    lastplayed: Optional[str] = None
    
    # Hidden field (not shown in UI)
    hidden: bool = False
    
    # Preserve unknown XML fields (sortname, kidgame, altemulator, etc.)
    extra_fields: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        """Decode HTML entities in text fields."""
        if self.name:
            self.name = html.unescape(self.name)
        if self.desc:
            self.desc = html.unescape(self.desc)
        if self.developer:
            self.developer = html.unescape(self.developer)
        if self.publisher:
            self.publisher = html.unescape(self.publisher)
        if self.genre:
            self.genre = html.unescape(self.genre)
    
    @classmethod
    def from_api_response(
        cls,
        game_info: Dict,
        rom_path: str,
        media_paths: Optional[Dict[str, str]] = None
    ) -> 'GameEntry':
        """
        Create GameEntry from ScreenScraper API response.
        
        Args:
            game_info: Parsed API response dict
            rom_path: Relative path to ROM file
            media_paths: Dict of media type to relative path
            
        Returns:
            GameEntry instance
        """
        # Extract preferred name (us region preferred)
        names = game_info.get('names', {})
        name = names.get('us') or names.get('wor') or names.get('eu') or list(names.values())[0] if names else 'Unknown'
        
        # Extract preferred description (use language codes, not region codes)
        descs = game_info.get('descriptions', {})
        desc = descs.get('en') or descs.get('fr') or descs.get('de') or descs.get('es') or None
        
        # Convert rating from ScreenScraper's 0-20 scale to ES-DE's 0-1 scale
        api_rating = game_info.get('rating')
        rating = float(api_rating) / 20.0 if api_rating is not None else None
        
        # Format release date
        release_dates = game_info.get('release_dates', {})
        release_date_str = release_dates.get('us') or release_dates.get('wor') or release_dates.get('eu') or None
        releasedate = cls._format_release_date(release_date_str) if release_date_str else None
        
        # Extract genres (hyphen-separated, no spaces)
        genres = game_info.get('genres', [])
        genre = '-'.join(genres) if genres else None
        
        # Media paths
        media_paths = media_paths or {}
        
        return cls(
            path=rom_path,
            name=name,
            screenscraper_id=str(game_info.get('id', '')),
            desc=desc,
            rating=rating,
            releasedate=releasedate,
            developer=game_info.get('developer'),
            publisher=game_info.get('publisher'),
            genre=genre,
            players=game_info.get('players'),
            image=media_paths.get('box-2D') or media_paths.get('cover'),
            thumbnail=media_paths.get('screenshot'),
            marquee=media_paths.get('screenmarquee'),
            video=media_paths.get('video')
        )
    
    @staticmethod
    def _format_release_date(date_str: str) -> str:
        """
        Format release date to ES-DE format (YYYYMMDDTHHMMSS).
        
        Args:
            date_str: Date string from API (YYYY-MM-DD or similar)
            
        Returns:
            Formatted date string
        """
        try:
            # Try parsing YYYY-MM-DD format
            if '-' in date_str:
                parts = date_str.split('-')
                year = parts[0]
                month = parts[1] if len(parts) > 1 else '01'
                day = parts[2] if len(parts) > 2 else '01'
                return f"{year}{month}{day}T000000"
            # Already in correct format or just a year
            elif len(date_str) == 4:  # Just year
                return f"{date_str}0101T000000"
            else:
                return date_str
        except Exception:
            return date_str


@dataclass
class GamelistMetadata:
    """Provider metadata for gamelist.xml."""
    system: str
    software: str = "curateur"
    database: str = "ScreenScraper.fr"
    web: str = "http://www.screenscraper.fr"
    
    def __post_init__(self):
        """Ensure system is set."""
        if not self.system:
            raise ValueError("System name is required")
