"""
Media file organization and path management.

Handles organizing downloaded media in ES-DE directory structure and
managing file naming conventions.
"""

import os
from pathlib import Path
from typing import Optional
from .media_types import get_directory_for_media_type


class MediaOrganizer:
    """
    Organizes media files in ES-DE directory structure.

    Directory structure:
        <media_root>/<system>/<media_type>/<basename>.<ext>

    Examples:
        - covers: downloaded_media/nes/covers/Super Mario Bros.jpg
        - screenshots: downloaded_media/nes/screenshots/Zelda.png
        - titlescreens: downloaded_media/snes/titlescreens/F-Zero.jpg
    """

    def __init__(self, media_root: Path):
        """
        Initialize media organizer.

        Args:
            media_root: Root directory for media storage
                       (e.g., Path('downloaded_media'))
        """
        self.media_root = Path(media_root)

    def get_media_path(
        self, system: str, media_type: str, rom_basename: str, extension: str
    ) -> Path:
        """
        Get the full path for a media file.

        Args:
            system: System name (e.g., 'nes', 'snes')
            media_type: ScreenScraper media type (e.g., 'box-2D', 'ss')
            rom_basename: ROM filename without extension
            extension: Media file extension (e.g., 'jpg', 'png')

        Returns:
            Full path for media file

        Example:
            >>> organizer.get_media_path('nes', 'box-2D', 'Super Mario Bros', 'jpg')
            Path('downloaded_media/nes/covers/Super Mario Bros.jpg')
        """
        # Get ES-DE directory name for media type
        media_dir = get_directory_for_media_type(media_type)

        # Build path: <root>/<system>/<media_dir>/<basename>.<ext>
        return self.media_root / system / media_dir / f"{rom_basename}.{extension}"

    def get_rom_basename(self, rom_path: str) -> str:
        """
        Extract basename from ROM path for media naming.

        Handles special cases:
        - M3U playlists: Use M3U filename (not disc 1)
        - Disc subdirectories: Use directory name including extension (e.g., "Armada (USA).cue")
        - Standard ROMs: Use filename without extension

        Args:
            rom_path: Path to ROM file or directory

        Returns:
            Basename for media file naming

        Examples:
            - "Skies of Aleria.m3u" -> "Skies of Aleria"
            - "Armada (USA).cue/" (directory) -> "Armada (USA).cue"
            - "Star Quest.zip" -> "Star Quest"
        """
        path = Path(rom_path)
        name = path.name

        # For disc subdirectories (directories with extensions like .cue, .gdi),
        # keep the full name including extension
        if path.is_dir() and "." in name:
            return name

        # For files inside disc subdirectories, use the parent directory name
        # Disc subdirectory structure:
        #   Game.cue/          <- parent directory (has extension in name)
        #   └── Game.cue       <- file with same name as parent
        parent = path.parent
        parent_name = parent.name

        # Check if parent is a disc subdirectory:
        # 1. Parent has an extension in its name (e.g., "Game.cue")
        # 2. File has the same name as its parent directory
        if parent.is_dir() and "." in parent_name and path.name == parent_name:
            return parent_name

        # For regular files, remove the extension
        if "." in name:
            return os.path.splitext(name)[0]

        return name

    def ensure_directory_exists(self, file_path: Path) -> None:
        """
        Ensure parent directory exists for a file path.

        Args:
            file_path: Path to file (directory will be created)
        """
        file_path.parent.mkdir(parents=True, exist_ok=True)

    def get_all_media_paths(
        self, system: str, rom_basename: str, media_types: list[str]
    ) -> dict[str, Path]:
        """
        Get paths for all media types for a ROM.

        Args:
            system: System name
            rom_basename: ROM basename
            media_types: List of media types to get paths for

        Returns:
            Dict mapping media type to path

        Example:
            >>> organizer.get_all_media_paths('nes', 'Mario', ['box-2D', 'ss'])
            {
                'box-2D': Path('downloaded_media/nes/covers/Mario.jpg'),
                'ss': Path('downloaded_media/nes/screenshots/Mario.png')
            }
        """
        paths = {}

        for media_type in media_types:
            # Use jpg as default extension (will be updated when downloaded)
            path = self.get_media_path(system, media_type, rom_basename, "jpg")
            paths[media_type] = path

        return paths

    def file_exists(self, file_path: Path) -> bool:
        """
        Check if a media file exists.

        Args:
            file_path: Path to check

        Returns:
            True if file exists, False otherwise
        """
        return file_path.exists() and file_path.is_file()

    def get_relative_path(self, file_path: Path, base_path: Path) -> str:
        """
        Get relative path from base to file.

        Used for gamelist.xml path generation.

        Args:
            file_path: Absolute file path
            base_path: Base directory path

        Returns:
            Relative path string (e.g., "./covers/game.jpg")
        """
        try:
            rel = file_path.relative_to(base_path)
            return f"./{rel.as_posix()}"
        except ValueError:
            # Not relative - return absolute path
            return str(file_path)
