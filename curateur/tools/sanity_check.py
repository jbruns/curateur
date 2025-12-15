#!/usr/bin/env python3
"""
ROM Directory Sanity Checker

Validates ROM directories against ES-DE system definitions:
- File extensions match system configuration
- No zero-byte files
- File sizes within reasonable statistical range
- Multi-disc sets properly organized in .multidisc/ with valid .m3u files
- Bin/cue sets properly structured in .cue directories
- No hidden files except .multidisc/
- Uniform compression (no mixing compressed and uncompressed ROMs)
"""

import argparse
import logging
import re
import statistics
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from curateur.config.es_systems import SystemDefinition, parse_es_systems
from curateur.config.loader import load_config, ConfigError
from curateur.config.validator import validate_config, ValidationError
from curateur.scanner.disc_handler import is_disc_subdirectory, DiscSubdirError
from curateur.scanner.hash_calculator import format_file_size
from curateur.scanner.m3u_parser import parse_m3u, M3UError

logger = logging.getLogger(__name__)


@dataclass
class ValidationIssue:
    """Represents a single validation issue."""

    category: str  # Issue category for grouping
    file_path: Path
    message: str
    severity: str = "warning"  # warning or error


@dataclass
class SystemReport:
    """Validation report for a single system."""

    system_name: str
    system_fullname: str
    rom_path: Path
    files_checked: int = 0
    issues: List[ValidationIssue] = field(default_factory=list)

    def add_issue(
        self, category: str, file_path: Path, message: str, severity: str = "warning"
    ):
        """Add a validation issue."""
        self.issues.append(ValidationIssue(category, file_path, message, severity))

    def has_issues(self) -> bool:
        """Check if system has any issues."""
        return len(self.issues) > 0


@dataclass
class ValidationReport:
    """Overall validation report."""

    system_reports: List[SystemReport] = field(default_factory=list)

    def total_files_checked(self) -> int:
        """Total files checked across all systems."""
        return sum(report.files_checked for report in self.system_reports)

    def total_issues(self) -> int:
        """Total issues found across all systems."""
        return sum(len(report.issues) for report in self.system_reports)

    def systems_with_issues(self) -> int:
        """Number of systems with issues."""
        return sum(1 for report in self.system_reports if report.has_issues())


def parse_cue_file(cue_path: Path) -> List[str]:
    """
    Parse .cue file and extract referenced bin files.

    Args:
        cue_path: Path to .cue file

    Returns:
        List of referenced bin filenames
    """
    bin_files = []
    try:
        content = cue_path.read_text(errors="ignore")
        for line in content.splitlines():
            line_strip = line.strip()
            if not line_strip.upper().startswith("FILE"):
                continue
            # Parse: FILE "track01.bin" BINARY
            match = re.search(r'FILE\s+"([^"]+)"', line_strip, flags=re.IGNORECASE)
            if match:
                bin_files.append(match.group(1))
    except Exception as e:
        logger.warning(f"Error parsing cue file {cue_path}: {e}")

    return bin_files


def parse_gdi_file(gdi_path: Path) -> List[str]:
    """
    Parse .gdi file and extract referenced track files.

    GDI format: Each line after first contains: track_num lba type sector_size filename offset
    Example: 1 0 4 2352 track01.bin 0

    Args:
        gdi_path: Path to .gdi file

    Returns:
        List of referenced track filenames
    """
    track_files = []
    try:
        content = gdi_path.read_text(errors="ignore")
        lines = content.splitlines()

        # First line is track count, skip it
        for line in lines[1:]:
            line_strip = line.strip()
            if not line_strip:
                continue

            # Parse: track_num lba type sector_size filename offset
            parts = line_strip.split(maxsplit=4)
            if len(parts) >= 5:
                # Filename is the 5th field, may have quotes
                filename = parts[4].split()[0].strip('"')
                track_files.append(filename)
    except Exception as e:
        logger.warning(f"Error parsing gdi file {gdi_path}: {e}")

    return track_files


