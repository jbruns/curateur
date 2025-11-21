"""
Main media downloader integration.

Coordinates URL selection, downloading, validation, and organization of game media.
"""

import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from .url_selector import MediaURLSelector
from .downloader import ImageDownloader
from .organizer import MediaOrganizer


class DownloadResult:
    """Result of a media download operation."""
    
    def __init__(
        self,
        media_type: str,
        success: bool,
        file_path: Optional[Path] = None,
        error: Optional[str] = None,
        dimensions: Optional[Tuple[int, int]] = None
    ):
        """
        Initialize download result.
        
        Args:
            media_type: Type of media (e.g., 'box-2D', 'ss')
            success: Whether download succeeded
            file_path: Path to downloaded file (if successful)
            error: Error message (if failed)
            dimensions: Image dimensions (width, height) if available
        """
        self.media_type = media_type
        self.success = success
        self.file_path = file_path
        self.error = error
        self.dimensions = dimensions
    
    def __repr__(self) -> str:
        if self.success:
            dims = f" ({self.dimensions[0]}x{self.dimensions[1]})" if self.dimensions else ""
            return f"DownloadResult({self.media_type}: ✓{dims})"
        else:
            return f"DownloadResult({self.media_type}: ✗ {self.error})"


class MediaDownloader:
    """
    Main media downloader coordinating all media operations.
    
    Integrates:
    - URL selection with region prioritization
    - Image downloading with retry logic
    - Image validation with Pillow
    - File organization in ES-DE structure
    """
    
    def __init__(
        self,
        media_root: Path,
        client,  # httpx.AsyncClient
        preferred_regions: Optional[List[str]] = None,
        enabled_media_types: Optional[List[str]] = None,
        timeout: int = 30,
        max_retries: int = 3,
        min_width: int = 50,
        min_height: int = 50
    ):
        """
        Initialize media downloader.
        
        Args:
            media_root: Root directory for media storage
            client: httpx.AsyncClient for HTTP requests
            preferred_regions: Region priority list
            enabled_media_types: Media types to download
            timeout: Download timeout in seconds
            max_retries: Maximum download retry attempts
            min_width: Minimum image width in pixels
            min_height: Minimum image height in pixels
        """
        self.url_selector = MediaURLSelector(
            preferred_regions=preferred_regions,
            enabled_media_types=enabled_media_types
        )
        
        self.downloader = ImageDownloader(
            client=client,
            timeout=timeout,
            max_retries=max_retries,
            min_width=min_width,
            min_height=min_height
        )
        
        self.organizer = MediaOrganizer(media_root)
    
    async def download_media_for_game(
        self,
        media_list: List[Dict],
        rom_path: str,
        system: str
    ) -> List[DownloadResult]:
        """
        Download all enabled media for a game concurrently.
        
        Args:
            media_list: List of media dicts from API response
            rom_path: Path to ROM file (for basename and region detection)
            system: System name (e.g., 'nes', 'snes')
            
        Returns:
            List of DownloadResult objects
            
        Example:
            results = await downloader.download_media_for_game(
                api_response['media'],
                'Super Mario Bros (USA).nes',
                'nes'
            )
            
            for result in results:
                if result.success:
                    print(f"Downloaded {result.media_type} to {result.file_path}")
                else:
                    print(f"Failed to download {result.media_type}: {result.error}")
        """
        # Get ROM basename for file naming
        rom_basename = self.organizer.get_rom_basename(rom_path)
        
        # Select best media URLs
        selected_media = self.url_selector.select_media_urls(media_list, rom_path)
        
        # Download all media types concurrently using asyncio.gather
        download_tasks = [
            self._download_single_media(
                media_type,
                media_info,
                system,
                rom_basename
            )
            for media_type, media_info in selected_media.items()
        ]
        
        results = await asyncio.gather(*download_tasks)
        return list(results)
    
    async def _download_single_media(
        self,
        media_type: str,
        media_info: Dict,
        system: str,
        rom_basename: str
    ) -> DownloadResult:
        """
        Download a single media file.
        
        Args:
            media_type: Media type (e.g., 'box-2D')
            media_info: Media dict with 'url', 'format', etc.
            system: System name
            rom_basename: ROM basename for file naming
            
        Returns:
            DownloadResult object
        """
        url = media_info.get('url')
        file_format = media_info.get('format', 'jpg')
        
        if not url:
            return DownloadResult(
                media_type=media_type,
                success=False,
                error="No URL provided"
            )
        
        # Get output path
        output_path = self.organizer.get_media_path(
            system,
            media_type,
            rom_basename,
            file_format
        )
        
        # Skip image validation for non-image types (PDFs, videos)
        validate = media_type not in ['manuel', 'video']
        
        # Download and validate
        success, error = await self.downloader.download(url, output_path, validate=validate)
        
        if success:
            # Get dimensions (only for images)
            dimensions = None
            if media_type not in ['manuel', 'video']:
                dimensions = self.downloader.get_image_dimensions(output_path)
            
            return DownloadResult(
                media_type=media_type,
                success=True,
                file_path=output_path,
                dimensions=dimensions
            )
        else:
            return DownloadResult(
                media_type=media_type,
                success=False,
                error=error
            )
    
    def get_media_summary(self, results: List[DownloadResult]) -> Dict:
        """
        Generate summary statistics for download results.
        
        Args:
            results: List of DownloadResult objects
            
        Returns:
            Dict with summary statistics:
            {
                'total': 4,
                'successful': 3,
                'failed': 1,
                'success_rate': 0.75,
                'by_type': {
                    'box-2D': True,
                    'ss': True,
                    'sstitle': False,
                    'screenmarquee': True
                }
            }
        """
        total = len(results)
        successful = sum(1 for r in results if r.success)
        failed = total - successful
        
        by_type = {r.media_type: r.success for r in results}
        
        return {
            'total': total,
            'successful': successful,
            'failed': failed,
            'success_rate': successful / total if total > 0 else 0.0,
            'by_type': by_type
        }
    
    def check_existing_media(
        self,
        system: str,
        rom_basename: str
    ) -> Dict[str, bool]:
        """
        Check which media files already exist for a ROM.
        
        Args:
            system: System name
            rom_basename: ROM basename
            
        Returns:
            Dict mapping media type to existence status:
            {
                'box-2D': True,
                'ss': False,
                'sstitle': True,
                'screenmarquee': False
            }
        """
        existing = {}
        
        for media_type in self.url_selector.enabled_media_types:
            # Check with common extensions
            for ext in ['jpg', 'png', 'gif', 'webp']:
                path = self.organizer.get_media_path(
                    system,
                    media_type,
                    rom_basename,
                    ext
                )
                if self.organizer.file_exists(path):
                    existing[media_type] = True
                    break
            else:
                existing[media_type] = False
        
        return existing
