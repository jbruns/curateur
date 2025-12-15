#!/usr/bin/env python3
"""
Deduplicate multi-disc entries in gamelist.xml files.

This script removes duplicate entries for multi-disc games, keeping only
Disc 1 (or the first available disc) for each multi-disc set.

Usage:
    python -m curateur.tools.deduplicate_multidisc /path/to/gamelist.xml
    python -m curateur.tools.deduplicate_multidisc /path/to/gamelist1.xml /path/to/gamelist2.xml

Options:
    --dry-run    Show what would be removed without making changes
    --backup     Create backup before modifying (default: enabled)
    --no-backup  Skip creating backup file
"""

import argparse
import sys
from pathlib import Path
from typing import List, Dict, Tuple
from collections import defaultdict
import shutil

from lxml import etree

from curateur.gamelist.parser import GamelistParser
from curateur.gamelist.xml_writer import GamelistWriter
from curateur.gamelist.game_entry import GameEntry, GamelistMetadata
from curateur.tools.organize_roms import split_base_and_disc


def group_multidisc_entries(
    entries: List[GameEntry],
) -> Dict[str, List[Tuple[GameEntry, int]]]:
    """
    Group game entries by base name, tracking disc numbers.

    Args:
        entries: List of GameEntry objects

    Returns:
        Dict mapping base names to list of (entry, disc_number) tuples
    """
    groups = defaultdict(list)
    single_entries = []

    for entry in entries:
        # Extract filename from path (e.g., "./Game.bin" -> "Game.bin")
        path_str = entry.path or ""
        filename = Path(path_str).name

        # Split into base name and disc number
        base_name, disc_number = split_base_and_disc(Path(filename).stem)

        if disc_number is None:
            # Not a multi-disc entry, add to singles
            single_entries.append((entry, None))
        else:
            # Multi-disc entry, group by base name (case-insensitive)
            groups[base_name.lower()].append((entry, disc_number))

    # Also add single entries as their own groups
    for entry, _ in single_entries:
        path_str = entry.path or ""
        filename = Path(path_str).name
        key = Path(filename).stem.lower()
        groups[key].append((entry, None))

    return groups


def deduplicate_multidisc(
    entries: List[GameEntry], dry_run: bool = False
) -> Tuple[List[GameEntry], List[GameEntry]]:
    """
    Remove duplicate multi-disc entries, keeping only the first disc.

    Args:
        entries: List of GameEntry objects
        dry_run: If True, don't actually modify, just report

    Returns:
        Tuple of (kept_entries, removed_entries)
    """
    groups = group_multidisc_entries(entries)

    kept_entries = []
    removed_entries = []

    for base_name, group in groups.items():
        if len(group) == 1:
            # Single entry (or single disc), always keep
            kept_entries.append(group[0][0])
        else:
            # Multiple entries with same base name
            # Check if they have disc numbers
            has_disc_numbers = any(disc_num is not None for _, disc_num in group)

            if not has_disc_numbers:
                # No disc numbers detected, keep all (might be different games)
                for entry, _ in group:
                    kept_entries.append(entry)
            else:
                # Sort by disc number (None values go last)
                sorted_group = sorted(group, key=lambda x: (x[1] is None, x[1] or 999))

                # Keep the first (lowest disc number)
                kept_entry, kept_disc = sorted_group[0]
                kept_entries.append(kept_entry)

                # Mark the rest as removed
                for entry, disc_num in sorted_group[1:]:
                    removed_entries.append(entry)
                    if not dry_run:
                        print(
                            f"  Removing: {entry.path} (Disc {disc_num}) - keeping Disc {kept_disc}"
                        )

    return kept_entries, removed_entries