def extract_disc_number(filename: str) -> Optional[int]:
    """
    Extract disc number from filename using strict pattern (Disc N).

    Args:
        filename: Filename to parse

    Returns:
        Disc number or None if not found
    """
    match = re.search(r"\(Disc (\d+)\)", filename, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return None


def validate_system(
    system: SystemDefinition, rom_root: Path, verbose: bool = False
) -> SystemReport:
    """
    Validate a single system's ROM directory.

    Args:
        system: System definition
        rom_root: Base ROM directory path
        verbose: Enable verbose logging

    Returns:
        SystemReport with validation results
    """
    report = SystemReport(
        system_name=system.name,
        system_fullname=system.fullname,
        rom_path=system.resolve_rom_path(rom_root),
    )

    # Check if ROM directory exists
    if not report.rom_path.exists():
        logger.info(f"ROM directory not found, skipping: {report.rom_path}")
        return report

    if not report.rom_path.is_dir():
        logger.warning(f"ROM path is not a directory: {report.rom_path}")
        return report

    logger.info(f"Validating {system.fullname} ({system.name}): {report.rom_path}")

    # Collect all files recursively
    all_files = []
    for item in report.rom_path.rglob("*"):
        if item.is_file():
            all_files.append(item)

    report.files_checked = len(all_files)

    if verbose:
        logger.info(f"  Found {len(all_files)} files to validate")

    # Track file sizes for statistical analysis
    file_sizes = []

    # Track compression types for uniformity check
    compressed_files = []
    uncompressed_files = []
    compressed_exts = {".zip", ".7z", ".rar"}

    # Track M3U files and .multidisc contents for multi-disc validation
    m3u_files = []
    multidisc_files = []

    # Track .cue directories for bin/cue validation
    cue_directories = []

    # Track potential multi-disc files outside .multidisc
    misplaced_multidisc_files = []

    # Validate each file
    for file_path in all_files:
        relative_path = file_path.relative_to(report.rom_path)

        # Check for hidden files/directories (except .multidisc)
        path_parts = relative_path.parts
        for part in path_parts:
            if part.startswith(".") and part != ".multidisc":
                report.add_issue(
                    "Hidden Files",
                    file_path,
                    f"Unexpected hidden file or directory: {relative_path}",
                )
                break

        # Check if file is in a .cue directory
        in_cue_dir = any(
            is_disc_subdirectory(file_path.parent, system.extensions)
            for parent in file_path.parents
            if parent != report.rom_path
        )

        # Track .m3u files
        if file_path.suffix.lower() == ".m3u":
            m3u_files.append(file_path)

        # Track files in .multidisc directory
        if ".multidisc" in path_parts:
            multidisc_files.append(file_path)
        else:
            # Check for multi-disc pattern outside .multidisc (if system supports M3U)
            if system.supports_m3u() and not in_cue_dir:
                # Check if filename contains disc pattern
                if extract_disc_number(file_path.name) is not None:
                    misplaced_multidisc_files.append(file_path)

        # Check file extension (skip files inside .cue directories for extension check)
        if not in_cue_dir:
            file_ext = file_path.suffix.lower()
            if file_ext not in system.extensions:
                report.add_issue(
                    "Invalid Extensions",
                    file_path,
                    f"File extension '{file_ext}' not supported by system {system.name}. "
                    f"Supported: {', '.join(system.extensions)}",
                )

        # Check file size
        try:
            file_size = file_path.stat().st_size

            # Check for zero-byte files
            if file_size == 0:
                report.add_issue(
                    "Zero-Byte Files", file_path, "File is empty (0 bytes)"
                )
            else:
                # Track non-zero file sizes for statistical analysis
                # Skip tracking files in special directories
                if not in_cue_dir and ".multidisc" not in path_parts:
                    file_sizes.append((file_path, file_size))

            # Track compression type (only for ROM files, not in special dirs)
            if not in_cue_dir and ".multidisc" not in path_parts:
                file_ext = file_path.suffix.lower()
                if file_ext in compressed_exts:
                    compressed_files.append(file_path)
                elif file_ext in system.extensions:
                    uncompressed_files.append(file_path)

        except Exception as e:
            report.add_issue(
                "File Access Error", file_path, f"Error accessing file: {e}"
            )

    # Statistical analysis for file size outliers (minimum 10 files)
    if len(file_sizes) >= 10:
        sizes_only = [size for _, size in file_sizes]
        mean_size = statistics.mean(sizes_only)
        stdev_size = statistics.stdev(sizes_only)

        # Flag files > 3 standard deviations from mean
        for file_path, file_size in file_sizes:
            if stdev_size > 0:  # Avoid division by zero
                z_score = abs((file_size - mean_size) / stdev_size)
                if z_score > 5:
                    report.add_issue(
                        "Size Outliers",
                        file_path,
                        f"File size {format_file_size(file_size)} is unusually large "
                        f"(>5σ from mean of {format_file_size(int(mean_size))})",
                    )

    # Check compression uniformity (only at top level, not in subdirs)
    if compressed_files and uncompressed_files:
        # Only check files directly in ROM path, not in subdirectories
        top_level_compressed = [
            f for f in compressed_files if f.parent == report.rom_path
        ]
        top_level_uncompressed = [
            f for f in uncompressed_files if f.parent == report.rom_path
        ]

        if top_level_compressed and top_level_uncompressed:
            report.add_issue(
                "Mixed Compression",
                report.rom_path,
                f"Directory contains both compressed ({len(top_level_compressed)}) "
                f"and uncompressed ({len(top_level_uncompressed)}) ROMs. "
                f"Directory should be uniform.",
            )

    # Multi-disc validation (only if system supports .m3u)
    if system.supports_m3u():
        validate_multidisc(
            report,
            system,
            m3u_files,
            multidisc_files,
            misplaced_multidisc_files,
            verbose,
        )

    # Bin/cue validation for disc-based systems
    validate_cue_directories(report, system, verbose)

    return report


def validate_multidisc(
    report: SystemReport,
    system: SystemDefinition,
    m3u_files: List[Path],
    multidisc_files: List[Path],
    misplaced_multidisc_files: List[Path],
    verbose: bool,
):
    """
    Validate multi-disc organization.

    Args:
        report: System report to add issues to
        system: System definition
        m3u_files: List of .m3u files found
        multidisc_files: List of files in .multidisc directory
        misplaced_multidisc_files: List of files with disc pattern outside .multidisc
        verbose: Enable verbose logging
    """
    multidisc_dir = report.rom_path / ".multidisc"

    # Valid file types that can be referenced in M3U files
    valid_m3u_extensions = {".cue", ".gdi", ".iso", ".chd"}

    # Track which files in .multidisc are referenced (by M3U, .cue, or .gdi)
    referenced_files = set()

    # Validate each M3U file
    for m3u_path in m3u_files:
        try:
            disc_files = parse_m3u(m3u_path)

            if not disc_files:
                report.add_issue(
                    "M3U Issues",
                    m3u_path,
                    "M3U file is empty or contains no valid disc references",
                )
                continue

            # Check that all referenced discs exist and have valid extensions
            for disc_path in disc_files:
                # Check file type
                if disc_path.suffix.lower() not in valid_m3u_extensions:
                    report.add_issue(
                        "M3U Issues",
                        m3u_path,
                        f"M3U references invalid file type '{disc_path.suffix}' in {disc_path.name}. "
                        f"Must be one of: {', '.join(sorted(valid_m3u_extensions))}",
                    )

                if not disc_path.exists():
                    report.add_issue(
                        "M3U Issues",
                        m3u_path,
                        f"M3U references non-existent file: {disc_path.name}",
                    )
                else:
                    # Track that this file is referenced
                    referenced_files.add(disc_path)

            # Validate disc ordering (strict sequential)
            disc_numbers = []
            for disc_path in disc_files:
                disc_num = extract_disc_number(disc_path.name)
                if disc_num is not None:
                    disc_numbers.append(disc_num)

            if disc_numbers:
                # Check if sequential starting from 1
                expected = list(range(1, len(disc_numbers) + 1))
                if sorted(disc_numbers) != expected:
                    report.add_issue(
                        "M3U Issues",
                        m3u_path,
                        f"Disc numbering not sequential. Expected (Disc 1) through "
                        f"(Disc {len(disc_numbers)}), found: {sorted(disc_numbers)}",
                    )
                # Check if in correct order
                elif disc_numbers != expected:
                    report.add_issue(
                        "M3U Issues",
                        m3u_path,
                        f"Discs not in correct order. Found: {disc_numbers}, "
                        f"expected: {expected}",
                    )

        except M3UError as e:
            report.add_issue("M3U Issues", m3u_path, f"Error parsing M3U file: {e}")
        except Exception as e:
            report.add_issue(
                "M3U Issues", m3u_path, f"Unexpected error validating M3U: {e}"
            )

    # Validate .cue and .gdi files in .multidisc directory
    for file_path in multidisc_files:
        file_ext = file_path.suffix.lower()

        # Parse .cue files in .multidisc
        if file_ext == ".cue":
            try:
                referenced_bins = parse_cue_file(file_path)

                if not referenced_bins:
                    report.add_issue(
                        "Cue/Gdi Issues",
                        file_path,
                        "Cue file in .multidisc contains no FILE references",
                    )
                    continue

                # Check that all referenced files exist
                for bin_filename in referenced_bins:
                    bin_path = file_path.parent / bin_filename
                    if not bin_path.exists():
                        report.add_issue(
                            "Cue/Gdi Issues",
                            file_path,
                            f"Cue file references non-existent file: {bin_filename}",
                        )
                    else:
                        # Track referenced file
                        referenced_files.add(bin_path)

            except Exception as e:
                report.add_issue(
                    "Cue/Gdi Issues", file_path, f"Error parsing cue file: {e}"
                )

        # Parse .gdi files in .multidisc
        elif file_ext == ".gdi":
            try:
                referenced_tracks = parse_gdi_file(file_path)

                if not referenced_tracks:
                    report.add_issue(
                        "Cue/Gdi Issues",
                        file_path,
                        "GDI file in .multidisc contains no track references",
                    )
                    continue

                # Check that all referenced files exist
                for track_filename in referenced_tracks:
                    track_path = file_path.parent / track_filename
                    if not track_path.exists():
                        report.add_issue(
                            "Cue/Gdi Issues",
                            file_path,
                            f"GDI file references non-existent file: {track_filename}",
                        )
                    else:
                        # Track referenced file
                        referenced_files.add(track_path)

            except Exception as e:
                report.add_issue(
                    "Cue/Gdi Issues", file_path, f"Error parsing gdi file: {e}"
                )

    # Check for orphaned files in .multidisc directory
    if multidisc_dir.exists():
        for file_path in multidisc_files:
            file_ext = file_path.suffix.lower()

            # Skip the M3U, .cue, and .gdi files themselves (they're the index files)
            if file_ext in {".m3u", ".cue", ".gdi"}:
                continue

            # Check if file is referenced by any M3U, .cue, or .gdi
            if file_path not in referenced_files:
                report.add_issue(
                    "Orphaned Files",
                    file_path,
                    "File in .multidisc directory is not referenced by any .m3u, .cue, or .gdi file",
                )

    # Check for multi-disc files outside .multidisc directory
    for file_path in misplaced_multidisc_files:
        disc_num = extract_disc_number(file_path.name)
        report.add_issue(
            "Misplaced Multi-Disc",
            file_path,
            f"Multi-disc file (Disc {disc_num}) should be in .multidisc directory with corresponding .m3u file",
        )


def validate_cue_directories(
    report: SystemReport, system: SystemDefinition, verbose: bool
):
    """
    Validate .cue directory structure and bin/cue file relationships.

    Args:
        report: System report to add issues to
        system: System definition
        verbose: Enable verbose logging
    """
    # Find all .cue directories
    for item in report.rom_path.rglob("*"):
        if not item.is_dir():
            continue

        if is_disc_subdirectory(item, system.extensions):
            # This is a .cue directory - validate it
            dir_name = item.name
            expected_file = item / dir_name

            # Check that the main .cue file exists
            if not expected_file.exists():
                report.add_issue(
                    "Bin/Cue Issues",
                    item,
                    f"Cue directory missing expected file: {dir_name}",
                )
                continue

            # Parse the .cue file to find referenced bins
            referenced_bins = parse_cue_file(expected_file)

            if not referenced_bins:
                report.add_issue(
                    "Bin/Cue Issues",
                    expected_file,
                    "Cue file contains no FILE references",
                )
                continue

            # Check that all referenced bins exist
            for bin_filename in referenced_bins:
                bin_path = item / bin_filename
                if not bin_path.exists():
                    report.add_issue(
                        "Bin/Cue Issues",
                        expected_file,
                        f"Cue file references missing file: {bin_filename}",
                    )

            # Check for extra files in the directory
            expected_files = {dir_name} | set(referenced_bins)
            actual_files = {f.name for f in item.iterdir() if f.is_file()}

            extra_files = actual_files - expected_files
            if extra_files:
                for extra_file in extra_files:
                    report.add_issue(
                        "Bin/Cue Issues",
                        item / extra_file,
                        f"Extra file in .cue directory not referenced in {dir_name}",
                    )


def print_report(report: ValidationReport, verbose: bool = False):
    """
    Print validation report to console.

    Args:
        report: Validation report
        verbose: Enable verbose output
    """
    print("\n" + "=" * 80)
    print("ROM DIRECTORY SANITY CHECK REPORT")
    print("=" * 80)

    for sys_report in report.system_reports:
        if not sys_report.files_checked:
            continue

        print(f"\n{sys_report.system_fullname} ({sys_report.system_name})")
        print(f"  Path: {sys_report.rom_path}")
        print(f"  Files checked: {sys_report.files_checked}")

        if not sys_report.has_issues():
            print(f"  Status: ✓ No issues found")
            continue

        print(f"  Issues found: {len(sys_report.issues)}")
        print()

        # Group issues by category
        issues_by_category = defaultdict(list)
        for issue in sys_report.issues:
            issues_by_category[issue.category].append(issue)

        # Print issues by category
        categories_order = [
            "Invalid Extensions",
            "Zero-Byte Files",
            "Size Outliers",
            "Hidden Files",
            "M3U Issues",
            "Cue/Gdi Issues",
            "Bin/Cue Issues",
            "Orphaned Files",
            "Misplaced Multi-Disc",
            "Mixed Compression",
            "File Access Error",
        ]

        for category in categories_order:
            if category not in issues_by_category:
                continue

            issues = issues_by_category[category]
            print(f"  {category} ({len(issues)}):")

            for issue in issues:
                # Show path relative to ROM directory for readability
                try:
                    rel_path = issue.file_path.relative_to(sys_report.rom_path)
                except ValueError:
                    rel_path = issue.file_path

                print(f"    - {rel_path}")
                print(f"      {issue.message}")

    # Print summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total files checked: {report.total_files_checked()}")
    print(f"Total issues found: {report.total_issues()}")
    print(
        f"Systems with issues: {report.systems_with_issues()} / {len(report.system_reports)}"
    )

    if report.total_issues() == 0:
        print("\n✓ All ROM directories passed validation!")
    else:
        print(f"\n✗ Found {report.total_issues()} issue(s) requiring attention.")


def create_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser."""
    parser = argparse.ArgumentParser(
        prog="curateur-sanity",
        description="ROM Directory Sanity Checker for ES-DE",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  curateur-sanity                    # Check all systems
  curateur-sanity --systems nes snes # Check specific systems
  curateur-sanity --verbose          # Show detailed progress
  curateur-sanity --config custom.yaml
        """,
    )

    parser.add_argument(
        "--config",
        type=Path,
        metavar="PATH",
        help="Path to config.yaml (default: ./config.yaml)",
    )

    parser.add_argument(
        "--systems",
        nargs="+",
        metavar="SYSTEM",
        help="System short names to check (default: all configured systems)",
    )

    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """
    Main entry point for ROM directory sanity checker.

    Args:
        argv: Command line arguments (for testing)

    Returns:
        Exit code (0 for success, 1 for issues found, 2 for errors)
    """
    parser = create_parser()
    args = parser.parse_args(argv)

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=log_level, format="%(levelname)s: %(message)s")

    # Load and validate configuration
    try:
        config = load_config(args.config)
        validate_config(config)
    except (ConfigError, ValidationError) as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 2
    except Exception as e:
        print(f"Error loading configuration: {e}", file=sys.stderr)
        return 2

    # Parse ES systems
    try:
        es_systems_path = Path(config["paths"]["es_systems"]).expanduser()
        all_systems = parse_es_systems(es_systems_path)
    except Exception as e:
        print(f"Error parsing ES systems: {e}", file=sys.stderr)
        return 2

    # Get ROM root path
    rom_root = Path(config["paths"]["roms"]).expanduser()

    # Determine which systems to check
    if args.systems:
        # User specified systems via CLI
        systems_to_check = [s for s in all_systems if s.name in args.systems]
        if len(systems_to_check) != len(args.systems):
            found_names = {s.name for s in systems_to_check}
            missing = set(args.systems) - found_names
            print(f"Warning: Unknown systems: {', '.join(missing)}", file=sys.stderr)
    else:
        # Check systems from config, or all if config list is empty
        configured_systems = config.get("scraping", {}).get("systems", [])
        if configured_systems:
            systems_to_check = [s for s in all_systems if s.name in configured_systems]
        else:
            systems_to_check = all_systems

    if not systems_to_check:
        print("No systems to check.", file=sys.stderr)
        return 2

    logger.info(f"Checking {len(systems_to_check)} system(s)")

    # Validate each system
    validation_report = ValidationReport()

    for system in systems_to_check:
        sys_report = validate_system(system, rom_root, args.verbose)
        validation_report.system_reports.append(sys_report)

    # Print report
    print_report(validation_report, args.verbose)

    # Return appropriate exit code
    if validation_report.total_issues() > 0:
        return 1  # Issues found
    else:
        return 0  # All clean


if __name__ == "__main__":
    sys.exit(main())
