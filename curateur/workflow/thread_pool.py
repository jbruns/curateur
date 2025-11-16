"""
Thread pool management for parallel operations

Manages parallel API calls and downloads within ScreenScraper limits.
"""

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Callable, Iterator, Tuple, Any, Dict

logger = logging.getLogger(__name__)


class ThreadPoolManager:
    """
    Manages parallel operations within ScreenScraper thread limits
    
    Features:
    - Respects API-provided maxthreads limit
    - Separate pools for API and downloads
    - Dynamic pool sizing based on API quota
    - Graceful degradation to single-threaded
    
    Example:
        manager = ThreadPoolManager(config)
        
        # Initialize based on API limits
        manager.initialize_pools({'maxthreads': 4})
        
        # Submit API batch
        for rom, result in manager.submit_api_batch(scrape_func, rom_list):
            process_result(rom, result)
        
        # Submit download batch
        for media, result in manager.submit_download_batch(download_func, media_list):
            handle_download(media, result)
        
        # Clean shutdown
        manager.shutdown()
    """
    
    def __init__(self, config: dict):
        """
        Initialize thread pool manager
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.api_pool: Optional[ThreadPoolExecutor] = None
        self.download_pool: Optional[ThreadPoolExecutor] = None
        self.max_threads = 1  # Conservative default
        self.lock = threading.Lock()
        self._initialized = False
    
    def initialize_pools(self, api_provided_limits: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize thread pools based on API limits
        
        Args:
            api_provided_limits: dict with 'maxthreads' from API response
        """
        with self.lock:
            if self._initialized:
                logger.debug("Thread pools already initialized")
                return
            
            # Determine max threads
            self.max_threads = self._determine_max_threads(api_provided_limits)
            
            # Create pools (API uses fewer threads than downloads)
            api_workers = max(1, self.max_threads // 2)
            download_workers = self.max_threads
            
            self.api_pool = ThreadPoolExecutor(
                max_workers=api_workers,
                thread_name_prefix="api"
            )
            self.download_pool = ThreadPoolExecutor(
                max_workers=download_workers,
                thread_name_prefix="download"
            )
            
            self._initialized = True
            
            logger.info(
                f"Thread pools initialized: API={api_workers}, Download={download_workers}"
            )
    
    def _determine_max_threads(self, api_limits: Optional[Dict[str, Any]]) -> int:
        """
        Determine max threads considering:
        1. API-provided maxthreads
        2. User override (if enabled and valid)
        3. Conservative default (1)
        
        Args:
            api_limits: API-provided limits dict
        
        Returns:
            Maximum thread count to use
        """
        # Check for rate limit override
        from curateur.api.rate_override import RateLimitOverride
        override = RateLimitOverride(self.config)
        
        if override.is_enabled():
            limits = override.get_effective_limits(api_limits)
            return limits.max_threads
        
        # Use API-provided limit
        if api_limits and 'maxthreads' in api_limits:
            return int(api_limits['maxthreads'])
        
        # Fall back to config or default
        config_threads = self.config.get('scraping', {}).get('max_threads', 0)
        if config_threads > 0:
            return config_threads
        
        return 1  # Conservative default
    
    def submit_api_batch(
        self,
        api_func: Callable,
        rom_batch: list
    ) -> Iterator[Tuple[Any, Any]]:
        """
        Submit batch of API requests
        
        Args:
            api_func: Function to call for each ROM (signature: func(rom) -> result)
            rom_batch: List of ROM info dicts
        
        Yields:
            Tuple of (rom, result) as they complete
            If error occurs, result will be dict with 'error' key
        
        Example:
            def scrape_rom(rom):
                return api_client.get_game_info(rom)
            
            for rom, result in manager.submit_api_batch(scrape_rom, roms):
                if 'error' in result:
                    logger.error(f"Failed: {rom['filename']} - {result['error']}")
                else:
                    process_result(rom, result)
        """
        if not self._initialized:
            self.initialize_pools()
        
        if not self.api_pool:
            # Fallback to sequential processing
            logger.warning("API pool not initialized, processing sequentially")
            for rom in rom_batch:
                try:
                    result = api_func(rom)
                    yield (rom, result)
                except Exception as e:
                    yield (rom, {'error': str(e)})
            return
        
        # Submit all tasks
        futures = {}
        for rom in rom_batch:
            future = self.api_pool.submit(api_func, rom)
            futures[future] = rom
        
        # Yield results as they complete
        for future in as_completed(futures):
            rom = futures[future]
            try:
                result = future.result()
                yield (rom, result)
            except Exception as e:
                logger.error(f"API call failed for {rom}: {e}")
                yield (rom, {'error': str(e)})
    
    def submit_download_batch(
        self,
        download_func: Callable,
        media_batch: list
    ) -> Iterator[Tuple[Any, Any]]:
        """
        Submit batch of media downloads
        
        Args:
            download_func: Function to call for each media (signature: func(media) -> result)
            media_batch: List of media info dicts
        
        Yields:
            Tuple of (media, result) as they complete
            If error occurs, result will be dict with 'error' key
        
        Example:
            def download_media(media):
                return downloader.download(media['url'], media['path'])
            
            for media, result in manager.submit_download_batch(download_media, media_list):
                if 'error' in result:
                    logger.error(f"Download failed: {media['type']} - {result['error']}")
                else:
                    verify_media(media, result)
        """
        if not self._initialized:
            self.initialize_pools()
        
        if not self.download_pool:
            # Fallback to sequential processing
            logger.warning("Download pool not initialized, processing sequentially")
            for media in media_batch:
                try:
                    result = download_func(media)
                    yield (media, result)
                except Exception as e:
                    yield (media, {'error': str(e)})
            return
        
        # Submit all tasks
        futures = {}
        for media in media_batch:
            future = self.download_pool.submit(download_func, media)
            futures[future] = media
        
        # Yield results as they complete
        for future in as_completed(futures):
            media = futures[future]
            try:
                result = future.result()
                yield (media, result)
            except Exception as e:
                logger.error(f"Download failed for {media}: {e}")
                yield (media, {'error': str(e)})
    
    def shutdown(self, wait: bool = True) -> None:
        """
        Gracefully shutdown all pools
        
        Args:
            wait: If True, wait for running tasks to complete
        """
        with self.lock:
            if self.api_pool:
                logger.debug("Shutting down API pool...")
                self.api_pool.shutdown(wait=wait)
                self.api_pool = None
            
            if self.download_pool:
                logger.debug("Shutting down download pool...")
                self.download_pool.shutdown(wait=wait)
                self.download_pool = None
            
            self._initialized = False
            logger.info("Thread pools shut down")
    
    def get_stats(self) -> dict:
        """
        Get thread pool statistics
        
        Returns:
            Dictionary with pool statistics
        """
        return {
            'max_threads': self.max_threads,
            'api_pool_initialized': self.api_pool is not None,
            'download_pool_initialized': self.download_pool is not None,
            'initialized': self._initialized
        }
    
    def is_initialized(self) -> bool:
        """
        Check if pools are initialized
        
        Returns:
            True if pools are initialized
        """
        return self._initialized
