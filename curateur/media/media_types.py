"""
Media type definitions for curateur.

Maps ScreenScraper media types to ES-DE directory structure.
"""

from enum import Enum
from typing import Dict


class MediaType(Enum):
    """
    Media types supported by curateur (MVP subset).
    
    Maps ScreenScraper API media types to ES-DE directory names.
    """
    # MVP media types (Phase 4)
    BOX_2D = 'box-2D'           # Front box art
    SCREENSHOT = 'ss'            # In-game screenshot
    TITLESCREEN = 'sstitle'      # Title screen
    MARQUEE = 'screenmarquee'    # Arcade marquee
    
    # Milestone 2 additions (future)
    # BOX_3D = 'box-3D'
    # BACKCOVER = 'box-2D-back'
    # FANART = 'fanart'
    # MANUAL = 'manuel'
    # PHYSICAL_MEDIA = 'support-2D'
    # VIDEO = 'video'
    # WHEEL = 'wheel'


# Maps ScreenScraper media type strings to ES-DE directory names
MEDIA_TYPE_MAP: Dict[str, str] = {
    'box-2D': 'covers',
    'ss': 'screenshots',
    'sstitle': 'titlescreens',
    'screenmarquee': 'marquees',
    
    # Milestone 2 (for future reference)
    # 'box-3D': '3dboxes',
    # 'box-2D-back': 'backcovers',
    # 'fanart': 'fanart',
    # 'manuel': 'manuals',
    # 'support-2D': 'physicalmedia',
    # 'video': 'videos',
    # 'wheel': 'wheel',
}


def get_directory_for_media_type(media_type: str) -> str:
    """
    Get the ES-DE directory name for a ScreenScraper media type.
    
    Args:
        media_type: ScreenScraper media type (e.g., 'box-2D', 'ss')
        
    Returns:
        ES-DE directory name (e.g., 'covers', 'screenshots')
        
    Raises:
        ValueError: If media type is not supported
    """
    if media_type not in MEDIA_TYPE_MAP:
        raise ValueError(f"Unsupported media type: {media_type}")
    
    return MEDIA_TYPE_MAP[media_type]


def is_supported_media_type(media_type: str) -> bool:
    """
    Check if a media type is supported in the current MVP.
    
    Args:
        media_type: ScreenScraper media type string
        
    Returns:
        True if supported, False otherwise
    """
    return media_type in MEDIA_TYPE_MAP
