"""
Path handling for gamelist generation.

Manages conversion between absolute and relative paths for ROMs and media.
"""

import os
from pathlib import Path
from typing import Optional


class PathHandler:
    """
    Handles path conversions for gamelist.xml.
    
    ES-DE expects:
    - ROM paths relative to gamelist directory (starts with ./)
    - Media paths relative to gamelist directory
    """
    
    def __init__(
        self,
        rom_directory: Path,
        media_directory: Path,
        gamelist_directory: Path
    ):
        """
        Initialize path handler.
        
        Args:
            rom_directory: Absolute path to ROM directory
            media_directory: Absolute path to media directory
            gamelist_directory: Absolute path to gamelist directory
        """
        self.rom_directory = Path(rom_directory).resolve()
        self.media_directory = Path(media_directory).resolve()
        self.gamelist_directory = Path(gamelist_directory).resolve()
    
    def get_relative_rom_path(self, rom_path: Path) -> str:
        """
        Convert absolute ROM path to relative path for gamelist.xml.
        
        Args:
            rom_path: Absolute path to ROM file/directory
            
        Returns:
            Relative path string (e.g., "./Game.zip")
        """
        try:
            # Get path relative to ROM directory
            rel_path = rom_path.relative_to(self.rom_directory)
            return f"./{rel_path.as_posix()}"
        except ValueError:
            # Not relative to ROM directory - use filename only
            return f"./{rom_path.name}"
    
    def get_relative_media_path(
        self,
        media_path: Path,
        from_directory: Optional[Path] = None
    ) -> str:
        """
        Convert absolute media path to relative path for gamelist.xml.
        
        Args:
            media_path: Absolute path to media file
            from_directory: Base directory for relative path
                          (defaults to gamelist_directory)
            
        Returns:
            Relative path string
        """
        base = from_directory or self.gamelist_directory
        
        try:
            # Get path relative to base directory
            rel_path = media_path.relative_to(base)
            return f"./{rel_path.as_posix()}"
        except ValueError:
            # Try relative to media directory
            try:
                rel_path = media_path.relative_to(self.media_directory)
                # Need to construct path from gamelist to media
                return self._get_path_from_gamelist_to_media(rel_path)
            except ValueError:
                # Can't make relative - use absolute
                return str(media_path)
    
    def _get_path_from_gamelist_to_media(self, media_rel_path: Path) -> str:
        """
        Get path from gamelist directory to media file.
        
        Args:
            media_rel_path: Path relative to media directory
            
        Returns:
            Relative path from gamelist to media file
        """
        # Calculate path from gamelist directory to media directory
        try:
            # Get common parent
            common = os.path.commonpath([
                self.gamelist_directory,
                self.media_directory
            ])
            common_path = Path(common)
            
            # Get parts from common to each directory
            gamelist_parts = self.gamelist_directory.relative_to(common_path).parts
            media_parts = self.media_directory.relative_to(common_path).parts
            
            # Build relative path
            # Go up from gamelist directory
            up_levels = ['..'] * len(gamelist_parts)
            # Then down to media directory
            down_path = list(media_parts) + list(media_rel_path.parts)
            
            full_path = up_levels + down_path
            return './' + '/'.join(full_path)
            
        except ValueError:
            # No common path - use absolute
            return str(self.media_directory / media_rel_path)
    
    def resolve_rom_path(self, relative_path: str) -> Path:
        """
        Convert relative ROM path from gamelist.xml to absolute path.
        
        Args:
            relative_path: Relative path from gamelist (e.g., "./Game.zip")
            
        Returns:
            Absolute path to ROM file
        """
        # Remove leading ./
        clean_path = relative_path.lstrip('./')
        return self.rom_directory / clean_path
    
    def normalize_path(self, path: str) -> str:
        """
        Normalize path separators to forward slashes.
        
        Args:
            path: Path string
            
        Returns:
            Normalized path with forward slashes
        """
        return path.replace('\\', '/')
    
    def get_rom_basename(self, rom_path: str) -> str:
        """
        Get basename from ROM path for media naming.
        
        Handles:
        - Standard ROMs: Remove extension
        - M3U playlists: Remove .m3u extension
        - Disc subdirectories: Keep full name with extension
        
        Args:
            rom_path: ROM path (can be relative or absolute)
            
        Returns:
            Basename for media file naming
        """
        # Get filename from path
        name = os.path.basename(rom_path.lstrip('./'))
        
        # Check if it's a disc subdirectory (has disc/disk in name)
        if 'disc' in name.lower() or 'disk' in name.lower():
            # Keep extension for disc subdirs
            return name
        
        # Remove extension for normal files
        if '.' in name:
            return os.path.splitext(name)[0]
        
        return name
