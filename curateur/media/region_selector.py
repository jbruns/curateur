"""
Region detection and prioritization for media selection.

Handles detecting regions from ROM filenames and selecting the best
media based on region preferences.
"""

import logging
import re
from typing import List, Optional, Dict

logger = logging.getLogger(__name__)


# ScreenScraper region codes
REGION_CODES = {
    'us': ['USA', 'US', 'U'],
    'eu': ['Europe', 'EUR', 'EU', 'E'],
    'jp': ['Japan', 'JPN', 'JP', 'J'],
    'wor': ['World', 'WOR', 'W'],
    'fr': ['France', 'FR', 'F'],
    'de': ['Germany', 'DE', 'G'],
    'es': ['Spain', 'ES', 'S'],
    'it': ['Italy', 'IT', 'I'],
    'nl': ['Netherlands', 'NL'],
    'pt': ['Portugal', 'PT'],
    'br': ['Brazil', 'BR'],
    'au': ['Australia', 'AU'],
    'kr': ['Korea', 'KR', 'K'],
    'cn': ['China', 'CN'],
    'tw': ['Taiwan', 'TW'],
}


def detect_region_from_filename(filename: str) -> List[str]:
    """
    Detect region codes from ROM filename.
    
    Looks for region indicators in parentheses, e.g.:
    - "Game Name (USA).zip" -> ['us']
    - "Game (Japan, USA).nes" -> ['jp', 'us']
    - "Game (Europe) (En,Fr,De).zip" -> ['eu']
    
    Args:
        filename: ROM filename
        
    Returns:
        List of detected region codes (lowercase, e.g., ['us', 'eu'])
        Empty list if no regions detected
    """
    detected_regions = []
    
    # Language codes to ignore (these are not regions)
    language_codes = {'en', 'fr', 'de', 'es', 'it', 'nl', 'pt', 'ja', 'ko', 'zh'}
    
    # Extract content from parentheses
    paren_content = re.findall(r'\(([^)]+)\)', filename)
    
    for content in paren_content:
        # Split by commas to handle multiple regions
        parts = [p.strip() for p in content.split(',')]
        
        for part in parts:
            # Skip language codes
            if part.lower() in language_codes:
                continue
            
            # Check each region code
            for region_code, indicators in REGION_CODES.items():
                for indicator in indicators:
                    if part.upper() == indicator.upper():
                        if region_code not in detected_regions:
                            detected_regions.append(region_code)
                        break
    
    return detected_regions


def select_best_region(
    available_regions: List[str],
    rom_filename: str,
    preferred_regions: Optional[List[str]] = None
) -> Optional[str]:
    """
    Select the best region from available options.
    
    Priority order:
    1. Regions detected in ROM filename (ordered by preferred_regions)
    2. Remaining regions from preferred_regions list
    3. None if no match found
    
    Args:
        available_regions: List of region codes available in API response
        rom_filename: ROM filename for region detection
        preferred_regions: User-configured region priority list
                          (default: ['us', 'wor', 'eu', 'jp'])
        
    Returns:
        Best matching region code, or None if no match
        
    Example:
        ROM: "Game (Japan, USA).nes"
        Available: ['us', 'jp', 'eu']
        Preferred: ['us', 'wor', 'eu', 'jp']
        
        Detected from ROM: ['jp', 'us']
        Priority order: ['us', 'jp', 'wor', 'eu']  # ROM regions first, ordered by config
        Result: 'us' (first match in priority order)
    """
    if not available_regions:
        logger.debug(f"    select_best_region: no available regions")
        return None
    
    # Default region preferences
    if preferred_regions is None:
        preferred_regions = ['us', 'wor', 'eu', 'jp']
    
    # Detect regions from ROM filename
    rom_regions = detect_region_from_filename(rom_filename)
    logger.debug(f"    select_best_region: ROM regions = {rom_regions}, preferred = {preferred_regions}")
    
    # Build priority list:
    # 1. ROM regions, ordered by preferred_regions
    # 2. Remaining preferred_regions
    priority_list = []
    
    # Add ROM regions in preferred_regions order
    for region in preferred_regions:
        if region in rom_regions:
            priority_list.append(region)
    
    # Add remaining preferred regions
    for region in preferred_regions:
        if region not in priority_list:
            priority_list.append(region)
    
    logger.debug(f"    select_best_region: priority list = {priority_list}")
    
    # Find first match in priority list
    for region in priority_list:
        if region in available_regions:
            logger.debug(f"    select_best_region: matched region '{region}'")
            return region
    
    # No match in priority list - check if any ROM region is available
    # (handles case where ROM has region not in preferred_regions)
    for region in rom_regions:
        if region in available_regions:
            logger.debug(f"    select_best_region: matched ROM region '{region}' (not in preferred list)")
            return region
    
    logger.debug(f"    select_best_region: no match found")
    return None


def get_media_for_region(
    media_list: List[Dict],
    media_type: str,
    region: Optional[str] = None
) -> Optional[Dict]:
    """
    Get media entry matching type and region.
    
    Args:
        media_list: List of media dicts from API response
        media_type: Media type to find (e.g., 'box-2D', 'ss')
        region: Region code to match (e.g., 'us', 'eu')
                If None, returns first match regardless of region
        
    Returns:
        Media dict with 'url', 'format', 'region', etc.
        None if no match found
    """
    for media in media_list:
        # Check media type match
        if media.get('type') != media_type:
            continue
        
        # If region specified, check region match
        if region is not None:
            if media.get('region') == region:
                return media
        else:
            # No region specified, return first match
            return media
    
    return None


def should_use_region_filtering(media_type: str) -> bool:
    """
    Check if media type should use region filtering.
    
    Some media types (fanart, video) typically don't have region variants
    and should not use region filtering.
    
    Args:
        media_type: ScreenScraper media type
        
    Returns:
        True if region filtering should be applied, False otherwise
    """
    # Media types that don't use region filtering
    no_region_types = {'fanart', 'video'}
    
    return media_type not in no_region_types
