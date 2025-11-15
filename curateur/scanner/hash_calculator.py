"""CRC32 hash calculation for ROM files."""

import zlib
from pathlib import Path
from typing import Optional


def calculate_crc32(file_path: Path, size_limit: int = 1073741824) -> Optional[str]:
    """
    Calculate CRC32 hash for a file, respecting size limits.
    
    Args:
        file_path: Path to file to hash
        size_limit: Maximum file size to hash (default 1GB). Set 0 to skip hashing.
        
    Returns:
        Uppercase hex CRC32 string (8 characters), or None if file exceeds limit
        
    Raises:
        IOError: If file cannot be read
    """
    if size_limit == 0:
        return None
    
    file_size = file_path.stat().st_size
    
    if file_size > size_limit:
        return None
    
    # Calculate CRC32 in chunks to handle large files efficiently
    crc = 0
    chunk_size = 1024 * 1024  # 1MB chunks
    
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            crc = zlib.crc32(chunk, crc)
    
    # Convert to unsigned 32-bit value and format as uppercase hex
    crc = crc & 0xFFFFFFFF
    return f"{crc:08X}"


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.
    
    Args:
        size_bytes: Size in bytes
        
    Returns:
        Formatted string (e.g., "1.5 MB", "750 KB")
    """
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"
