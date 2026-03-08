"""MAME ROM organizer module for curateur.

This module provides functionality to organize MAME ROM sets, parse local metadata
sources (MAME XML, INI files, history.xml), extract and organize media files, and
generate ES-DE compatible gamelist.xml files.
"""

from .history_parser import HistoryParser
from .ini_parser import INIParser
from .mame_gamelist_generator import MAMEGamelistGenerator
from .mame_media_organizer import MAMEMediaOrganizer
from .mame_metadata_builder import MAMEMetadataBuilder
from .mame_rom_copier import MAMEROMCopier
from .mame_xml_parser import MAMEMachine, MAMEXMLParser
from .media_extractor import MediaExtractor

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
