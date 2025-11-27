"""
Gamelist backup utilities

Provides functionality to create timestamped backups of gamelist.xml files
before processing begins.
"""

import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class GamelistBackup:
    """Handles backup operations for gamelist.xml files"""

    @staticmethod
    def create_backup(gamelist_path: Path) -> Optional[Path]:
        """
        Create a timestamped backup of gamelist.xml

        Args:
            gamelist_path: Path to the gamelist.xml file to backup

        Returns:
            Path to the backup file if successful, None if failed

        Raises:
            FileNotFoundError: If gamelist_path doesn't exist
            PermissionError: If unable to write backup file
            OSError: If other filesystem errors occur
        """
        if not gamelist_path.exists():
            raise FileNotFoundError(f"Gamelist not found: {gamelist_path}")

        if not gamelist_path.is_file():
            raise ValueError(f"Path is not a file: {gamelist_path}")

        # Generate timestamp (format: YYYYMMDD_HHMMSS_microseconds)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

        # Create backup filename in same directory
        backup_filename = f"gamelist_curateur_backup_{timestamp}.bak"
        backup_path = gamelist_path.parent / backup_filename

        try:
            logger.info(f"Creating backup: {backup_path.name}")
            shutil.copy2(gamelist_path, backup_path)
            logger.info(f"Backup created successfully: {backup_path}")
            return backup_path
        except PermissionError as e:
            logger.error(f"Permission denied creating backup: {e}")
            raise
        except OSError as e:
            logger.error(f"Failed to create backup: {e}")
            raise

    @staticmethod
    def list_backups(gamelist_dir: Path) -> list[Path]:
        """
        List all curateur backup files in a directory

        Args:
            gamelist_dir: Directory to search for backups

        Returns:
            List of backup file paths, sorted by modification time (newest first)
        """
        if not gamelist_dir.exists() or not gamelist_dir.is_dir():
            return []

        # Find all backup files matching our pattern
        backups = list(gamelist_dir.glob("gamelist_curateur_backup_*.bak"))

        # Sort by modification time, newest first
        backups.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        return backups

    @staticmethod
    def restore_backup(backup_path: Path, target_path: Optional[Path] = None) -> Path:
        """
        Restore a backup file

        Args:
            backup_path: Path to the backup file
            target_path: Optional target path (defaults to gamelist.xml in same directory)

        Returns:
            Path to the restored file

        Raises:
            FileNotFoundError: If backup file doesn't exist
            PermissionError: If unable to write target file
        """
        if not backup_path.exists():
            raise FileNotFoundError(f"Backup file not found: {backup_path}")

        # Default target is gamelist.xml in same directory
        if target_path is None:
            target_path = backup_path.parent / "gamelist.xml"

        try:
            logger.info(f"Restoring backup {backup_path.name} to {target_path}")
            shutil.copy2(backup_path, target_path)
            logger.info(f"Backup restored successfully: {target_path}")
            return target_path
        except PermissionError as e:
            logger.error(f"Permission denied restoring backup: {e}")
            raise
        except OSError as e:
            logger.error(f"Failed to restore backup: {e}")
            raise

    @staticmethod
    def cleanup_old_backups(gamelist_dir: Path, keep_count: int = 5) -> int:
        """
        Remove old backup files, keeping only the most recent ones

        Args:
            gamelist_dir: Directory containing backup files
            keep_count: Number of recent backups to keep (default: 5)

        Returns:
            Number of backups deleted
        """
        backups = GamelistBackup.list_backups(gamelist_dir)

        if len(backups) <= keep_count:
            return 0

        # Delete old backups beyond keep_count
        deleted = 0
        for backup in backups[keep_count:]:
            try:
                logger.debug(f"Removing old backup: {backup.name}")
                backup.unlink()
                deleted += 1
            except OSError as e:
                logger.warning(f"Failed to delete old backup {backup.name}: {e}")

        if deleted > 0:
            logger.info(f"Cleaned up {deleted} old backup(s), kept {keep_count} most recent")

        return deleted
