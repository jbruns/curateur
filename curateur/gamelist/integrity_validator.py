"""
Gamelist Integrity Validator

Validates gamelist.xml entries against actual ROM files on disk and provides
cleanup functionality for orphaned entries.
"""

from pathlib import Path
from typing import List
from dataclasses import dataclass
import logging
import shutil

from .game_entry import GameEntry

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of gamelist integrity validation"""
    is_valid: bool
    match_ratio: float
    missing_roms: List[str]  # String paths, not Path objects
    orphaned_entries: List[GameEntry]


class IntegrityValidator:
    """
    Validates gamelist integrity by comparing entries to actual ROM files
    
    Implements ratio-based validation:
    - Calculate presence ratio: present_roms / gamelist_entries
    - Warn if ratio < threshold (default: 90%)
    - Provide cleanup options for missing ROM entries
    """
    
    def __init__(self, threshold: float = 0.90):
        """
        Initialize integrity validator
        
        Args:
            threshold: Minimum ratio for valid gamelist (default: 0.90 = 90%)
        """
        self.threshold = threshold
        logger.info(f"Integrity Validator initialized (threshold={self.threshold:.1%})")
    
    def validate(
        self, 
        entries: List[GameEntry], 
        rom_files: List[Path]
    ) -> ValidationResult:
        """
        Validate gamelist entries against ROM files on disk.
        
        Args:
            entries: List of GameEntry objects from gamelist
            rom_files: List of ROM file Paths from disk
            
        Returns:
            ValidationResult with validation details
        """
        if not entries:
            logger.info("No gamelist entries to validate")
            return ValidationResult(
                is_valid=True,
                match_ratio=1.0,
                missing_roms=[],
                orphaned_entries=[]
            )
        
        # Create set of ROM basenames for fast lookup
        rom_basenames = {rom_file.stem for rom_file in rom_files}
        
        # Find missing ROMs (in gamelist but not on disk)
        missing_roms = []
        orphaned_entries = []
        
        for entry in entries:
            # Extract basename from path
            path = entry.path
            # Remove leading ./
            if path.startswith('./'):
                path_clean = path[2:]
            else:
                path_clean = path
            
            basename = Path(path_clean).stem if path_clean else None
            
            if basename and basename not in rom_basenames:
                missing_roms.append(entry.path)  # Keep as string with ./ prefix
                orphaned_entries.append(entry)
        
        # Calculate match ratio
        match_ratio = self._calculate_match_ratio(
            total=len(entries),
            matches=len(entries) - len(missing_roms)
        )
        
        # Check if valid
        is_valid = match_ratio >= self.threshold
        
        logger.info(
            f"Validation: {len(entries) - len(missing_roms)}/{len(entries)} ROMs present "
            f"({match_ratio:.1%}, threshold: {self.threshold:.1%})"
        )
        
        if not is_valid:
            logger.warning(f"Integrity check failed: {len(missing_roms)} missing ROMs")
        
        return ValidationResult(
            is_valid=is_valid,
            match_ratio=match_ratio,
            missing_roms=missing_roms,
            orphaned_entries=orphaned_entries
        )
    
    def _calculate_match_ratio(self, total: int, matches: int) -> float:
        """
        Calculate match ratio.
        
        Args:
            total: Total number of entries
            matches: Number of matching entries
            
        Returns:
            Match ratio (0.0 to 1.0)
        """
        if total == 0:
            return 1.0
        return matches / total
    
    def _identify_missing_roms(
        self,
        entries: List[GameEntry],
        rom_directory: Path
    ) -> List[str]:
        """
        Identify ROM files that are in gamelist but not on disk.
        
        Args:
            entries: List of GameEntry objects
            rom_directory: Path to ROM directory
            
        Returns:
            List of missing ROM paths (as strings)
        """
        missing = []
        
        for entry in entries:
            path = entry.path
            if path.startswith('./'):
                path_clean = path[2:]
            else:
                path_clean = path
            
            rom_path = rom_directory / path_clean
            if not rom_path.exists():
                missing.append(entry.path)  # Keep original format
        
        return missing
    
    def prompt_user(self, result: ValidationResult) -> bool:
        """
        Prompt user whether to clean up orphaned entries.
        
        Args:
            result: ValidationResult with issues
            
        Returns:
            True if user confirms cleanup
        """
        from curateur.ui import prompts
        
        total_entries = len(result.missing_roms) + int(
            result.match_ratio * len(result.missing_roms) / (1 - result.match_ratio)
        ) if result.match_ratio < 1.0 else len(result.missing_roms)
        
        message = (
            f"\nGamelist integrity issue:\n"
            f"  - {total_entries} total entries\n"
            f"  - {len(result.missing_roms)} missing ROMs ({(1-result.match_ratio):.1%})\n"
            f"  - Threshold: {self.threshold:.1%}\n"
            f"\nCleanup will remove orphaned entries and move media to CLEANUP/.\n"
            f"Continue with cleanup?"
        )
        
        return prompts.confirm(message, default=False)
    
    def _cleanup_entries(
        self,
        all_entries: List[GameEntry],
        orphaned: List[GameEntry]
    ) -> List[GameEntry]:
        """
        Remove orphaned entries from list.
        
        Args:
            all_entries: Complete list of entries
            orphaned: Entries to remove
            
        Returns:
            Cleaned list of entries
        """
        orphaned_paths = {entry.path for entry in orphaned}
        return [entry for entry in all_entries if entry.path not in orphaned_paths]
    
    def _cleanup_media(
        self,
        orphaned_entries: List[GameEntry],
        media_directory: Path
    ) -> None:
        """
        Move orphaned media files to CLEANUP directory.
        
        Args:
            orphaned_entries: Entries whose media should be cleaned up
            media_directory: Path to media directory
        """
        cleanup_dir = media_directory / "CLEANUP"
        cleanup_dir.mkdir(parents=True, exist_ok=True)
        
        moved_count = 0
        
        for entry in orphaned_entries:
            # Extract basename from path
            path = entry.path
            if path.startswith('./'):
                path = path[2:]
            
            basename = Path(path).stem
            
            # Check each media type subdirectory
            for media_subdir in media_directory.glob('*'):
                if not media_subdir.is_dir() or media_subdir.name == 'CLEANUP':
                    continue
                
                # Find media files for this ROM
                for media_file in media_subdir.glob(f"{basename}.*"):
                    # Create cleanup subdirectory
                    cleanup_subdir = cleanup_dir / media_subdir.name
                    cleanup_subdir.mkdir(parents=True, exist_ok=True)
                    
                    # Move file to cleanup
                    dest = cleanup_subdir / media_file.name
                    try:
                        shutil.move(str(media_file), str(dest))
                        moved_count += 1
                        logger.debug(f"Moved orphaned media: {media_file.name} -> CLEANUP")
                    except Exception as e:
                        logger.error(f"Failed to move {media_file}: {e}")
        
        if moved_count > 0:
            logger.info(f"Moved {moved_count} orphaned media files to CLEANUP")