def parse_gamelist_metadata(gamelist_path: Path) -> GamelistMetadata:
    """
    Parse metadata from existing gamelist.xml.

    Args:
        gamelist_path: Path to gamelist.xml file

    Returns:
        GamelistMetadata object
    """
    tree = etree.parse(str(gamelist_path))
    root = tree.getroot()

    # Try to get provider info from existing gamelist
    provider = root.find("provider")
    if provider is not None:
        system_elem = provider.find("System")
        software_elem = provider.find("Software")
        database_elem = provider.find("Database")
        web_elem = provider.find("Web")

        system = (
            system_elem.text if system_elem is not None and system_elem.text else None
        )
        software = (
            software_elem.text
            if software_elem is not None and software_elem.text
            else "curateur"
        )
        database = (
            database_elem.text
            if database_elem is not None and database_elem.text
            else "ScreenScraper.fr"
        )
        web = (
            web_elem.text
            if web_elem is not None and web_elem.text
            else "http://www.screenscraper.fr"
        )
    else:
        system = None
        software = "curateur"
        database = "ScreenScraper.fr"
        web = "http://www.screenscraper.fr"

    # If system not in provider, try to infer from path
    # e.g., /path/to/gamelists/gc/gamelist.xml -> gc
    if not system:
        parts = gamelist_path.parts
        # Look for parent directory name (assumes structure like .../gamelists/SYSTEM/gamelist.xml)
        if len(parts) >= 2 and gamelist_path.name == "gamelist.xml":
            system = parts[-2]  # Parent directory
        else:
            system = "unknown"

    return GamelistMetadata(
        system=system, software=software, database=database, web=web
    )


def process_gamelist(
    gamelist_path: Path, dry_run: bool = False, create_backup: bool = True
) -> None:
    """
    Process a single gamelist.xml file.

    Args:
        gamelist_path: Path to gamelist.xml file
        dry_run: If True, don't modify files
        create_backup: If True, create backup before modifying
    """
    print(f"\nProcessing: {gamelist_path}")

    # Check if file exists
    if not gamelist_path.exists():
        print(f"ERROR: File not found: {gamelist_path}")
        return

    # Parse gamelist metadata
    try:
        metadata = parse_gamelist_metadata(gamelist_path)
    except Exception as e:
        print(f"ERROR: Failed to parse gamelist metadata: {e}")
        return

    # Parse gamelist entries
    parser = GamelistParser()
    try:
        entries = parser.parse_gamelist(gamelist_path)
    except Exception as e:
        print(f"ERROR: Failed to parse gamelist: {e}")
        return

    print(f"Found {len(entries)} total entries")

    # Deduplicate
    kept_entries, removed_entries = deduplicate_multidisc(entries, dry_run=dry_run)

    # Show summary
    if removed_entries:
        print(f"\nSummary:")
        print(f"  Total entries: {len(entries)}")
        print(f"  Kept entries: {len(kept_entries)}")
        print(f"  Removed duplicates: {len(removed_entries)}")

        if dry_run:
            print(
                "\n[DRY RUN] No changes made. Run without --dry-run to apply changes."
            )
        else:
            # Create backup
            if create_backup:
                backup_path = gamelist_path.with_suffix(".xml.backup")
                shutil.copy2(gamelist_path, backup_path)
                print(f"\nBackup created: {backup_path}")

            # Write cleaned gamelist (using parsed metadata)
            writer = GamelistWriter(metadata)
            writer.write_gamelist(kept_entries, gamelist_path)
            print(f"\nCleaned gamelist written: {gamelist_path}")
    else:
        print("\nNo duplicate multi-disc entries found. No changes needed.")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Deduplicate multi-disc entries in gamelist.xml files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process a single gamelist
  python -m curateur.tools.deduplicate_multidisc /path/to/gamelist.xml

  # Dry run to see what would be removed
  python -m curateur.tools.deduplicate_multidisc --dry-run /path/to/gamelist.xml

  # Process multiple gamelists
  python -m curateur.tools.deduplicate_multidisc /roms/system1/gamelist.xml /roms/system2/gamelist.xml

  # Process without creating backup
  python -m curateur.tools.deduplicate_multidisc --no-backup /path/to/gamelist.xml
        """,
    )

    parser.add_argument(
        "gamelists", nargs="+", type=Path, help="Path(s) to gamelist.xml file(s)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without making changes",
    )

    parser.add_argument(
        "--backup",
        dest="create_backup",
        action="store_true",
        default=True,
        help="Create backup before modifying (default)",
    )

    parser.add_argument(
        "--no-backup",
        dest="create_backup",
        action="store_false",
        help="Skip creating backup file",
    )

    args = parser.parse_args()

    # Process each gamelist
    for gamelist_path in args.gamelists:
        try:
            process_gamelist(
                gamelist_path, dry_run=args.dry_run, create_backup=args.create_backup
            )
        except Exception as e:
            print(f"ERROR processing {gamelist_path}: {e}")
            import traceback

            traceback.print_exc()

    print("\nDone!")


if __name__ == "__main__":
    main()
