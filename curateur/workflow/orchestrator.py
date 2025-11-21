"""
Workflow orchestrator for curateur scraping operations.

Coordinates the complete scraping workflow:
1. Scan ROMs
2. Query API for metadata
3. Download media
4. Generate gamelist
"""

import asyncio
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Callable
from dataclasses import dataclass
import time

from ..config.es_systems import SystemDefinition
from ..scanner.rom_scanner import scan_system
from ..scanner.rom_types import ROMInfo
from ..api.client import ScreenScraperClient
from ..api.error_handler import SkippableAPIError, categorize_error, ErrorCategory
from ..api.match_scorer import calculate_match_confidence
from ..ui.prompts import prompt_for_search_match
from ..ui.console_ui import Operations
from ..media.media_downloader import MediaDownloader
from ..gamelist.generator import GamelistGenerator
from ..gamelist.game_entry import GameEntry
from ..workflow.work_queue import WorkQueueManager, Priority

logger = logging.getLogger(__name__)


@dataclass
class ScrapingResult:
    """Result of scraping a single ROM."""
    rom_path: Path
    success: bool
    error: Optional[str] = None
    api_id: Optional[str] = None
    media_downloaded: int = 0
    game_info: Optional[dict] = None
    media_paths: Optional[dict] = None


@dataclass
class SystemResult:
    """Result of scraping an entire system."""
    system_name: str
    total_roms: int
    scraped: int
    failed: int
    skipped: int
    results: List[ScrapingResult]
    work_queue_stats: Optional[dict] = None
    failed_items: Optional[list] = None
    not_found_items: Optional[list] = None


