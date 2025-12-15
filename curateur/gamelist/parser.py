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
            extra_fields=self._get_extra_fields(game_elem),
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
            "path",
            "name",
            "desc",
            "rating",
            "releasedate",
            "developer",
            "publisher",
            "genre",
            "players",
        }

        # User-editable fields that curateur reads and preserves but doesn't write
        # (handled explicitly in code, not as extra_fields)
        user_fields = {"favorite", "lastplayed", "hidden", "playcount"}

        # Media paths (tracked internally, not written to XML)
        media_fields = {"image", "thumbnail", "marquee", "video"}

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
