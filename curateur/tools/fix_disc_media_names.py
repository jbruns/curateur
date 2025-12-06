#!/usr/bin/env python3
"""
Fix media file naming for disc subdirectories.

This script renames media files for disc subdirectories to include the full
directory name with extension. For example:
  - Before: downloaded_media/dreamcast/3dboxes/Armada (USA).png
  - After:  downloaded_media/dreamcast/3dboxes/Armada (USA).cue.png

Usage:
    python -m curateur.tools.fix_disc_media_names /path/to/roms /path/to/downloaded_media
"""

import argparse
import sys
from pathlib import Path
from typing import List, Tuple


def is_disc_subdirectory(path: Path) -> bool:
    """
    Check if a directory looks like a disc subdirectory.
    
    A disc subdirectory has an extension in its name (e.g., .cue, .gdi)
    and contains a file with the same name.
    """
    if not path.is_dir():
        return False
    
    dir_name = path.name
    
    # Must have an extension
    if '.' not in dir_name:
        return False
    
    # Check if contained file exists with same name
    expected_file = path / dir_name
    return expected_file.exists() and expected_file.is_file()


def find_disc_subdirectories(rom_dir: Path) -> List[Path]:
    """
    Find all disc subdirectories in a ROM directory.
    
    Args:
        rom_dir: ROM directory to scan
        
    Returns:
        List of disc subdirectory paths
    """
    disc_subdirs = []
    
    if not rom_dir.exists():
        return disc_subdirs
    
    for item in rom_dir.iterdir():
        if is_disc_subdirectory(item):
            disc_subdirs.append(item)
    
    return disc_subdirs


def find_media_files_needing_rename(
    media_root: Path,
    system: str,
    disc_subdir_name: str,
    verbose: bool = False
) -> List[Tuple[Path, Path]]:
    """
    Find media files that need to be renamed for a disc subdirectory.
    
    Args:
        media_root: Root of downloaded_media directory
        system: System name (e.g., 'dreamcast')
        disc_subdir_name: Full disc subdirectory name (e.g., 'Armada (USA).cue')
        verbose: Print debug information
        
    Returns:
        List of (old_path, new_path) tuples for files that need renaming
    """
    renames = []
    
    # Check if media_root already includes the system name
    # (e.g., if user passed ~/downloaded_media/dreamcast instead of ~/downloaded_media)
    if media_root.name == system:
        system_media_dir = media_root
        if verbose:
            print(f"  DEBUG: media_root already includes system name, using: {system_media_dir}")
    else:
        system_media_dir = media_root / system
        if verbose:
            print(f"  DEBUG: Appending system to media_root: {system_media_dir}")
    
    if not system_media_dir.exists():
        if verbose:
            print(f"  DEBUG: System media directory does not exist: {system_media_dir}")
        return renames
    
    # Extract basename without extension (e.g., 'Armada (USA).cue' -> 'Armada (USA)')
    if '.' in disc_subdir_name:
        basename_without_ext = disc_subdir_name.rsplit('.', 1)[0]
    else:
        # No extension, nothing to fix
        if verbose:
            print(f"  DEBUG: Disc subdir '{disc_subdir_name}' has no extension, skipping")
        return renames
    
    if verbose:
        print(f"  DEBUG: Looking for media files matching: {basename_without_ext}.*")
    
    # Check all media type directories
    for media_type_dir in system_media_dir.iterdir():
        if not media_type_dir.is_dir():
            continue
        
        if verbose:
            print(f"  DEBUG: Checking directory: {media_type_dir.name}")
        
        # Look for files with the old naming pattern (without disc extension)
        matching_files = list(media_type_dir.glob(f"{basename_without_ext}.*"))
        if verbose and matching_files:
            print(f"  DEBUG: Found {len(matching_files)} matching files in {media_type_dir.name}")
        
        for media_file in matching_files:
            # Get the media file extension
            media_ext = media_file.suffix
            
            # New name should include the disc extension
            new_name = f"{disc_subdir_name}{media_ext}"
            new_path = media_type_dir / new_name
            
            # Only add if target doesn't already exist
            if not new_path.exists():
                renames.append((media_file, new_path))
    
    return renames


def main():
    parser = argparse.ArgumentParser(
        description='Fix media file naming for disc subdirectories',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fix media for a single system
  python -m curateur.tools.fix_disc_media_names /roms/dreamcast /downloaded_media/dreamcast

  # Dry run to see what would be renamed
  python -m curateur.tools.fix_disc_media_names /roms/dreamcast /downloaded_media/dreamcast --dry-run
        """
    )
    
    parser.add_argument(
        'rom_dir',
        type=Path,
        help='ROM directory to scan for disc subdirectories'
    )
    
    parser.add_argument(
        'media_root',
        type=Path,
        help='Root of downloaded_media directory (or system-specific media dir)'
    )
    
    parser.add_argument(
        '--system',
        type=str,
        help='System name (e.g., dreamcast). If not provided, inferred from rom_dir name'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be renamed without actually renaming files'
    )
    
    parser.add_argument(
        '--verbose',
        '-v',
        action='store_true',
        help='Show detailed debug information'
    )
    
    args = parser.parse_args()
    
    rom_dir = args.rom_dir.resolve()
    media_root = args.media_root.resolve()
    
    # Determine system name
    if args.system:
        system_name = args.system
    else:
        system_name = rom_dir.name
    
    print(f"System: {system_name}")
    print(f"ROM directory: {rom_dir}")
    print(f"Media root: {media_root}")
    print()
    
    # Find disc subdirectories
    print("Scanning for disc subdirectories...")
    disc_subdirs = find_disc_subdirectories(rom_dir)
    
    if not disc_subdirs:
        print("No disc subdirectories found.")
        return 0
    
    print(f"Found {len(disc_subdirs)} disc subdirectories:")
    for disc_dir in disc_subdirs:
        print(f"  - {disc_dir.name}")
    print()
    
    # Find media files that need renaming
    all_renames = []
    for disc_dir in disc_subdirs:
        if args.verbose:
            print(f"\nChecking disc subdirectory: {disc_dir.name}")
        renames = find_media_files_needing_rename(
            media_root,
            system_name,
            disc_dir.name,
            verbose=args.verbose
        )
        all_renames.extend(renames)
    
    if not all_renames:
        print("No media files need renaming. All names are correct!")
        return 0
    
    print(f"Found {len(all_renames)} files to rename:")
    print()
    
    for old_path, new_path in all_renames:
        print(f"  {old_path.relative_to(media_root)}")
        print(f"    -> {new_path.relative_to(media_root)}")
        print()
    
    if args.dry_run:
        print("DRY RUN - No files were renamed")
        return 0
    
    # Perform renames
    print("Renaming files...")
    success_count = 0
    error_count = 0
    
    for old_path, new_path in all_renames:
        try:
            old_path.rename(new_path)
            success_count += 1
            print(f"✓ Renamed: {old_path.name} -> {new_path.name}")
        except Exception as e:
            error_count += 1
            print(f"✗ Error renaming {old_path.name}: {e}", file=sys.stderr)
    
    print()
    print(f"Complete: {success_count} renamed, {error_count} errors")
    
    return 0 if error_count == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
