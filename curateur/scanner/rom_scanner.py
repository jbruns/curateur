"""Main ROM scanner implementation."""

import logging
import os
from pathlib import Path
from typing import List, Dict, Optional, Set, Tuple

from curateur.config.es_systems import SystemDefinition
from curateur.scanner.rom_types import ROMInfo, ROMType
from curateur.scanner.hash_calculator import calculate_hash
from curateur.scanner.m3u_parser import parse_m3u, get_disc1_file, M3UError
from curateur.scanner.disc_handler import (
    is_disc_subdirectory,
    validate_disc_subdirectory,
    DiscSubdirError
)

logger = logging.getLogger(__name__)


class ScannerError(Exception):
    """ROM scanning errors."""
    pass


def scan_system(
    system: SystemDefinition,
    rom_root: Path,
    crc_size_limit: int = 1073741824
) -> List[ROMInfo]:
    """
    Scan a system's ROM directory for all valid ROM files.
    
    Args:
        system: System definition from es_systems.xml
        rom_root: Root ROM directory (for %ROMPATH% substitution)
        crc_size_limit: Maximum file size for CRC calculation (default 1GB)
        
    Returns:
        List of ROMInfo objects for all discovered ROMs
        
    Raises:
        ScannerError: If ROM directory cannot be scanned
    """
    rom_path = system.resolve_rom_path(rom_root)
    
    # Check if directory exists
    if not rom_path.exists():
        logger.info(f"ROM directory not found, skipping system: {rom_path}")
        return []
    
    if not rom_path.is_dir():
        raise ScannerError(f"ROM path is not a directory: {rom_path}")
    
    # Scan directory
    try:
        entries = list(rom_path.iterdir())
        logger.info(f"Found {len(entries)} entries in {rom_path}")
    except PermissionError as e:
        raise ScannerError(f"Permission denied accessing ROM directory: {rom_path}")
    except Exception as e:
        raise ScannerError(f"Failed to scan ROM directory: {e}")
    
    if not entries:
        # Empty directory is not an error, just return empty list
        return []
    
    # Process entries
    roms = []
    m3u_files = set()
    disc_subdirs = set()
    
    for entry in entries:
        # Skip hidden files/directories
        if entry.name.startswith('.'):
            continue
        
        try:
            rom_info = _process_entry(entry, system, crc_size_limit)
            if rom_info:
                roms.append(rom_info)
                
                # Track M3U and disc subdirs for conflict detection
                if rom_info.rom_type == ROMType.M3U_PLAYLIST:
                    m3u_files.add(rom_info.basename)
                elif rom_info.rom_type == ROMType.DISC_SUBDIR:
                    disc_subdirs.add(rom_info.basename)
        except (M3UError, DiscSubdirError) as e:
            # Log error but continue scanning
            print(f"Warning: Skipping {entry.name}: {e}")
            continue
    
    # Detect conflicts
    conflicts = _detect_conflicts(roms, m3u_files, disc_subdirs)
    if conflicts:
        # Remove conflicting entries
        conflict_basenames = {c[0] for c in conflicts}
        roms = [r for r in roms if r.basename not in conflict_basenames]
        
        # Log conflicts
        for basename, types in conflicts:
            print(
                f"Warning: Conflict detected for '{basename}': "
                f"both {' and '.join(types)} present. Skipping both."
            )
    
    logger.info(f"Scan complete: {len(roms)} ROMs found after processing {len(entries)} entries and resolving {len(conflicts)} conflicts")
    return roms


def _process_entry(
    entry: Path,
    system: SystemDefinition,
    crc_size_limit: int
) -> Optional[ROMInfo]:
    """
    Process a single filesystem entry (file or directory).
    
    Args:
        entry: Path to file or directory
        system: System definition
        crc_size_limit: CRC calculation size limit
        
    Returns:
        ROMInfo object or None if entry should be skipped
        
    Raises:
        M3UError: If M3U parsing fails
        DiscSubdirError: If disc subdirectory validation fails
    """
    entry_lower = entry.name.lower()
    
    # Check if entry matches system extensions
    matches_extension = any(
        entry_lower.endswith(ext) for ext in system.extensions
    )
    
    if not matches_extension:
        return None
    
    # Determine ROM type and process accordingly
    if entry.is_dir():
        return _process_disc_subdirectory(entry, system, crc_size_limit)
    elif entry_lower.endswith('.m3u'):
        return _process_m3u_file(entry, system, crc_size_limit)
    else:
        return _process_standard_rom(entry, system, crc_size_limit)


