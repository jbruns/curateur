"""
Gamelist XML parser and merger.

Parses existing gamelist.xml files and merges with new scraped data,
preserving user edits.
"""

from copy import deepcopy
from pathlib import Path
from typing import List, Dict, Optional
from lxml import etree
from .game_entry import GameEntry


class GamelistParser:
    """
    Parses ES-DE gamelist.xml files.
    
    Extracts game entries while preserving user-editable fields.
    """
    
    def parse_gamelist(self, gamelist_path: Path) -> List[GameEntry]:
        """
        Parse gamelist.xml file.
        
        Args:
            gamelist_path: Path to gamelist.xml file
            
        Returns:
            List of GameEntry objects
            
        Raises:
            FileNotFoundError: If gamelist file doesn't exist
            etree.XMLSyntaxError: If XML is malformed
        """
        if not gamelist_path.exists():
            raise FileNotFoundError(f"Gamelist not found: {gamelist_path}")
        
        tree = etree.parse(str(gamelist_path))
        root = tree.getroot()
        
        entries = []
        for game_elem in root.findall("game"):
            entry = self._parse_game_element(game_elem)
            if entry:
                entries.append(entry)
        
        return entries
    
    def _parse_game_element(self, game_elem: etree.Element) -> Optional[GameEntry]:
        """
        Parse a single <game> element.
        
        Args:
            game_elem: <game> XML element
            
        Returns:
            GameEntry object or None if invalid
        """
        # Extract path (required)
        path = self._get_text(game_elem, "path")
        if not path:
            return None
        
        # Extract name (required)
        name = self._get_text(game_elem, "name")
        if not name:
            return None
        
        # Create entry with basic fields
        entry = GameEntry(
            path=path,
            name=name,
            screenscraper_id=game_elem.get("id"),
            desc=self._get_text(game_elem, "desc"),
            rating=self._get_float(game_elem, "rating"),
            releasedate=self._get_text(game_elem, "releasedate"),
            developer=self._get_text(game_elem, "developer"),
            publisher=self._get_text(game_elem, "publisher"),
            genre=self._get_text(game_elem, "genre"),
            players=self._get_text(game_elem, "players"),
            image=self._get_text(game_elem, "image"),
            thumbnail=self._get_text(game_elem, "thumbnail"),
            marquee=self._get_text(game_elem, "marquee"),
            video=self._get_text(game_elem, "video"),
            favorite=self._get_bool(game_elem, "favorite"),
            playcount=self._get_int(game_elem, "playcount"),
            lastplayed=self._get_text(game_elem, "lastplayed"),
            hidden=self._get_bool(game_elem, "hidden"),
            extra_fields=self._get_extra_fields(game_elem)
        )
        
        return entry
    
    def _get_text(self, element: etree.Element, tag: str) -> Optional[str]:
        """Get text content of child element."""
        child = element.find(tag)
        return child.text if child is not None and child.text else None
    
    def _get_float(self, element: etree.Element, tag: str) -> Optional[float]:
        """Get float value of child element."""
        text = self._get_text(element, tag)
        if text:
            try:
                return float(text)
            except ValueError:
                return None
        return None
    
    def _get_int(self, element: etree.Element, tag: str) -> Optional[int]:
        """Get integer value of child element."""
        text = self._get_text(element, tag)
        if text:
            try:
                return int(text)
            except ValueError:
                return None
        return None
    
    def _get_bool(self, element: etree.Element, tag: str) -> bool:
        """Get boolean value of child element."""
        text = self._get_text(element, tag)
        return text and text.lower() == "true"
    
    def _get_extra_fields(self, element: etree.Element) -> dict:
        """Extract unknown XML fields not managed by curateur."""
        # Fields that curateur actively manages and updates
        managed_fields = {
            'path', 'name', 'desc', 'rating', 'releasedate',
            'developer', 'publisher', 'genre', 'players'
        }
        
        # User-editable fields that curateur reads and preserves but doesn't write
        # (handled explicitly in code, not as extra_fields)
        user_fields = {
            'favorite', 'lastplayed', 'hidden', 'playcount'
        }
        
        # Media paths (tracked internally, not written to XML)
        media_fields = {
            'image', 'thumbnail', 'marquee', 'video'
        }
        
        # Combine all known fields
        known_fields = managed_fields | user_fields | media_fields
        
        extra = {}
        for child in element:
            if child.tag in known_fields:
                continue
            
            if len(child) > 0 or child.attrib:
                # Preserve full element (attributes/children) for unknown structured fields
                extra[child.tag] = deepcopy(child)
            elif child.text:
                extra[child.tag] = child.text
            else:
                # Empty element without text/children - keep structure
                extra[child.tag] = deepcopy(child)
        
        return extra


