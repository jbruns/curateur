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
    Manages parallel operations within ScreenScraper worker limits using producer-consumer pattern
    
    Workers continuously pull work from queue until system completion.
    
    Features:
    - Respects API-provided maxthreads limit (worker count)
    - Concurrent worker execution with asyncio
    - Dynamic pool sizing based on API quota
    - Active work tracking for UI display
    - Graceful shutdown with completion waiting
    
    Example:
        manager = ThreadPoolManager(config)
        
        # Initialize based on API limits
        manager.initialize_pools({'maxthreads': 4})
        
        # Spawn workers
        manager.spawn_workers(work_queue, process_rom, ui_callback, count=1)
        
        # Scale after authentication
        await manager.scale_workers(4)
        
        # Wait for all work to complete
        await manager.wait_for_completion()
        
        # Clean shutdown
        await manager.stop_workers()
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
        self._shutdown_event = asyncio.Event()
        
        # Worker management
        self._worker_tasks: list = []
        self._work_queue = None
        self._rom_processor = None
        self._operation_callback = None
        
        # Result collection
        self._results: list = []
        self._results_lock = asyncio.Lock()
    
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
            workers = limits.max_workers
            logger.info(f"Using rate_limit_override max_workers: {workers}")
            return workers
        
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
        DEPRECATED: Legacy batch processing method (kept for compatibility)
        
        Use spawn_workers() + wait_for_completion() for producer-consumer pattern instead.
        
        Submit batch of ROMs for end-to-end async processing (hash -> API -> download -> verify)
        
        Each ROM is processed completely by an async task. The operation_callback
        is invoked for each processing stage to update UI.
        
        Args:
            rom_processor: Async function to call for each ROM (signature: async func(rom, callback) -> result)
            rom_batch: List of ROM info dicts
            operation_callback: Optional callback for operation updates
        
        Yields:
            Tuple of (rom, result) as they complete
        """
        logger.warning("submit_rom_batch() is deprecated, use spawn_workers() + wait_for_completion()")
        
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
        
        # Create async wrapper that respects semaphore
        async def process_with_semaphore(rom):
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
                    self._active_work_count = max(0, self._active_work_count - 1)
        
        # Create all tasks and yield as they complete
        tasks = [asyncio.create_task(process_with_semaphore(rom)) for rom in rom_batch]
        
        for coro in asyncio.as_completed(tasks):
            try:
                rom, result = await coro
                yield (rom, result)
            except Exception as e:
                logger.error(f"Task failed: {e}")
                yield (None, {'error': str(e)})
    
    def spawn_workers(
        self,
        work_queue: 'WorkQueueManager',
        rom_processor: Callable[[Any, Optional[Callable]], Awaitable[Any]],
        operation_callback: Optional[Callable[[str, str, str, str, Optional[float], Optional[int], Optional[int]], None]],
        count: int
    ) -> None:
        """
        Spawn worker coroutines that continuously process items from work queue
        
        Workers pull work items from queue, process them, and repeat until:
        - Queue is empty AND system marked complete
        - Shutdown event is set
        
        Args:
            work_queue: WorkQueueManager instance to pull work from
            rom_processor: Async function to process each ROM
            operation_callback: Optional UI callback for progress updates
            count: Number of workers to spawn
        """
        if not self._initialized:
            self.initialize_pools()
        
        # Store references for scaling
        self._work_queue = work_queue
        self._rom_processor = rom_processor
        self._operation_callback = operation_callback
        
        logger.info(f"Spawning {count} worker(s)")
        
        for i in range(count):
            worker_task = asyncio.create_task(self._worker_loop(i + 1))
            self._worker_tasks.append(worker_task)
    
    async def _worker_loop(self, worker_id: int) -> None:
        """
        Worker coroutine that continuously processes work items
        
        Args:
            worker_id: Numeric identifier for this worker (for logging)
        """
        logger.debug(f"Worker {worker_id} started")
        
        while not self._shutdown_event.is_set():
            # Check if work queue is done
            if self._work_queue.is_system_complete() and self._work_queue.is_empty():
                logger.debug(f"Worker {worker_id} exiting - system complete and queue empty")
                break
            
            # Check for shutdown before getting new work
            if self._shutdown_event.is_set():
                logger.info(f"Worker {worker_id} shutting down - not starting new work")
                break
            
            # Get next work item
            try:
                work_item = await asyncio.wait_for(
                    self._work_queue.get_work_async(),
                    timeout=1.0  # Check shutdown event periodically
                )
            except asyncio.TimeoutError:
                # No work available, check again
                continue
            except asyncio.CancelledError:
                logger.debug(f"Worker {worker_id} cancelled")
                break
            
            if work_item is None:
                # System complete
                logger.debug(f"Worker {worker_id} received None - system complete")
                break
            
            # Check shutdown again before starting work
            if self._shutdown_event.is_set():
                logger.info(f"Worker {worker_id} not starting {work_item.rom_info.get('filename', 'unknown')} - shutdown requested")
                # Put work back in queue for graceful handling
                self._work_queue.queue.put_nowait((work_item.priority, work_item))
                break
            
            # Reconstruct ROMInfo from work item
            from ..scanner.rom_types import ROMType
            from pathlib import Path
            rom_info_dict = work_item.rom_info
            
            try:
                rom_info = type('ROMInfo', (), {
                    'path': Path(rom_info_dict['path']),
                    'filename': rom_info_dict['filename'],
                    'basename': rom_info_dict['basename'],
                    'rom_type': ROMType(rom_info_dict['rom_type']),
                    'system': rom_info_dict['system'],
                    'query_filename': rom_info_dict['query_filename'],
                    'file_size': rom_info_dict['file_size'],
                    'hash_type': rom_info_dict.get('hash_type', 'crc32'),
                    'hash_value': rom_info_dict.get('hash_value'),
                    'crc_size_limit': rom_info_dict.get('crc_size_limit', 1073741824),
                    'disc_files': [Path(f) for f in rom_info_dict['disc_files']] if rom_info_dict.get('disc_files') else None,
                    'contained_file': Path(rom_info_dict['contained_file']) if rom_info_dict.get('contained_file') else None
                })()
            except Exception as e:
                logger.error(f"Worker {worker_id} failed to reconstruct ROMInfo: {e}")
                await self._work_queue.mark_processed(work_item)
                continue
            
            # Process ROM with semaphore (respects concurrency limit)
            # This ensures in-flight work completes even during shutdown
            async with self._lock:
                self._active_work_count += 1
            
            try:
                logger.debug(f"Worker {worker_id} starting {rom_info.filename}")
                async with self.semaphore:
                    result = await self._rom_processor(rom_info, self._operation_callback, self._shutdown_event)
                    
                logger.debug(f"Worker {worker_id} completed {rom_info.filename}")
                
                # Store result
                async with self._results_lock:
                    self._results.append((rom_info, result))
                    
                # Mark as processed
                await self._work_queue.mark_processed(work_item)
                
                # Handle failures (retry if needed) - but not during shutdown
                if not self._shutdown_event.is_set() and not result.success and result.error:
                    # Check if retryable
                    if 'timeout' in result.error.lower() or 'network' in result.error.lower():
                        self._work_queue.retry_failed(work_item, result.error)
                
            except Exception as e:
                logger.error(f"Worker {worker_id} failed processing {rom_info.filename}: {e}")
                await self._work_queue.mark_processed(work_item)
            finally:
                async with self._lock:
                    self._active_work_count = max(0, self._active_work_count - 1)
        
        logger.debug(f"Worker {worker_id} finished")
    
    async def scale_workers(self, new_total: int) -> None:
        """
        Scale worker pool to new total count
        
        Only supports scaling up (adding workers). To scale down, use stop_workers()
        and respawn fresh pool.
        
        Args:
            new_total: Target total number of workers
        """
        current_count = len(self._worker_tasks)
        
        if new_total <= current_count:
            logger.debug(f"Worker count already at {current_count}, not scaling to {new_total}")
            return
        
        # Update semaphore limit
        self.max_concurrent = new_total
        self.semaphore = asyncio.Semaphore(new_total)
        
        # Spawn additional workers
        additional = new_total - current_count
        logger.info(f"Scaling workers from {current_count} to {new_total} (+{additional})")
        
        for i in range(additional):
            worker_id = current_count + i + 1
            worker_task = asyncio.create_task(self._worker_loop(worker_id))
            self._worker_tasks.append(worker_task)
    
    async def wait_for_completion(self) -> list:
        """
        Wait for all workers to finish processing and return results
        
        This waits for:
        1. Work queue to drain (all items processed)
        2. All worker tasks to complete
        
        Returns:
            List of (rom_info, result) tuples
        """
        logger.debug("Waiting for workers to complete...")
        
        # Wait for queue to drain
        if self._work_queue:
            await self._work_queue.drain()
        
        # Wait for all workers to finish
        if self._worker_tasks:
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)
        
        logger.info("All workers completed")
        
        # Return collected results
        async with self._results_lock:
            return self._results.copy()
    
    def clear_results(self) -> None:
        """Clear accumulated results (call before processing new system)"""
        self._results = []
    
    async def get_current_results(self) -> list:
        """Get current accumulated results (non-blocking, for progress tracking)"""
        async with self._results_lock:
            return self._results.copy()
    
    async def stop_workers(self, timeout: float = 30.0) -> None:
        """
        Gracefully stop all workers
        
        Sets shutdown event to prevent new work from starting, then waits for
        in-flight tasks to complete. Any work not yet started is left in the queue.
        
        Args:
            timeout: Maximum time to wait for workers to finish in-flight work (seconds)
        """
        if not self._worker_tasks:
            logger.debug("No workers to stop")
            return
        
        active_count = self._active_work_count
        total_workers = len(self._worker_tasks)
        
        logger.info(f"Stopping {total_workers} worker(s) - {active_count} currently active...")
        logger.info("Workers will finish in-flight tasks but not start new ones")
        
        # Set shutdown event to stop workers from starting new work
        self._shutdown_event.set()
        
        # Wait for workers to finish in-flight work (with timeout)
        try:
            await asyncio.wait_for(
                asyncio.gather(*self._worker_tasks, return_exceptions=True),
                timeout=timeout
            )
            logger.info(f"All {total_workers} workers stopped gracefully")
        except asyncio.TimeoutError:
            logger.warning(f"Workers did not complete in-flight work within {timeout}s, cancelling...")
            incomplete_count = sum(1 for task in self._worker_tasks if not task.done())
            logger.warning(f"Cancelling {incomplete_count} worker(s) still in progress")
            
            for task in self._worker_tasks:
                if not task.done():
                    task.cancel()
            
            # Wait for cancellations
            await asyncio.gather(*self._worker_tasks, return_exceptions=True)
            logger.info("Workers cancelled")
        
        # Report queue status
        if self._work_queue:
            remaining = self._work_queue.queue.qsize()
            if remaining > 0:
                logger.info(f"{remaining} work item(s) left in queue (not started)")
        
        # Clear worker list and reset state
        self._worker_tasks = []
        self._shutdown_event.clear()
        async with self._lock:
            self._active_work_count = 0
    
    async def shutdown(self, wait: bool = True) -> None:
        """
        Gracefully shutdown task pool
        
        Args:
            wait: If True, wait for running tasks to complete
        """
        await self.stop_workers()
        
        async with self._lock:
            self.semaphore = None
            self._initialized = False
            self._work_queue = None
            self._rom_processor = None
            self._operation_callback = None
            logger.info("Task pool shut down")
    
    async def get_stats(self) -> dict:
        """
        Get task pool statistics
        
        Returns:
            Dictionary with pool statistics including active workers
        """
        async with self._lock:
            return {
                'active_workers': self._active_work_count,
                'total_workers': len(self._worker_tasks),
                'max_workers': self.max_concurrent,
                'initialized': self._initialized
            }
    
    def is_initialized(self) -> bool:
        """
        Check if pools are initialized
        
        Returns:
            True if pools are initialized
        """
        return self._initialized
