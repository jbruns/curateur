"""
Async task pool management for parallel operations

Manages parallel API calls and downloads within ScreenScraper limits.
"""

import asyncio
import logging
from typing import Optional, Callable, AsyncIterator, Tuple, Any, Dict, Awaitable

logger = logging.getLogger(__name__)


class ThreadPoolManager:
    """
    Manages parallel operations within ScreenScraper worker limits
    
    Now using asyncio tasks instead of thread pool for better responsiveness.
    
    Features:
    - Respects API-provided maxthreads limit (worker count)
    - Concurrent task execution with asyncio.gather()
    - Dynamic pool sizing based on API quota
    - Active work tracking for UI display
    - Graceful task cancellation
    
    Example:
        manager = ThreadPoolManager(config)
        
        # Initialize based on API limits
        manager.initialize_pools({'maxthreads': 4})
        
        # Submit ROM batch (each task does full ROM processing)
        async for rom, result in manager.submit_rom_batch(process_func, rom_list, ui_callback):
            handle_result(rom, result)
        
        # Clean shutdown
        await manager.shutdown()
    """
    
    def __init__(self, config: dict):
        """
        Initialize task pool manager
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.max_concurrent = 1  # Conservative default
        self.semaphore: Optional[asyncio.Semaphore] = None
        self._initialized = False
        
        # Work tracking for UI display
        self._active_work_count = 0
        self._lock = asyncio.Lock()
        self._shutdown_flag = False
        
        # Pending rescale tracking
        self._pending_rescale = False
        self._pending_max_concurrent = 1
    
    def initialize_pools(self, api_provided_limits: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize task pool based on API limits
        
        Args:
            api_provided_limits: dict with 'maxthreads' from API response
        """
        if self._initialized:
            logger.debug("Task pool already initialized")
            return
        
        # Determine max concurrent tasks (respects ScreenScraper's maxthreads limit)
        self.max_concurrent = self._determine_max_threads(api_provided_limits)
        
        # Create semaphore to limit concurrent tasks
        self.semaphore = asyncio.Semaphore(self.max_concurrent)
        
        self._initialized = True
        
        logger.info(
            f"Task pool initialized: {self.max_concurrent} concurrent tasks (ScreenScraper limit)"
        )
    
    def _determine_max_threads(self, api_limits: Optional[Dict[str, Any]]) -> int:
        """
        Determine max workers considering:
        1. API-provided maxthreads (authoritative upper bound)
        2. User override (if enabled) - clamped to API limit
        3. Conservative default (1)
        
        Args:
            api_limits: API-provided limits dict
        
        Returns:
            Maximum worker count to use (1 <= result <= API maxthreads)
        """
        # Get API-provided limit (authoritative upper bound)
        api_maxthreads = None
        if api_limits and 'maxthreads' in api_limits:
            api_maxthreads = int(api_limits['maxthreads'])
        
        # Check if rate limit override is enabled
        rate_limit_override_enabled = self.config.get('scraping', {}).get('rate_limit_override_enabled', False)
        
        if rate_limit_override_enabled:
            # User has override enabled - use RateLimitOverride to get effective limits
            from curateur.api.rate_override import RateLimitOverride
            override = RateLimitOverride(self.config)
            limits = override.get_effective_limits(api_limits)
            threads = limits.max_threads
            logger.info(f"Using rate_limit_override maxthreads: {threads}")
            return threads
        
        # Use API-provided limit (no override)
        if api_maxthreads is not None:
            logger.info(f"Using API-provided maxthreads: {api_maxthreads}")
            return api_maxthreads
        
        # Fall back to conservative default if API limit not available
        logger.info("Using default maxthreads: 1 (API limit not yet available)")
        return 1
    
    async def submit_rom_batch(
        self,
        rom_processor: Callable[[Any, Optional[Callable]], Awaitable[Any]],
        rom_batch: list,
        operation_callback: Optional[Callable[[str, str, str, str, Optional[float], Optional[int], Optional[int]], None]] = None
    ) -> AsyncIterator[Tuple[Any, Any]]:
        """
        Submit batch of ROMs for end-to-end async processing (hash -> API -> download -> verify)
        
        Each ROM is processed completely by an async task. The operation_callback
        is invoked for each processing stage to update UI.
        
        Args:
            rom_processor: Async function to call for each ROM (signature: async func(rom, callback) -> result)
            rom_batch: List of ROM info dicts
            operation_callback: Optional callback for operation updates
                                Signature: callback(worker_name, rom_name, operation, details, progress_pct, total_tasks, completed_tasks)
        
        Yields:
            Tuple of (rom, result) as they complete
            If error occurs, result will be dict with 'error' key
        
        Example:
            async def process_rom(rom, callback):
                # callback will be called at each stage: hashing, API, downloading, verifying
                return await orchestrator.scrape_rom(rom, callback)
            
            async for rom, result in manager.submit_rom_batch(process_rom, roms, ui_callback):
                if 'error' in result:
                    logger.error(f"Failed: {rom['filename']}")
                else:
                    logger.info(f"Completed: {rom['filename']}")
        """
        if not self._initialized:
            self.initialize_pools()
        
        if not self.semaphore:
            # Fallback to sequential processing
            logger.warning("Task pool not initialized, processing ROMs sequentially")
            for rom in rom_batch:
                try:
                    result = await rom_processor(rom, operation_callback)
                    yield (rom, result)
                except Exception as e:
                    logger.error(f"ROM processing failed for {rom}: {e}")
                    yield (rom, {'error': str(e)})
            return
        
        # Create async wrapper that respects semaphore and tracks work
        async def process_with_semaphore(rom):
            # Increment active count before acquiring semaphore (worker is active during entire processing)
            async with self._lock:
                self._active_work_count += 1
            try:
                async with self.semaphore:
                    result = await rom_processor(rom, operation_callback)
                    return (rom, result)
            except Exception as e:
                logger.error(f"ROM processing failed for {rom}: {e}")
                return (rom, {'error': str(e)})
            finally:
                async with self._lock:
                    if not self._shutdown_flag:
                        self._active_work_count = max(0, self._active_work_count - 1)
        
        # Create all tasks
        tasks = [asyncio.create_task(process_with_semaphore(rom)) for rom in rom_batch]
        
        # Yield results as they complete
        for coro in asyncio.as_completed(tasks):
            try:
                rom, result = await coro
                yield (rom, result)
            except Exception as e:
                logger.error(f"Task failed: {e}")
                # Try to extract ROM from failed task
                yield (None, {'error': str(e)})
    
    async def shutdown(self, wait: bool = True) -> None:
        """
        Gracefully shutdown task pool
        
        Args:
            wait: If True, wait for running tasks to complete (not used in async version)
        """
        async with self._lock:
            # Set shutdown flag to immediately zero active work counter
            self._shutdown_flag = True
            self._active_work_count = 0
            
            self.semaphore = None
            self._initialized = False
            logger.info("Task pool shut down")
    
    async def get_stats(self) -> dict:
        """
        Get task pool statistics
        
        Returns:
            Dictionary with pool statistics including active workers
        """
        async with self._lock:
            return {
                'active_threads': self._active_work_count,
                'max_threads': self.max_concurrent,
                'initialized': self._initialized
            }
    
    def is_initialized(self) -> bool:
        """
        Check if pools are initialized
        
        Returns:
            True if pools are initialized
        """
        return self._initialized