class GamelistMerger:
    """
    Merges new scraped data with existing gamelist entries.

    Preserves user-editable fields while updating scraped metadata.
    """

    # User-editable fields that should be preserved from existing gamelist
    # Note: playcount is preserved but not written to new gamelist (user-managed only)
    USER_FIELDS = {
        'favorite',
        'playcount',
        'lastplayed',
        'hidden'
    }

    def __init__(
        self,
        merge_strategy: str = 'preserve_user_edits',
        auto_favorite_enabled: bool = False,
        auto_favorite_threshold: float = 0.9
    ):
        """
        Initialize gamelist merger.

        Args:
            merge_strategy: Merge strategy ('preserve_user_edits', 'refresh_metadata', 'reset_all')
            auto_favorite_enabled: Enable automatic favorite flag for highly-rated games
            auto_favorite_threshold: Rating threshold (0.0-1.0) for auto-favorite

        Note:
            Auto-favorite only applies in 'refresh_metadata' and 'reset_all' modes.
            In 'preserve_user_edits' mode, favorite field is never modified.
        """
        self.merge_strategy = merge_strategy
        self.auto_favorite_enabled = auto_favorite_enabled
        self.auto_favorite_threshold = auto_favorite_threshold
    
    def merge_entries(
        self,
        existing_entries: List[GameEntry],
        new_entries: List[GameEntry]
    ) -> List[GameEntry]:
        """
        Merge new entries with existing entries.

        Args:
            existing_entries: Entries from existing gamelist.xml
            new_entries: Newly scraped entries

        Returns:
            Merged list of GameEntry objects

        Logic:
        - For ROMs in both lists: Update metadata, preserve user fields
        - For ROMs only in new list: Add as new entries
        - For ROMs only in existing list: Keep (user may have manual entries)
        """
        from logging import getLogger
        logger = getLogger(__name__)

        logger.debug(
            f"GamelistMerger: strategy={self.merge_strategy}, "
            f"auto_favorite_enabled={self.auto_favorite_enabled}, threshold={self.auto_favorite_threshold}"
        )

        # Build lookup by path
        existing_by_path = {entry.path: entry for entry in existing_entries}
        new_by_path = {entry.path: entry for entry in new_entries}

        merged = []
        processed_paths = set()

        # Check if auto-favorite is allowed for this strategy
        auto_favorite_allowed = self.merge_strategy != 'preserve_user_edits'

        # Process new entries (update or add)
        for path, new_entry in new_by_path.items():
            if path in existing_by_path:
                # Merge: update metadata, preserve user fields
                merged_entry = self._merge_single_entry(
                    existing_by_path[path],
                    new_entry
                )
                merged.append(merged_entry)
            else:
                # New entry - apply auto-favorite if enabled and strategy allows
                if auto_favorite_allowed and self.auto_favorite_enabled and new_entry.rating is not None:
                    if new_entry.rating >= self.auto_favorite_threshold:
                        logger.debug(f"Auto-favoriting new entry: {new_entry.name} (rating={new_entry.rating})")
                        new_entry.favorite = True
                    else:
                        logger.debug(f"Not auto-favoriting {new_entry.name}: rating {new_entry.rating} < threshold {self.auto_favorite_threshold}")
                else:
                    if not auto_favorite_allowed:
                        logger.debug(f"Skipping auto-favorite for {new_entry.name}: strategy={self.merge_strategy} does not allow")
                    else:
                        logger.debug(f"Skipping auto-favorite for {new_entry.name}: enabled={self.auto_favorite_enabled}, rating={new_entry.rating}")
                merged.append(new_entry)

            processed_paths.add(path)
        
        # Preserve existing entries not in new list
        for path, existing_entry in existing_by_path.items():
            if path not in processed_paths:
                merged.append(existing_entry)
        
        return merged
    
    def _merge_single_entry(
        self,
        existing: GameEntry,
        new: GameEntry
    ) -> GameEntry:
        """
        Merge a single entry, preserving user fields.

        Args:
            existing: Existing entry with user data
            new: New entry with fresh scraped data

        Returns:
            Merged GameEntry
        """
        from logging import getLogger
        logger = getLogger(__name__)

        # Determine favorite flag: preserve existing, or apply auto-favorite if strategy allows
        favorite = existing.favorite
        auto_favorite_allowed = self.merge_strategy != 'preserve_user_edits'

        if auto_favorite_allowed and self.auto_favorite_enabled and new.rating is not None:
            if new.rating >= self.auto_favorite_threshold and not existing.favorite:
                logger.debug(f"Auto-favoriting existing entry: {new.name} (rating={new.rating})")
                favorite = True

        # Start with new entry (fresh metadata)
        merged = GameEntry(
            path=new.path,
            name=new.name,
            screenscraper_id=new.screenscraper_id,
            desc=new.desc,
            rating=new.rating,
            releasedate=new.releasedate,
            developer=new.developer,
            publisher=new.publisher,
            genre=new.genre,
            players=new.players,
            image=new.image,
            thumbnail=new.thumbnail,
            marquee=new.marquee,
            video=new.video,
            # Preserve user-editable fields from existing (with auto-favorite override)
            favorite=favorite,
            playcount=existing.playcount,
            lastplayed=existing.lastplayed,
            hidden=existing.hidden,
            # Preserve unknown fields from existing
            extra_fields=deepcopy(existing.extra_fields)
        )

        return merged
