"""
Gamelist generation package for curateur.

Handles parsing, merging, and writing ES-DE gamelist.xml files.
"""

from .backup import GamelistBackup
from .game_entry import GameEntry, GamelistMetadata
from .generator import GamelistGenerator
from .metadata_merger import MetadataMerger
from .parser import GamelistParser
from .path_handler import PathHandler
from .xml_writer import GamelistWriter

__all__ = [
    "GameEntry",
    "GamelistMetadata",
    "GamelistWriter",
    "GamelistParser",
    "MetadataMerger",
    "PathHandler",
    "GamelistGenerator",
    "GamelistBackup",
]
