"""Hash calculation for ROM and media files."""

import zlib
import hashlib
from pathlib import Path
from typing import Optional


def calculate_hash(
    file_path: Path,
    algorithm: str = 'crc32',
    size_limit: int = 1073741824
) -> Optional[str]:
    """
    Calculate hash for a file using specified algorithm.
    
    Args:
        file_path: Path to file to hash
        algorithm: Hash algorithm ('crc32', 'md5', 'sha1')
        size_limit: Maximum file size to hash (default 1GB). Set 0 for no limit.
        
    Returns:
        Uppercase hex hash string, or None if file exceeds limit
        
    Raises:
        IOError: If file cannot be read
        ValueError: If algorithm is not supported
    """
    if algorithm not in ('crc32', 'md5', 'sha1'):
        raise ValueError(f"Unsupported hash algorithm: {algorithm}")
    
    file_size = file_path.stat().st_size
    
    # Only check size limit if one is set (non-zero)
    if size_limit > 0 and file_size > size_limit:
        return None
    
    chunk_size = 8 * 1024 * 1024  # 8MB chunks for better I/O efficiency
    
    if algorithm == 'crc32':
        # Calculate CRC32
        crc = 0
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                crc = zlib.crc32(chunk, crc)
        
        # Convert to unsigned 32-bit value and format as uppercase hex
        crc = crc & 0xFFFFFFFF
        return f"{crc:08X}"
    
    else:
        # Calculate MD5 or SHA1
        hasher = hashlib.md5() if algorithm == 'md5' else hashlib.sha1()
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                hasher.update(chunk)
        
        return hasher.hexdigest().upper()


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
