"""
Media-Only Download Handler

Downloads missing media for existing gamelist entries without updating metadata.
Preserves existing gamelist.xml structure and content.
"""

from pathlib import Path
from typing import Dict, List, Set, Optional
import logging

logger = logging.getLogger(__name__)


class MediaOnlyHandler:
    """
    Downloads media without modifying gamelist metadata
    
    Workflow:
    1. Parse existing gamelist.xml entries
    2. Make API call to get media URLs for each ROM
    3. Download only missing media types
    4. Skip download if skip_existing_media=true and file exists
    5. Preserve all gamelist metadata (no updates)
    
    Key difference from full scrape:
    - API response used ONLY for media URLs
    - No metadata updates to gamelist
    - No gamelist write operations
    """
    
    def __init__(self, config: dict, media_downloader):
        """
        Initialize media-only handler
        
        Args:
            config: Configuration dictionary
            media_downloader: MediaDownloader instance
        """
        self.config = config
        self.media_downloader = media_downloader
        self.skip_existing = config.get('media', {}).get('skip_existing_media', True)
        logger.info(
            f"Media-Only Handler initialized "
            f"(skip_existing={self.skip_existing})"
        )
    
    def determine_missing_media(self, rom_info: dict, media_root: Path, 
                               system_name: str, enabled_types: List[str]) -> List[str]:
        """
        Check which media types are missing for a ROM
        
        Args:
            rom_info: ROM info dict with 'basename'
            media_root: Root media directory
            system_name: System name
            enabled_types: List of enabled media types
        
        Returns:
            List of missing media types
        """
        basename = rom_info.get('basename')
        if not basename:
            return enabled_types
        
        missing_types = []
        system_media_dir = media_root / system_name
        
        for media_type in enabled_types:
            media_type_dir = system_media_dir / media_type
            
            if not media_type_dir.exists():
                # Directory doesn't exist, all media missing
                missing_types.append(media_type)
                continue
            
            # Check for any file with this basename
            matching_files = list(media_type_dir.glob(f"{basename}.*"))
            
            if not matching_files:
                missing_types.append(media_type)
        
        if missing_types:
            logger.debug(
                f"Missing media for {basename}: {', '.join(missing_types)}"
            )
        
        return missing_types
    
    async def download_missing_media(self, rom_info: dict, api_response: dict,
                                    media_root: Path, system_name: str,
                                    missing_types: List[str]) -> Dict[str, bool]:
        """
        Download only missing media types
        
        Args:
            rom_info: ROM info dict
            api_response: API response containing media URLs
            media_root: Root media directory
            system_name: System name
            missing_types: List of media types to download
        
        Returns:
            Dict mapping media type to success status
        """
        results = {}
        
        if not missing_types:
            logger.debug(f"No missing media for {rom_info.get('basename')}")
            return results
        
        # Extract media URLs from API response
        media_urls = self._extract_media_urls(api_response, missing_types)
        
        # Download each missing media type
        for media_type in missing_types:
            url = media_urls.get(media_type)
            
            if not url:
                logger.warning(
                    f"No URL available for {media_type} "
                    f"({rom_info.get('basename')})"
                )
                results[media_type] = False
                continue
            
            # Check if file exists and skip_existing is enabled
            basename = rom_info.get('basename')
            media_type_dir = media_root / system_name / media_type
            
            if self.skip_existing and media_type_dir.exists():
                existing_files = list(media_type_dir.glob(f"{basename}.*"))
                if existing_files:
                    logger.debug(
                        f"Skipping existing {media_type}: {existing_files[0].name}"
                    )
                    results[media_type] = True
                    continue
            
            # Download media
            success = await self.media_downloader.download_media(
                url=url,
                media_type=media_type,
                system_name=system_name,
                basename=basename
            )
            
            results[media_type] = success
            
            if success:
                logger.info(f"Downloaded {media_type} for {basename}")
            else:
                logger.warning(f"Failed to download {media_type} for {basename}")
        
        return results
    
    def _extract_media_urls(self, api_response: dict, 
                           media_types: List[str]) -> Dict[str, str]:
        """
        Extract media URLs from API response
        
        Args:
            api_response: ScreenScraper API response
            media_types: List of media types to extract
        
        Returns:
            Dict mapping media type to URL
        """
        urls = {}
        
        # API response structure: response['jeu']['medias']
        game_data = api_response.get('response', {}).get('jeu', {})
        medias = game_data.get('medias', [])
        
        # Map our media types to ScreenScraper media types
        type_mapping = {
            'screenshot': 'ss',
            'titlescreen': 'sstitle',
            'marquee': 'wheel',
            'box2dfront': 'box-2D',
            'box3d': 'box-3D',
            'fanart': 'fanart',
            'video': 'video-normalized',
            'manual': 'manuel',
        }
        
        for media_type in media_types:
            ss_type = type_mapping.get(media_type)
            
            if not ss_type:
                logger.warning(f"Unknown media type mapping: {media_type}")
                continue
            
            # Find matching media in API response
            for media in medias:
                if media.get('type') == ss_type:
                    # Prefer highest quality
                    url = media.get('url')
                    if url:
                        urls[media_type] = url
                        break
        
        return urls
    
    def process_rom(self, rom_info: dict, gamelist_entry: Optional[dict],
                   api_response: dict, media_root: Path, 
                   system_name: str, enabled_types: List[str]) -> Dict[str, bool]:
        """
        Process a single ROM in media-only mode
        
        Args:
            rom_info: ROM info from scanner
            gamelist_entry: Existing gamelist entry (if any)
            api_response: ScreenScraper API response
            media_root: Root media directory
            system_name: System name
            enabled_types: List of enabled media types
        
        Returns:
            Dict mapping media type to download success
        """
        # Determine which media types are missing
        missing_types = self.determine_missing_media(
            rom_info, media_root, system_name, enabled_types
        )
        
        if not missing_types:
            logger.debug(f"All media present for {rom_info.get('basename')}")
            return {}
        
        # Download missing media
        # Note: In async context, caller should await this
        # For now, return synchronous indication
        logger.info(
            f"Media-only download needed for {rom_info.get('basename')}: "
            f"{', '.join(missing_types)}"
        )
        
        return {media_type: False for media_type in missing_types}  # Placeholder
