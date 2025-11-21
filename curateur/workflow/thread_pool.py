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
    
    async def rescale_pools(self, api_provided_limits: Dict[str, Any]) -> bool:
        """
        Dynamically rescale task pool based on updated API limits.
        
        This allows scaling up after the first API response reveals actual maxthreads.
        
        Args:
            api_provided_limits: dict with 'maxthreads' from API response
        
        Returns:
            True if pool was rescaled, False if no change needed
        """
        new_max_concurrent = self._determine_max_threads(api_provided_limits)
        
        async with self._lock:
            if not self._initialized:
                # Not yet initialized, just initialize with new limits
                logger.info(f"Task pool not yet initialized, initializing with {new_max_concurrent} tasks")
                self.initialize_pools(api_provided_limits)
                return True
            
            if new_max_concurrent == self.max_concurrent:
                # No change needed
                logger.debug(f"Concurrent task count unchanged at {self.max_concurrent}")
                return False
            
            logger.info(
                f"Rescaling task pool: {self.max_concurrent} -> {new_max_concurrent} concurrent tasks"
            )
            
            # Update max concurrent tasks
            self.max_concurrent = new_max_concurrent
            
            # Create new semaphore with new limit
            self.semaphore = asyncio.Semaphore(self.max_concurrent)
            
            # Reset active work count after rescale
            self._active_work_count = 0
            
            logger.info(
                f"Task pool rescaled: {self.max_concurrent} concurrent tasks"
            )
            return True
    
    async def apply_pending_rescale(self) -> bool:
        """
        Apply a pending rescale. With async, rescaling is immediate, so this is a no-op.
        Kept for API compatibility.
        
        Returns:
            False (no pending rescale in async version)
        """
        return False

    def _determine_max_threads(self, api_limits: Optional[Dict[str, Any]]) -> int:
        """
        Determine max workers considering:
        1. API-provided maxthreads
        2. User override (if enabled and valid)
        3. Conservative default (1)
        
        Args:
            api_limits: API-provided limits dict
        
        Returns:
            Maximum worker count to use
        """
        # Check for rate limit override
        from curateur.api.rate_override import RateLimitOverride
        override = RateLimitOverride(self.config)
        
        if override.is_enabled():
            limits = override.get_effective_limits(api_limits)
            logger.info(f"Using override maxthreads: {limits.max_threads}")
            return limits.max_threads
        
        # Use API-provided limit
        if api_limits and 'maxthreads' in api_limits:
            threads = int(api_limits['maxthreads'])
            logger.info(f"Using API-provided maxthreads: {threads}")
            return threads
        
        # Fall back to config or default
        config_threads = self.config.get('scraping', {}).get('max_threads', 0)
        if config_threads > 0:
            logger.info(f"Using config maxthreads: {config_threads}")
            return config_threads
        
        logger.info("Using default maxthreads: 1")
        return 1  # Conservative default
    
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
            async with self.semaphore:
                async with self._lock:
                    self._active_work_count += 1
                try:
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