def _process_standard_rom(
    rom_file: Path,
    system: SystemDefinition,
    crc_size_limit: int
) -> ROMInfo:
    """Process a standard ROM file."""
    file_size = rom_file.stat().st_size
    
    # Store crc_size_limit for later hashing in pipeline
    # Hash calculation deferred to pipeline for parallel processing
    
    # Get basename (filename without extension)
    basename = rom_file.stem
    
    return ROMInfo(
        path=rom_file,
        filename=rom_file.name,
        basename=basename,
        rom_type=ROMType.STANDARD,
        system=system.name,
        query_filename=rom_file.name,
        file_size=file_size,
        hash_type="crc32",
        hash_value=None,  # Will be calculated in pipeline
        crc_size_limit=crc_size_limit
    )


def _process_m3u_file(
    m3u_file: Path,
    system: SystemDefinition,
    crc_size_limit: int
) -> ROMInfo:
    """
    Process an M3U playlist file.
    
    Uses disc 1 file properties for API identification.
    """
    # Parse M3U and get disc files
    disc_files = parse_m3u(m3u_file)
    disc1_file = get_disc1_file(m3u_file)
    
    # Use disc 1 file for identification
    file_size = disc1_file.stat().st_size
    # Hash calculation deferred to pipeline
    
    # Basename is M3U filename (not disc 1)
    basename = m3u_file.stem
    
    return ROMInfo(
        path=m3u_file,
        filename=m3u_file.name,
        basename=basename,
        rom_type=ROMType.M3U_PLAYLIST,
        system=system.name,
        query_filename=disc1_file.name,
        file_size=file_size,
        hash_type="crc32",
        hash_value=None,  # Will be calculated in pipeline
        disc_files=disc_files,
        crc_size_limit=crc_size_limit
    )


def _process_disc_subdirectory(
    disc_subdir: Path,
    system: SystemDefinition,
    crc_size_limit: int
) -> ROMInfo:
    """
    Process a disc subdirectory.
    
    Uses contained file properties for API identification.
    """
    # Validate and get contained file
    contained_file = validate_disc_subdirectory(disc_subdir, system.extensions)
    
    # Use contained file for identification
    file_size = contained_file.stat().st_size
    # Hash calculation deferred to pipeline
    
    # Basename is directory name (includes extension)
    basename = disc_subdir.name
    
    return ROMInfo(
        path=disc_subdir,
        filename=disc_subdir.name,
        basename=basename,
        rom_type=ROMType.DISC_SUBDIR,
        system=system.name,
        query_filename=contained_file.name,
        file_size=file_size,
        hash_type="crc32",
        hash_value=None,  # Will be calculated in pipeline
        contained_file=contained_file,
        crc_size_limit=crc_size_limit
    )


def _detect_conflicts(
    roms: List[ROMInfo],
    m3u_files: Set[str],
    disc_subdirs: Set[str]
) -> List[Tuple[str, List[str]]]:
    """
    Detect conflicts between M3U files and disc subdirectories.
    
    A conflict occurs when both an M3U file and a disc subdirectory exist
    with similar basenames (e.g., "Game.m3u" and "Game (Disc 1).cue/").
    
    Args:
        roms: List of all scanned ROMs
        m3u_files: Set of M3U basenames
        disc_subdirs: Set of disc subdirectory basenames
        
    Returns:
        List of (basename, [types]) tuples for conflicting entries
    """
    conflicts = []
    
    # Check for exact basename matches between M3U and disc subdirs
    # This is conservative - we only flag exact conflicts
    for m3u_base in m3u_files:
        for disc_base in disc_subdirs:
            # Check if they refer to the same game
            # Example: "Game.m3u" conflicts with "Game (Disc 1).cue"
            if _basenames_conflict(m3u_base, disc_base):
                conflicts.append((m3u_base, ['M3U playlist', 'disc subdirectory']))
                break
    
    return conflicts


def _basenames_conflict(basename1: str, basename2: str) -> bool:
    """
    Check if two basenames refer to the same game.
    
    Simple heuristic: check if one is a prefix of the other,
    or if they match after removing disc numbers.
    
    Args:
        basename1: First basename
        basename2: Second basename
        
    Returns:
        True if basenames likely refer to same game
    """
    # Normalize for comparison
    norm1 = basename1.lower().strip()
    norm2 = basename2.lower().strip()
    
    # Remove common disc indicators
    for disc_pattern in [' (disc 1)', ' (disc 2)', ' disc 1', ' disc 2', 
                         ' - disc 1', ' - disc 2', '(disc 1)', '(disc 2)']:
        norm1 = norm1.replace(disc_pattern, '')
        norm2 = norm2.replace(disc_pattern, '')
    
    # Check for match
    return norm1 == norm2 or norm1.startswith(norm2) or norm2.startswith(norm1)