class WorkflowOrchestrator:
    """
    Orchestrates the complete scraping workflow.
    
    Coordinates:
    - ROM scanning
    - API metadata fetching
    - Media downloading
    - Gamelist generation
    """
    
    def __init__(
        self,
        api_client: ScreenScraperClient,
        rom_directory: Path,
        media_directory: Path,
        gamelist_directory: Path,
        work_queue: WorkQueueManager,
        dry_run: bool = False,
        enable_search_fallback: bool = False,
        search_confidence_threshold: float = 0.7,
        search_max_results: int = 5,
        interactive_search: bool = False,
        preferred_regions: Optional[List[str]] = None,
        thread_manager: Optional['ThreadPoolManager'] = None,
        performance_monitor: Optional['PerformanceMonitor'] = None,
        console_ui: Optional['ConsoleUI'] = None
    ):
        """
        Initialize workflow orchestrator.
        
        Args:
            api_client: Configured API client
            rom_directory: Root directory for ROMs
            media_directory: Root directory for downloaded media
            gamelist_directory: Root directory for gamelists
            work_queue: WorkQueueManager for retry handling (required)
            dry_run: If True, simulate actions without making changes
            enable_search_fallback: Enable search when hash lookup fails
            search_confidence_threshold: Minimum confidence score to accept match
            search_max_results: Maximum search results to consider
            interactive_search: Enable interactive prompts for search matches
            preferred_regions: Region preference list for scoring
            thread_manager: Optional ThreadPoolManager for parallel operations
            performance_monitor: Optional PerformanceMonitor for metrics tracking
            console_ui: Optional ConsoleUI for rich display
        """
        self.api_client = api_client
        self.rom_directory = rom_directory
        self.media_directory = media_directory
        self.gamelist_directory = gamelist_directory
        self.work_queue = work_queue
        self.dry_run = dry_run
        self.enable_search_fallback = enable_search_fallback
        self.search_confidence_threshold = search_confidence_threshold
        self.search_max_results = search_max_results
        self.interactive_search = interactive_search
        self.preferred_regions = preferred_regions or ['us', 'wor', 'eu']
        
        # Phase D components (optional)
        self.thread_manager = thread_manager
        self.performance_monitor = performance_monitor
        self.console_ui = console_ui
        
        # Track unmatched ROMs per system
        self.unmatched_roms: Dict[str, List[str]] = {}
        
        # Track if we've scaled thread pools based on API limits
        self._thread_pools_scaled = False
    
    async def scrape_system(
        self,
        system: SystemDefinition,
        media_types: List[str] = None,
        preferred_regions: List[str] = None,
        progress_tracker = None
    ) -> SystemResult:
        """
        Scrape a single system.
        
        Args:
            system: System definition
            media_types: Media types to download (default: ['box-2D', 'ss'])
            preferred_regions: Region priority list (default: ['us', 'wor', 'eu'])
            progress_tracker: Optional progress tracker to update with ROM count
            
        Returns:
            SystemResult with scraping statistics
        """
        if media_types is None:
            media_types = ['box-2D', 'ss']
        
        if preferred_regions is None:
            preferred_regions = ['us', 'wor', 'eu']
        
        # Step 1: Scan ROMs
        rom_entries = scan_system(
            system,
            rom_root=self.rom_directory,
            crc_size_limit=1073741824
        )
        
        # Notify progress tracker with actual ROM count
        if progress_tracker:
            progress_tracker.start_system(system.fullname, len(rom_entries))
        
        results = []
        not_found_items = []
        scraped_count = 0
        failed_count = 0
        skipped_count = 0
        
        # Step 2-4: Process each ROM (parallel or sequential)
        if self.thread_manager and not self.dry_run:
            # Use parallel processing with work queue
            results, not_found_items = await self._scrape_roms_parallel(
                system,
                rom_entries,
                media_types,
                preferred_regions
            )
        else:
            # Use sequential processing
            for rom_info in rom_entries:
                result = await self._scrape_rom(
                    system,
                    rom_info,
                    media_types,
                    preferred_regions
                )
                results.append(result)
        
        # Count results
        for result in results:
            if result.success:
                scraped_count += 1
            elif result.error:
                failed_count += 1
            else:
                skipped_count += 1
        
        # Step 5: Generate gamelist
        if not self.dry_run and scraped_count > 0:
            try:
                # Display system-level operation in UI
                if self.console_ui:
                    self.console_ui.display_system_operation(
                        system_name=system.name,
                        operation=Operations.WRITING_GAMELIST,
                        details="Generating gamelist.xml..."
                    )
                
                self._generate_gamelist(system, results)
                
                # Clear system operation from UI
                if self.console_ui:
                    self.console_ui.clear_system_operation()
            except Exception as e:
                if self.console_ui:
                    self.console_ui.clear_system_operation()
                print(f"Warning: Failed to generate gamelist: {e}")
        
        # Step 6: Write unmatched ROMs log if any
        if system.name in self.unmatched_roms and self.unmatched_roms[system.name]:
            try:
                self._write_unmatched_roms(system.name)
            except Exception as e:
                logger.warning(f"Failed to write unmatched ROMs log for {system.name}: {e}")
        
        # Step 7: Write not-found items log if any
        if not_found_items:
            try:
                self._write_not_found_summary(system, not_found_items)
            except Exception as e:
                logger.warning(f"Failed to write not-found summary for {system.name}: {e}")
        
        return SystemResult(
            system_name=system.fullname,
            total_roms=len(rom_entries),
            scraped=scraped_count,
            failed=failed_count,
            skipped=skipped_count,
            results=results,
            work_queue_stats=self.work_queue.get_stats() if self.work_queue else None,
            failed_items=self.work_queue.get_failed_items() if self.work_queue else None,
            not_found_items=not_found_items
        )
    
    async def _scrape_rom(
        self,
        system: SystemDefinition,
        rom_info: ROMInfo,
        media_types: List[str],
        preferred_regions: List[str],
        operation_callback: Optional[Callable[[str, str, str, str, Optional[float], Optional[int], Optional[int]], None]] = None
    ) -> ScrapingResult:
        """
        Scrape a single ROM.
        
        Args:
            system: System definition
            rom_info: ROM information from scanner
            media_types: Media types to download
            preferred_regions: Region priority list
            operation_callback: Optional callback for UI updates
                                Signature: callback(task_name, rom_name, operation, details, progress_pct, total_tasks, completed_tasks)
            
        Returns:
            ScrapingResult
        """
        rom_path = rom_info.path
        rom_name = rom_info.filename
        task_name = f"task-{id(asyncio.current_task())}"
        
        # Task tracking for progress
        total_tasks = 2  # Initial: 1 for hash, 1 for API
        completed_tasks = 0
        
        # Helper to emit events with task progress
        def emit(operation: str, details: str, progress: Optional[float] = None, increment_task: bool = False):
            nonlocal completed_tasks
            if increment_task:
                completed_tasks += 1
            if operation_callback:
                operation_callback(task_name, rom_name, operation, details, progress, total_tasks, completed_tasks)
        
        try:
            # Step 1: Hashing (already done in scanner, just increment the counter)
            if rom_info.hash_value:
                completed_tasks += 1  # Don't emit - already complete
            
            # Step 2: Query API (hash-based lookup)
            if self.dry_run:
                return ScrapingResult(
                    rom_path=rom_path,
                    success=True,
                    api_id="DRY_RUN"
                )
            
            game_info = None
            api_start = time.time()
            
            # Emit BEFORE starting the API call
            emit(Operations.FETCHING_METADATA, "ScreenScraper API...")
            
            try:
                game_info = await self.api_client.query_game(rom_info)
                api_duration = time.time() - api_start
                
                # Record API timing
                if hasattr(self, 'performance_monitor') and self.performance_monitor:
                    self.performance_monitor.record_api_call(api_duration)
                
                logger.debug(f"Hash lookup successful for {rom_info.filename}")
                # Increment task counter but don't emit completion status
                completed_tasks += 1
                
                # After first successful API call, check if we should scale thread pools
                if not self._thread_pools_scaled and self.thread_manager:
                    user_limits = self.api_client.get_user_limits()
                    if user_limits:
                        logger.info(f"API limits received for rescaling: {user_limits}")
                        
                        # Attempt to rescale pools based on actual API limits
                        scaled = await self.thread_manager.rescale_pools(user_limits)
                        if scaled:
                            logger.info("Task pool dynamically scaled based on API limits")
                        else:
                            logger.info("Task pool rescale not needed (already at correct size)")
                        self._thread_pools_scaled = True
                
            except SkippableAPIError as e:
                logger.debug(f"Hash lookup failed for {rom_info.filename}: {e}")
                
                # Try search fallback if enabled
                if self.enable_search_fallback:
                    emit(Operations.SEARCH_FALLBACK, "Trying text search...")
                    logger.info(f"Attempting search fallback for {rom_info.filename}")
                    game_info = await self._search_fallback(rom_info, preferred_regions)
                    
                    if game_info:
                        api_duration = time.time() - api_start
                        
                        # Record API timing
                        if hasattr(self, 'performance_monitor') and self.performance_monitor:
                            self.performance_monitor.record_api_call(api_duration)
                        
                        logger.info(f"Search fallback successful for {rom_info.filename}")
                        # Increment task counter but don't emit completion status
                        completed_tasks += 1
                    else:
                        logger.info(f"Search fallback found no matches for {rom_info.filename}")
                        emit(Operations.NO_MATCHES, "Game not found in database")
            
            if not game_info:
                # Track as unmatched
                system_name = system.name
                if system_name not in self.unmatched_roms:
                    self.unmatched_roms[system_name] = []
                self.unmatched_roms[system_name].append(rom_info.filename)
                
                return ScrapingResult(
                    rom_path=rom_path,
                    success=False,
                    error="No game info found from API"
                )
            
            # Step 3: Download media
            media_downloader = MediaDownloader(
                media_root=self.media_directory,
                client=self.api_client.client,
                preferred_regions=preferred_regions,
                enabled_media_types=media_types
            )
            
            media_paths = {}
            media_count = 0
            media_downloaded_count = 0
            
            try:
                # Get media dict from game_info and flatten to list
                media_dict = game_info.get('media', {})
                if media_dict:
                    # Convert dict of lists to flat list
                    media_list = []
                    for media_type, media_items in media_dict.items():
                        media_list.extend(media_items)
                    
                    if media_list:
                        # Update total tasks with media count (reset progress bar)
                        total_tasks = completed_tasks + len(media_list)
                        emit(Operations.downloading_media(0, len(media_list), 'preparing'), Operations.media_summary(0, len(media_list)))
                        
                        download_results = await media_downloader.download_media_for_game(
                            media_list=media_list,
                            rom_path=str(rom_info.path),
                            system=system.name
                        )
                        
                        # Process results - just count, don't emit for each one
                        for result in download_results:
                            if result.success and result.file_path:
                                media_paths[result.media_type] = result.file_path
                                media_count += 1
                                media_downloaded_count += 1
                                completed_tasks += 1
                            elif not result.success:
                                # Log media download failures
                                logger.warning(
                                    f"Failed to download {result.media_type} for {rom_info.filename}: {result.error}"
                                )
                                completed_tasks += 1
            except Exception as e:
                # Log but don't fail the entire ROM for media errors
                logger.warning(f"Media download error for {rom_info.filename}: {e}")
            
            # Don't emit final completion status - let worker go idle naturally
            
            return ScrapingResult(
                rom_path=rom_path,
                success=True,
                api_id=str(game_info.get('id', '')),
                media_downloaded=media_count,
                game_info=game_info,
                media_paths=media_paths
            )
            
        except Exception as e:
            logger.error(f"Error scraping {rom_info.filename}: {e}")
            return ScrapingResult(
                rom_path=rom_path,
                success=False,
                error=str(e)
            )
    
    def _create_rom_processor(
        self,
        system: SystemDefinition,
        media_types: List[str],
        preferred_regions: List[str]
    ) -> Callable:
        """
        Create a ROM processor function for use with ThreadPoolManager.submit_rom_batch
        
        Args:
            system: System definition
            media_types: Media types to download
            preferred_regions: Region preference list
            
        Returns:
            Async callable that processes a single ROM with optional callback
        """
        async def process_rom(
            rom_info: ROMInfo,
            operation_callback: Optional[Callable[[str, str, str, str, Optional[float], Optional[int], Optional[int]], None]] = None
        ) -> ScrapingResult:
            """
            Process a single ROM end-to-end
            
            Args:
                rom_info: ROM information
                operation_callback: Optional UI callback for progress updates
                
            Returns:
                ScrapingResult
            """
            rom_start_time = time.time()
            
            try:
                # Call the existing _scrape_rom method with callback
                result = await self._scrape_rom(
                    system=system,
                    rom_info=rom_info,
                    media_types=media_types,
                    preferred_regions=preferred_regions,
                    operation_callback=operation_callback
                )
                
                # Record total ROM processing time for performance metrics
                rom_duration = time.time() - rom_start_time
                if self.performance_monitor:
                    self.performance_monitor.record_rom_processing(rom_duration)
                
                return result
                
            except Exception as e:
                logger.error(f"ROM processor error for {rom_info.filename}: {e}")
                return ScrapingResult(
                    rom_path=rom_info.path,
                    success=False,
                    error=str(e)
                )
        
        return process_rom
    
    def _create_ui_callback(self) -> Optional[Callable]:
        """
        Create a UI callback for worker operation updates
        
        Returns:
            Callback function or None if no ConsoleUI
        """
        if not self.console_ui:
            return None
        
        def ui_callback(
            worker_name: str,
            rom_name: str,
            operation: str,
            details: str,
            progress_pct: Optional[float] = None,
            total_tasks: Optional[int] = None,
            completed_tasks: Optional[int] = None
        ) -> None:
            """
            Bridge operation events to ConsoleUI
            
            Args:
                worker_name: Name of the worker (e.g., "task-12345")
                rom_name: Name of the ROM being processed
                operation: Operation description (e.g., "Hashing ROM", "Fetching metadata")
                details: Additional details
                progress_pct: Optional progress percentage (0.0-100.0)
                total_tasks: Total number of tasks for current ROM
                completed_tasks: Number of completed tasks
            """
            # Get or assign worker ID
            worker_id = self.console_ui._get_or_assign_worker_id(worker_name)
            
            # Update worker operation
            self.console_ui.update_worker_operation(
                worker_id=worker_id,
                rom_name=rom_name,
                operation=operation,
                details=details,
                progress_pct=progress_pct,
                total_tasks=total_tasks,
                completed_tasks=completed_tasks
            )
        
        return ui_callback
    
    async def _scrape_roms_parallel(
        self,
        system: SystemDefinition,
        rom_entries: List[ROMInfo],
        media_types: List[str],
        preferred_regions: List[str]
    ) -> Tuple[List[ScrapingResult], List[dict]]:
        """
        Scrape ROMs in parallel using WorkQueueManager and async task pool.
        
        Uses work queue consumer pattern with selective retry based on error category.
        
        Args:
            system: System definition
            rom_entries: List of ROM information from scanner
            media_types: Media types to download
            preferred_regions: Region priority list
            
        Returns:
            Tuple of (results list, not_found_items list)
        """
        results = []
        not_found_items = []  # Track 404 errors separately
        rom_count = 0
        
        # Initialize idle workers in UI if available
        if self.console_ui and self.thread_manager and self.thread_manager.is_initialized():
            max_workers = self.thread_manager.max_concurrent
            for i in range(1, max_workers + 1):
                self.console_ui.clear_worker_operation(i)  # Pass integer, not string
        
        # Populate work queue with all ROM entries
        for rom_info in rom_entries:
            rom_info_dict = {
                'filename': rom_info.filename,
                'path': str(rom_info.path),
                'system': rom_info.system,
                'file_size': rom_info.file_size,
                'hash_type': rom_info.hash_type,
                'hash_value': rom_info.hash_value,
                'query_filename': rom_info.query_filename,
                'query_filename': rom_info.query_filename,
                'basename': rom_info.basename,
                'rom_type': rom_info.rom_type.value  # Serialize enum as string
            }
            self.work_queue.add_work(rom_info_dict, 'full_scrape', Priority.NORMAL)
        
        # Define work item processor
        async def process_work_item(work_item) -> dict:
            """Process a single work item from the queue"""
            rom_info_dict = work_item.rom_info
            
            # Reconstruct ROMInfo from dict
            from ..scanner.rom_types import ROMType
            rom_info = ROMInfo(
                path=Path(rom_info_dict['path']),
                filename=rom_info_dict['filename'],
                basename=rom_info_dict['basename'],
                rom_type=ROMType(rom_info_dict['rom_type']),  # Deserialize enum
                system=rom_info_dict['system'],
                query_filename=rom_info_dict['query_filename'],
                file_size=rom_info_dict['file_size'],
                hash_type=rom_info_dict.get('hash_type', 'crc32'),
                hash_value=rom_info_dict.get('hash_value')
            )
            
            try:
                # Query API
                game_info = None
                
                # Try hash-based lookup first
                try:
                    game_info = await self.api_client.query_game(rom_info)
                    if self.performance_monitor:
                        self.performance_monitor.record_api_call()
                    logger.debug(f"Hash lookup successful for {rom_info.filename}")
                    
                    # After first successful API call, check if we should scale thread pools
                    if not self._thread_pools_scaled and self.thread_manager:
                        user_limits = self.api_client.get_user_limits()
                        if user_limits:
                            logger.info(f"API limits received: {user_limits}")
                            
                            # Immediately update footer with fresh API limits
                            if self.console_ui:
                                self.console_ui.update_footer(
                                    stats={'successful': 0, 'failed': 0, 'skipped': 0},
                                    api_quota={
                                        'requests_today': user_limits.get('requeststoday', 0),
                                        'max_requests_per_day': user_limits.get('maxrequestsperday', 0)
                                    },
                                    thread_stats={
                                        'active_threads': 0,
                                        'max_threads': user_limits.get('maxthreads', 1)
                                    }
                                )
                            
                            # Attempt to rescale pools based on actual API limits
                            scaled = self.thread_manager.rescale_pools(user_limits)
                            if scaled:
                                logger.info("Thread pools dynamically scaled based on API limits")
                            self._thread_pools_scaled = True
                    
                except Exception as e:
                    # Categorize error for selective retry
                    exception, category = categorize_error(e)
                    
                    if category == ErrorCategory.NOT_FOUND:
                        # 404 - don't retry, track separately
                        return {
                            'rom_info': rom_info,
                            'category': 'not_found',
                            'error': str(exception)
                        }
                    elif category == ErrorCategory.RETRYABLE:
                        # 429, 5xx, network - retry
                        return {
                            'rom_info': rom_info,
                            'category': 'retryable',
                            'error': str(exception)
                        }
                    elif category == ErrorCategory.FATAL:
                        # 403 auth failure - propagate
                        raise exception
                    else:
                        # NON_RETRYABLE - log and skip
                        logger.debug(f"Hash lookup failed for {rom_info.filename}: {exception}")
                        
                        # Try search fallback if enabled
                        if self.enable_search_fallback:
                            logger.info(f"Attempting search fallback for {rom_info.filename}")
                            try:
                                game_info = await self._search_fallback(rom_info, preferred_regions)
                                if game_info:
                                    logger.info(f"Search fallback successful for {rom_info.filename}")
                                    if self.performance_monitor:
                                        self.performance_monitor.record_api_call()
                            except Exception as search_e:
                                search_exception, search_category = categorize_error(search_e)
                                if search_category == ErrorCategory.NOT_FOUND:
                                    return {
                                        'rom_info': rom_info,
                                        'category': 'not_found',
                                        'error': str(search_exception)
                                    }
                                elif search_category == ErrorCategory.RETRYABLE:
                                    return {
                                        'rom_info': rom_info,
                                        'category': 'retryable',
                                        'error': str(search_exception)
                                    }
                
                return {'rom_info': rom_info, 'game_info': game_info, 'category': 'success'}
                
            except Exception as e:
                exception, category = categorize_error(e)
                if category == ErrorCategory.FATAL:
                    raise exception
                return {
                    'rom_info': rom_info,
                    'category': category.value,
                    'error': str(exception)
                }
        
        # Work queue consumption - always use parallel processing (async tasks)
        # Even with max_concurrent=1, this allows dynamic rescaling after first API response
        if self.thread_manager:
            # Parallel batch processing with per-task UI updates
            logger.info(f"Using task pool with {self.thread_manager.max_concurrent} concurrent task(s)")
            
            # Create UI callback and ROM processor
            ui_callback = self._create_ui_callback()
            rom_processor = self._create_rom_processor(system, media_types, preferred_regions)
            
            while not self.work_queue.is_empty():
                # Apply any pending rescale from previous batch
                if await self.thread_manager.apply_pending_rescale():
                    logger.info(f"Task pool rescaled, new max: {self.thread_manager.max_concurrent}")
                
                # Recalculate batch size to adapt to dynamic task pool rescaling
                batch_size = self.thread_manager.max_concurrent * 2  # Keep tasks fed
                
                # Get batch of work items and extract ROMInfo objects
                batch = []
                work_items = []
                for _ in range(batch_size):
                    work_item = self.work_queue.get_work(timeout=0.01)
                    if work_item:
                        work_items.append(work_item)
                        # Reconstruct ROMInfo from work item
                        rom_info_dict = work_item.rom_info
                        from ..scanner.rom_types import ROMType
                        rom_info = ROMInfo(
                            path=Path(rom_info_dict['path']),
                            filename=rom_info_dict['filename'],
                            basename=rom_info_dict['basename'],
                            rom_type=ROMType(rom_info_dict['rom_type']),
                            system=rom_info_dict['system'],
                            query_filename=rom_info_dict['query_filename'],
                            file_size=rom_info_dict['file_size'],
                            hash_type=rom_info_dict.get('hash_type', 'crc32'),
                            hash_value=rom_info_dict.get('hash_value')
                        )
                        batch.append(rom_info)
                    else:
                        break
                
                if not batch:
                    break
                
                # Process batch with end-to-end ROM processing per task
                async for rom_info, result in self.thread_manager.submit_rom_batch(
                    rom_processor, batch, ui_callback
                ):
                    rom_count += 1
                    
                    # Convert ROMInfo to dict for compatibility
                    rom_info_dict = {
                        'filename': rom_info.filename,
                        'path': str(rom_info.path)
                    }
                    
                    # Update UI (footer and queue stats only - tasks update themselves)
                    # Count skipped ROMs (those with neither success nor error)
                    skipped = sum(1 for r in results if not r.success and not r.error)
                    self._update_ui_progress(
                        rom_info_dict, rom_count, len(rom_entries),
                        results, not_found_items, skipped
                    )
                    
                    # Store result
                    results.append(result)
                    
                    # Track not found items
                    if not result.success and result.error == "No game info found from API":
                        not_found_items.append({
                            'filename': rom_info.filename,
                            'path': str(rom_info.path)
                        })
                    
                    # Mark work item as processed (find matching work item)
                    for work_item in work_items:
                        if work_item.rom_info['filename'] == rom_info.filename:
                            self.work_queue.mark_processed(work_item)
                            break
        else:
            # Fallback: Direct sequential processing (when thread_manager is None)
            # This should rarely/never happen in normal operation
            logger.warning("No thread manager available - using direct sequential processing")
            
            # Sequential work queue consumption loop
            while not self.work_queue.is_empty():
                work_item = self.work_queue.get_work(timeout=0.1)
                if not work_item:
                    continue
                
                    rom_count += 1
                rom_info_dict = work_item.rom_info
                
                # Update UI
                self._update_ui_progress(
                    rom_info_dict, rom_count, len(rom_entries),
                    results, not_found_items
                )
                
                # Process the work item
                try:
                    api_result = await process_work_item(work_item)
                    
                    # Handle result using helper method
                    self._handle_api_result(
                        api_result, work_item, system, results, not_found_items,
                        media_types, preferred_regions
                    )
                
                except Exception as e:
                    # Fatal error - propagate
                    logger.error(f"Fatal error processing work item: {e}")
                    raise
        
        return results, not_found_items
    
    def _download_media_parallel(
        self,
        system: SystemDefinition,
        rom_info: ROMInfo,
        game_info: dict,
        media_types: List[str],
        preferred_regions: List[str]
    ) -> Tuple[dict, int]:
        """
        Download media files using MediaDownloader.
        
        Args:
            system: System definition
            rom_info: ROM information
            game_info: Game metadata from API
            media_types: Media types to download
            preferred_regions: Region priority list
            
        Returns:
            Tuple of (media_paths dict, media_count)
        """
        media_downloader = MediaDownloader(
            media_root=self.media_directory,
            preferred_regions=preferred_regions,
            enabled_media_types=media_types
        )
        
        media_paths = {}
        media_count = 0
        
        try:
            # Get media dict from game_info and flatten to list
            media_dict = game_info.get('media', {})
            if media_dict:
                # Convert dict of lists to flat list
                # media_dict format: {'box-2D': [{...}, {...}], 'ss': [{...}]}
                # Convert to: [{...}, {...}, {...}]
                media_list = []
                for media_type, media_items in media_dict.items():
                    media_list.extend(media_items)
                
                if media_list:
                    download_results = media_downloader.download_media_for_game(
                        media_list=media_list,
                        rom_path=str(rom_info.path),
                        system=system.name
                    )
                    
                    # Process results
                    for result in download_results:
                        if result.success and result.file_path:
                            media_paths[result.media_type] = result.file_path
                            media_count += 1
                            
                            if self.performance_monitor:
                                self.performance_monitor.record_download()
                        elif not result.success:
                            # Log media download failures
                            logger.warning(
                                f"Failed to download {result.media_type} for {rom_info.filename}: {result.error}"
                            )
        except Exception as e:
            logger.debug(f"Media download failed: {e}")
        
        return media_paths, media_count
    
    async def _search_fallback(
        self,
        rom_info: ROMInfo,
        preferred_regions: List[str]
    ) -> Optional[Dict]:
        """
        Search fallback when hash lookup fails.
        
        Searches by filename, scores candidates, and either auto-selects
        best match or prompts user interactively.
        
        Args:
            rom_info: ROM information from scanner
            preferred_regions: Region preference list for scoring
            
        Returns:
            Game data dictionary if match found, None otherwise
        """
        try:
            # Search API
            results = await self.api_client.search_game(
                rom_info,
                max_results=self.search_max_results
            )
            
            if not results:
                logger.debug(f"Search returned no results for {rom_info.filename}")
                return None
            
            # Convert ROM info to dict for scorer
            rom_info_dict = {
                'path': str(rom_info.path),
                'filename': rom_info.filename,
                'size': rom_info.file_size,
                'crc32': rom_info.crc32,
                'system': rom_info.system,
            }
            
            # Score each candidate
            scored_candidates = []
            for game_data in results:
                confidence = calculate_match_confidence(
                    rom_info_dict,
                    game_data,
                    preferred_regions
                )
                scored_candidates.append((game_data, confidence))
            
            # Sort by confidence (highest first)
            scored_candidates.sort(key=lambda x: x[1], reverse=True)
            
            # Log all candidates
            logger.debug(f"Search candidates for {rom_info.filename}:")
            for i, (game, score) in enumerate(scored_candidates, 1):
                game_name = game.get('names', {}).get('en', 'Unknown')
                logger.debug(f"  {i}. {game_name} - {score:.1%}")
            
            # Interactive mode: prompt user
            if self.interactive_search:
                return prompt_for_search_match(
                    rom_info.filename,
                    scored_candidates,
                    self.search_confidence_threshold
                )
            
            # Automatic mode: take best if above threshold
            best_game, best_score = scored_candidates[0]
            
            if best_score >= self.search_confidence_threshold:
                game_name = best_game.get('names', {}).get('en', 'Unknown')
                logger.info(
                    f"Auto-selected search match for {rom_info.filename}: "
                    f"{game_name} (confidence: {best_score:.1%})"
                )
                return best_game
            else:
                logger.info(
                    f"Best match below threshold for {rom_info.filename}: "
                    f"{best_score:.1%} < {self.search_confidence_threshold:.1%}"
                )
                return None
                
        except SkippableAPIError as e:
            logger.debug(f"Search API error for {rom_info.filename}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in search fallback for {rom_info.filename}: {e}")
            return None
    
    def _generate_gamelist(
        self,
        system: SystemDefinition,
        results: List[ScrapingResult]
    ) -> None:
        """
        Generate gamelist.xml for system.
        
        Args:
            system: System definition
            results: Scraping results
        """
        generator = GamelistGenerator(
            system_name=system.name,
            full_system_name=system.fullname,
            rom_directory=self.rom_directory / system.name,
            media_directory=self.media_directory / system.name,
            gamelist_directory=self.gamelist_directory / system.name
        )
        
        # Prepare scraped games data
        scraped_games = []
        
        for result in results:
            if result.success and result.game_info:
                scraped_games.append({
                    'rom_path': result.rom_path,
                    'game_info': result.game_info,
                    'media_paths': result.media_paths or {}
                })
        
        # Generate gamelist (merge with existing if present)
        if scraped_games:
            try:
                generator.generate_gamelist(
                    scraped_games=scraped_games,
                    merge_existing=True
                )
            except Exception as e:
                raise Exception(f"Failed to generate gamelist: {e}")
    
    def _write_unmatched_roms(self, system_name: str) -> None:
        """
        Write unmatched ROMs to log file.
        
        Creates a text file listing all ROMs that couldn't be matched
        for a given system.
        
        Args:
            system_name: System short name
        """
        unmatched = self.unmatched_roms.get(system_name, [])
        if not unmatched:
            return
        
        # Write to gamelist directory
        output_dir = self.gamelist_directory / system_name
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / "unmatched_roms.txt"
        
        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(f"# Unmatched ROMs for {system_name}\n")
                f.write(f"# Total: {len(unmatched)}\n")
                f.write(f"# These ROMs could not be matched via hash lookup")
                if self.enable_search_fallback:
                    f.write(" or search fallback")
                f.write(".\n#\n")
                
                for filename in sorted(unmatched):
                    f.write(f"{filename}\n")
            
            logger.info(f"Wrote {len(unmatched)} unmatched ROMs to {output_file}")
        except Exception as e:
            logger.error(f"Failed to write unmatched ROMs log: {e}")
            raise
    
    def _write_not_found_summary(self, system: SystemDefinition, not_found_items: List[dict]) -> None:
        """
        Write not-found items (404 errors) to summary file.
        
        Creates a text file listing all ROMs that returned 404 from the API.
        
        Args:
            system: System definition
            not_found_items: List of dicts with rom_info and error
        """
        if not not_found_items:
            return
        
        # Write to gamelist directory
        output_dir = self.gamelist_directory / system.name
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{system.name}_not_found.txt"
        
        try:
            from datetime import datetime
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(f"# Not Found ROMs for {system.fullname}\n")
                f.write(f"# Generated: {timestamp}\n")
                f.write(f"# Total ROMs not found in ScreenScraper: {len(not_found_items)}\n")
                f.write("#\n")
                f.write("# These ROMs returned 404 (Not Found) from the API\n")
                f.write("#\n\n")
                
                for item in sorted(not_found_items, key=lambda x: x['rom_info'].filename):
                    rom_info = item['rom_info']
                    error = item['error']
                    f.write(f"ROM: {rom_info.filename}\n")
                    if hasattr(rom_info, 'crc32') and rom_info.crc32:
                        f.write(f"  CRC32: {rom_info.crc32}\n")
                    f.write(f"  Size: {rom_info.file_size} bytes\n")
                    f.write(f"  Error: {error}\n")
                    f.write("\n")
            
            logger.info(f"Wrote not-found items to {output_file}")
        except Exception as e:
            logger.error(f"Failed to write not-found summary: {e}")
            raise
    
    def _update_ui_progress(
        self,
        rom_info_dict: dict,
        rom_count: int,
        total_roms: int,
        results: list,
        not_found_items: list,
        skipped_count: int = 0
    ) -> None:
        """Update UI with current progress"""
        if not self.console_ui:
            return
        
        # Update work queue stats
        queue_stats = self.work_queue.get_stats()
        self.console_ui.update_work_queue_stats(
            pending=queue_stats['pending'],
            processed=queue_stats['processed'],
            failed=queue_stats['failed'],
            not_found=len(not_found_items),
            retry_count=sum(item['retry_count'] for item in self.work_queue.get_failed_items())
        )
        
        # Update footer with current stats and performance metrics
        successful_count = sum(1 for r in results if r.success)
        failed_count = sum(1 for r in results if r.error)
        
        # Get performance metrics if available
        performance_metrics = None
        if self.performance_monitor:
            metrics = self.performance_monitor.get_metrics()
            performance_metrics = {
                'avg_api_time': metrics.avg_api_time * 1000,  # Convert to milliseconds
                'avg_rom_time': metrics.avg_rom_time,  # Keep in seconds
                'eta_seconds': metrics.eta_seconds
            }
        
        # Get thread stats if available
        thread_stats = None
        if self.thread_manager and self.thread_manager.is_initialized():
            stats = self.thread_manager.get_stats()
            thread_stats = {
                'active_threads': stats.get('active_threads', 0),
                'max_threads': stats.get('max_threads', 1)
            }
        
        # Get real API quota from user limits
        user_limits = self.api_client.get_user_limits() or {}
        api_quota = {
            'requests_today': user_limits.get('requeststoday', 0),
            'max_requests_per_day': user_limits.get('maxrequestsperday', 0)
        }
        
        self.console_ui.update_footer(
            stats={
                'successful': successful_count,
                'failed': failed_count,
                'skipped': skipped_count
            },
            api_quota=api_quota,
            thread_stats=thread_stats,
            performance_metrics=performance_metrics
        )
    
    def _handle_api_result(
        self,
        api_result: dict,
        work_item: 'WorkItem',
        system: 'SystemDefinition',
        results: list,
        not_found_items: list,
        media_types: List[str],
        preferred_regions: List[str]
    ) -> None:
        """Handle API result and update results/work queue"""
        if api_result['category'] == 'not_found':
            # 404 - track separately and mark processed
            not_found_items.append({
                'rom_info': api_result['rom_info'],
                'error': api_result['error']
            })
            self.work_queue.mark_processed(work_item)
        
        elif api_result['category'] == 'retryable':
            # Retry with higher priority
            self.work_queue.retry_failed(work_item, api_result['error'])
        
        elif api_result['category'] == 'success':
            game_info = api_result.get('game_info')
            rom_info = api_result['rom_info']
            
            if not game_info:
                # No game info - mark as unmatched
                system_name = system.name
                if system_name not in self.unmatched_roms:
                    self.unmatched_roms[system_name] = []
                self.unmatched_roms[system_name].append(rom_info.filename)
                
                result = ScrapingResult(
                    rom_path=rom_info.path,
                    success=False,
                    error="No game info found from API"
                )
                results.append(result)
                self.work_queue.mark_processed(work_item)
            else:
                # Download media in parallel
                media_paths, media_count = self._download_media_parallel(
                    system=system,
                    rom_info=rom_info,
                    game_info=game_info,
                    media_types=media_types,
                    preferred_regions=preferred_regions
                )
                
                # Update performance monitor
                if self.performance_monitor:
                    self.performance_monitor.record_rom_processed()
                
                result = ScrapingResult(
                    rom_path=rom_info.path,
                    success=True,
                    api_id=str(game_info.get('id', '')),
                    media_downloaded=media_count,
                    game_info=game_info,
                    media_paths=media_paths
                )
                results.append(result)
                self.work_queue.mark_processed(work_item)
        
        else:
            # Other categories - log and mark processed
            rom_info = api_result['rom_info']
            logger.warning(f"Non-retryable error for {rom_info.filename}: {api_result.get('error', 'unknown')}")
            result = ScrapingResult(
                rom_path=rom_info.path,
                success=False,
                error=api_result.get('error', 'Unknown error')
            )
            results.append(result)
            self.work_queue.mark_processed(work_item)

