"""
Media URL selection and prioritization.

Selects the best media URLs from ScreenScraper API responses based on
media type, region preferences, and quality.
"""

import logging
from typing import List, Dict, Optional
from .region_selector import (
    select_best_region,
    get_media_for_region,
    should_use_region_filtering
)
from .media_types import is_supported_media_type

logger = logging.getLogger(__name__)


class MediaURLSelector:
    """
    Selects optimal media URLs from ScreenScraper API responses.
    
    Handles:
    - Media type filtering (MVP types only)
    - Region prioritization
    - Quality/format selection
    """
    
    def __init__(
        self,
        preferred_regions: Optional[List[str]] = None,
        enabled_media_types: Optional[List[str]] = None
    ):
        """
        Initialize media URL selector.
        
        Args:
            preferred_regions: Region priority list (e.g., ['us', 'wor', 'eu', 'jp'])
            enabled_media_types: Media types to download (e.g., ['box-2D', 'ss'])
                                If None, uses all supported media types
        """
        self.preferred_regions = preferred_regions or ['us', 'wor', 'eu', 'jp']
        self.enabled_media_types = enabled_media_types or [
            'box-2D', 'ss', 'sstitle', 'screenmarquee', 'box-3D',
            'box-2D-back', 'fanart', 'manuel', 'support-2D', 'video', 'mixrbv2'
        ]
    
    def select_media_urls(
        self,
        media_list: List[Dict],
        rom_filename: str
    ) -> Dict[str, Dict]:
        """
        Select best media URLs for each enabled media type.
        
        Args:
            media_list: List of media dicts from API response
            rom_filename: ROM filename for region detection
            
        Returns:
            Dict mapping media type to media info:
            {
                'box-2D': {
                    'url': 'https://...',
                    'format': 'jpg',
                    'region': 'us',
                    'type': 'box-2D'
                },
                'ss': {...},
                ...
            }
        """
        selected_media = {}
        
        logger.debug(f"Selecting media for {rom_filename}")
        logger.debug(f"Enabled media types: {self.enabled_media_types}")
        logger.debug(f"Total media items in API response: {len(media_list)}")
        
        for media_type in self.enabled_media_types:
            # Skip if not supported in MVP
            if not is_supported_media_type(media_type):
                logger.debug(f"  Skipping {media_type}: not supported")
                continue
            
            # Get all available regions for this media type
            available_regions = self._get_available_regions(media_list, media_type)
            
            if not available_regions:
                # No media available for this type
                logger.debug(f"  {media_type}: no media available")
                continue
            
            logger.debug(f"  {media_type}: available regions = {available_regions}")
            
            # Select best region
            if should_use_region_filtering(media_type):
                best_region = select_best_region(
                    available_regions,
                    rom_filename,
                    self.preferred_regions
                )
                logger.debug(f"  {media_type}: selected region = {best_region} (region filtering enabled)")
            else:
                # No region filtering - use first available
                best_region = None
                logger.debug(f"  {media_type}: no region filtering, using first available")
            
            # Get media for selected region
            media_info = get_media_for_region(media_list, media_type, best_region)
            
            if media_info:
                selected_media[media_type] = media_info
                logger.debug(f"  {media_type}: selected media with region={media_info.get('region', 'N/A')}")
            else:
                logger.debug(f"  {media_type}: no media found for region {best_region}")
        
        logger.debug(f"Final selection: {len(selected_media)} media types: {list(selected_media.keys())}")
        return selected_media
    
    def _get_available_regions(
        self,
        media_list: List[Dict],
        media_type: str
    ) -> List[str]:
        """
        Get list of available regions for a media type.
        
        Args:
            media_list: List of media dicts from API response
            media_type: Media type to check
            
        Returns:
            List of region codes with available media
            For media types without regions (video, fanart), returns [None] if media exists
        """
        regions = []
        has_regionless_media = False
        
        for media in media_list:
            if media.get('type') == media_type:
                region = media.get('region')
                if region and region not in regions:
                    regions.append(region)
                elif not region:
                    # Track that we found media without a region attribute
                    has_regionless_media = True
        
        # For media types without regions, return [None] to indicate media exists
        if not regions and has_regionless_media:
            return [None]
        
        return regions
