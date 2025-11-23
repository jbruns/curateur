"""M3U playlist file parsing and validation."""

from pathlib import Path
from typing import List, Optional


class M3UError(Exception):
    """M3U parsing errors."""
    pass


def parse_m3u(m3u_path: Path) -> List[Path]:
    """
    Parse M3U playlist file and extract disc file paths.
    
    Args:
        m3u_path: Path to M3U file
        
    Returns:
        List of absolute paths to disc files referenced in M3U
        
    Raises:
        M3UError: If M3U file cannot be parsed or disc files not found
    """
    if not m3u_path.exists():
        raise M3UError(f"M3U file not found: {m3u_path}")
    
    if not m3u_path.is_file():
        raise M3UError(f"M3U path is not a file: {m3u_path}")
    
    disc_files = []
    m3u_dir = m3u_path.parent
    
    try:
        with open(m3u_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                
                # Skip empty lines and comments
                if not line or line.startswith('#'):
                    continue
                
                # Parse path (can be relative or absolute)
                disc_path = Path(line)
                
                # Resolve relative paths
                if not disc_path.is_absolute():
                    disc_path = (m3u_dir / disc_path).resolve()
                
                disc_files.append(disc_path)
    
    except Exception as e:
        raise M3UError(f"Failed to read M3U file: {e}")
    
    if not disc_files:
        raise M3UError(f"No disc files found in M3U: {m3u_path}")
    
    return disc_files


def get_disc1_file(m3u_path: Path) -> Path:
    """
    Get the first disc file from an M3U playlist.
    
    This is used for API identification, as ScreenScraper matches
    games based on disc 1 properties.
    
    Args:
        m3u_path: Path to M3U file
        
    Returns:
        Path to first disc file
        
    Raises:
        M3UError: If M3U cannot be parsed or disc 1 not found
    """
    disc_files = parse_m3u(m3u_path)
    
    if not disc_files:
        raise M3UError(f"No disc files in M3U: {m3u_path}")
    
    disc1_path = disc_files[0]
    
    if not disc1_path.exists():
        raise M3UError(
            f"Disc 1 file not found: {disc1_path}\n"
            f"  Referenced in: {m3u_path}"
        )
    
    return disc1_path
