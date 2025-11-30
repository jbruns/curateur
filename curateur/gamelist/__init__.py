"""
Gamelist generation package for curateur.

Handles parsing, merging, and writing ES-DE gamelist.xml files.
"""

from .game_entry import GameEntry, GamelistMetadata
from .xml_writer import GamelistWriter
from .parser import GamelistParser
from .metadata_merger import MetadataMerger
from .path_handler import PathHandler
from .generator import GamelistGenerator
from .backup import GamelistBackup

__all__ = [
    'GameEntry',
    'GamelistMetadata',
    'GamelistWriter',
    'GamelistParser',
    'MetadataMerger',
    'PathHandler',
    'GamelistGenerator',
    'GamelistBackup',
]
