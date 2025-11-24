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
from typing import List, Dict, Optional, Tuple, Callable, Any, TYPE_CHECKING
from dataclasses import dataclass
import time

if TYPE_CHECKING:
    from ..workflow.thread_pool import ThreadPoolManager
    from ..workflow.performance import PerformanceMonitor
    from ..ui.console_ui import ConsoleUI
    from ..api.throttle import ThrottleManager

from ..config.es_systems import SystemDefinition
from ..scanner.rom_scanner import scan_system
from ..scanner.rom_types import ROMInfo
from ..scanner.hash_calculator import calculate_hash
from ..api.client import ScreenScraperClient
from ..api.cache import MetadataCache
from ..api.error_handler import SkippableAPIError, categorize_error, ErrorCategory
from ..api.match_scorer import calculate_match_confidence
from ..ui.prompts import prompt_for_search_match
from ..ui.console_ui import Operations
from ..media.media_downloader import MediaDownloader
from ..media.media_types import to_singular
from ..gamelist.generator import GamelistGenerator
from ..gamelist.game_entry import GameEntry
from ..gamelist.parser import GamelistParser
from ..gamelist.integrity_validator import IntegrityValidator
from ..gamelist.metadata_merger import MetadataMerger
from ..workflow.work_queue import WorkQueueManager, Priority
from ..workflow.evaluator import WorkflowEvaluator, WorkflowDecision
from ..workflow.checkpoint import CheckpointManager, prompt_resume_from_checkpoint

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
    skipped: bool = False
    skip_reason: Optional[str] = None


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
        config: Dict[str, Any],
        dry_run: bool = False,
        enable_search_fallback: bool = False,
        search_confidence_threshold: float = 0.7,
        search_max_results: int = 5,
        interactive_search: bool = False,
        preferred_regions: Optional[List[str]] = None,
        thread_manager: Optional['ThreadPoolManager'] = None,
        performance_monitor: Optional['PerformanceMonitor'] = None,
        console_ui: Optional['ConsoleUI'] = None,
        throttle_manager: Optional['ThrottleManager'] = None,
        clear_cache: bool = False
    ):
        """
        Initialize workflow orchestrator.
        
        Args:
            api_client: Configured API client
            rom_directory: Root directory for ROMs
            media_directory: Root directory for downloaded media
            gamelist_directory: Root directory for gamelists
            work_queue: WorkQueueManager for retry handling (required)
            config: Configuration dictionary
            dry_run: If True, simulate actions without making changes
            enable_search_fallback: Enable search when hash lookup fails
            search_confidence_threshold: Minimum confidence score to accept match
            search_max_results: Maximum search results to consider
            interactive_search: Enable interactive prompts for search matches
            preferred_regions: Region preference list for scoring
            thread_manager: Optional ThreadPoolManager for parallel operations
            performance_monitor: Optional PerformanceMonitor for metrics tracking
            console_ui: Optional ConsoleUI for rich display
            throttle_manager: Optional ThrottleManager for quota tracking
            clear_cache: Whether to clear metadata cache before scraping
        """
        self.api_client = api_client
        self.rom_directory = rom_directory
        self.media_directory = media_directory
        self.gamelist_directory = gamelist_directory
        self.work_queue = work_queue
        self.config = config
        self.dry_run = dry_run
        self.enable_search_fallback = enable_search_fallback
        self.search_confidence_threshold = search_confidence_threshold
        self.search_max_results = search_max_results
        self.interactive_search = interactive_search
        self.preferred_regions = preferred_regions or ['us', 'wor', 'eu']
        self.clear_cache = clear_cache
        
        # Phase D components (optional)
        self.thread_manager = thread_manager
        self.performance_monitor = performance_monitor
        self.console_ui = console_ui
        self.throttle_manager = throttle_manager
        
        # Initialize workflow evaluator with cache for media hash lookups
        self.evaluator = WorkflowEvaluator(self.config, cache=self.api_client.cache if self.api_client else None)
        
        # Initialize integrity validator
        integrity_threshold = self.config.get('scraping', {}).get('gamelist_integrity_threshold', 0.95)
        self.integrity_validator = IntegrityValidator(threshold=integrity_threshold)
        
        # Store paths for easy access
        self.paths = {
            'roms': self.rom_directory,
            'media': self.media_directory,
            'gamelists': self.gamelist_directory
        }
        
        # Track unmatched ROMs per system
        self.unmatched_roms: Dict[str, List[str]] = {}
        
        # Checkpoint manager (initialized per-system)
        self.checkpoint_manager: Optional[CheckpointManager] = None
    
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
        
        # Step 0: System start logging
        logger.info(f"=== Begin work for system: {system.name} ===")
        logger.info(f"Platform: {system.platform}")
        logger.info(f"Path: {system.path}")
        
        # Reset pipeline stages UI for new system
        if self.console_ui:
            self.console_ui.reset_pipeline_stages()
        
        # Initialize checkpoint manager for this system
        gamelist_dir = self.paths['gamelists'] / system.name
        self.checkpoint_manager = CheckpointManager(
            str(gamelist_dir),
            system.name,
            self.config
        )
        
        # Initialize metadata cache for this system
        enable_cache = self.config.get('runtime', {}).get('enable_cache', True)
        
        # Log warning if cache is disabled
        if not enable_cache:
            logger.warning(
                f"Metadata cache is DISABLED by configuration (runtime.enable_cache=false). "
                f"All API queries will be performed even for unchanged ROMs. "
                f"Existing cache will be ignored but not deleted."
            )
        
        cache = MetadataCache(
            gamelist_directory=gamelist_dir,
            ttl_days=7,
            enabled=enable_cache
        )
        
        # Handle cache operations
        if self.clear_cache:
            if enable_cache:
                # Clear cache and start fresh
                cleared_count = cache.clear()
                logger.info(f"Cleared metadata cache: {cleared_count} entries removed, building new cache")
            else:
                # Cache disabled - clear would be meaningless
                logger.warning(
                    f"--clear-cache specified but cache is disabled (runtime.enable_cache=false). "
                    f"No cache will be cleared or created."
                )
        else:
            # Cleanup expired entries on startup (only if cache enabled)
            if enable_cache:
                expired_count = cache.cleanup_expired()
                if expired_count > 0:
                    logger.info(f"Cleaned up {expired_count} expired cache entries")
        
        # Log cache stats
        cache_stats = cache.get_stats()
        if cache_stats['enabled'] and cache_stats['valid_entries'] > 0:
            logger.info(
                f"Metadata cache: {cache_stats['valid_entries']} valid entries, "
                f"{cache_stats['expired_entries']} expired"
            )
        elif not cache_stats['enabled']:
            logger.info("Metadata cache: DISABLED")
        
        # Update API client with cache for this system
        self.api_client.cache = cache
        
        # Try to load existing checkpoint
        checkpoint = self.checkpoint_manager.load_checkpoint()
        resume_from_checkpoint = False
        
        if checkpoint:
            # Prompt user to resume from checkpoint
            resume_from_checkpoint = prompt_resume_from_checkpoint(checkpoint)
            if not resume_from_checkpoint:
                # User wants fresh start - remove checkpoint
                self.checkpoint_manager.remove_checkpoint()
                logger.info("Starting fresh scrape (checkpoint discarded)")
        
        # Step 1: Scan ROMs
        logger.info("Scanning ROMs...")
        crc_size_limit = self.config.get('runtime', {}).get('crc_size_limit', 1073741824)
        rom_entries = scan_system(
            system,
            rom_root=self.rom_directory,
            crc_size_limit=crc_size_limit
        )
        logger.info(f"ROM scan complete: {len(rom_entries)} files found")
        
        # Update UI with scanner count
        if self.console_ui:
            self.console_ui.update_scanner(len(rom_entries))
        
        # Set total ROM count for checkpoint tracking
        self.checkpoint_manager.set_total_roms(len(rom_entries))
        
        # Filter out already-processed ROMs if resuming
        if resume_from_checkpoint:
            original_count = len(rom_entries)
            rom_entries = [
                rom for rom in rom_entries 
                if not self.checkpoint_manager.is_processed(rom.filename)
            ]
            skipped_from_checkpoint = original_count - len(rom_entries)
            if skipped_from_checkpoint > 0:
                logger.info(
                    f"Resuming from checkpoint: skipping {skipped_from_checkpoint} "
                    f"already-processed ROMs, {len(rom_entries)} remaining"
                )
        
        # Notify progress tracker with actual ROM count
        if progress_tracker:
            progress_tracker.start_system(system.fullname, len(rom_entries))
        
        # Step 2: Parse and validate existing gamelist
        gamelist_path = self.paths['gamelists'] / system.name / 'gamelist.xml'
        existing_entries = []
        
        if gamelist_path.exists():
            logger.info("Parsing existing gamelist...")
            parser = GamelistParser()
            try:
                existing_entries = parser.parse_gamelist(gamelist_path)
                logger.info(f"Parsed {len(existing_entries)} entries from existing gamelist")
                
                # Validate gamelist integrity
                rom_paths = [rom_info.path for rom_info in rom_entries]
                validation_result = self.integrity_validator.validate(existing_entries, rom_paths)
                
                logger.info(f"Gamelist validation: {validation_result.match_ratio:.1%} match ratio")
                
                # Update UI: Set integrity score
                if self.console_ui:
                    self.console_ui.set_integrity_score(validation_result.match_ratio)
                
                if not validation_result.is_valid:
                    logger.warning(
                        f"Gamelist integrity check failed for {system.name}: "
                        f"{validation_result.match_ratio:.1%} match ratio "
                        f"(threshold: {self.integrity_validator.threshold:.1%})"
                    )
                    logger.info(
                        f"Missing ROMs: {len(validation_result.missing_roms)}, "
                        f"Orphaned entries: {len(validation_result.orphaned_entries)}"
                    )
                    
                    # Prompt user for confirmation (if interactive)
                    if not self._prompt_gamelist_validation_failure(system.name, validation_result):
                        logger.info(f"Skipping system {system.name} due to validation failure")
                        return SystemResult(
                            system_name=system.fullname,
                            total_roms=len(rom_entries),
                            scraped=0,
                            failed=0,
                            skipped=len(rom_entries),
                            results=[]
                        )
            except Exception as e:
                logger.warning(f"Failed to parse existing gamelist: {e}")
                existing_entries = []
        else:
            logger.info("Gamelist validation: not applicable (no existing gamelist)")
        
        results = []
        not_found_items = []
        scraped_count = 0
        failed_count = 0
        skipped_count = 0
        
        # Step 2-4: Process ROMs through concurrent pipeline
        results, not_found_items = await self._scrape_roms_parallel(
            system,
            rom_entries,
            media_types,
            preferred_regions,
            existing_entries
        )
        
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
                        details=f"Generating gamelist.xml ({scraped_count} entries)..."
                    )
                
                logger.info(f"Committing gamelist: {scraped_count} entries")
                integrity_result = self._generate_gamelist(system, results)
                
                # Show validation result
                if self.console_ui and integrity_result:
                    validation_status = "passed" if integrity_result.get('valid', False) else "failed"
                    integrity_pct = int(integrity_result.get('integrity_score', 0) * 100)
                    self.console_ui.set_system_operation(
                        "Gamelist validation",
                        f"{validation_status} ({integrity_pct}% integrity)"
                    )
                    # Brief pause to show result
                    import asyncio
                    await asyncio.sleep(1)
                
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
        
        # Step 8: Reset work queue for next system
        if self.work_queue:
            self.work_queue.reset_for_new_system()
            logger.debug(f"Work queue reset after completing {system.name}")
        
        # Step 9: Write summary log
        self._write_summary_log(system, results, scraped_count, skipped_count, failed_count)
        
        # Step 10: Remove checkpoint after successful completion
        if self.checkpoint_manager:
            self.checkpoint_manager.remove_checkpoint()
        
        logger.info(
            f"System complete: {system.name} - "
            f"{scraped_count} successful, {skipped_count} skipped, {failed_count} failed"
        )
        logger.info(f"=== End work for system: {system.name} ===")
        
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
        existing_entries: List[GameEntry] = None,
        operation_callback: Optional[Callable[[str, str, str, str, Optional[float], Optional[int], Optional[int]], None]] = None,
        shutdown_event: Optional[asyncio.Event] = None
    ) -> ScrapingResult:
        """
        Scrape a single ROM.
        
        Args:
            system: System definition
            rom_info: ROM information from scanner
            media_types: Media types to download
            preferred_regions: Region priority list
            existing_entries: List of existing gamelist entries
            operation_callback: Optional callback for UI updates
                                Signature: callback(task_name, rom_name, operation, details, progress_pct, total_tasks, completed_tasks)
            shutdown_event: Optional event to check for cancellation
            
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
            # Step 1: ROM hash (already calculated during batch pre-processing)
            rom_hash = rom_info.hash_value
            
            if not rom_hash:
                logger.debug(f"[{rom_info.filename}] No hash value available (skipped or failed during batch hashing)")
                completed_tasks += 1
            else:
                logger.debug(f"[{rom_info.filename}] Using pre-calculated hash: {rom_hash}")
                completed_tasks += 1
            
            # Step 2: Look up existing gamelist entry for this ROM
            gamelist_entry = None
            if existing_entries:
                rom_relative_path = f"./{rom_info.filename}"
                for entry in existing_entries:
                    if entry.path == rom_relative_path:
                        gamelist_entry = entry
                        break
            
            # Step 3: Evaluate ROM with WorkflowEvaluator
            decision = self.evaluator.evaluate_rom(
                rom_info=rom_info,
                gamelist_entry=gamelist_entry,
                rom_hash=rom_hash
            )
            
            # Log evaluator decision at DEBUG level
            logger.debug(
                f"Evaluator decision for {rom_info.filename}: "
                f"fetch_metadata={decision.fetch_metadata}, "
                f"update_metadata={decision.update_metadata}, "
                f"update_media={decision.update_media}, "
                f"media_to_download={decision.media_to_download}, "
                f"media_to_validate={decision.media_to_validate}, "
                f"clean_disabled_media={decision.clean_disabled_media}, "
                f"skip_reason={decision.skip_reason}"
            )
            
            # Check if ROM should be skipped
            if decision.skip_reason:
                logger.info(f"[{rom_info.filename}] Skipping: {decision.skip_reason}")
                return ScrapingResult(
                    rom_path=rom_info.path,
                    success=True,
                    error=None,
                    skipped=True,
                    skip_reason=decision.skip_reason
                )
            
            # Step 4: Query API (hash-based lookup) - only if needed
            if self.dry_run:
                return ScrapingResult(
                    rom_path=rom_info.path,
                    success=True,
                    api_id="DRY_RUN"
                )
            
            game_info = None
            
            if decision.fetch_metadata:
                # Update UI: Start API fetch for this ROM
                if self.console_ui:
                    self.console_ui.update_api_fetch_stage(rom_info.filename, 'start')
                
                # Check if we have cached data
                from_cache = False
                if self.api_client.cache:
                    cached_data = self.api_client.cache.get(rom_hash, rom_size=rom_info.path.stat().st_size)
                    from_cache = cached_data is not None
                
                logger.info(
                    f"[{rom_info.filename}] Fetching metadata "
                    f"(hash={rom_hash}, size={rom_info.path.stat().st_size})"
                )
                logger.debug(
                    f"API request: hash={rom_hash}, "
                    f"size={rom_info.file_size}, "
                    f"system_id={system.platform}"
                )
                
                api_start = time.time()
                
                try:
                    game_info = await self.api_client.query_game(rom_info, shutdown_event=shutdown_event)
                    api_duration = time.time() - api_start
                    
                    # Record API timing
                    if hasattr(self, 'performance_monitor') and self.performance_monitor:
                        self.performance_monitor.record_api_call(api_duration)
                    
                    if game_info:
                        # Count non-empty fields
                        field_count = len([k for k in game_info.keys() if game_info.get(k)])
                        logger.info(
                            f"[{rom_info.filename}] "
                            f"Metadata processed: {field_count} fields, "
                            f"{len(game_info.get('names', {}))} names, "
                            f"{len(game_info.get('descriptions', {}))} descriptions, "
                            f"language={self.config.get('scraping', {}).get('preferred_language', 'en')}"
                        )
                        logger.debug(
                            f"[{rom_info.filename}] "
                            f"Metadata fields: name={game_info.get('name', 'N/A')[:50]}, "
                            f"desc={game_info.get('desc', 'N/A')[:50]}..."
                        )
                    
                    logger.debug(f"[{rom_info.filename}] Hash lookup successful")
                    # Increment task counter but don't emit completion status
                    completed_tasks += 1
                    
                    # Update UI: Complete API fetch (report if it was a cache hit)
                    if self.console_ui:
                        self.console_ui.update_api_fetch_stage(rom_info.filename, 'complete', cache_hit=from_cache)
                    
                except asyncio.CancelledError:
                    # Shutdown requested during API call
                    logger.info(f"[{rom_info.filename}] API request cancelled (shutdown)")
                    return ScrapingResult(
                        rom_path=rom_info.path,
                        success=False,
                        error="Cancelled due to shutdown"
                    )
                except SkippableAPIError as e:
                    logger.debug(f"[{rom_info.filename}] Hash lookup failed: {e}")
                    
                    # Try search fallback if enabled
                    if self.enable_search_fallback:
                        logger.info(f"[{rom_info.filename}] Attempting search fallback")
                        game_info = await self._search_fallback(rom_info, preferred_regions, shutdown_event=shutdown_event)
                        
                        if game_info:
                            api_duration = time.time() - api_start
                            
                            # Record API timing
                            if hasattr(self, 'performance_monitor') and self.performance_monitor:
                                self.performance_monitor.record_api_call(api_duration)
                            
                            logger.info(f"[{rom_info.filename}] Search fallback successful")
                            
                            # Update UI: Search fallback used
                            if self.console_ui:
                                self.console_ui.increment_search_fallback()
                            
                            # Increment task counter but don't emit completion status
                            completed_tasks += 1
                        else:
                            logger.info(f"[{rom_info.filename}] Search fallback: no matches found")
                    else:
                        raise
            
            if not game_info and decision.fetch_metadata:
                # Track as unmatched
                system_name = system.name
                if system_name not in self.unmatched_roms:
                    self.unmatched_roms[system_name] = []
                self.unmatched_roms[system_name].append(rom_info.filename)
                
                # Update UI: Unmatched ROM count
                if self.console_ui:
                    self.console_ui.increment_unmatched()
                
                return ScrapingResult(
                    rom_path=rom_info.path,
                    success=False,
                    error="No game info found from API"
                )
            
            # Step 5: Process media with hash validation
            media_paths = {}
            media_count = 0
            media_hashes = {}
            hash_algorithm = self.config.get('runtime', {}).get('hash_algorithm', 'crc32')
            
            # Get media config
            media_config = self.config.get('media', {})
            validation_mode = media_config.get('validation_mode', 'disabled')
            image_min_dimension = media_config.get('image_min_dimension', 50)
            
            if game_info:
                # Use throttle manager's semaphore for unified concurrency control
                # This ensures metadata API calls and media downloads share the same limit
                global_semaphore = self.throttle_manager.concurrency_semaphore if self.throttle_manager else None
                
                media_downloader = MediaDownloader(
                    media_root=self.media_directory,
                    client=self.api_client.client,
                    preferred_regions=preferred_regions,
                    enabled_media_types=media_types,
                    hash_algorithm=hash_algorithm,
                    validation_mode=validation_mode,
                    min_width=image_min_dimension,
                    min_height=image_min_dimension,
                    download_semaphore=global_semaphore
                )
                
                # Get media list from game_info
                media_dict = game_info.get('media', {})
                media_list = []
                if media_dict:
                    for media_type, media_items in media_dict.items():
                        media_list.extend(media_items)
                
                logger.debug(
                    f"[{rom_info.filename}] Media availability: "
                    f"decision.media_to_download={decision.media_to_download}, "
                    f"media_list_count={len(media_list)}, "
                    f"media_types_in_api={list(media_dict.keys()) if media_dict else []}"
                )
                
                # Download all media files concurrently (from decision.media_to_download)
                if decision.media_to_download and media_list:
                    # Convert singular ES-DE types to ScreenScraper media types for filtering
                    # E.g., 'cover' -> 'covers' -> 'box-2D'
                    from ..media.media_types import to_plural, convert_directory_names_to_media_types
                    
                    # First convert singular to plural directory names
                    plural_dirs = [to_plural(t) for t in decision.media_to_download]
                    
                    # Then convert directory names to ScreenScraper media types
                    screenscraper_types = convert_directory_names_to_media_types(plural_dirs)
                    
                    logger.debug(
                        f"[{rom_info.filename}] Media type conversion: "
                        f"singular={decision.media_to_download} -> "
                        f"plural_dirs={plural_dirs} -> "
                        f"screenscraper={screenscraper_types}"
                    )
                    
                    # Filter media list to only include types we want to download
                    filtered_media_list = [
                        m for m in media_list 
                        if m.get('type') in screenscraper_types
                    ]
                    
                    if filtered_media_list:
                        logger.info(
                            f"[{rom_info.filename}] Downloading {len(decision.media_to_download)} media types concurrently: "
                            f"{', '.join(decision.media_to_download)}"
                        )
                        
                        # Create progress callback to update UI during download
                        def media_progress_callback(media_type: str, current_idx: int, total_count: int):
                            # Update pipeline UI
                            if self.console_ui:
                                self.console_ui.update_media_download_stage(
                                    rom_info.filename,
                                    media_type,
                                    'start'
                                )
                        
                        # Download all media concurrently
                        download_results, _ = await media_downloader.download_media_for_game(
                            media_list=filtered_media_list,
                            rom_path=str(rom_info.path),
                            system=system.name,
                            progress_callback=media_progress_callback,
                            shutdown_event=shutdown_event
                        )
                        
                        # Process results
                        for result in download_results:
                            if result.success and result.file_path:
                                # Convert ScreenScraper media type to ES-DE singular form for logging/tracking
                                from ..media.media_types import get_directory_for_media_type, to_singular
                                plural_dir = get_directory_for_media_type(result.media_type)
                                media_type_singular = to_singular(plural_dir)
                                
                                # Update UI: Media download complete
                                if self.console_ui:
                                    self.console_ui.update_media_download_stage(
                                        rom_info.filename,
                                        result.media_type,
                                        'complete'
                                    )
                                
                                # Track using singular ES-DE type
                                media_paths[media_type_singular] = result.file_path
                                media_count += 1
                                completed_tasks += 1
                                
                                # Log successful download with ES-DE singular type
                                logger.info(
                                    f"[{rom_info.filename}] Downloaded {media_type_singular}"
                                )
                                
                                # Store hash from download result (already calculated by media_downloader)
                                if result.hash_value:
                                    media_hashes[media_type_singular] = result.hash_value
                                    logger.debug(
                                        f"[{rom_info.filename}] Media hash: {media_type_singular} = {result.hash_value}"
                                    )
                                else:
                                    logger.debug(f"[{rom_info.filename}] No hash available for {media_type_singular}")
                
                # Validate existing media (only in normal or strict mode)
                if decision.media_to_validate and validation_mode != 'disabled':
                    for media_type_singular in decision.media_to_validate:
                        # Check if media file exists
                        media_path = self._get_media_path(system, media_type_singular, rom_info.path)
                        if not media_path or not media_path.exists():
                            # File doesn't exist - add to download list
                            logger.debug(f"[{rom_info.filename}] Media file missing: {media_type_singular}, will download")
                            if media_type_singular not in decision.media_to_download:
                                decision.media_to_download.append(media_type_singular)
                            continue
                        
                        # Get expected hash from cache
                        expected_hash = None
                        if self.api_client.cache and rom_hash:
                            expected_hash = self.api_client.cache.get_media_hash(rom_hash, media_type_singular)
                        
                        if not expected_hash:
                            # No hash in cache
                            if validation_mode == 'strict':
                                # Strict mode: re-download files without cached hashes
                                logger.debug(f"[{rom_info.filename}] No cached hash for {media_type_singular} in strict mode, will re-download")
                                if media_type_singular not in decision.media_to_download:
                                    decision.media_to_download.append(media_type_singular)
                            else:
                                # Normal mode: accept existing file
                                logger.debug(f"[{rom_info.filename}] Media exists (no cached hash): {media_type_singular}")
                                media_paths[media_type_singular] = str(media_path)
                                if self.console_ui:
                                    self.console_ui.increment_media_validated(media_type_singular)
                            continue
                        
                        # Strict mode: Calculate current hash and compare
                        if validation_mode == 'strict':
                            current_hash = calculate_hash(
                                media_path,
                                algorithm=hash_algorithm,
                                size_limit=0
                            )
                            
                            if current_hash == expected_hash:
                                # Hash matches - keep existing file
                                logger.info(f"[{rom_info.filename}] Media validated: {media_type_singular} (hash={current_hash})")
                                media_paths[media_type_singular] = str(media_path)
                                media_hashes[media_type_singular] = current_hash
                                
                                if self.console_ui:
                                    self.console_ui.increment_media_validated(media_type_singular)
                            else:
                                # Hash mismatch - re-download
                                logger.info(
                                    f"[{rom_info.filename}] Media hash mismatch: {media_type_singular} "
                                    f"(expected: {expected_hash}, got: {current_hash}) - will re-download"
                                )
                                if media_type_singular not in decision.media_to_download:
                                    decision.media_to_download.append(media_type_singular)
                        else:
                            # Normal mode: trust cached hash, no file validation
                            logger.debug(f"[{rom_info.filename}] Media exists with cached hash: {media_type_singular}")
                            media_paths[media_type_singular] = str(media_path)
                            media_hashes[media_type_singular] = expected_hash
                            if self.console_ui:
                                self.console_ui.increment_media_validated(media_type_singular)
                    
                    # Re-download any media that failed validation
                    if decision.media_to_download:
                        # Filter media_list for types that need re-download
                        from ..media.media_types import to_plural, convert_directory_names_to_media_types
                        plural_dirs = [to_plural(t) for t in decision.media_to_download]
                        screenscraper_types = convert_directory_names_to_media_types(plural_dirs)
                        
                        redownload_media_list = [
                            m for m in media_list 
                            if m.get('type') in screenscraper_types
                        ]
                        
                        if redownload_media_list:
                            logger.info(
                                f"[{rom_info.filename}] Re-downloading {len(redownload_media_list)} media types after validation"
                            )
                            
                            def media_redownload_callback(media_type: str, current_idx: int, total_count: int):
                                if self.console_ui:
                                    self.console_ui.update_media_download_stage(
                                        rom_info.filename,
                                        media_type,
                                        'start'
                                    )
                            
                            download_results, _ = await media_downloader.download_media_for_game(
                                media_list=redownload_media_list,
                                rom_path=str(rom_info.path),
                                system=system.name,
                                progress_callback=media_redownload_callback,
                                shutdown_event=shutdown_event
                            )
                            
                            # Process re-download results
                            for result in download_results:
                                if result.success and result.file_path:
                                    # Convert ScreenScraper media type to ES-DE singular form for logging/tracking
                                    from ..media.media_types import get_directory_for_media_type, to_singular
                                    plural_dir = get_directory_for_media_type(result.media_type)
                                    media_type_singular = to_singular(plural_dir)
                                    
                                    media_paths[media_type_singular] = result.file_path
                                    media_count += 1
                                    
                                    logger.info(
                                        f"[{rom_info.filename}] Re-downloaded {media_type_singular}: "
                                        f"{result.file_path}"
                                    )
                                    
                                    if result.hash_value:
                                        media_hashes[media_type_singular] = result.hash_value
                                    
                                    if self.console_ui:
                                        self.console_ui.update_media_download_stage(
                                            rom_info.filename,
                                            media_type_singular,
                                            'complete'
                                        )
            
            # Clean disabled media types if configured
            if decision.clean_disabled_media:
                from ..media.media_types import MEDIA_TYPE_SINGULAR
                
                # Get all possible media types (singular form)
                all_media_types = set(MEDIA_TYPE_SINGULAR.values())
                # Get currently enabled media types (already in singular form)
                enabled_types = set(media_types)
                # Find disabled types
                disabled_types = all_media_types - enabled_types
                
                for media_type_singular in disabled_types:
                    media_path = self._get_media_path(system, rom_info, media_type_singular)
                    
                    if media_path and media_path.exists():
                        if not self.dry_run:
                            # Move to CLEANUP directory instead of deleting
                            from ..media.media_types import to_plural
                            media_type_plural = to_plural(media_type_singular)
                            cleanup_dir = self.media_directory / "CLEANUP" / system.name / media_type_plural
                            cleanup_dir.mkdir(parents=True, exist_ok=True)
                            
                            cleanup_path = cleanup_dir / media_path.name
                            media_path.rename(cleanup_path)
                            
                            logger.info(
                                f"[{rom_info.filename}] Cleaned disabled media: {media_type_singular} "
                                f"(moved to CLEANUP/{system.name}/{media_type_plural})"
                            )
                        else:
                            logger.info(
                                f"[{rom_info.filename}] Would clean disabled media: {media_type_singular}"
                            )
            
            # Step 6: Create or update GameEntry (without hash - using cache instead)
            if decision.update_metadata and game_info:
                # Create entry from API response
                game_entry = GameEntry.from_api_response(
                    game_info=game_info,
                    rom_path=f"./{rom_info.filename}",
                    media_paths=media_paths
                )
                
                # Merge with existing entry if present
                if gamelist_entry and decision.update_metadata:
                    scraping_config = self.config.get('scraping', {})
                    merge_strategy = scraping_config.get('merge_strategy', 'preserve_user_edits')
                    auto_favorite_enabled = scraping_config.get('auto_favorite_enabled', False)
                    auto_favorite_threshold = scraping_config.get('auto_favorite_threshold', 0.9)
                    
                    merger = MetadataMerger(
                        merge_strategy=merge_strategy,
                        auto_favorite_enabled=auto_favorite_enabled,
                        auto_favorite_threshold=auto_favorite_threshold
                    )
                    
                    merge_result = merger.merge_entries(gamelist_entry, game_entry)
                    
                    game_entry = merge_result.merged_entry
                    
                    logger.debug(
                        f"Metadata merged: {len(merge_result.preserved_fields)} preserved, "
                        f"{len(merge_result.updated_fields)} updated"
                    )
                
                # Update cache with media hashes (if cache enabled and we have hashes)
                if self.api_client.cache and rom_hash and media_hashes:
                    self.api_client.cache.update_media_hashes(rom_hash, media_hashes)
                    logger.debug(f"Updated cache with {len(media_hashes)} media hashes for {rom_info.filename}")
                
                # Update UI: ROM complete
                if self.console_ui:
                    self.console_ui.increment_completed()
                
                return ScrapingResult(
                    rom_path=rom_info.path,
                    success=True,
                    api_id=str(game_info.get('id', '')),
                    media_downloaded=media_count,
                    game_info=game_info,
                    media_paths=media_paths
                )
            
            # Return success even if no updates made
            # Update UI: ROM complete
            if self.console_ui:
                self.console_ui.increment_completed()
            
            return ScrapingResult(
                rom_path=rom_info.path,
                success=True,
                api_id=str(game_info.get('id', '')) if game_info else None,
                media_downloaded=media_count,
                game_info=game_info,
                media_paths=media_paths
            )
            
        except Exception as e:
            logger.error(f"[{rom_info.filename}] Error scraping: {e}")
            
            return ScrapingResult(
                rom_path=rom_info.path,
                success=False,
                error=str(e)
            )
    
    def _create_rom_processor(
        self,
        system: SystemDefinition,
        media_types: List[str],
        preferred_regions: List[str],
        existing_entries: List[GameEntry] = None
    ) -> Callable:
        """
        Create a ROM processor function for use with ThreadPoolManager.submit_rom_batch
        
        Args:
            system: System definition
            media_types: Media types to download
            preferred_regions: Region preference list
            existing_entries: List of existing gamelist entries
            
        Returns:
            Async callable that processes a single ROM with optional callback
        """
        async def process_rom(
            rom_info: ROMInfo,
            operation_callback: Optional[Callable[[str, str, str, str, Optional[float], Optional[int], Optional[int]], None]] = None,
            shutdown_event: Optional[asyncio.Event] = None
        ) -> ScrapingResult:
            """
            Process a single ROM end-to-end
            
            Args:
                rom_info: ROM information
                operation_callback: Optional UI callback for progress updates
                shutdown_event: Optional event to check for cancellation
                
            Returns:
                ScrapingResult
            """
            rom_start_time = time.time()
            
            try:
                # Call the existing _scrape_rom method with callback and existing_entries
                result = await self._scrape_rom(
                    system=system,
                    rom_info=rom_info,
                    media_types=media_types,
                    preferred_regions=preferred_regions,
                    existing_entries=existing_entries,
                    operation_callback=operation_callback,
                    shutdown_event=shutdown_event
                )
                
                # Record total ROM processing time for performance metrics
                rom_duration = time.time() - rom_start_time
                if self.performance_monitor:
                    self.performance_monitor.record_rom_processing(rom_duration)
                
                return result
                
            except Exception as e:
                logger.error(f"[{rom_info.filename}] ROM processor error: {e}")
                return ScrapingResult(
                    rom_path=rom_info.path,
                    success=False,
                    error=str(e)
                )
        
        return process_rom
    
    async def _batch_hash_roms(
        self,
        rom_entries: List[ROMInfo],
        hash_algorithm: str,
        batch_size: int = 100
    ) -> List[ROMInfo]:
        """
        Hash ROMs in concurrent batches to feed the pipeline.
        
        Processes ROMs in batches using asyncio.gather() with asyncio.to_thread()
        to maximize CPU utilization while preventing memory exhaustion.
        
        Args:
            rom_entries: List of ROM entries to hash
            hash_algorithm: Hash algorithm to use (crc32, md5, sha1, etc)
            batch_size: Number of ROMs to hash concurrently per batch
            
        Returns:
            List of ROMInfo objects with hash_value populated
        """
        from ..scanner.rom_types import ROMType
        from ..scanner.m3u_parser import get_disc1_file
        from ..scanner.disc_handler import get_contained_file
        
        total = len(rom_entries)
        hashed_count = 0
        
        # Update UI: Start hashing stage
        if self.console_ui:
            self.console_ui.update_hashing_progress(0, total, 'Starting...')
        
        for i in range(0, total, batch_size):
            batch = rom_entries[i:i + batch_size]
            
            # Create hash tasks for this batch
            hash_tasks = []
            for rom_info in batch:
                # Skip if hash already calculated
                if rom_info.hash_value:
                    continue
                
                # Determine which file to hash based on ROM type
                hash_file = None
                if rom_info.rom_type == ROMType.STANDARD:
                    hash_file = rom_info.path
                elif rom_info.rom_type == ROMType.M3U_PLAYLIST:
                    try:
                        hash_file = get_disc1_file(rom_info.path)
                    except Exception as e:
                        logger.warning(f"Failed to get disc1 file for {rom_info.name}: {e}")
                        continue
                elif rom_info.rom_type == ROMType.DISC_SUBDIR:
                    # Use contained file that was stored during scanning
                    if rom_info.contained_file:
                        hash_file = rom_info.contained_file
                    else:
                        try:
                            hash_file = get_contained_file(rom_info.path)
                        except Exception as e:
                            logger.warning(f"Failed to get contained file for {rom_info.name}: {e}")
                            continue
                else:
                    hash_file = rom_info.path
                
                if not hash_file:
                    logger.warning(f"No hash file determined for {rom_info.name}")
                    continue
                
                # Wrap calculate_hash in asyncio.to_thread for concurrent execution
                size_limit = rom_info.crc_size_limit
                task = asyncio.to_thread(
                    calculate_hash,
                    hash_file,
                    algorithm=hash_algorithm,
                    size_limit=size_limit
                )
                hash_tasks.append((rom_info, task))
            
            # Execute batch concurrently
            if hash_tasks:
                results = await asyncio.gather(*[task for _, task in hash_tasks], return_exceptions=True)
                
                # Assign hash values to ROM entries
                for (rom_info, _), result in zip(hash_tasks, results):
                    if isinstance(result, Exception):
                        logger.warning(f"Failed to hash {rom_info.name}: {result}")
                    else:
                        rom_info.hash_value = result
                        hashed_count += 1
            
            # Progress logging every 1000 ROMs
            if (i + batch_size) % 1000 == 0 or (i + batch_size) >= total:
                logger.debug(f"Hashed {min(i + batch_size, total)}/{total} ROMs ({hashed_count} successful)")
                
                # Update UI with current progress
                if self.console_ui:
                    current_count = min(i + batch_size, total)
                    batch_num = (i // batch_size) + 1
                    total_batches = (total + batch_size - 1) // batch_size
                    self.console_ui.update_hashing_progress(
                        current_count, 
                        total, 
                        f'batch {batch_num}/{total_batches}'
                    )
        
        # Mark hashing complete
        if self.console_ui:
            self.console_ui.update_hashing_progress(total, total, 'Complete')
        
        return rom_entries
    
    async def _scrape_roms_parallel(
        self,
        system: SystemDefinition,
        rom_entries: List[ROMInfo],
        media_types: List[str],
        preferred_regions: List[str],
        existing_entries: List[GameEntry] = None
    ) -> Tuple[List[ScrapingResult], List[dict]]:
        """
        Scrape ROMs in parallel using WorkQueueManager and async task pool.
        
        Uses work queue consumer pattern with selective retry based on error category.
        
        Args:
            system: System definition
            rom_entries: List of ROM information from scanner
            media_types: Media types to download
            preferred_regions: Region priority list
            existing_entries: List of existing gamelist entries
            
        Returns:
            Tuple of (results list, not_found_items list)
        """
        results = []
        not_found_items = []  # Track 404 errors separately
        rom_count = 0
        
        # Pre-hash ROMs in batches for better throughput (feeds pipeline efficiently)
        logger.info(f"Pre-hashing {len(rom_entries)} ROMs in concurrent batches of 100")
        hash_algorithm = self.config.get('runtime', {}).get('hash_algorithm', 'crc32')
        rom_entries = await self._batch_hash_roms(rom_entries, hash_algorithm, batch_size=100)
        logger.info(f"ROM hashing complete: {sum(1 for r in rom_entries if r.hash_value)} hashed, {sum(1 for r in rom_entries if not r.hash_value)} skipped")
        
        # Populate work queue with all ROM entries
        logger.info(f"Populating work queue with {len(rom_entries)} ROM entries")
        successfully_added = 0
        for idx, rom_info in enumerate(rom_entries):
            try:
                # Removed excessive debug logging that was causing BrokenPipeError with Rich
                rom_info_dict = {
                    'filename': rom_info.filename,
                    'path': str(rom_info.path),
                    'system': rom_info.system,
                    'file_size': rom_info.file_size,
                    'hash_type': rom_info.hash_type,
                    'hash_value': rom_info.hash_value,
                    'query_filename': rom_info.query_filename,
                    'basename': rom_info.basename,
                    'rom_type': rom_info.rom_type.value,  # Serialize enum as string
                    'crc_size_limit': rom_info.crc_size_limit,
                    'disc_files': [str(f) for f in rom_info.disc_files] if rom_info.disc_files else None,
                    'contained_file': str(rom_info.contained_file) if rom_info.contained_file else None
                }
                self.work_queue.add_work(rom_info_dict, 'full_scrape', Priority.NORMAL)
                successfully_added += 1
            except KeyboardInterrupt:
                logger.warning(f"Keyboard interrupt received while adding ROM {idx} to queue")
                raise
            except SystemExit as e:
                logger.error(f"SystemExit raised while adding ROM {idx} ({rom_info.filename}): exit code {e.code}", exc_info=True)
                raise
            except BaseException as e:
                logger.error(f"BaseException raised while adding ROM {idx} ({rom_info.filename}): {type(e).__name__}: {e}", exc_info=True)
                raise
            except Exception as e:
                logger.error(f"Failed to add ROM {idx} ({rom_info.filename}) to work queue: {e}", exc_info=True)
                raise
        
        logger.info(f"Work queue populated: successfully added {successfully_added}/{len(rom_entries)}, queue reports {self.work_queue.get_stats()['pending']} items queued")
        
        # Work queue consumption using producer-consumer pattern with concurrent tasks
        if self.thread_manager and self.thread_manager.is_initialized() and not self.dry_run:
            logger.info(f"Using task pool with {self.thread_manager.max_concurrent} concurrent task(s)")
            
            # Create ROM processor (no UI callback needed for pipeline UI)
            rom_processor = self._create_rom_processor(system, media_types, preferred_regions, existing_entries)
            
            # Clear any previous results
            self.thread_manager.clear_results()
            
            # Spawn concurrent tasks that will continuously process from queue
            await self.thread_manager.spawn_workers(
                work_queue=self.work_queue,
                rom_processor=rom_processor,
                operation_callback=None,
                count=self.thread_manager.max_concurrent
            )
            
            logger.info(f"Pipeline tasks spawned. Waiting for completion...")
            
            # Start background task for periodic UI updates (Work Queue + Statistics)
            ui_update_task = None
            if self.console_ui:
                ui_update_task = asyncio.create_task(
                    self._periodic_ui_update(not_found_items, len(rom_entries))
                )
            
            # Wait for all work to complete and collect results
            task_results = await self.thread_manager.wait_for_completion()
            
            # Stop periodic UI updates
            if ui_update_task:
                ui_update_task.cancel()
                try:
                    await ui_update_task
                except asyncio.CancelledError:
                    # Expected when cancelling periodic task
                    pass
            
            logger.info(f"All pipeline tasks completed ({len(task_results)} results)")
            
            # Convert task results to our expected format and record in checkpoint
            for rom_info, result in task_results:
                rom_count += 1
                results.append(result)
                
                # Record in checkpoint
                if self.checkpoint_manager:
                    action = 'skip' if result.skipped else 'full_scrape'
                    self.checkpoint_manager.add_processed_rom(
                        rom_info.filename,
                        action,
                        result.success,
                        result.error
                    )
                    # Save checkpoint periodically
                    self.checkpoint_manager.save_checkpoint()
                
                # Track not found items
                if not result.success and result.error == "No game info found from API":
                    not_found_items.append({
                        'filename': rom_info.filename,
                        'path': str(rom_info.path)
                    })
            
            # Final UI update after all results collected
            if self.console_ui:
                await self._update_ui_progress(
                    rom_info_dict={'filename': 'Complete'},
                    rom_count=rom_count,
                    total_roms=len(rom_entries),
                    results=results,
                    not_found_items=not_found_items
                )
            
            # Mark system complete and stop pipeline tasks
            self.work_queue.mark_system_complete()
            await self.thread_manager.stop_workers()
            
        else:
            # Fallback: Simple sequential processing
            # Used when: dry-run mode, thread_manager not initialized, or no thread_manager
            logger.info("Using simple sequential processing (no concurrent tasks)")
            
            # Sequential processing using _scrape_rom
            for rom_info in rom_entries:
                rom_count += 1
                
                # Update UI
                if self.console_ui:
                    await self._update_ui_progress(
                        {'filename': rom_info.filename}, rom_count, len(rom_entries),
                        results, not_found_items
                    )
                
                # Process ROM using unified method
                try:
                    result = await self._scrape_rom(
                        system=system,
                        rom_info=rom_info,
                        media_types=media_types,
                        preferred_regions=preferred_regions,
                        existing_entries=existing_entries
                    )
                    results.append(result)
                    
                    # Record in checkpoint
                    if self.checkpoint_manager:
                        action = 'skip' if result.skipped else 'full_scrape'
                        self.checkpoint_manager.add_processed_rom(
                            rom_info.filename,
                            action,
                            result.success,
                            result.error
                        )
                        # Save checkpoint periodically
                        self.checkpoint_manager.save_checkpoint()
                    
                    # Track not found items
                    if not result.success and result.error == "No game info found from API":
                        not_found_items.append({
                            'filename': rom_info.filename,
                            'path': str(rom_info.path)
                        })
                
                except Exception as e:
                    # Fatal error - propagate
                    logger.error(f"Fatal error processing ROM {rom_info.filename}: {e}")
                    raise
        
        return results, not_found_items
    
    async def _search_fallback(
        self,
        rom_info: ROMInfo,
        preferred_regions: List[str],
        shutdown_event: Optional[asyncio.Event] = None
    ) -> Optional[Dict]:
        """
        Search fallback when hash lookup fails.
        
        Searches by filename, scores candidates, and either auto-selects
        best match or prompts user interactively.
        
        Args:
            rom_info: ROM information from scanner
            preferred_regions: Region preference list for scoring
            shutdown_event: Optional event to check for cancellation
            
        Returns:
            Game data dictionary if match found, None otherwise
        """
        # Check for shutdown before searching
        if shutdown_event and shutdown_event.is_set():
            raise asyncio.CancelledError("Shutdown requested")
        
        try:
            # Search API
            results = await self.api_client.search_game(
                rom_info,
                shutdown_event=shutdown_event,
                max_results=self.search_max_results
            )
            
            if not results:
                logger.debug(f"[{rom_info.filename}] Search returned no results")
                return None
            
            # Convert ROM info to dict for scorer
            rom_info_dict = {
                'path': str(rom_info.path),
                'filename': rom_info.filename,
                'size': rom_info.file_size,
                'crc32': rom_info.hash_value,  # For backward compatibility with scorer
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
            logger.debug(f"[{rom_info.filename}] Search candidates:")
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
                    f"[{rom_info.filename}] Auto-selected search match: "
                    f"{game_name} (confidence: {best_score:.1%})"
                )
                return best_game
            else:
                logger.info(
                    f"[{rom_info.filename}] Best match below threshold: "
                    f"{best_score:.1%} < {self.search_confidence_threshold:.1%}"
                )
                return None
                
        except SkippableAPIError as e:
            logger.debug(f"[{rom_info.filename}] Search API error: {e}")
            return None
        except Exception as e:
            logger.error(f"[{rom_info.filename}] Unexpected error in search fallback: {e}")
            return None
    
    def _generate_gamelist(
        self,
        system: SystemDefinition,
        results: List[ScrapingResult]
    ) -> Optional[dict]:
        """
        Generate gamelist.xml for system.
        
        Args:
            system: System definition
            results: Scraping results
            
        Returns:
            Integrity validation result dict or None
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
                integrity_result = generator.generate_gamelist(
                    scraped_games=scraped_games,
                    merge_existing=True
                )
                return integrity_result
            except Exception as e:
                raise Exception(f"Failed to generate gamelist: {e}")
        
        return None
    
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
                    if rom_info.hash_value:
                        f.write(f"  {rom_info.hash_type.upper()}: {rom_info.hash_value}\n")
                    f.write(f"  Size: {rom_info.file_size} bytes\n")
                    f.write(f"  Error: {error}\n")
                    f.write("\n")
            
            logger.info(f"Wrote not-found items to {output_file}")
        except Exception as e:
            logger.error(f"Failed to write not-found summary: {e}")
            raise
    
    async def _periodic_ui_update(
        self,
        not_found_items: list,
        total_roms: int
    ) -> None:
        """Background task to periodically update UI during parallel processing"""
        paused_logged = False  # Track whether we've logged pause state
        
        try:
            while True:
                await asyncio.sleep(0.5)  # Update every 500ms
                
                # Check for pause state from keyboard controls
                if self.console_ui and self.console_ui.is_paused:
                    if not paused_logged:
                        logger.info("Processing paused - waiting for resume (press P to resume)")
                        paused_logged = True
                    # Continue loop but skip work processing
                    continue
                elif paused_logged:
                    # Transitioned from paused to resumed
                    logger.info("Processing resumed")
                    paused_logged = False
                
                # Get current results from thread manager (real-time)
                results = []
                if self.thread_manager:
                    task_results = await self.thread_manager.get_current_results()
                    # Extract just the result objects (task_results is list of (rom_info, result) tuples)
                    results = [result for _, result in task_results]
                
                # Call the main UI update method with real-time results
                await self._update_ui_progress(
                    rom_info_dict={'filename': 'Processing...'},
                    rom_count=len(results),
                    total_roms=total_roms,
                    results=results,
                    not_found_items=not_found_items
                )
        except asyncio.CancelledError:
            # Task cancelled when processing completes - this is expected
            logger.debug("Periodic UI update task cancelled")
    
    async def _update_ui_progress(
        self,
        rom_info_dict: dict,
        rom_count: int,
        total_roms: int,
        results: list,
        not_found_items: list
    ) -> None:
        """Update UI with current progress"""
        if not self.console_ui:
            return
        
        # Get work queue stats for queue pending count
        queue_stats = self.work_queue.get_stats()
        
        # Update footer with current stats and performance metrics
        # Calculate counts matching the logic in scrape_system()
        successful_count = sum(1 for r in results if r.success)
        failed_count = sum(1 for r in results if not r.success and r.error)
        skipped_count = sum(1 for r in results if not r.success and not r.error)
        
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
            stats = await self.thread_manager.get_stats()
            thread_stats = {
                'active_threads': stats.get('active_tasks', 0),
                'max_threads': stats.get('max_tasks', 1)
            }
        
        # Get API quota from throttle manager
        api_quota = {}
        if self.throttle_manager:
            api_quota = self.throttle_manager.get_quota_stats()
        
        self.console_ui.update_footer(
            stats={
                'successful': successful_count,
                'failed': failed_count,
                'skipped': skipped_count
            },
            api_quota=api_quota,
            thread_stats=thread_stats,
            performance_metrics=performance_metrics,
            queue_pending=queue_stats['pending']
        )
    
    def _prompt_gamelist_validation_failure(
        self,
        system_name: str,
        validation_result
    ) -> bool:
        """
        Prompt user whether to continue when gamelist validation fails.
        
        Args:
            system_name: Name of the system
            validation_result: ValidationResult from IntegrityValidator
            
        Returns:
            True to continue, False to skip system
        """
        # In non-interactive mode, always continue
        if not self.interactive_search:
            return True
        
        # Prompt user
        print(f"\n⚠️  Gamelist validation failed for {system_name}")
        print(f"   Match ratio: {validation_result.match_ratio:.1%} (threshold: {self.integrity_validator.threshold:.1%})")
        print(f"   Missing ROMs: {len(validation_result.missing_roms)}")
        print(f"   Orphaned entries: {len(validation_result.orphaned_entries)}")
        
        response = input("\nContinue processing this system? [y/N]: ").strip().lower()
        return response in ('y', 'yes')
    
    def _get_media_path(
        self,
        system: SystemDefinition,
        rom_info: ROMInfo,
        media_type_singular: str
    ) -> Optional[Path]:
        """
        Get the expected path for a media file.
        
        Args:
            system: System definition
            rom_info: ROM information
            media_type_singular: Singular media type name
            
        Returns:
            Path to media file, or None if not found
        """
        from ..media.media_types import get_directory_for_media_type
        
        try:
            # Convert singular to ES-DE directory name
            directory = get_directory_for_media_type(media_type_singular)
        except ValueError:
            logger.warning(f"Unknown media type: {media_type_singular}")
            return None
        
        # Build path: media_root / system / directory / rom_stem.ext
        media_dir = self.media_directory / system.name / directory
        rom_stem = rom_info.path.stem
        
        # Try common image extensions
        for ext in ['.png', '.jpg', '.jpeg']:
            media_path = media_dir / f"{rom_stem}{ext}"
            if media_path.exists():
                return media_path
        
        return None
    
    def _write_summary_log(
        self,
        system: SystemDefinition,
        results: List[ScrapingResult],
        scraped_count: int,
        skipped_count: int,
        failed_count: int
    ) -> None:
        """
        Write summary log for a system.
        
        Args:
            system: System definition
            results: List of scraping results
            scraped_count: Number of successfully scraped ROMs
            skipped_count: Number of skipped ROMs
            failed_count: Number of failed ROMs
        """
        from datetime import datetime
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        gamelist_dir = self.paths['gamelists'] / system.name
        gamelist_dir.mkdir(parents=True, exist_ok=True)
        
        summary_path = gamelist_dir / f"curateur_summary_{timestamp}.log"
        
        try:
            with open(summary_path, 'w') as f:
                f.write(f"Curateur Summary - {system.name}\n")
                f.write(f"Generated: {timestamp}\n")
                f.write(f"{'='*60}\n\n")
                
                f.write(f"Total ROMs: {len(results)}\n")
                f.write(f"Successful: {scraped_count}\n")
                f.write(f"Skipped: {skipped_count}\n")
                f.write(f"Failed: {failed_count}\n\n")
                
                # Successful results
                successful_results = [r for r in results if r.success and not r.error]
                if successful_results:
                    f.write("=== Successful ===\n")
                    for result in successful_results:
                        f.write(f"✓ {result.rom_path.name}\n")
                    f.write("\n")
                
                # Skipped results
                skipped_results = [r for r in results if hasattr(r, 'skipped') and r.skipped]
                if skipped_results:
                    f.write("=== Skipped ===\n")
                    for result in skipped_results:
                        reason = getattr(result, 'skip_reason', 'Unknown reason')
                        f.write(f"○ {result.rom_path.name} - {reason}\n")
                    f.write("\n")
                
                # Failed results
                failed_results = [r for r in results if not r.success]
                if failed_results:
                    f.write("=== Failed ===\n")
                    for result in failed_results:
                        f.write(f"✗ {result.rom_path.name} - {result.error}\n")
                    f.write("\n")
            
            logger.info(f"Summary log written: {summary_path}")
        except Exception as e:
            logger.warning(f"Failed to write summary log: {e}")


