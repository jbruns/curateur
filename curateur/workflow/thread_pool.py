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
    - Single unified worker pool (each worker processes one ROM end-to-end)
    - Dynamic pool sizing based on API quota
    - Active work tracking for UI display
    - Graceful degradation to single-threaded
    
    Example:
        manager = ThreadPoolManager(config)
        
        # Initialize based on API limits
        manager.initialize_pools({'maxthreads': 4})
        
        # Submit ROM batch (each worker does full ROM processing)
        for rom, result in manager.submit_rom_batch(process_func, rom_list, ui_callback):
            handle_result(rom, result)
        
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
        self.worker_pool: Optional[ThreadPoolExecutor] = None
        self.max_threads = 1  # Conservative default
        self.lock = threading.Lock()
        self._initialized = False
        
        # Work tracking for UI display
        self._active_work_count = 0
        self._shutdown_flag = False
        
        # Pending rescale tracking
        self._pending_rescale = False
        self._pending_max_threads = 1
    
    def initialize_pools(self, api_provided_limits: Optional[Dict[str, Any]] = None) -> None:
        """
        Initialize thread pool based on API limits
        
        Args:
            api_provided_limits: dict with 'maxthreads' from API response
        """
        with self.lock:
            if self._initialized:
                logger.debug("Thread pool already initialized")
                return
            
            # Determine max threads (respects ScreenScraper's maxthreads limit)
            self.max_threads = self._determine_max_threads(api_provided_limits)
            
            # Create single unified worker pool
            # Each worker handles one ROM end-to-end (metadata + media downloads)
            self.worker_pool = ThreadPoolExecutor(
                max_workers=self.max_threads,
                thread_name_prefix="worker"
            )
            
            self._initialized = True
            
            logger.info(
                f"Thread pool initialized: {self.max_threads} workers (ScreenScraper limit)"
            )
    
    def rescale_pools(self, api_provided_limits: Dict[str, Any]) -> bool:
        """
        Dynamically rescale thread pool based on updated API limits.
        
        This allows scaling up after the first API response reveals actual maxthreads.
        The pool is recreated with new limits. Any in-flight work will complete
        before the pool is shut down.
        
        Args:
            api_provided_limits: dict with 'maxthreads' from API response
        
        Returns:
            True if pool was rescaled, False if no change needed
        """
        new_max_threads = self._determine_max_threads(api_provided_limits)
        
        with self.lock:
            if not self._initialized:
                # Not yet initialized, just initialize with new limits
                logger.info(f"Thread pool not yet initialized, initializing with {new_max_threads} threads")
                self.initialize_pools(api_provided_limits)
                return True
            
            if new_max_threads == self.max_threads:
                # No change needed
                logger.debug(f"Thread count unchanged at {self.max_threads}")
                return False
            
            # Check if we're being called from within a worker thread
            current_thread = threading.current_thread()
            if current_thread.name.startswith('worker'):
                # Cannot rescale from within a worker thread - defer it
                logger.info(
                    f"Deferring thread pool rescale: {self.max_threads} -> {new_max_threads} workers "
                    f"(called from worker thread {current_thread.name})"
                )
                self._pending_rescale = True
                self._pending_max_threads = new_max_threads
                return False  # Not rescaled yet, but will be
            
            # Safe to rescale from main thread
            logger.info(
                f"Rescaling thread pool: {self.max_threads} -> {new_max_threads} workers"
            )
            
            # Shut down existing pool (wait for in-flight work)
            if self.worker_pool:
                self.worker_pool.shutdown(wait=True)
            
            # Update max threads
            self.max_threads = new_max_threads
            
            # Recreate pool with new limit
            self.worker_pool = ThreadPoolExecutor(
                max_workers=self.max_threads,
                thread_name_prefix="worker"
            )
            
            # Reset active work count after rescale
            self._active_work_count = 0
            
            logger.info(
                f"Thread pool rescaled: {self.max_threads} workers"
            )
            return True
    
    def apply_pending_rescale(self) -> bool:
        """
        Apply a pending rescale that was deferred from a worker thread.
        Should be called from the main thread between batches.
        
        Returns:
            True if rescale was applied, False if no pending rescale
        """
        with self.lock:
            if not self._pending_rescale:
                return False
            
            new_max_threads = self._pending_max_threads
            logger.info(
                f"Applying deferred thread pool rescale: {self.max_threads} -> {new_max_threads} workers"
            )
            
            # Shut down existing pool (safe - we're not in a worker thread)
            if self.worker_pool:
                self.worker_pool.shutdown(wait=True)
            
            # Update max threads
            self.max_threads = new_max_threads
            
            # Recreate pool with new limit
            self.worker_pool = ThreadPoolExecutor(
                max_workers=self.max_threads,
                thread_name_prefix="worker"
            )
            
            # Reset active work count after rescale
            self._active_work_count = 0
            
            # Clear pending flag
            self._pending_rescale = False
            
            logger.info(
                f"Thread pool rescaled: {self.max_threads} workers"
            )
            return True

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
    
    def submit_rom_batch(
        self,
        rom_processor: Callable,
        rom_batch: list,
        operation_callback: Optional[Callable[[str, str, str, str, Optional[float]], None]] = None
    ) -> Iterator[Tuple[Any, Any]]:
        """
        Submit batch of ROMs for end-to-end processing (hash -> API -> download -> verify)
        
        Each ROM is processed completely by a single worker thread. The operation_callback
        is invoked for each processing stage to update UI.
        
        Args:
            rom_processor: Function to call for each ROM (signature: func(rom, callback) -> result)
            rom_batch: List of ROM info dicts
            operation_callback: Optional callback for operation updates
                                Signature: callback(thread_name, rom_name, operation, details, progress_pct)
        
        Yields:
            Tuple of (rom, result) as they complete
            If error occurs, result will be dict with 'error' key
        
        Example:
            def process_rom(rom, callback):
                # callback will be called at each stage: hashing, API, downloading, verifying
                return orchestrator.scrape_rom(rom, callback)
            
            for rom, result in manager.submit_rom_batch(process_rom, roms, ui_callback):
                if 'error' in result:
                    logger.error(f"Failed: {rom['filename']}")
                else:
                    logger.info(f"Completed: {rom['filename']}")
        """
        if not self._initialized:
            self.initialize_pools()
        
        if not self.worker_pool:
            # Fallback to sequential processing
            logger.warning("Worker pool not initialized, processing ROMs sequentially")
            for rom in rom_batch:
                try:
                    result = rom_processor(rom, operation_callback)
                    yield (rom, result)
                except Exception as e:
                    yield (rom, {'error': str(e)})
            return
        
        # Submit all tasks with work tracking
        futures = {}
        for rom in rom_batch:
            future = self.worker_pool.submit(rom_processor, rom, operation_callback)
            futures[future] = rom
        
        # Update active count to total submitted futures
        with self.lock:
            self._active_work_count = len(futures)
        
        # Yield results as they complete and track remaining work
        completed = 0
        for future in as_completed(futures):
            rom = futures[future]
            try:
                result = future.result()
                yield (rom, result)
            except Exception as e:
                logger.error(f"ROM processing failed for {rom}: {e}")
                yield (rom, {'error': str(e)})
            finally:
                # Update counter to reflect remaining work
                completed += 1
                with self.lock:
                    if self._shutdown_flag:
                        self._active_work_count = 0
                    else:
                        self._active_work_count = len(futures) - completed
    
    def shutdown(self, wait: bool = True) -> None:
        """
        Gracefully shutdown worker pool
        
        Args:
            wait: If True, wait for running tasks to complete
        """
        with self.lock:
            # Set shutdown flag to immediately zero active work counter
            self._shutdown_flag = True
            self._active_work_count = 0
            
            if self.worker_pool:
                logger.debug("Shutting down worker pool...")
                self.worker_pool.shutdown(wait=wait)
                self.worker_pool = None
            
            self._initialized = False
            logger.info("Thread pool shut down")
    
    def get_stats(self) -> dict:
        """
        Get thread pool statistics
        
        Returns:
            Dictionary with pool statistics including active workers
        """
        with self.lock:
            return {
                'active_threads': self._active_work_count,
                'max_threads': self.max_threads,
                'initialized': self._initialized
            }
    
    def is_initialized(self) -> bool:
        """
        Check if pools are initialized
        
        Returns:
            True if pools are initialized
        """
        return self._initialized
