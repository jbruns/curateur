"""
Media type definitions for curateur.

Maps ScreenScraper media types to ES-DE directory structure.
"""

from enum import Enum
from typing import Dict, List


class MediaType(Enum):
    """
    Media types supported by curateur.
    
    Maps ScreenScraper API media types to ES-DE directory names.
    """
    # Core media types
    BOX_2D = 'box-2D'              # Front box art
    SCREENSHOT = 'ss'               # In-game screenshot
    TITLESCREEN = 'sstitle'         # Title screen
    MARQUEE = 'screenmarquee'       # Arcade marquee
    BOX_3D = 'box-3D'              # 3D box art
    BACKCOVER = 'box-2D-back'      # Back cover art
    FANART = 'fanart'              # Fanart/wallpapers
    MANUAL = 'manuel'              # PDF manuals
    PHYSICAL_MEDIA = 'support-2D'  # Disc/cartridge art
    VIDEO = 'video'                # Video gameplay
    MIXIMAGE = 'mixrbv2'           # Composite/mix images


# Maps ScreenScraper media type strings to ES-DE directory names
MEDIA_TYPE_MAP: Dict[str, str] = {
    'box-2D': 'covers',
    'ss': 'screenshots',
    'sstitle': 'titlescreens',
    'screenmarquee': 'marquees',
    'box-3D': '3dboxes',
    'box-2D-back': 'backcovers',
    'fanart': 'fanart',
    'manuel': 'manuals',
    'support-2D': 'physicalmedia',
    'video': 'videos',
    'mixrbv2': 'miximages',
}

# Reverse map: ES-DE directory names to ScreenScraper media types
DIRECTORY_TO_MEDIA_TYPE: Dict[str, str] = {v: k for k, v in MEDIA_TYPE_MAP.items()}

# Maps plural ES-DE directory names to singular forms (for gamelist.xml and UI)
MEDIA_TYPE_SINGULAR: Dict[str, str] = {
    'covers': 'cover',
    'screenshots': 'screenshot',
    'titlescreens': 'titlescreen',
    'marquees': 'marquee',
    '3dboxes': '3dbox',
    'backcovers': 'backcover',
    'fanart': 'fanart',
    'manuals': 'manual',
    'physicalmedia': 'physicalmedia',
    'videos': 'video',
    'miximages': 'miximage',
}

# Reverse map: singular forms to plural ES-DE directory names
SINGULAR_TO_PLURAL: Dict[str, str] = {v: k for k, v in MEDIA_TYPE_SINGULAR.items()}


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


def convert_directory_names_to_media_types(directory_names: List[str]) -> List[str]:
    """
    Convert ES-DE directory names to ScreenScraper media type names.
    
    Args:
        directory_names: List of ES-DE directory names (e.g., ['covers', 'screenshots'])
        
    Returns:
        List of ScreenScraper media types (e.g., ['box-2D', 'ss'])
    """
    media_types = []
    for dir_name in directory_names:
        if dir_name in DIRECTORY_TO_MEDIA_TYPE:
            media_types.append(DIRECTORY_TO_MEDIA_TYPE[dir_name])
    return media_types


def to_singular(plural_type: str) -> str:
    """
    Convert plural ES-DE directory name to singular form.
    
    Args:
        plural_type: Plural ES-DE directory name (e.g., 'covers', 'screenshots')
        
    Returns:
        Singular form (e.g., 'cover', 'screenshot')
        
    Raises:
        ValueError: If plural_type is not recognized
    """
    if plural_type not in MEDIA_TYPE_SINGULAR:
        raise ValueError(f"Unknown plural media type: {plural_type}")
    
    return MEDIA_TYPE_SINGULAR[plural_type]


def to_plural(singular_type: str) -> str:
    """
    Convert singular form to plural ES-DE directory name.
    
    Args:
        singular_type: Singular form (e.g., 'cover', 'screenshot')
        
    Returns:
        Plural ES-DE directory name (e.g., 'covers', 'screenshots')
        
    Raises:
        ValueError: If singular_type is not recognized
    """
    if singular_type not in SINGULAR_TO_PLURAL:
        raise ValueError(f"Unknown singular media type: {singular_type}")
    
    return SINGULAR_TO_PLURAL[singular_type]
