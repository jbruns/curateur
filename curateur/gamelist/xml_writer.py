"""
XML writer for ES-DE gamelist.xml files.

Generates properly formatted gamelist.xml with provider info and game entries.
"""

from pathlib import Path
from typing import List
from copy import deepcopy
from lxml import etree
from .game_entry import GameEntry, GamelistMetadata


class GamelistWriter:
    """
    Writes ES-DE gamelist.xml files.
    
    Features:
    - Proper XML structure with provider metadata
    - HTML entity handling (lxml auto-escapes)
    - Pretty-printed output
    - UTF-8 encoding
    """
    
    def __init__(self, metadata: GamelistMetadata):
        """
        Initialize gamelist writer.
        
        Args:
            metadata: Provider metadata for the gamelist
        """
        self.metadata = metadata
    
    def write_gamelist(
        self,
        game_entries: List[GameEntry],
        output_path: Path
    ) -> None:
        """
        Write gamelist.xml file.
        
        Args:
            game_entries: List of GameEntry objects
            output_path: Path to output gamelist.xml file
        """
        # Create root element
        root = etree.Element("gameList")
        
        # Add provider section
        provider = self._create_provider_element()
        root.append(provider)
        
        # Add game entries
        for entry in game_entries:
            game_elem = self._create_game_element(entry)
            root.append(game_elem)
        
        # Write to file
        tree = etree.ElementTree(root)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        tree.write(
            str(output_path),
            encoding='utf-8',
            xml_declaration=True,
            pretty_print=True
        )
    
    def _create_provider_element(self) -> etree.Element:
        """
        Create provider metadata element.
        
        Returns:
            <provider> element with metadata
        """
        provider = etree.Element("provider")
        
        # Add child elements
        system_elem = etree.SubElement(provider, "System")
        system_elem.text = self.metadata.system
        
        software_elem = etree.SubElement(provider, "software")
        software_elem.text = self.metadata.software
        
        database_elem = etree.SubElement(provider, "database")
        database_elem.text = self.metadata.database
        
        web_elem = etree.SubElement(provider, "web")
        web_elem.text = self.metadata.web
        
        return provider
    
    def _create_game_element(self, entry: GameEntry) -> etree.Element:
        """
        Create game element from GameEntry.
        
        Args:
            entry: GameEntry object
            
        Returns:
            <game> element with all metadata
        """
        game = etree.Element("game")
        
        # Add attributes
        if entry.screenscraper_id:
            game.set("id", entry.screenscraper_id)
            game.set("source", "ScreenScraper.fr")
        
        # Add required fields
        self._add_element(game, "path", entry.path)
        self._add_element(game, "name", entry.name)
        
        # Add optional metadata fields
        if entry.desc:
            self._add_element(game, "desc", entry.desc)
        
        if entry.rating is not None:
            # Format rating without trailing zeros (0.9 instead of 0.900000)
            rating_str = f"{entry.rating:.6f}".rstrip('0').rstrip('.')
            self._add_element(game, "rating", rating_str)
        
        if entry.releasedate:
            self._add_element(game, "releasedate", entry.releasedate)
        
        if entry.developer:
            self._add_element(game, "developer", entry.developer)
        
        if entry.publisher:
            self._add_element(game, "publisher", entry.publisher)
        
        if entry.genre:
            self._add_element(game, "genre", entry.genre)
        
        if entry.players:
            self._add_element(game, "players", entry.players)
        
        # Add user-editable fields
        if entry.favorite:
            self._add_element(game, "favorite", "true")
        
        if entry.playcount is not None:
            self._add_element(game, "playcount", str(entry.playcount))
        
        if entry.lastplayed:
            self._add_element(game, "lastplayed", entry.lastplayed)
        
        if entry.hidden:
            self._add_element(game, "hidden", "true")
        
        # Add extra fields (unknown fields preserved from existing gamelist)
        for tag, value in sorted(entry.extra_fields.items(), key=lambda item: item[0]):
            if isinstance(value, etree._Element):
                game.append(deepcopy(value))
            elif value is not None:
                self._add_element(game, tag, str(value))
        
        return game
    
    def _add_element(
        self,
        parent: etree.Element,
        tag: str,
        text: str
    ) -> None:
        """
        Add a child element with text content.
        
        Args:
            parent: Parent element
            tag: Element tag name
            text: Text content (will be XML-escaped by lxml)
        """
        elem = etree.SubElement(parent, tag)
        elem.text = text
    
    def validate_output(self, output_path: Path) -> bool:
        """
        Validate that output XML is well-formed.
        
        Args:
            output_path: Path to gamelist.xml file
            
        Returns:
            True if valid, False otherwise
        """
        try:
            tree = etree.parse(str(output_path))
            root = tree.getroot()
            
            # Check root element
            if root.tag != "gameList":
                return False
            
            # Check for provider section
            provider = root.find("provider")
            if provider is None:
                return False
            
            return True
            
        except Exception:
            return False
