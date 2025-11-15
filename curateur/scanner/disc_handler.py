"""Disc-based ROM subdirectory handling."""

from pathlib import Path
from typing import Optional, List


class DiscSubdirError(Exception):
    """Disc subdirectory validation errors."""
    pass


def is_disc_subdirectory(path: Path, system_extensions: List[str]) -> bool:
    """
    Check if a directory is a disc subdirectory.
    
    A disc subdirectory is a directory where:
    - Directory name ends with a valid system extension
    - Contains a file with the same name as the directory
    
    Args:
        path: Directory path to check
        system_extensions: List of valid extensions for the system (e.g., ['.cue', '.gdi'])
        
    Returns:
        True if path is a valid disc subdirectory
    """
    if not path.is_dir():
        return False
    
    dir_name = path.name
    
    # Check if directory name has valid extension
    dir_lower = dir_name.lower()
    has_valid_ext = any(dir_lower.endswith(ext) for ext in system_extensions)
    
    if not has_valid_ext:
        return False
    
    # Check if contained file exists with same name
    expected_file = path / dir_name
    
    return expected_file.exists() and expected_file.is_file()


def get_contained_file(disc_subdir: Path) -> Path:
    """
    Get the file contained within a disc subdirectory.
    
    Args:
        disc_subdir: Path to disc subdirectory
        
    Returns:
        Path to contained file
        
    Raises:
        DiscSubdirError: If subdirectory is invalid or file not found
    """
    if not disc_subdir.is_dir():
        raise DiscSubdirError(f"Not a directory: {disc_subdir}")
    
    dir_name = disc_subdir.name
    expected_file = disc_subdir / dir_name
    
    if not expected_file.exists():
        raise DiscSubdirError(
            f"Expected file not found in disc subdirectory:\n"
            f"  Directory: {disc_subdir}\n"
            f"  Expected: {expected_file}"
        )
    
    if not expected_file.is_file():
        raise DiscSubdirError(
            f"Expected file is not a regular file: {expected_file}"
        )
    
    return expected_file


def validate_disc_subdirectory(disc_subdir: Path, system_extensions: List[str]) -> Path:
    """
    Validate a disc subdirectory structure and return contained file.
    
    Args:
        disc_subdir: Path to disc subdirectory
        system_extensions: Valid extensions for the system
        
    Returns:
        Path to validated contained file
        
    Raises:
        DiscSubdirError: If validation fails
    """
    if not is_disc_subdirectory(disc_subdir, system_extensions):
        raise DiscSubdirError(
            f"Invalid disc subdirectory structure: {disc_subdir}\n"
            f"  Directory name must end with valid extension: {system_extensions}\n"
            f"  Must contain file with same name as directory"
        )
    
    return get_contained_file(disc_subdir)
