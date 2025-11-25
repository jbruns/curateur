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
            rom_path: Absolute path to ROM file/directory (Path or str)
            
        Returns:
            Relative path string (e.g., "./Game.zip")
        """
        # Convert to Path if string
        rom_path = Path(rom_path)
        
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

    def to_absolute_rom_path(self, rom_path: str) -> Path:
        """
        Convert a relative ROM path (from gamelist) to an absolute path.
        
        Args:
            rom_path: Relative ROM path (e.g., './Game.zip') or absolute path
        
        Returns:
            Absolute Path to the ROM
        """
        path_obj = Path(rom_path)
        if path_obj.is_absolute():
            return path_obj
        return self.resolve_rom_path(rom_path)
    
    def get_media_basename(self, rom_path: Path) -> str:
        """
        Get basename for media file from ROM path.
        
        Handles:
        - Standard ROMs: Remove extension
        - M3U playlists: Use m3u filename without extension
        - Disc subdirectories: Use parent directory name
        
        Args:
            rom_path: Path to ROM file
            
        Returns:
            Basename for media file naming
        """
        rom_path = Path(rom_path)
        
        # If it's a directory (disc subdirectory), use directory name
        if rom_path.is_dir():
            return rom_path.name
        
        # If it's an M3U file, use its name without extension
        if rom_path.suffix.lower() == '.m3u':
            return rom_path.stem
        
        # For disc files in subdirectories, use the parent directory name
        parent_name = rom_path.parent.name
        if 'disc' in parent_name.lower() or 'disk' in parent_name.lower():
            return parent_name
        
        # Standard ROM: use filename without extension
        return rom_path.stem
    
    def calculate_media_path_from_gamelist(
        self,
        media_path: Path,
        rom_relative_path: str = None,
        media_type: str = None
    ) -> str:
        """
        Calculate relative path from gamelist directory to media file.
        
        Can be called two ways:
        1. With media_path only - returns relative path to that media file
        2. With rom_relative_path and media_type - calculates expected media path
        
        Args:
            media_path: Absolute path to media file (or rom_relative_path if using mode 2)
            rom_relative_path: (Optional) Relative ROM path from gamelist
            media_type: (Optional) Media type ('covers', 'screenshots', etc.)
            
        Returns:
            Relative path string from gamelist to media file
        """
        # Mode 2: Calculate expected media path from ROM path
        if rom_relative_path is not None and media_type is not None:
            # media_path is actually rom_relative_path in this case
            rom_abs = self.to_absolute_rom_path(str(media_path))
            basename = self.get_media_basename(rom_abs)
            
            # Determine file extension based on media type
            if media_type == 'videos':
                ext = '.mp4'
            else:
                ext = '.png'
            
            # Construct media path
            media_abs = self.media_directory / media_type / f"{basename}{ext}"
        else:
            # Mode 1: Convert provided media path to relative
            media_abs = Path(media_path)
        
        # Calculate relative path from gamelist to media
        return self.get_relative_media_path(media_abs)
