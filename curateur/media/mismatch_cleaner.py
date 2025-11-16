"""
Media Mismatch Cleaner

Removes media types that are not in the enabled media type list.
Opt-in cleanup functionality to maintain media directory hygiene.
"""

from pathlib import Path
from typing import Dict, List, Set
import logging
import shutil

logger = logging.getLogger(__name__)


class MismatchCleaner:
    """
    Removes media files for types not in enabled list
    
    Handles scenarios:
    - User disables a media type after previous scraping
    - Cleanup of legacy media from configuration changes
    - Media type rationalization
    
    Features:
    - Moves files to CLEANUP/ rather than deleting
    - Dry-run mode for preview
    - Interactive confirmation
    """
    
    def __init__(self, enabled_media_types: List[str], config: dict):
        """
        Initialize mismatch cleaner
        
        Args:
            enabled_media_types: List of currently enabled media types
            config: Configuration dictionary
        """
        self.enabled_types = set(enabled_media_types)
        self.config = config
        logger.info(f"Mismatch Cleaner initialized with types: {', '.join(enabled_media_types)}")
    
    def scan_for_mismatches(self, media_root: Path, system_name: str) -> Dict[str, List[Path]]:
        """
        Scan media directory for disabled media types
        
        Args:
            media_root: Root media directory
            system_name: System name (e.g., 'nes', 'psx')
        
        Returns:
            Dict mapping media type to list of files to remove
        """
        system_media_dir = media_root / system_name
        
        if not system_media_dir.exists():
            logger.debug(f"No media directory for {system_name}")
            return {}
        
        mismatches = {}
        
        # Check each subdirectory (media type)
        for media_type_dir in system_media_dir.iterdir():
            if not media_type_dir.is_dir():
                continue
            
            media_type = media_type_dir.name
            
            # Skip if this is an enabled type
            if media_type in self.enabled_types:
                continue
            
            # Skip special directories
            if media_type in ('CLEANUP', '.DS_Store'):
                continue
            
            # List all files in this disabled media type directory
            files = [f for f in media_type_dir.iterdir() if f.is_file()]
            
            if files:
                mismatches[media_type] = files
                logger.info(f"Found {len(files)} files for disabled type: {media_type}")
        
        return mismatches
    
    def prompt_cleanup(self, mismatches: Dict[str, List[Path]], system_name: str) -> bool:
        """
        Interactive prompt for cleanup confirmation
        
        Args:
            mismatches: Dict from scan_for_mismatches
            system_name: System name
        
        Returns:
            bool: True if user confirms cleanup
        """
        if not mismatches:
            return False
        
        total_files = sum(len(files) for files in mismatches.values())
        
        print("\n" + "=" * 70)
        print("Media Type Mismatch Detected")
        print("=" * 70)
        print(f"System: {system_name}")
        print(f"Enabled media types: {', '.join(sorted(self.enabled_types))}")
        print()
        print("Disabled media types found:")
        for media_type, files in sorted(mismatches.items()):
            print(f"  - {media_type}: {len(files)} files")
        print()
        print(f"Total files to clean: {total_files}")
        print()
        print("Actions if you proceed:")
        print(f"  - Move {total_files} files to CLEANUP/{system_name}/<media_type>/")
        print("  - Remove empty media type directories")
        print()
        
        while True:
            response = input("Proceed with cleanup? [y/N]: ").lower().strip()
            if response in ('y', 'yes'):
                logger.info(f"User confirmed cleanup for {system_name}")
                return True
            elif response in ('n', 'no', ''):
                logger.info(f"User declined cleanup for {system_name}")
                return False
            else:
                print("Please enter 'y' or 'n'")
    
    def execute_cleanup(self, mismatches: Dict[str, List[Path]], 
                       media_root: Path, system_name: str) -> int:
        """
        Execute cleanup by moving files to CLEANUP
        
        Args:
            mismatches: Dict from scan_for_mismatches
            media_root: Root media directory
            system_name: System name
        
        Returns:
            int: Number of files moved
        """
        cleanup_root = media_root / "CLEANUP" / system_name
        cleanup_root.mkdir(parents=True, exist_ok=True)
        
        moved_count = 0
        
        for media_type, files in mismatches.items():
            # Create cleanup subdirectory
            cleanup_subdir = cleanup_root / media_type
            cleanup_subdir.mkdir(parents=True, exist_ok=True)
            
            # Move each file
            for file_path in files:
                dest = cleanup_subdir / file_path.name
                try:
                    shutil.move(str(file_path), str(dest))
                    moved_count += 1
                    logger.debug(f"Moved: {file_path.name} -> CLEANUP/{system_name}/{media_type}/")
                except Exception as e:
                    logger.error(f"Failed to move {file_path}: {e}")
            
            # Remove empty source directory
            source_dir = file_path.parent if files else None
            if source_dir and source_dir.exists() and not any(source_dir.iterdir()):
                try:
                    source_dir.rmdir()
                    logger.debug(f"Removed empty directory: {source_dir}")
                except Exception as e:
                    logger.error(f"Failed to remove directory {source_dir}: {e}")
        
        logger.info(f"Cleanup complete: moved {moved_count} files to CLEANUP")
        return moved_count
    
    def cleanup_system(self, media_root: Path, system_name: str, 
                      interactive: bool = True) -> int:
        """
        Complete cleanup workflow for a system
        
        Args:
            media_root: Root media directory
            system_name: System name
            interactive: If True, prompt for confirmation
        
        Returns:
            int: Number of files moved
        """
        # Scan for mismatches
        mismatches = self.scan_for_mismatches(media_root, system_name)
        
        if not mismatches:
            logger.debug(f"No media type mismatches found for {system_name}")
            return 0
        
        # Get confirmation if interactive
        if interactive:
            if not self.prompt_cleanup(mismatches, system_name):
                return 0
        
        # Execute cleanup
        return self.execute_cleanup(mismatches, media_root, system_name)
