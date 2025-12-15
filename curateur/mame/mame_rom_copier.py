"""Copy MAME ROMs and CHD files to target directory.

Handles disk space validation, file copying with skip logic, and CHD directory management.
"""

import logging
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from dataclasses import dataclass

from .mame_xml_parser import MAMEXMLParser, MAMEMachine

logger = logging.getLogger(__name__)


@dataclass
class CopyStats:
    """Statistics for ROM/CHD copying operation."""

    roms_total: int = 0
    roms_copied: int = 0
    roms_skipped: int = 0
    chds_total: int = 0
    chds_copied: int = 0
    chds_skipped: int = 0
    bytes_copied: int = 0


class MAMEROMCopier:
    """Copies MAME ROM and CHD files to target directory."""

    def __init__(
        self,
        source_rom_path: Path,
        source_chd_path: Optional[Path],
        target_rom_path: Path,
        mame_parser: MAMEXMLParser,
    ):
        """Initialize ROM copier.

        Args:
            source_rom_path: Path to source ROM directory
            source_chd_path: Optional path to source CHD directory
            target_rom_path: Path to target ROM directory
            mame_parser: Parsed MAME XML data
        """
        self.source_rom_path = source_rom_path
        self.source_chd_path = source_chd_path
        self.target_rom_path = target_rom_path
        self.mame_parser = mame_parser

    def copy_roms_and_chds(
        self, shortnames: Set[str], dry_run: bool = False
    ) -> Tuple[CopyStats, List[str]]:
        """Copy ROMs and CHDs for specified games.

        Args:
            shortnames: Set of MAME shortnames to copy
            dry_run: If True, only validate without copying

        Returns:
            Tuple of (CopyStats, list of validation errors)
        """
        stats = CopyStats()
        errors = []

        # Validate source directories
        if not self.source_rom_path.exists():
            errors.append(f"Source ROM path does not exist: {self.source_rom_path}")
            return stats, errors

        # Calculate required space
        required_space = self._calculate_required_space(shortnames)
        available_space = shutil.disk_usage(self.target_rom_path.parent).free

        logger.info(f"Disk space check:")
        logger.info(f"  Required: {self._format_bytes(required_space)}")
        logger.info(f"  Available: {self._format_bytes(available_space)}")

        if required_space > available_space:
            error_msg = (
                f"Insufficient disk space: need {self._format_bytes(required_space)}, "
                f"have {self._format_bytes(available_space)}"
            )
            errors.append(error_msg)
            logger.error(error_msg)
            return stats, errors

        if dry_run:
            logger.info("Dry run mode: skipping actual file operations")
            return stats, errors

        # Create target directory
        self.target_rom_path.mkdir(parents=True, exist_ok=True)

        # Copy ROMs
        logger.info(f"Copying ROMs to {self.target_rom_path}")
        self._copy_roms(shortnames, stats, errors)

        # Copy CHDs (if source path provided)
        if self.source_chd_path:
            logger.info(f"Copying CHDs from {self.source_chd_path}")
            self._copy_chds(shortnames, stats, errors)

        # Log summary
        logger.info(f"Copy complete:")
        logger.info(f"  ROMs: {stats.roms_copied} copied, {stats.roms_skipped} skipped")
        if self.source_chd_path:
            logger.info(
                f"  CHDs: {stats.chds_copied} copied, {stats.chds_skipped} skipped"
            )
        logger.info(f"  Total data: {self._format_bytes(stats.bytes_copied)}")

        return stats, errors

    def _calculate_required_space(self, shortnames: Set[str]) -> int:
        """Calculate total disk space required for ROMs and CHDs.

        Args:
            shortnames: Set of MAME shortnames

        Returns:
            Required bytes
        """
        total_bytes = 0

        # Calculate ROM sizes
        for shortname in shortnames:
            rom_path = self.source_rom_path / f"{shortname}.zip"
            if rom_path.exists():
                total_bytes += rom_path.stat().st_size

        # Calculate CHD sizes
        if self.source_chd_path:
            for shortname in shortnames:
                machine = self.mame_parser.get_machine(shortname)
                if machine and machine.has_chd_requirement():
                    chd_dir = self.source_chd_path / shortname
                    if chd_dir.exists():
                        total_bytes += self._get_directory_size(chd_dir)

        return total_bytes

    def _get_directory_size(self, path: Path) -> int:
        """Get total size of directory and contents.

        Args:
            path: Directory path

        Returns:
            Total bytes
        """
        total = 0
        try:
            for item in path.rglob("*"):
                if item.is_file():
                    total += item.stat().st_size
        except Exception as e:
            logger.warning(f"Error calculating size of {path}: {e}")
        return total

    def _copy_roms(self, shortnames: Set[str], stats: CopyStats, errors: List[str]):
        """Copy ROM files.

        Args:
            shortnames: Set of MAME shortnames
            stats: CopyStats to update
            errors: List to append errors to
        """
        for shortname in sorted(shortnames):
            source_rom = self.source_rom_path / f"{shortname}.zip"
            target_rom = self.target_rom_path / f"{shortname}.zip"

            stats.roms_total += 1

            if not source_rom.exists():
                errors.append(f"ROM not found: {shortname}.zip")
                continue

            # Check if already exists with matching size/timestamp
            if target_rom.exists():
                source_stat = source_rom.stat()
                target_stat = target_rom.stat()
                if (
                    source_stat.st_size == target_stat.st_size
                    and abs(source_stat.st_mtime - target_stat.st_mtime) < 2
                ):
                    logger.debug(f"Skipping {shortname}.zip (already exists)")
                    stats.roms_skipped += 1
                    continue
                else:
                    # File exists but differs - remove it before copying
                    logger.debug(f"Removing outdated {shortname}.zip before copying")
                    try:
                        target_rom.unlink()
                    except Exception as e:
                        error_msg = f"Error removing {shortname}.zip: {e}"
                        errors.append(error_msg)
                        logger.error(error_msg)
                        continue

            # Copy ROM
            try:
                shutil.copy2(source_rom, target_rom)
                stats.roms_copied += 1
                stats.bytes_copied += source_rom.stat().st_size
                logger.debug(f"Copied {shortname}.zip")
            except Exception as e:
                error_msg = f"Error copying {shortname}.zip: {e}"
                errors.append(error_msg)
                logger.error(error_msg)

    def _copy_chds(self, shortnames: Set[str], stats: CopyStats, errors: List[str]):
        """Copy CHD directories.

        Args:
            shortnames: Set of MAME shortnames
            stats: CopyStats to update
            errors: List to append errors to
        """
        if not self.source_chd_path.exists():
            logger.warning(f"Source CHD path does not exist: {self.source_chd_path}")
            return

        for shortname in sorted(shortnames):
            machine = self.mame_parser.get_machine(shortname)
            if not machine or not machine.has_chd_requirement():
                continue

            stats.chds_total += 1

            source_chd_dir = self.source_chd_path / shortname
            target_chd_dir = self.target_rom_path / shortname

            if not source_chd_dir.exists():
                errors.append(f"CHD directory not found: {shortname}/")
                continue

            # Validate CHD directory has required discs
            required_chds = machine.get_required_chd_names()
            missing_chds = []
            for chd_name in required_chds:
                chd_file = source_chd_dir / f"{chd_name}.chd"
                if not chd_file.exists():
                    missing_chds.append(chd_name)

            if missing_chds:
                warning = f"CHD directory {shortname}/ missing discs: {', '.join(missing_chds)}"
                logger.warning(warning)
                # Continue with partial copy

            # Check if already exists
            if target_chd_dir.exists():
                # Check if all files match
                all_match = True
                for source_file in source_chd_dir.rglob("*"):
                    if not source_file.is_file():
                        continue

                    rel_path = source_file.relative_to(source_chd_dir)
                    target_file = target_chd_dir / rel_path

                    if not target_file.exists():
                        all_match = False
                        break

                    source_stat = source_file.stat()
                    target_stat = target_file.stat()
                    if (
                        source_stat.st_size != target_stat.st_size
                        or abs(source_stat.st_mtime - target_stat.st_mtime) > 2
                    ):
                        all_match = False
                        break

                if all_match:
                    logger.debug(f"Skipping CHD {shortname}/ (already exists)")
                    stats.chds_skipped += 1
                    continue

            # Log CHD copy with size
            chd_size = self._get_directory_size(source_chd_dir)
            logger.info(f"Copying CHD {shortname}/ ({self._format_bytes(chd_size)})...")

            # Copy CHD directory
            try:
                if target_chd_dir.exists():
                    shutil.rmtree(target_chd_dir)

                shutil.copytree(
                    source_chd_dir, target_chd_dir, copy_function=shutil.copy2
                )
                stats.chds_copied += 1
                stats.bytes_copied += chd_size
                logger.info(f"  Copied {shortname}/")
            except Exception as e:
                error_msg = f"Error copying CHD {shortname}/: {e}"
                errors.append(error_msg)
                logger.error(error_msg)

    def _format_bytes(self, bytes_count: int) -> str:
        """Format byte count as human-readable string.

        Args:
            bytes_count: Number of bytes

        Returns:
            Formatted string (e.g., "1.5 GB")
        """
        for unit in ["B", "KB", "MB", "GB", "TB"]:
            if bytes_count < 1024.0:
                return f"{bytes_count:.1f} {unit}"
            bytes_count /= 1024.0
        return f"{bytes_count:.1f} PB"
