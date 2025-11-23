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
        dimensions: Optional[Tuple[int, int]] = None,
        hash_value: Optional[str] = None
    ):
        """
        Initialize download result.
        
        Args:
            media_type: Type of media (e.g., 'box-2D', 'ss')
            success: Whether download succeeded
            file_path: Path to downloaded file (if successful)
            error: Error message (if failed)
            dimensions: Image dimensions (width, height) if available
            hash_value: Hash of downloaded file (if successful)
        """
        self.media_type = media_type
        self.success = success
        self.file_path = file_path
        self.error = error
        self.dimensions = dimensions
        self.hash_value = hash_value
    
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
        min_height: int = 50,
        hash_algorithm: str = 'crc32',
        download_semaphore: Optional[asyncio.Semaphore] = None
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
            hash_algorithm: Hash algorithm for file verification ('crc32', 'md5', 'sha1')
            download_semaphore: Optional semaphore to limit concurrent downloads globally
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
        self.hash_algorithm = hash_algorithm
        self.download_semaphore = download_semaphore
    
    async def download_media_for_game(
        self,
        media_list: List[Dict],
        rom_path: str,
        system: str,
        progress_callback: Optional[callable] = None,
        shutdown_event: Optional['asyncio.Event'] = None
    ) -> tuple[List[DownloadResult], int]:
        """
        Download all enabled media for a game concurrently.
        
        Args:
            media_list: List of media dicts from API response
            rom_path: Path to ROM file (for basename and region detection)
            system: System name (e.g., 'nes', 'snes')
            progress_callback: Optional callback(media_type, idx, total) called before each download starts
            
        Returns:
            Tuple of (list of DownloadResult objects, count of media to download)
            
        Example:
            results, selected_count = await downloader.download_media_for_game(
                api_response['media'],
                'Super Mario Bros (USA).nes',
                'nes'
            )
            
            print(f"Downloading {selected_count} media files")
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
        
        # Download media concurrently for better throughput
        results = []
        total_media = len(selected_media)
        
        async def download_with_callback(idx: int, media_type: str, media_info: Dict) -> DownloadResult:
            """Download single media file with progress callback and semaphore."""
            # Check for shutdown before starting download
            if shutdown_event and shutdown_event.is_set():
                return DownloadResult(
                    media_type=media_type,
                    success=False,
                    error="Cancelled due to shutdown"
                )
            
            # Call progress callback before starting download
            if progress_callback:
                progress_callback(media_type, idx, total_media)
            
            # Acquire semaphore if provided (limits concurrent downloads globally)
            if self.download_semaphore:
                async with self.download_semaphore:
                    return await self._download_single_media(
                        media_type, media_info, system, rom_basename
                    )
            else:
                return await self._download_single_media(
                    media_type, media_info, system, rom_basename
                )
        
        # Create download tasks for all media types
        download_tasks = [
            download_with_callback(idx, media_type, media_info)
            for idx, (media_type, media_info) in enumerate(selected_media.items(), 1)
        ]
        
        # Execute all downloads concurrently
        if download_tasks:
            results = await asyncio.gather(*download_tasks, return_exceptions=False)
        
        return results, len(selected_media)
    
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
            
            # Calculate hash asynchronously in thread pool
            import asyncio
            from curateur.scanner.hash_calculator import calculate_hash
            import logging
            logger = logging.getLogger(__name__)
            hash_value = None
            
            # Skip hashing for very small files (<50KB) - dimension validation is sufficient
            file_size = output_path.stat().st_size
            if file_size < 50 * 1024:
                logger.debug(f"Skipping hash for small {media_type} ({file_size} bytes)")
            else:
                try:
                    # Run hash calculation in thread pool to avoid blocking
                    hash_value = await asyncio.to_thread(
                        calculate_hash,
                        output_path,
                        algorithm=self.hash_algorithm,
                        size_limit=0  # No size limit for media files
                    )
                    logger.debug(f"Calculated hash for {media_type}: {hash_value}")
                except Exception as e:
                    # Hash calculation failed - continue without hash
                    logger.warning(f"Failed to calculate hash for {media_type} at {output_path}: {e}")
                    pass
            
            return DownloadResult(
                media_type=media_type,
                success=True,
                file_path=output_path,
                dimensions=dimensions,
                hash_value=hash_value
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
