#!/usr/bin/env python3
"""
Copy ROM subset with matching media and gamelists.

This tool takes a pre-filtered ROM directory and copies matching media files
and gamelists to new target locations. The source ROM directory is assumed
complete and valid.
"""

import argparse
import logging
import shutil
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

from curateur.config.es_systems import parse_es_systems, SystemDefinition
from curateur.media.media_types import MEDIA_TYPE_MAP
from curateur.scanner.disc_handler import is_disc_subdirectory

logger = logging.getLogger(__name__)


# All media type directory names from MEDIA_TYPE_MAP
MEDIA_DIRECTORIES = [
    "covers",
    "screenshots",
    "titlescreens",
    "marquees",
    "3dboxes",
    "backcovers",
    "fanart",
    "manuals",
    "physicalmedia",
    "videos",
    "miximages",
]


def create_parser() -> argparse.ArgumentParser:
    """Create argument parser."""
    parser = argparse.ArgumentParser(
        description="Copy ROM subset with matching media and gamelists",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s /roms_subset /media /media_new /gamelists /gamelists_new --es-systems es_systems.cfg
  %(prog)s /roms_subset /media /media_new /gamelists /gamelists_new --es-systems es_systems.cfg --systems nes snes
  %(prog)s /roms_subset /media /media_new /gamelists /gamelists_new --es-systems es_systems.cfg --dry-run
""",
    )

    parser.add_argument(
        "source_roms", type=Path, help="Source ROM directory (pre-filtered subset)"
    )
    parser.add_argument("source_media", type=Path, help="Source media directory")
    parser.add_argument("target_media", type=Path, help="Target media directory")
    parser.add_argument("source_gamelists", type=Path, help="Source gamelist directory")
    parser.add_argument("target_gamelists", type=Path, help="Target gamelist directory")
    parser.add_argument(
        "--es-systems", type=Path, required=True, help="Path to es_systems.cfg file"
    )
    parser.add_argument(
        "--systems",
        nargs="+",
        help="Specific systems to process (default: all systems found in source_roms)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview operations without copying files",
    )
    parser.add_argument("--verbose", action="store_true", help="Enable verbose logging")

    return parser


def scan_roms_for_system(system: SystemDefinition, source_roms: Path) -> Set[str]:
    """
    Scan source ROM directory for a system and extract basenames.

    Args:
        system: System definition with extensions
        source_roms: Source ROM root directory

    Returns:
        Set of ROM basenames (preserving original casing)
    """
    system_dir = source_roms / system.name

    if not system_dir.exists():
        logger.debug(f"ROM directory not found: {system_dir}")
        return set()

    if not system_dir.is_dir():
        logger.warning(f"Not a directory: {system_dir}")
        return set()

    basenames = set()

    # Normalize extensions to lowercase for comparison
    extensions_lower = [ext.lower() for ext in system.extensions]

    for entry in system_dir.iterdir():
        # Skip hidden files
        if entry.name.startswith("."):
            continue

        if entry.is_file():
            # Check if file extension matches system extensions (case-insensitive)
            file_lower = entry.name.lower()
            if any(file_lower.endswith(ext) for ext in extensions_lower):
                # Use stem for regular ROM files (preserves casing)
                basenames.add(entry.stem)
                logger.debug(f"Found ROM file: {entry.name} -> basename: {entry.stem}")

        elif entry.is_dir():
            # Check if it's a disc subdirectory
            if is_disc_subdirectory(entry, system.extensions):
                # Use full directory name as basename for disc subdirs (preserves casing)
                basenames.add(entry.name)
                logger.debug(
                    f"Found disc subdir: {entry.name} -> basename: {entry.name}"
                )

    return basenames


def find_media_files(
    basename: str, system: str, source_media: Path, media_type: str
) -> List[Path]:
    """
    Find media files matching basename (case-insensitive).

    Args:
        basename: ROM basename to match
        system: System name
        source_media: Source media root directory
        media_type: Media type directory name (e.g., 'covers', 'screenshots')

    Returns:
        List of matching media file paths
    """
    media_dir = source_media / system / media_type

    if not media_dir.exists() or not media_dir.is_dir():
        return []

    matches = []
    basename_lower = basename.lower()

    # Iterate directory and compare stems case-insensitively
    for entry in media_dir.iterdir():
        if entry.is_file():
            if entry.stem.lower() == basename_lower:
                matches.append(entry)
                logger.debug(f"Matched media: {entry.name} for basename: {basename}")

    return matches


def copy_media_files(
    basenames: Set[str],
    system: str,
    source_media: Path,
    target_media: Path,
    dry_run: bool,
) -> int:
    """
    Copy media files for all basenames in a system.

    Args:
        basenames: Set of ROM basenames
        system: System name
        source_media: Source media root directory
        target_media: Target media root directory
        dry_run: If True, only preview operations

    Returns:
        Number of media files copied
    """
    files_copied = 0

    # Check if source media system directory exists
    source_system_media = source_media / system
    if not source_system_media.exists():
        logger.warning(f"Source media directory not found: {source_system_media}")
        return 0

    for basename in basenames:
        for media_type in MEDIA_DIRECTORIES:
            media_files = find_media_files(basename, system, source_media, media_type)

            for media_file in media_files:
                # Prepare target path
                target_dir = target_media / system / media_type
                target_file = target_dir / media_file.name

                if dry_run:
                    logger.info(f"[DRY RUN] Would copy: {media_file} -> {target_file}")
                    files_copied += 1
                else:
                    # Create target directory if needed
                    target_dir.mkdir(parents=True, exist_ok=True)

                    # Copy file preserving metadata
                    shutil.copy2(media_file, target_file)
                    logger.debug(f"Copied: {media_file} -> {target_file}")
                    files_copied += 1

    return files_copied


def copy_gamelist_and_cache(
    system: str, source_gamelists: Path, target_gamelists: Path, dry_run: bool
) -> tuple[bool, bool]:
    """
    Copy gamelist.xml and .cache directory for a system.

    Args:
        system: System name
        source_gamelists: Source gamelist root directory
        target_gamelists: Target gamelist root directory
        dry_run: If True, only preview operations

    Returns:
        Tuple of (gamelist_copied, cache_copied)
    """
    gamelist_copied = False
    cache_copied = False

    # Check if source gamelist directory exists
    source_system_gamelist = source_gamelists / system
    if not source_system_gamelist.exists():
        logger.warning(f"Source gamelist directory not found: {source_system_gamelist}")
        return (False, False)

    # Copy gamelist.xml
    source_gamelist = source_system_gamelist / "gamelist.xml"
    if source_gamelist.exists() and source_gamelist.is_file():
        target_dir = target_gamelists / system
        target_gamelist = target_dir / "gamelist.xml"

        if dry_run:
            logger.info(f"[DRY RUN] Would copy: {source_gamelist} -> {target_gamelist}")
            gamelist_copied = True
        else:
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_gamelist, target_gamelist)
            logger.info(f"Copied gamelist: {source_gamelist} -> {target_gamelist}")
            gamelist_copied = True
    else:
        logger.debug(f"No gamelist.xml found for system: {system}")

    # Copy .cache directory
    source_cache = source_system_gamelist / ".cache"
    if source_cache.exists() and source_cache.is_dir():
        target_cache = target_gamelists / system / ".cache"

        if dry_run:
            logger.info(f"[DRY RUN] Would copy: {source_cache} -> {target_cache}")
            cache_copied = True
        else:
            # Copy tree with dirs_exist_ok=True to handle existing directories
            shutil.copytree(source_cache, target_cache, dirs_exist_ok=True)
            logger.info(f"Copied cache: {source_cache} -> {target_cache}")
            cache_copied = True
    else:
        logger.debug(f"No .cache directory found for system: {system}")

    return (gamelist_copied, cache_copied)


def main(argv: Optional[List[str]] = None) -> int:
    """
    Main entry point.

    Args:
        argv: Command-line arguments (defaults to sys.argv)

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    parser = create_parser()
    args = parser.parse_args(argv)

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    # Validate and resolve paths
    source_roms = args.source_roms.expanduser().resolve()
    source_media = args.source_media.expanduser().resolve()
    target_media = args.target_media.expanduser().resolve()
    source_gamelists = args.source_gamelists.expanduser().resolve()
    target_gamelists = args.target_gamelists.expanduser().resolve()
    es_systems_path = args.es_systems.expanduser().resolve()

    # Check required paths
    if not source_roms.exists():
        logger.error(f"Source ROM directory not found: {source_roms}")
        return 1

    if not es_systems_path.exists():
        logger.error(f"ES systems file not found: {es_systems_path}")
        return 1

    # Warn about missing optional source directories
    if not source_media.exists():
        logger.warning(f"Source media directory not found: {source_media}")

    if not source_gamelists.exists():
        logger.warning(f"Source gamelist directory not found: {source_gamelists}")

    if args.dry_run:
        logger.info("=== DRY RUN MODE - No files will be copied ===")

    # Parse ES systems
    try:
        all_systems = parse_es_systems(es_systems_path)
    except Exception as e:
        logger.error(f"Failed to parse ES systems file: {e}")
        return 1

    # Filter systems if specified
    if args.systems:
        systems_to_process = [s for s in all_systems if s.name in args.systems]
        if not systems_to_process:
            logger.error(f"No matching systems found for: {args.systems}")
            return 1
    else:
        systems_to_process = all_systems

    # Statistics
    systems_processed = 0
    total_roms = 0
    total_media_files = 0
    total_gamelists = 0
    total_caches = 0

    # Process each system
    for system in systems_to_process:
        logger.info(f"=== Processing system: {system.name} ({system.fullname}) ===")

        # Scan ROMs
        basenames = scan_roms_for_system(system, source_roms)

        if not basenames:
            logger.info(f"No ROMs found for system: {system.name}")
            continue

        rom_count = len(basenames)
        logger.info(f"Found {rom_count} ROMs for {system.name}")
        total_roms += rom_count

        # Copy media files
        media_copied = copy_media_files(
            basenames, system.name, source_media, target_media, args.dry_run
        )
        logger.info(f"Copied {media_copied} media files for {system.name}")
        total_media_files += media_copied

        # Copy gamelist and cache
        gamelist_copied, cache_copied = copy_gamelist_and_cache(
            system.name, source_gamelists, target_gamelists, args.dry_run
        )

        if gamelist_copied:
            total_gamelists += 1
        if cache_copied:
            total_caches += 1

        systems_processed += 1

    # Print summary
    logger.info("=" * 50)
    logger.info("=== SUMMARY ===")
    logger.info(f"Systems processed: {systems_processed}")
    logger.info(f"Total ROMs scanned: {total_roms}")
    logger.info(f"Total media files copied: {total_media_files}")
    logger.info(f"Gamelists copied: {total_gamelists}")
    logger.info(f"Cache directories copied: {total_caches}")

    if args.dry_run:
        logger.info("=== DRY RUN COMPLETE - No files were actually copied ===")

    return 0


if __name__ == "__main__":
    sys.exit(main())
