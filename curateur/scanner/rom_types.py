"""ROM type definitions and data structures."""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List
from enum import Enum


class ROMType(Enum):
    """Types of ROM entries that can be scanned."""
    STANDARD = "standard"           # Regular ROM file (zip, nes, bin, etc.)
    M3U_PLAYLIST = "m3u_playlist"   # M3U playlist file
    DISC_SUBDIR = "disc_subdir"     # Disc subdirectory


@dataclass
class ROMInfo:
    """
    Information about a scanned ROM file.
    
    This is the primary data structure passed through the scraping pipeline.
    """
    # File identification
    path: Path                      # Absolute path to ROM file/directory
    filename: str                   # Filename (for gamelist.xml <path>)
    basename: str                   # Basename for media files (without extension)
    rom_type: ROMType               # Type of ROM entry
    system: str                     # System short name (e.g., 'nes', 'psx')
    
    # Identification data for API queries
    query_filename: str             # Filename to send to API
    file_size: int                  # File size in bytes
    crc32: Optional[str] = None     # CRC32 hash (uppercase hex, or None if skipped)
    
    # M3U-specific data
    disc_files: Optional[List[Path]] = None  # List of disc files in M3U
    
    # Disc subdirectory-specific data
    contained_file: Optional[Path] = None    # File inside disc subdir
    
    def get_media_basename(self) -> str:
        """
        Get the basename to use for media files.
        
        Returns:
            Basename without directory path, suitable for media filenames
        """
        return self.basename
    
    def get_gamelist_path(self) -> str:
        """
        Get the path to use in gamelist.xml <path> element.
        
        Returns:
            Relative path string for gamelist.xml
        """
        return f"./{self.filename}"
