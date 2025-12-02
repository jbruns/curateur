"""MAME ROM organizer module for curateur.

This module provides functionality to organize MAME ROM sets, parse local metadata
sources (MAME XML, INI files, history.xml), extract and organize media files, and
generate ES-DE compatible gamelist.xml files.
"""

from .mame_xml_parser import MAMEXMLParser, MAMEMachine
from .ini_parser import INIParser
from .history_parser import HistoryParser
from .media_extractor import MediaExtractor
from .mame_metadata_builder import MAMEMetadataBuilder
from .mame_rom_copier import MAMEROMCopier
from .mame_media_organizer import MAMEMediaOrganizer
from .mame_gamelist_generator import MAMEGamelistGenerator

__all__ = [
    "MAMEXMLParser",
    "MAMEMachine",
    "INIParser",
    "HistoryParser",
    "MediaExtractor",
    "MAMEMetadataBuilder",
    "MAMEROMCopier",
    "MAMEMediaOrganizer",
    "MAMEGamelistGenerator",
]
