"""
Gamelist Integrity Validator

Validates gamelist.xml entries against actual ROM files on disk and provides
cleanup functionality for orphaned entries.
"""

from pathlib import Path
from typing import Dict, List, NamedTuple
import logging

logger = logging.getLogger(__name__)


class ValidationResult(NamedTuple):
    """Result of gamelist integrity validation"""
    is_valid: bool
    ratio: float
    missing_roms: List[dict]
    orphaned_media: Dict[str, List[Path]]


class IntegrityValidator:
    """
    Validates gamelist integrity by comparing entries to actual ROM files
    
    Implements ratio-based validation:
    - Calculate presence ratio: present_roms / gamelist_entries
    - Warn if ratio < threshold (default: 95%)
    - Provide cleanup options for missing ROM entries
    """
    
    def __init__(self, config: dict):
        """
        Initialize integrity validator
        
        Args:
            config: Configuration dictionary
        """
        self.threshold = config.get('scraping', {}).get(
            'gamelist_integrity_threshold', 0.95
        )
        logger.info(f"Integrity Validator initialized (threshold={self.threshold:.1%})")
    
    def validate_gamelist(self, gamelist_entries: List[dict], 
                         scanned_roms: List[dict]) -> ValidationResult:
        """
        Compare gamelist entries to scanned ROMs
        
        Args:
            gamelist_entries: List of entries from gamelist.xml
            scanned_roms: List of ROM info dicts from scanner
        
        Returns:
            ValidationResult with validation details
        """
        if not gamelist_entries:
            logger.info("No gamelist entries to validate")
            return ValidationResult(
                is_valid=True,
                ratio=1.0,
                missing_roms=[],
                orphaned_media={}
            )
        
        # Create set of scanned ROM basenames for fast lookup
        scanned_basenames = {rom.get('basename') for rom in scanned_roms}
        
        # Find missing ROMs (in gamelist but not on disk)
        missing_roms = []
        for entry in gamelist_entries:
            # Extract basename from path
            path = entry.get('path', '')
            # Remove leading ./
            if path.startswith('./'):
                path = path[2:]
            
            basename = Path(path).stem if path else None
            
            if basename and basename not in scanned_basenames:
                missing_roms.append(entry)
        
        # Calculate presence ratio
        total_entries = len(gamelist_entries)
        present_count = total_entries - len(missing_roms)
        ratio = present_count / total_entries if total_entries > 0 else 1.0
        
        # Check if valid
        is_valid = ratio >= self.threshold
        
        logger.info(
            f"Validation: {present_count}/{total_entries} ROMs present "
            f"({ratio:.1%}, threshold: {self.threshold:.1%})"
        )
        
        if not is_valid:
            logger.warning(f"Integrity check failed: {len(missing_roms)} missing ROMs")
        
        return ValidationResult(
            is_valid=is_valid,
            ratio=ratio,
            missing_roms=missing_roms,
            orphaned_media={}  # Populated by caller if needed
        )
    
    def prompt_cleanup_action(self, validation_result: ValidationResult, 
                             system_name: str) -> bool:
        """
        Interactive prompt for handling integrity issues
        
        Args:
            validation_result: Result from validate_gamelist
            system_name: System name (e.g., 'nes', 'psx')
        
        Returns:
            bool: True if user confirms cleanup
        """
        missing_count = len(validation_result.missing_roms)
        total_entries = missing_count + int(
            validation_result.ratio * missing_count / (1 - validation_result.ratio)
        ) if validation_result.ratio < 1.0 else missing_count
        
        print("\n" + "=" * 70)
        print("⚠ WARNING: Gamelist integrity issue detected")
        print("=" * 70)
        print(f"System: {system_name}")
        print(f"Gamelist entries: {total_entries}")
        print(f"ROMs present: {total_entries - missing_count} ({validation_result.ratio:.1%})")
        print(f"Missing ROMs: {missing_count}")
        print()
        print("This may indicate moved/deleted ROM files.")
        print()
        print("Actions if you proceed:")
        print(f"  - Remove {missing_count} entries from gamelist.xml")
        print("  - Move associated media to <media>/CLEANUP/<system>/<media_type>/")
        print("  - Continue scanning for new ROMs")
        print()
        
        while True:
            response = input("Proceed? [y/N]: ").lower().strip()
            if response in ('y', 'yes'):
                logger.info(f"User confirmed cleanup for {system_name}")
                return True
            elif response in ('n', 'no', ''):
                logger.info(f"User declined cleanup for {system_name}")
                return False
            else:
                print("Please enter 'y' or 'n'")
    
    def execute_cleanup(self, validation_result: ValidationResult, system_name: str,
                       media_root: Path, gamelist_path: Path) -> None:
        """
        Execute cleanup operations
        
        Args:
            validation_result: Result from validate_gamelist
            system_name: System name
            media_root: Root media directory path
            gamelist_path: Path to gamelist.xml
        """
        from lxml import etree
        import shutil
        
        logger.info(f"Starting cleanup for {system_name}")
        
        # Create CLEANUP directory structure
        cleanup_root = media_root / "CLEANUP" / system_name
        cleanup_root.mkdir(parents=True, exist_ok=True)
        
        # Track orphaned media
        orphaned_count = 0
        
        # Move orphaned media for each missing ROM
        for entry in validation_result.missing_roms:
            path = entry.get('path', '')
            if path.startswith('./'):
                path = path[2:]
            
            basename = Path(path).stem if path else None
            if not basename:
                continue
            
            # Check each media type subdirectory
            system_media_dir = media_root / system_name
            if system_media_dir.exists():
                for media_type_dir in system_media_dir.iterdir():
                    if not media_type_dir.is_dir():
                        continue
                    
                    media_type = media_type_dir.name
                    
                    # Find media files for this ROM
                    for media_file in media_type_dir.glob(f"{basename}.*"):
                        # Create cleanup subdirectory
                        cleanup_subdir = cleanup_root / media_type
                        cleanup_subdir.mkdir(parents=True, exist_ok=True)
                        
                        # Move file to cleanup
                        dest = cleanup_subdir / media_file.name
                        try:
                            shutil.move(str(media_file), str(dest))
                            orphaned_count += 1
                            logger.debug(f"Moved orphaned media: {media_file.name} -> CLEANUP")
                        except Exception as e:
                            logger.error(f"Failed to move {media_file}: {e}")
        
        # Remove missing ROM entries from gamelist
        # Parse existing gamelist
        if not gamelist_path.exists():
            logger.warning(f"Gamelist not found: {gamelist_path}")
            return
        
        tree = etree.parse(str(gamelist_path))
        root = tree.getroot()
        
        # Build set of paths to remove
        paths_to_remove = {entry.get('path') for entry in validation_result.missing_roms}
        
        # Remove game elements
        removed_count = 0
        for game_elem in root.findall('.//game'):
            path_elem = game_elem.find('path')
            if path_elem is not None and path_elem.text in paths_to_remove:
                root.remove(game_elem)
                removed_count += 1
        
        # Write updated gamelist atomically
        temp_path = gamelist_path.with_suffix('.tmp')
        tree.write(
            str(temp_path),
            encoding='utf-8',
            xml_declaration=True,
            pretty_print=True
        )
        temp_path.replace(gamelist_path)
        
        logger.info(
            f"Cleanup complete: removed {removed_count} entries, "
            f"moved {orphaned_count} media files to CLEANUP"
        )
        
        print(f"\n✓ Cleanup complete:")
        print(f"  - Removed {removed_count} gamelist entries")
        print(f"  - Moved {orphaned_count} orphaned media files to CLEANUP/")
