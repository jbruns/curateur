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
from datetime import datetime
import time

if TYPE_CHECKING:
    from ..workflow.thread_pool import ThreadPoolManager
    from ..workflow.performance import PerformanceMonitor
    from ..ui.headless_logger import HeadlessLogger
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
from ..media.media_downloader import MediaDownloader
from ..media.media_types import to_singular
from ..gamelist.generator import GamelistGenerator
from ..gamelist.game_entry import GameEntry
from ..gamelist.parser import GamelistParser
from ..gamelist.integrity_validator import IntegrityValidator
from ..gamelist.metadata_merger import MetadataMerger
from ..gamelist.backup import GamelistBackup
from ..workflow.work_queue import WorkQueueManager, Priority
from ..workflow.evaluator import WorkflowEvaluator, WorkflowDecision

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
    game_entry: Optional['GameEntry'] = None  # Pre-merged entry from MetadataMerger
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
        throttle_manager: Optional['ThrottleManager'] = None,
        clear_cache: bool = False,
        event_bus: Optional[Any] = None,
        textual_ui: Optional[Any] = None
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
            throttle_manager: Optional ThrottleManager for quota tracking
            clear_cache: Whether to clear metadata cache before scraping
            event_bus: Optional EventBus for UI event emissions
            textual_ui: Optional Textual UI instance for flag polling
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
        self.throttle_manager = throttle_manager
        self.event_bus = event_bus
        self.textual_ui = textual_ui

        # Search response handling for interactive search
        self.search_response_queues: Dict[str, asyncio.Queue] = {}  # request_id -> response queue
        self.search_response_lock = asyncio.Lock()

        # Initialize workflow evaluator with cache for media hash lookups
        self.evaluator = WorkflowEvaluator(self.config, cache=self.api_client.cache if self.api_client else None)

        # Initialize integrity validator
        integrity_threshold = self.config.get('scraping', {}).get('gamelist_integrity_threshold', 0.95)
        self.integrity_validator = IntegrityValidator(threshold=integrity_threshold)

        # Initialize metadata merger (reused for all ROMs)
        scraping_config = self.config.get('scraping', {})
        self.metadata_merger = MetadataMerger(
            merge_strategy=scraping_config.get('merge_strategy', 'preserve_user_edits'),
            auto_favorite_enabled=scraping_config.get('auto_favorite_enabled', False),
            auto_favorite_threshold=scraping_config.get('auto_favorite_threshold', 0.9)
        )

        # Store sortname config
        self.auto_sortname_enabled = scraping_config.get('auto_sortname_enabled', False)

        # Store paths for easy access
        self.paths = {
            'roms': self.rom_directory,
            'media': self.media_directory,
            'gamelists': self.gamelist_directory
        }

        # Track unmatched ROMs per system
        self.unmatched_roms: Dict[str, List[str]] = {}

        # Session statistics for aggregate tracking (never decrement, only increment)
        self.session_stats = {
            'api_successful': 0,
            'api_failed': 0,
            'api_queued': 0,
            'search_fallback': 0,
            'unmatched': 0,
            'media_by_type': {},  # {'box-2D': {'successful': N, 'failed': M, 'validated': X, 'skipped': Y}, ...}
            'media_validated': 0,
            'media_skipped': 0,
            'media_failed': 0,
            'cache_existing': 0,
            'cache_added': 0,
            'gamelist_existing': 0,
            'gamelist_added': 0,
            'gamelist_updated': 0
        }

        # Active request tracking for Details tab
        # request_id -> {'rom_name': str, 'stage': str, 'start_time': float, 'retry_count': int, 'last_failure': str}
        self.active_requests: Dict[str, Dict[str, Any]] = {}

    def update_search_config(
        self,
        enable_fallback: bool = None,
        confidence_threshold: float = None,
        max_results: int = None
    ) -> None:
        """Update search configuration at runtime.

        Args:
            enable_fallback: Enable/disable search fallback (None to skip)
            confidence_threshold: New confidence threshold 0.0-1.0 (None to skip)
            max_results: New max search results (None to skip)
        """
        if enable_fallback is not None:
            self.enable_search_fallback = enable_fallback
            logger.info(f"Set search fallback to {enable_fallback}")

        if confidence_threshold is not None:
            self.search_confidence_threshold = confidence_threshold
            logger.info(f"Updated search confidence threshold to {confidence_threshold:.0%}")

        if max_results is not None:
            self.search_max_results = max_results
            logger.info(f"Updated search max results to {max_results}")

    async def scrape_system(
        self,
        system: SystemDefinition,
        media_types: List[str] = None,
        preferred_regions: List[str] = None,
        progress_tracker = None,
        current_system_index: int = 0,
        total_systems: int = 1
    ) -> SystemResult:
        """
        Scrape a single system.

        Args:
            system: System definition
            media_types: Media types to download (default: ['box-2D', 'ss'])
            preferred_regions: Region priority list (default: ['us', 'wor', 'eu'])
            progress_tracker: Optional progress tracker to update with ROM count
            current_system_index: Index of this system in the system list (0-based)
            total_systems: Total number of systems being scraped

        Returns:
            SystemResult with scraping statistics
        """
        if media_types is None:
            media_types = ['box-2D', 'ss']

        if preferred_regions is None:
            preferred_regions = ['us', 'wor', 'eu']

        # Step 0: System start logging
        system_start_time = time.time()
        logger.info(f"=== Begin work for system: {system.name} ===")
        logger.info(f"Platform: {system.platform}")
        logger.info(f"Path: {system.path}")

        gamelist_dir = self.paths['gamelists'] / system.name

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

        # Track cache existing count for this system
        self.session_stats['cache_existing'] = cache_stats.get('valid_entries', 0)

        # Step 1: Scan ROMs
        logger.info("Scanning ROMs...")
        crc_size_limit = self.config.get('runtime', {}).get('crc_size_limit', 1073741824)
        rom_entries = scan_system(
            system,
            rom_root=self.rom_directory,
            crc_size_limit=crc_size_limit
        )
        logger.info(f"ROM scan complete: {len(rom_entries)} files found")

        # Early exit if no ROMs found - don't create any directories or files
        if len(rom_entries) == 0:
            logger.info(f"No ROMs found for {system.name}, skipping all filesystem operations")
            # Reset work queue for next system
            if self.work_queue:
                self.work_queue.reset_for_new_system()
                logger.debug(f"Work queue reset after completing {system.name}")
            return SystemResult(
                system_name=system.fullname,
                total_roms=0,
                scraped=0,
                failed=0,
                skipped=0,
                results=[],
                work_queue_stats=self.work_queue.get_stats() if self.work_queue else None,
                failed_items=self.work_queue.get_failed_items() if self.work_queue else None,
                not_found_items=[]
            )

        # Notify progress tracker with actual ROM count
        if progress_tracker:
            progress_tracker.start_system(system.fullname, len(rom_entries))

        # Emit SystemStartedEvent and LogEntryEvent for UI
        if self.event_bus:
            from ..ui.events import SystemStartedEvent, LogEntryEvent
            await self.event_bus.publish(
                SystemStartedEvent(
                    system_name=system.name,
                    system_fullname=system.fullname,
                    total_roms=len(rom_entries),
                    current_index=current_system_index,
                    total_systems=total_systems
                )
            )
            await self.event_bus.publish(
                LogEntryEvent(
                    level=logging.INFO,
                    message=f"Started processing {system.fullname} ({len(rom_entries)} ROMs)",
                    timestamp=datetime.now()
                )
            )

        # Step 2: Parse and validate existing gamelist
        gamelist_path = self.paths['gamelists'] / system.name / 'gamelist.xml'
        existing_entries = []

        if gamelist_path.exists():
            logger.info("Parsing existing gamelist...")
            parser = GamelistParser()
            try:
                existing_entries = parser.parse_gamelist(gamelist_path)
                logger.info(f"Parsed {len(existing_entries)} entries from existing gamelist")
                
                # Track existing gamelist count
                self.session_stats['gamelist_existing'] = len(existing_entries)

                # Validate gamelist integrity
                rom_paths = [rom_info.path for rom_info in rom_entries]
                validation_result = self.integrity_validator.validate(existing_entries, rom_paths)

                logger.info(f"Gamelist validation: {validation_result.match_ratio:.1%} match ratio")

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

        # Backup existing gamelist before processing begins
        if gamelist_path.exists() and not self.dry_run:
            try:
                backup_path = GamelistBackup.create_backup(gamelist_path)
                logger.info(f"Gamelist backed up to: {backup_path.name}")
            except Exception as e:
                logger.error(f"Failed to create gamelist backup: {e}")
                # Continue processing even if backup fails
                # User may not have write permissions or disk may be full

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
        # Write gamelist if there are new entries OR existing entries to maintain
        if not self.dry_run and (scraped_count > 0 or existing_entries):
            try:
                logger.info(f"Committing gamelist: {scraped_count} entries")
                logger.debug(f"About to call _generate_gamelist with {len(results)} results")
                integrity_result = self._generate_gamelist(system, results)
                logger.debug(f"_generate_gamelist returned: {integrity_result}")

                # Brief pause to show result
                import asyncio
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Failed to generate gamelist: {e}", exc_info=True)
                print(f"Warning: Failed to generate gamelist: {e}")

        # Step 6: Write unmatched ROMs log if any
        if len(rom_entries) > 0 and system.name in self.unmatched_roms and self.unmatched_roms[system.name]:
            try:
                self._write_unmatched_roms(system.name)
            except Exception as e:
                logger.warning(f"Failed to write unmatched ROMs log for {system.name}: {e}")

        # Step 7: Write not-found items log if any
        if len(rom_entries) > 0 and not_found_items:
            try:
                self._write_not_found_summary(system, not_found_items)
            except Exception as e:
                logger.warning(f"Failed to write not-found summary for {system.name}: {e}")

        # Step 8: Reset work queue for next system
        if self.work_queue:
            self.work_queue.reset_for_new_system()
            logger.debug(f"Work queue reset after completing {system.name}")

        # Step 9: Write summary log (only if ROMs were processed)
        if len(rom_entries) > 0:
            self._write_summary_log(system, results, scraped_count, skipped_count, failed_count)

        logger.info(
            f"System complete: {system.name} - "
            f"{scraped_count} successful, {skipped_count} skipped, {failed_count} failed"
        )
        logger.info(f"=== End work for system: {system.name} ===")

        # Emit SystemCompletedEvent and GamelistUpdateEvent for UI
        if self.event_bus:
            from ..ui.events import SystemCompletedEvent, LogEntryEvent, GamelistUpdateEvent
            system_duration = time.time() - system_start_time
            await self.event_bus.publish(
                SystemCompletedEvent(
                    system_name=system.name,
                    total_roms=scraped_count + failed_count + skipped_count,
                    successful=scraped_count,
                    failed=failed_count,
                    skipped=skipped_count,
                    elapsed_time=system_duration
                )
            )
            # Emit gamelist update stats
            await self.event_bus.publish(
                GamelistUpdateEvent(
                    system=system.name,
                    existing=self.session_stats['gamelist_existing'],
                    added=self.session_stats['gamelist_added'],
                    updated=self.session_stats['gamelist_updated']
                )
            )
            await self.event_bus.publish(
                LogEntryEvent(
                    level=logging.INFO,
                    message=f"Completed {system.name}: {scraped_count} successful, {failed_count} failed, {skipped_count} skipped in {system_duration:.1f}s",
                    timestamp=datetime.now()
                )
            )

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
        operation_callback: Optional[
            Callable[[str, str, str, str, Optional[float], Optional[int], Optional[int]], None]
        ] = None,
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
                rom_hash=rom_hash,
                system=system
            )

            # Log evaluator decision at DEBUG level
            logger.debug(
                f"Evaluator decision for {rom_info.filename}: "
                f"fetch_metadata={decision.fetch_metadata}, "
                f"update_metadata={decision.update_metadata}, "
                f"media_to_download={decision.media_to_download}, "
                f"media_to_validate={decision.media_to_validate}, "
                f"clean_disabled_media={decision.clean_disabled_media}, "
                f"skip_reason={decision.skip_reason}"
            )

            # Check if ROM should be skipped
            if decision.skip_reason:
                logger.info(f"[{rom_info.filename}] Skipping: {decision.skip_reason}")

                # Emit ROMProgressEvent for skipped ROM
                if self.event_bus:
                    from ..ui.events import ROMProgressEvent
                    await self.event_bus.publish(
                        ROMProgressEvent(
                            rom_name=rom_info.filename,
                            system=system.name,
                            status="skipped",
                            detail=decision.skip_reason
                        )
                    )

                # Preserve existing gamelist entry for skipped ROMs
                return ScrapingResult(
                    rom_path=rom_info.path,
                    success=True,
                    error=None,
                    skipped=True,
                    skip_reason=decision.skip_reason,
                    game_entry=gamelist_entry  # Preserve existing entry
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
                # Check if we have cached data
                from_cache = False
                if self.api_client.cache:
                    cached_data = self.api_client.cache.get(rom_hash, rom_size=rom_info.file_size)
                    from_cache = cached_data is not None

                source_label = "CACHED" if from_cache else "API"
                logger.info(
                    f"[{rom_info.filename}] Fetching metadata [{source_label}] "
                    f"(hash={rom_hash}, size={rom_info.file_size})"
                )
                logger.debug(
                    f"API request: hash={rom_hash}, "
                    f"size={rom_info.file_size}, "
                    f"system_id={system.platform}"
                )

                api_start = time.time()

                # Emit ActiveRequestEvent - API fetch started (only if not from cache)
                if self.event_bus and not from_cache:
                    from ..ui.events import ActiveRequestEvent
                    await self.event_bus.publish(
                        ActiveRequestEvent(
                            request_id=f"{rom_info.filename}-api",
                            rom_name=rom_info.filename,
                            stage="API Fetch",
                            status="started",
                            duration=0.0
                        )
                    )

                try:
                    game_info = await self.api_client.query_game(rom_info, shutdown_event=shutdown_event)
                    api_duration = time.time() - api_start
                    
                    # Ensure 'desc' field is extracted from 'descriptions' if missing (for old cache entries)
                    if game_info and 'descriptions' in game_info and 'desc' not in game_info:
                        descriptions = game_info['descriptions']
                        preferred_lang = self.config.get('scraping', {}).get('preferred_language', 'en')
                        
                        # Extract description using same logic as response_parser
                        if preferred_lang in descriptions:
                            game_info['desc'] = descriptions[preferred_lang]
                        elif 'en' in descriptions:
                            game_info['desc'] = descriptions['en']
                        elif descriptions:
                            game_info['desc'] = list(descriptions.values())[0]

                    # Emit ActiveRequestEvent - API fetch completed (only if not from cache)
                    if self.event_bus and not from_cache:
                        from ..ui.events import ActiveRequestEvent
                        await self.event_bus.publish(
                            ActiveRequestEvent(
                                request_id=f"{rom_info.filename}-api",
                                rom_name=rom_info.filename,
                                stage="API Fetch",
                                status="completed",
                                duration=api_duration
                            )
                        )

                    # Track cache additions (new API calls that get cached)
                    if game_info and not from_cache:
                        self.session_stats['cache_added'] += 1
                        self.session_stats['api_successful'] += 1

                    # Record API timing only if it was NOT a cache hit
                    if hasattr(self, 'performance_monitor') and self.performance_monitor and not from_cache:
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

                        # Emit GameCompletedEvent
                        if self.event_bus:
                            from ..ui.events import GameCompletedEvent
                            
                            # Extract year from release_dates (prefer us, wor, eu)
                            release_dates = game_info.get('release_dates', {})
                            release_date_str = release_dates.get('us') or release_dates.get('wor') or release_dates.get('eu') or None
                            year = release_date_str[:4] if release_date_str and len(release_date_str) >= 4 else 'Unknown'
                            
                            # Extract single genre from genres list
                            genres = game_info.get('genres', [])
                            genre = ', '.join(genres[:2]) if genres else 'Unknown'  # Limit to 2 genres for display
                            
                            await self.event_bus.publish(
                                GameCompletedEvent(
                                    game_id=game_info.get('id', ''),
                                    title=game_info.get('name', 'Unknown'),
                                    year=year,
                                    genre=genre,
                                    developer=game_info.get('developer', 'Unknown'),
                                    publisher=game_info.get('publisher', 'Unknown'),
                                    players=game_info.get('players', 'Unknown'),
                                    rating=game_info.get('rating'),
                                    description=game_info.get('desc', '')[:300]  # Truncate for performance
                                )
                            )
                            await asyncio.sleep(0)  # Yield to event processor

                    logger.debug(f"[{rom_info.filename}] Hash lookup successful")
                    # Increment task counter but don't emit completion status
                    completed_tasks += 1

                    # Emit ROMProgressEvent
                    if self.event_bus and game_info:
                        from ..ui.events import ROMProgressEvent
                        await self.event_bus.publish(
                            ROMProgressEvent(
                                rom_name=rom_info.filename,
                                system=system.name,
                                status="querying",
                                detail=f"Fetched metadata for {game_info.get('name', 'Unknown')}"
                            )
                        )
                        await asyncio.sleep(0)  # Yield to event processor

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

                    # Emit ActiveRequestEvent - API fetch failed
                    if self.event_bus and not from_cache:
                        from ..ui.events import ActiveRequestEvent
                        await self.event_bus.publish(
                            ActiveRequestEvent(
                                request_id=f"{rom_info.filename}-api",
                                rom_name=rom_info.filename,
                                stage="API Fetch",
                                status="failed",
                                duration=time.time() - api_start,
                                last_failure=str(e)
                            )
                        )

                    # Try search fallback if enabled
                    if self.enable_search_fallback:
                        logger.info(f"[{rom_info.filename}] Attempting search fallback")
                        
                        # Emit ActiveRequestEvent - Search started
                        if self.event_bus:
                            from ..ui.events import ActiveRequestEvent
                            await self.event_bus.publish(
                                ActiveRequestEvent(
                                    request_id=f"{rom_info.filename}-search",
                                    rom_name=rom_info.filename,
                                    stage="Search",
                                    status="started",
                                    duration=0.0
                                )
                            )
                        
                        # Track search fallback attempt
                        self.session_stats['search_fallback'] += 1
                        
                        search_start = time.time()
                        game_info = await self._search_fallback(
                            rom_info,
                            preferred_regions,
                            shutdown_event=shutdown_event
                        )
                        search_duration = time.time() - search_start

                        if game_info:
                            api_duration = time.time() - api_start

                            # Emit ActiveRequestEvent - Search completed
                            if self.event_bus:
                                from ..ui.events import ActiveRequestEvent
                                await self.event_bus.publish(
                                    ActiveRequestEvent(
                                        request_id=f"{rom_info.filename}-search",
                                        rom_name=rom_info.filename,
                                        stage="Search",
                                        status="completed",
                                        duration=search_duration
                                    )
                                )

                            # Record API timing
                            if hasattr(self, 'performance_monitor') and self.performance_monitor:
                                self.performance_monitor.record_api_call(api_duration)

                            logger.info(f"[{rom_info.filename}] Search fallback successful")

                            # Increment task counter but don't emit completion status
                            completed_tasks += 1
                        else:
                            # Emit ActiveRequestEvent - Search failed
                            if self.event_bus:
                                from ..ui.events import ActiveRequestEvent
                                await self.event_bus.publish(
                                    ActiveRequestEvent(
                                        request_id=f"{rom_info.filename}-search",
                                        rom_name=rom_info.filename,
                                        stage="Search",
                                        status="failed",
                                        duration=search_duration,
                                        last_failure="No matches found"
                                    )
                                )
                            
                            logger.info(f"[{rom_info.filename}] Search fallback: no matches found")
                    else:
                        raise

            if not game_info and decision.fetch_metadata:
                # Track as unmatched
                system_name = system.name
                if system_name not in self.unmatched_roms:
                    self.unmatched_roms[system_name] = []
                self.unmatched_roms[system_name].append(rom_info.filename)
                
                # Increment unmatched counter
                self.session_stats['unmatched'] += 1
                
                # Emit search activity event
                if self.event_bus:
                    from ..ui.events import SearchActivityEvent
                    await self.event_bus.publish(
                        SearchActivityEvent(
                            fallback_count=self.session_stats['search_fallback'],
                            unmatched_count=self.session_stats['unmatched']
                        )
                    )

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
                # Use separate media download semaphore for higher throughput
                # This allows media downloads to proceed independently from API rate limits
                media_semaphore = self.throttle_manager.media_download_semaphore if self.throttle_manager else None

                media_downloader = MediaDownloader(
                    media_root=self.media_directory,
                    client=self.api_client.client,
                    preferred_regions=preferred_regions,
                    enabled_media_types=media_types,
                    hash_algorithm=hash_algorithm,
                    validation_mode=validation_mode,
                    min_width=image_min_dimension,
                    min_height=image_min_dimension,
                    download_semaphore=media_semaphore,
                    event_bus=self.event_bus
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
                    # Convert singular ES-DE types to ScreenScraper media types for checking disk
                    # E.g., 'cover' -> 'covers' -> 'box-2D'
                    from ..media.media_types import to_plural, convert_directory_names_to_media_types

                    # Check which media already exists on disk
                    # If validation enabled, we'll validate these against fresh API hashes
                    rom_basename = media_downloader.organizer.get_rom_basename(str(rom_info.path))
                    existing_media = {}
                    existing_media_paths = {}

                    for media_type_singular in decision.media_to_download:
                        # Convert singular to ScreenScraper type for path lookup
                        plural_dir = to_plural(media_type_singular)
                        screenscraper_types = convert_directory_names_to_media_types([plural_dir])

                        if screenscraper_types:
                            screenscraper_type = screenscraper_types[0]
                            # Check with common extensions
                            for ext in ['jpg', 'png', 'gif', 'webp', 'mp4', 'pdf']:
                                media_path = media_downloader.organizer.get_media_path(
                                    system.name,
                                    screenscraper_type,
                                    rom_basename,
                                    ext
                                )
                                if media_downloader.organizer.file_exists(media_path):
                                    existing_media[media_type_singular] = True
                                    existing_media_paths[media_type_singular] = Path(media_path)
                                    logger.debug(
                                        "[%s] Media %s already exists at %s",
                                        rom_info.filename,
                                        media_type_singular,
                                        media_path
                                    )
                                    break
                        else:
                            logger.warning(
                                "[%s] Could not convert media type %s to ScreenScraper type",
                                rom_info.filename,
                                media_type_singular
                            )
                            existing_media[media_type_singular] = False

                    # Validate existing media if validation mode is enabled
                    # This handles the case where cache expired or ROM changed but media may still be good
                    validated_media = []
                    failed_validation = []

                    if validation_mode == 'disabled' and existing_media:
                        # Validation disabled - trust existing files without checking
                        for media_type_singular in existing_media:
                            if existing_media[media_type_singular]:
                                media_path = existing_media_paths.get(media_type_singular)
                                if media_path and media_path.exists():
                                    media_paths[media_type_singular] = str(media_path)
                                    validated_media.append(media_type_singular)
                                    logger.debug(
                                        "[%s] Skipping existing media (validation disabled): %s",
                                        rom_info.filename,
                                        media_type_singular
                                    )

                        if validated_media:
                            logger.info(
                                "[%s] Skipped existing media (validation disabled): %s",
                                rom_info.filename,
                                ", ".join(validated_media)
                            )

                    elif validation_mode != 'disabled' and existing_media:
                        # We have fresh API response with media URLs - we can extract expected hashes
                        # from the API response to validate existing files
                        for media_type_singular in existing_media:
                            if not existing_media[media_type_singular]:
                                continue
                                
                            media_path = existing_media_paths.get(media_type_singular)
                            if not media_path or not media_path.exists():
                                continue
                            
                            # Validate based on mode
                            validation_passed = False
                            
                            # Non-image media types (PDFs, videos) can't be validated with Pillow
                            is_image_type = media_type_singular not in ['manual', 'video']
                            
                            if validation_mode == 'strict':
                                # Strict mode: dimension check + hash validation (images only)
                                logger.debug(
                                    "[%s] Validating existing media (strict): %s",
                                    rom_info.filename,
                                    media_type_singular
                                )
                                
                                # First check dimensions and image integrity (only for images)
                                if is_image_type:
                                    is_valid, validation_error = (
                                        media_downloader.downloader.validate_existing_file(media_path)
                                    )
                                    if not is_valid:
                                        logger.debug(
                                            "[%s] Media validation failed (dimensions/integrity): %s - %s",
                                            rom_info.filename,
                                            media_type_singular,
                                            validation_error
                                        )
                                        failed_validation.append(media_type_singular)
                                        continue
                                
                                # Then validate hash (for all types)
                                current_hash = calculate_hash(
                                    media_path,
                                    algorithm=hash_algorithm,
                                    size_limit=0
                                )
                                
                                # Store hash for this media file
                                media_hashes[media_type_singular] = current_hash
                                validation_passed = True
                                
                            elif validation_mode == 'normal':
                                # Normal mode: dimension check and image integrity only (images only)
                                logger.debug(
                                    "[%s] Validating existing media (normal): %s",
                                    rom_info.filename,
                                    media_type_singular
                                )
                                
                                # Only validate images; PDFs and videos just pass in normal mode
                                if is_image_type:
                                    is_valid, validation_error = (
                                        media_downloader.downloader.validate_existing_file(media_path)
                                    )
                                    if not is_valid:
                                        logger.debug(
                                            "[%s] Media validation failed (dimensions/integrity): %s - %s",
                                            rom_info.filename,
                                            media_type_singular,
                                            validation_error
                                        )
                                        failed_validation.append(media_type_singular)
                                        continue
                                
                                validation_passed = True
                            
                            if validation_passed:
                                # We validated it - keep the file
                                media_paths[media_type_singular] = str(media_path)
                                validated_media.append(media_type_singular)
                                
                                # Track validated media stats
                                if media_type_singular not in self.session_stats['media_by_type']:
                                    self.session_stats['media_by_type'][media_type_singular] = {
                                        'successful': 0, 'failed': 0, 'validated': 0, 'skipped': 0
                                    }
                                self.session_stats['media_by_type'][media_type_singular]['validated'] += 1
                                self.session_stats['media_validated'] += 1
                    
                    # Log validation summary if we validated anything
                    if validated_media:
                        logger.info(
                            "[%s] Validated existing media (%s): %s",
                            rom_info.filename,
                            validation_mode,
                            ", ".join(validated_media)
                        )

                    # Filter out media that was validated successfully
                    media_types_to_download = [
                        mt for mt in decision.media_to_download
                        if mt not in validated_media
                    ]

                    if not media_types_to_download:
                        logger.info(f"[{rom_info.filename}] All media already exists on disk, skipping downloads")
                        # Clear download list and skip all download logic
                        decision.media_to_download = []
                    else:
                        if len(media_types_to_download) < len(decision.media_to_download):
                            skipped = len(decision.media_to_download) - len(media_types_to_download)
                            logger.info(
                                "[%s] %s media type(s) already exist, will attempt to download %s: %s",
                                rom_info.filename,
                                skipped,
                                len(media_types_to_download),
                                ", ".join(media_types_to_download)
                            )

                        # Update decision to only download missing media
                        decision.media_to_download = media_types_to_download

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

                        # Identify media types that were requested but not available in API
                        available_types = {m.get('type') for m in filtered_media_list}
                        unavailable_types = [
                            mt for mt, ss_type in zip(decision.media_to_download, screenscraper_types)
                            if ss_type not in available_types
                        ]
                        
                        if unavailable_types:
                            logger.info(
                                "[%s] %s media type(s) not available in API response: %s",
                                rom_info.filename,
                                len(unavailable_types),
                                ", ".join(unavailable_types)
                            )

                        if filtered_media_list:
                            # Count actual media types being downloaded (exclude unavailable ones)
                            actual_types_to_download = [mt for mt in decision.media_to_download
                                                       if mt not in unavailable_types]
                            logger.info(
                                "[%s] Downloading %s media types concurrently: %s",
                                rom_info.filename,
                                len(actual_types_to_download),
                                ", ".join(actual_types_to_download)
                            )

                            # Create progress callback to update UI during download
                            def media_progress_callback(media_type: str, current_idx: int, total_count: int):
                                pass

                            # Download all media concurrently
                            download_results, _ = await media_downloader.download_media_for_game(
                                media_list=filtered_media_list,
                                rom_path=str(rom_info.path),
                                system=system.name,
                                progress_callback=media_progress_callback,
                                shutdown_event=shutdown_event
                            )

                            # Process results - track successes and failures
                            successful_downloads = []
                            failed_downloads = []
                            
                            for result in download_results:
                                if result.success and result.file_path:
                                    # Convert ScreenScraper media type to ES-DE singular form for tracking
                                    from ..media.media_types import get_directory_for_media_type, to_singular
                                    plural_dir = get_directory_for_media_type(result.media_type)
                                    media_type_singular = to_singular(plural_dir)

                                    # Track using singular ES-DE type
                                    media_paths[media_type_singular] = result.file_path
                                    media_count += 1
                                    completed_tasks += 1
                                    successful_downloads.append(media_type_singular)
                                    
                                    # Track media stats by type
                                    if media_type_singular not in self.session_stats['media_by_type']:
                                        self.session_stats['media_by_type'][media_type_singular] = {
                                            'successful': 0, 'failed': 0, 'validated': 0, 'skipped': 0
                                        }
                                    self.session_stats['media_by_type'][media_type_singular]['successful'] += 1

                                    # Store hash from download result (already calculated by media_downloader)
                                    if result.hash_value:
                                        media_hashes[media_type_singular] = result.hash_value
                                        logger.debug(
                                            f"[{rom_info.filename}] Media hash: "
                                            f"{media_type_singular} = {result.hash_value}"
                                        )
                                    else:
                                        logger.debug(
                                            f"[{rom_info.filename}] "
                                            f"No hash available for {media_type_singular}"
                                        )
                                else:
                                    # Track failed download
                                    from ..media.media_types import get_directory_for_media_type, to_singular
                                    plural_dir = get_directory_for_media_type(result.media_type)
                                    media_type_singular = to_singular(plural_dir)
                                    failed_downloads.append((media_type_singular, result.error))
                                    
                                    # Track media failure stats
                                    if media_type_singular not in self.session_stats['media_by_type']:
                                        self.session_stats['media_by_type'][media_type_singular] = {
                                            'successful': 0, 'failed': 0, 'validated': 0, 'skipped': 0
                                        }
                                    self.session_stats['media_by_type'][media_type_singular]['failed'] += 1
                                    self.session_stats['media_failed'] += 1
                            
                            # Log consolidated download summary
                            if successful_downloads or failed_downloads:
                                summary_parts = []
                                if successful_downloads:
                                    summary_parts.append(
                                        f"{len(successful_downloads)} succeeded ({', '.join(successful_downloads)})"
                                    )
                                if failed_downloads:
                                    failed_types = [
                                        f"{mt} ({err})" for mt, err in failed_downloads
                                    ]
                                    summary_parts.append(
                                        f"{len(failed_downloads)} failed ({'; '.join(failed_types)})"
                                    )
                                
                                logger.info(
                                    f"[{rom_info.filename}] Media downloads: {' | '.join(summary_parts)}"
                                )
                        else:
                            logger.info(
                                "[%s] No media to download (all requested types unavailable)",
                                rom_info.filename
                            )

                        # Clear download list - validation may add items back if needed
                        decision.media_to_download = []

                    # Validate existing media (only in normal or strict mode)
                    if decision.media_to_validate and validation_mode != 'disabled':
                        # Track validation results for summary logging
                        validated_passed = []
                        validated_failed = []
                        validated_missing = []
                        validated_no_hash = []
                        validated_trusted = []

                        for media_type_singular in decision.media_to_validate:
                            # Check if media file exists
                            media_path = self._get_media_path(system, media_type_singular, rom_info.path)
                            if not media_path or not media_path.exists():
                                # File doesn't exist - add to download list
                                logger.debug(
                                    "[%s] Media file missing: %s, will download",
                                    rom_info.filename,
                                    media_type_singular
                                )
                                validated_missing.append(media_type_singular)
                                if media_type_singular not in decision.media_to_download:
                                    decision.media_to_download.append(media_type_singular)
                                continue

                            # Non-image media types (PDFs, videos) can't be validated with Pillow
                            is_image_type = media_type_singular not in ['manual', 'video']

                            # Get expected hash from cache
                            expected_hash = None
                            if self.api_client.cache and rom_hash:
                                expected_hash = self.api_client.cache.get_media_hash(rom_hash, media_type_singular)

                            if not expected_hash:
                                # No hash in cache
                                if validation_mode == 'strict':
                                    # Strict mode: re-download files without cached hashes
                                    validated_no_hash.append(media_type_singular)
                                    if media_type_singular not in decision.media_to_download:
                                        decision.media_to_download.append(media_type_singular)
                                else:
                                    # Normal mode: accept existing file without hash
                                    validated_trusted.append(media_type_singular)
                                    media_paths[media_type_singular] = str(media_path)
                                continue

                            # Validate based on mode
                            if validation_mode == 'strict':
                                # Strict mode: hash validation (for all media types)
                                logger.debug(
                                    "[%s] Media validation (strict): Calculating hash for %s",
                                    rom_info.filename,
                                    media_type_singular
                                )
                                current_hash = calculate_hash(
                                    media_path,
                                    algorithm=hash_algorithm,
                                    size_limit=0
                                )

                                if current_hash == expected_hash:
                                    # Hash matches - keep existing file
                                    validated_passed.append(media_type_singular)
                                    media_paths[media_type_singular] = str(media_path)
                                    media_hashes[media_type_singular] = current_hash
                                else:
                                    # Hash mismatch - re-download
                                    validated_failed.append((media_type_singular, expected_hash, current_hash))
                                    if media_type_singular not in decision.media_to_download:
                                        decision.media_to_download.append(media_type_singular)
                            else:
                                # Normal mode: dimension and integrity check (images only), trust files otherwise
                                logger.debug(
                                    "[%s] Media validation (normal): Checking %s",
                                    rom_info.filename,
                                    media_type_singular
                                )
                                
                                # Only validate images; PDFs and videos just pass in normal mode
                                if is_image_type:
                                    # Use media_downloader to validate dimensions and integrity
                                    # (we don't have media_downloader in this scope, need to create it)
                                    from ..media.downloader import ImageDownloader
                                    temp_downloader = ImageDownloader(
                                        client=self.api_client.client,
                                        min_width=image_min_dimension,
                                        min_height=image_min_dimension,
                                        validation_mode=validation_mode
                                    )
                                    
                                    is_valid, validation_error = temp_downloader.validate_existing_file(media_path)
                                    if is_valid:
                                        # Validation passed - keep file
                                        validated_trusted.append(media_type_singular)
                                        media_paths[media_type_singular] = str(media_path)
                                        media_hashes[media_type_singular] = expected_hash
                                    else:
                                        # Validation failed - re-download
                                        logger.debug(
                                            "[%s] Media validation failed (dimensions/integrity): %s - %s",
                                            rom_info.filename,
                                            media_type_singular,
                                            validation_error
                                        )
                                        validated_failed.append((
                                            media_type_singular,
                                            "cached",
                                            "dimension/integrity check failed"
                                        ))
                                        if media_type_singular not in decision.media_to_download:
                                            decision.media_to_download.append(media_type_singular)
                                else:
                                    # Non-image types (manual, video) - trust they exist in normal mode
                                    validated_trusted.append(media_type_singular)
                                    media_paths[media_type_singular] = str(media_path)
                                    media_hashes[media_type_singular] = expected_hash

                        # Log consolidated validation summary
                        if validated_passed or validated_failed or validated_missing or validated_no_hash:
                            summary_parts = []
                            if validated_passed:
                                summary_parts.append(
                                    f"{len(validated_passed)} passed ({', '.join(validated_passed)})"
                                )
                            if validated_trusted:
                                summary_parts.append(
                                    f"{len(validated_trusted)} trusted ({', '.join(validated_trusted)})"
                                )
                            if validated_failed:
                                failed_details = [f"{mt}" for mt, exp, got in validated_failed]
                                summary_parts.append(
                                    f"{len(validated_failed)} mismatch ({', '.join(failed_details)})"
                                )
                            if validated_no_hash:
                                summary_parts.append(
                                    f"{len(validated_no_hash)} no cached hash ({', '.join(validated_no_hash)})"
                                )
                            if validated_missing:
                                summary_parts.append(
                                    f"{len(validated_missing)} missing ({', '.join(validated_missing)})"
                                )

                            logger.info(
                                "[%s] Media validation (%s): %s",
                                rom_info.filename,
                                validation_mode,
                                " | ".join(summary_parts)
                            )

                    # Re-download any media that failed validation or is missing
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
                            # Count unique media types being re-downloaded
                            available_redownload_types = {m.get('type') for m in redownload_media_list}
                            actual_redownload_count = len([mt for mt in decision.media_to_download
                                                          if any(st in available_redownload_types
                                                                for st in screenscraper_types)])
                            
                            if validation_mode != 'disabled':
                                logger.info(
                                    "[%s] Re-downloading %s media types after validation",
                                    rom_info.filename,
                                    actual_redownload_count
                                )
                            else:
                                logger.info(
                                    "[%s] Downloading %s missing media types",
                                    rom_info.filename,
                                    actual_redownload_count
                                )

                            def media_redownload_callback(media_type: str, current_idx: int, total_count: int):
                                pass

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

                                    if validation_mode != 'disabled':
                                        logger.info(
                                            f"[{rom_info.filename}] Re-downloaded {media_type_singular}"
                                        )
                                    else:
                                        logger.info(
                                            f"[{rom_info.filename}] Downloaded {media_type_singular}"
                                        )

                                    if result.hash_value:
                                        media_hashes[media_type_singular] = result.hash_value

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
                    media_paths=media_paths,
                    auto_sortname_enabled=self.auto_sortname_enabled
                )

                # Merge with existing entry if present
                if gamelist_entry and decision.update_metadata:
                    merge_result = self.metadata_merger.merge_entries(gamelist_entry, game_entry)

                    game_entry = merge_result.merged_entry

                    logger.debug(
                        f"Metadata merged: {len(merge_result.preserved_fields)} preserved, "
                        f"{len(merge_result.updated_fields)} updated"
                    )
                    
                    # Track gamelist update if fields were changed
                    if len(merge_result.updated_fields) > 0:
                        self.session_stats['gamelist_updated'] += 1
                else:
                    # New entry - apply auto-favorite if enabled (no merge strategy check for new entries)
                    if self.metadata_merger.auto_favorite_enabled:
                        if (game_entry.rating is not None and
                                game_entry.rating >= self.metadata_merger.auto_favorite_threshold):
                            game_entry.favorite = True
                            logger.debug(f"Auto-favoriting new entry: {game_entry.name} (rating={game_entry.rating})")
                    
                    # Track new gamelist entry
                    if game_entry and decision.update_metadata:
                        self.session_stats['gamelist_added'] += 1

                # Update cache with media hashes (if cache enabled and we have hashes)
                if self.api_client.cache and rom_hash and media_hashes:
                    self.api_client.cache.update_media_hashes(rom_hash, media_hashes)
                    logger.debug(f"Updated cache with {len(media_hashes)} media hashes for {rom_info.filename}")

                return ScrapingResult(
                    rom_path=rom_info.path,
                    success=True,
                    api_id=str(game_info.get('id', '')),
                    media_downloaded=media_count,
                    game_info=game_info,
                    media_paths=media_paths,
                    game_entry=game_entry  # Store merged entry
                )

            # Return success even if no updates made
            return ScrapingResult(
                rom_path=rom_info.path,
                success=True,
                api_id=str(game_info.get('id', '')) if game_info else None,
                media_downloaded=media_count,
                game_info=game_info,
                media_paths=media_paths,
                game_entry=game_entry if decision.update_metadata and game_info else None
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
            operation_callback: Optional[
                Callable[[str, str, str, str, Optional[float], Optional[int], Optional[int]], None]
            ] = None,
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
        batch_size: int = 100,
        scrape_mode: str = 'changed',
        existing_entries: List[GameEntry] = None
    ) -> List[ROMInfo]:
        """
        Hash ROMs in concurrent batches to feed the pipeline.

        Processes ROMs in batches using asyncio.gather() with asyncio.to_thread()
        to maximize CPU utilization while preventing memory exhaustion.

        Args:
            rom_entries: List of ROM entries to hash
            hash_algorithm: Hash algorithm to use (crc32, md5, sha1, etc)
            batch_size: Number of ROMs to hash concurrently per batch
            scrape_mode: Scrape mode to determine which ROMs need hashing
            existing_entries: Existing gamelist entries for skip optimization

        Returns:
            List of ROMInfo objects with hash_value populated
        """
        from ..scanner.rom_types import ROMType
        from ..scanner.m3u_parser import get_disc1_file
        from ..scanner.disc_handler import get_contained_file

        total = len(rom_entries)
        hashed_count = 0
        last_log_time = time.time()
        log_interval = 10.0  # Log every 10 seconds minimum

        logger.info(f"Starting ROM hash calculation: {total} ROMs in batches of {batch_size}")

        for i in range(0, total, batch_size):
            batch = rom_entries[i:i + batch_size]

            # Create hash tasks for this batch
            hash_tasks = []
            for rom_info in batch:
                # Skip if hash already calculated
                if rom_info.hash_value:
                    continue

                # Skip hash calculation for existing ROMs in new_only mode
                if scrape_mode == 'new_only' and existing_entries:
                    rom_relative_path = f"./{rom_info.filename}"
                    if any(entry.path == rom_relative_path for entry in existing_entries):
                        logger.debug(f"Skipping hash for existing ROM in new_only mode: {rom_info.filename}")
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
                # Log what we're about to hash (for large files, show size)
                large_files = [rom_info for rom_info, _ in hash_tasks if rom_info.file_size > 100_000_000]  # > 100MB
                if large_files:
                    largest_gb = max(rom_info.file_size for rom_info in large_files) / (1024**3)
                    logger.info(
                        f"Hashing batch {(i // batch_size) + 1}: {len(hash_tasks)} files "
                        f"({len(large_files)} files > 100MB, largest: {largest_gb:.2f} GB)"
                    )

                results = await asyncio.gather(*[task for _, task in hash_tasks], return_exceptions=True)

                # Assign hash values to ROM entries
                for (rom_info, _), result in zip(hash_tasks, results):
                    if isinstance(result, Exception):
                        logger.warning(f"Failed to hash {rom_info.filename}: {result}")
                    else:
                        rom_info.hash_value = result
                        hashed_count += 1

            # Progress logging - update frequently (every 10 ROMs or 10 seconds)
            current_count = min(i + batch_size, total)
            current_time = time.time()
            should_log = (
                (current_count % 10 == 0) or  # Every 10 ROMs
                (current_time - last_log_time >= log_interval) or  # Every 10 seconds
                (current_count >= total)  # Always log completion
            )

            if should_log:
                logger.info(
                    f"Hashing progress: {current_count}/{total} ROMs processed "
                    f"({hashed_count} hashed, {current_count - hashed_count} skipped) "
                    f"[{(current_count / total * 100):.1f}%]"
                )
                last_log_time = current_time

            # Emit HashingProgressEvent
            if self.event_bus:
                from ..ui.events import HashingProgressEvent
                await self.event_bus.publish(
                    HashingProgressEvent(
                        completed=current_count,
                        total=total,
                        skipped=current_count - hashed_count,
                        in_progress=(current_count < total)
                    )
                )
                await asyncio.sleep(0)  # Yield to event processor

        # Emit final HashingProgressEvent
        if self.event_bus:
            from ..ui.events import HashingProgressEvent
            await self.event_bus.publish(
                HashingProgressEvent(
                    completed=total,
                    total=total,
                    skipped=total - hashed_count,
                    in_progress=False
                )
            )

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
        scrape_mode = self.config.get('scraping', {}).get('scrape_mode', 'changed')
        rom_entries = await self._batch_hash_roms(
            rom_entries,
            hash_algorithm,
            batch_size=100,
            scrape_mode=scrape_mode,
            existing_entries=existing_entries
        )
        logger.info(
            "ROM hashing complete: %s hashed, %s skipped",
            sum(1 for r in rom_entries if r.hash_value),
            sum(1 for r in rom_entries if not r.hash_value)
        )

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
                logger.error(
                    "SystemExit raised while adding ROM %s (%s): exit code %s",
                    idx,
                    rom_info.filename,
                    e.code,
                    exc_info=True
                )
                raise
            except BaseException as e:
                logger.error(
                    "BaseException raised while adding ROM %s (%s): %s: %s",
                    idx,
                    rom_info.filename,
                    type(e).__name__,
                    e,
                    exc_info=True
                )
                raise
            except Exception as e:
                logger.error(f"Failed to add ROM {idx} ({rom_info.filename}) to work queue: {e}", exc_info=True)
                raise

        logger.info(
            "Work queue populated: successfully added %s/%s, queue reports %s items queued",
            successfully_added,
            len(rom_entries),
            self.work_queue.get_stats()['pending']
        )

        # Work queue consumption using producer-consumer pattern with concurrent tasks
        if self.thread_manager and self.thread_manager.is_initialized() and not self.dry_run:
            logger.info(f"Using task pool with {self.thread_manager.max_concurrent} concurrent task(s)")

            # Create ROM processor (no UI callback needed for pipeline UI)
            rom_processor = self._create_rom_processor(system, media_types, preferred_regions, existing_entries)

            # Clear any previous results
            self.thread_manager.clear_results()

            # Create result callback for real-time UI updates
            async def on_rom_complete(rom_info, result):
                """Called immediately when each ROM completes processing"""
                # Emit real-time progress event
                if self.event_bus:
                    from ..ui.events import ROMProgressEvent
                    if result.success:
                        await self.event_bus.publish(
                            ROMProgressEvent(
                                rom_name=result.rom_path.name,
                                system=system.name,
                                status="complete",
                                detail=f"Successfully processed"
                            )
                        )
                    elif result.error:
                        await self.event_bus.publish(
                            ROMProgressEvent(
                                rom_name=result.rom_path.name,
                                system=system.name,
                                status="failed",
                                detail=result.error
                            )
                        )
                    else:
                        # Skipped
                        await self.event_bus.publish(
                            ROMProgressEvent(
                                rom_name=result.rom_path.name,
                                system=system.name,
                                status="skipped",
                                detail="ROM skipped"
                            )
                        )

            # Spawn concurrent tasks that will continuously process from queue
            await self.thread_manager.spawn_workers(
                work_queue=self.work_queue,
                rom_processor=rom_processor,
                operation_callback=None,
                result_callback=on_rom_complete,
                count=self.thread_manager.max_concurrent
            )

            logger.info(f"Pipeline tasks spawned. Waiting for completion...")

            # Start periodic UI updates in background
            ui_update_task = None
            if self.event_bus:
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
                    pass

            logger.info(f"All pipeline tasks completed ({len(task_results)} results)")

            # Deduplicate results by ROM path (keep last result for each ROM to handle retries)
            # This ensures that retried ROMs only count once in final statistics
            results_by_path = {}
            for rom_info, result in task_results:
                # Use string path as key for deduplication
                path_key = str(result.rom_path)
                results_by_path[path_key] = result

            # Convert deduplicated results to list
            for result in results_by_path.values():
                rom_count += 1
                results.append(result)

                # Track not found items
                if not result.success and result.error == "No game info found from API":
                    not_found_items.append({
                        'filename': result.rom_path.name,
                        'path': str(result.rom_path)
                    })

            # Mark system complete and stop pipeline tasks
            self.work_queue.mark_system_complete()
            await self.thread_manager.stop_workers()

        else:
            # Fallback: Simple sequential processing
            # Used when: dry-run mode, thread_manager not initialized, or no thread_manager
            logger.info("Using simple sequential processing (no concurrent tasks)")

            # Sequential processing using _scrape_rom
            for rom_info in rom_entries:
                # Check for quit request from Textual UI
                if self.textual_ui and self.textual_ui.should_quit:
                    logger.info("Quit requested from Textual UI during sequential processing")
                    break

                # Check for skip system request from Textual UI
                if self.textual_ui and self.textual_ui.should_skip_system:
                    logger.info("Skip system requested from Textual UI during sequential processing")
                    break

                rom_count += 1

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

                    # Emit real-time progress event for this ROM
                    if self.event_bus:
                        from ..ui.events import ROMProgressEvent
                        if result.success:
                            await self.event_bus.publish(
                                ROMProgressEvent(
                                    rom_name=result.rom_path.name,
                                    system=system.name,
                                    status="complete",
                                    detail=f"Successfully processed"
                                )
                            )
                        elif result.error:
                            await self.event_bus.publish(
                                ROMProgressEvent(
                                    rom_name=result.rom_path.name,
                                    system=system.name,
                                    status="failed",
                                    detail=result.error
                                )
                            )
                        else:
                            # Skipped
                            await self.event_bus.publish(
                                ROMProgressEvent(
                                    rom_name=result.rom_path.name,
                                    system=system.name,
                                    status="skipped",
                                    detail="ROM skipped"
                                )
                            )
                        
                        # Yield to event loop to allow events to be processed
                        await asyncio.sleep(0)

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

            # Interactive mode: wait for user selection via UI or console prompt
            if self.interactive_search:
                if self.textual_ui:
                    # Textual UI: use async event-driven flow
                    import uuid
                    request_id = str(uuid.uuid4())

                    selected_game = await self._wait_for_search_response(
                        request_id,
                        rom_info,
                        scored_candidates
                    )

                    if selected_game:
                        game_name = selected_game.get('names', {}).get('en', 'Unknown')
                        logger.info(
                            f"[{rom_info.filename}] User selected: {game_name}"
                        )
                        return selected_game
                    else:
                        logger.info(f"[{rom_info.filename}] User skipped/cancelled search")
                        return None
                else:
                    # Console UI: use blocking prompt
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

    async def _wait_for_search_response(
        self,
        request_id: str,
        rom_info: ROMInfo,
        scored_candidates: list
    ) -> Optional[Dict]:
        """Wait for user response to search prompt.

        Creates response queue, emits SearchRequestEvent, waits for response.
        No timeout - waits indefinitely while other work continues.

        Args:
            request_id: Unique request identifier
            rom_info: ROM information
            scored_candidates: List of (game_data, confidence) tuples

        Returns:
            Selected game data or None if skipped/cancelled
        """
        # Create response queue for this request
        response_queue = asyncio.Queue()
        async with self.search_response_lock:
            self.search_response_queues[request_id] = response_queue

        # Prepare search results for event
        search_results = [
            {
                "game_data": game_data,
                "confidence": confidence
            }
            for game_data, confidence in scored_candidates
        ]

        # Emit event to UI
        if self.event_bus:
            from ..ui.events import SearchRequestEvent
            await self.event_bus.publish(
                SearchRequestEvent(
                    request_id=request_id,
                    rom_name=rom_info.filename,
                    rom_path=str(rom_info.path),
                    system=rom_info.system,
                    search_results=search_results
                )
            )
            logger.debug(f"[{rom_info.filename}] Emitted SearchRequestEvent, waiting for user response...")

        # Wait for response (no timeout)
        try:
            response = await response_queue.get()
            logger.info(f"[{rom_info.filename}] User response: {response.action}")

            if response.action == 'selected' and response.selected_game:
                return response.selected_game
            else:
                return None

        finally:
            # Clean up queue
            async with self.search_response_lock:
                self.search_response_queues.pop(request_id, None)

    async def handle_search_response(self, response) -> None:
        """Handle search response from UI.

        Called by event bus when user makes selection.
        Puts response into the appropriate queue.

        Args:
            response: SearchResponseEvent from UI
        """
        async with self.search_response_lock:
            if response.request_id in self.search_response_queues:
                await self.search_response_queues[response.request_id].put(response)
                logger.debug(f"Search response delivered for request {response.request_id}")
            else:
                logger.warning(f"Received response for unknown request_id: {response.request_id}")

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
            gamelist_directory=self.gamelist_directory / system.name,
            merge_strategy=self.metadata_merger.merge_strategy,
            auto_favorite_enabled=self.metadata_merger.auto_favorite_enabled,
            auto_favorite_threshold=self.metadata_merger.auto_favorite_threshold,
            auto_sortname_enabled=self.auto_sortname_enabled
        )

        # Prepare scraped games data
        scraped_games = []

        for result in results:
            # Include successful scrapes and skipped ROMs with existing entries
            if result.success and result.game_info:
                scraped_games.append({
                    'rom_path': result.rom_path,
                    'game_info': result.game_info,
                    'media_paths': result.media_paths or {},
                    'game_entry': result.game_entry  # Pass pre-merged entry
                })
            elif result.skipped and result.game_entry:
                # Preserve existing entries for skipped ROMs (e.g., in new_only mode)
                scraped_games.append({
                    'rom_path': result.rom_path,
                    'game_info': None,
                    'media_paths': {},
                    'game_entry': result.game_entry  # Preserve existing entry
                })

        # Generate gamelist (merge with existing if present)
        # Even if no new games were scraped, regenerate to maintain existing entries
        gamelist_path = self.gamelist_directory / system.name / 'gamelist.xml'
        if scraped_games or gamelist_path.exists():
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

                for item in sorted(not_found_items, key=lambda x: x['rom_info'].filename.lower()):
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
        quit_prompted = False  # Track whether we've prompted for quit confirmation
        skip_prompted = False  # Track whether we've prompted for skip confirmation

        try:
            while True:
                await asyncio.sleep(0.5)  # Update every 500ms

                # Check for skip system request from keyboard controls

                # Check for pause state from keyboard controls
                if paused_logged:
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
        """Update UI with current progress via event emissions"""
        if not self.event_bus:
            return

        # Import event types
        from ..ui.events import (
            PerformanceUpdateEvent,
            CacheMetricsEvent, MediaStatsEvent
        )

        # Get performance metrics if available
        if self.performance_monitor:
            metrics = self.performance_monitor.get_metrics()
            
            # Get thread stats
            thread_stats = {'active_tasks': 0, 'max_tasks': 1}
            if self.thread_manager and self.thread_manager.is_initialized():
                thread_stats = await self.thread_manager.get_stats()
            
            # Get API quota
            api_quota = {'requeststoday': 0, 'maxrequestsperday': 0}
            if self.throttle_manager:
                api_quota = self.throttle_manager.get_quota_stats()
            
            # Get cache metrics
            cache_hit_rate = None
            if self.api_client and self.api_client.cache:
                cache_data = self.api_client.cache.get_metrics()
                cache_hit_rate = cache_data.get('hit_rate', 0.0)
            
            # Emit consolidated performance update
            await self.event_bus.publish(
                PerformanceUpdateEvent(
                    api_quota_used=api_quota.get('requeststoday', 0),
                    api_quota_limit=api_quota.get('maxrequestsperday', 0),
                    threads_in_use=thread_stats.get('active_tasks', 0),
                    threads_limit=thread_stats.get('max_tasks', 1),
                    throughput_history=list(metrics.throughput_history),
                    api_rate_history=list(metrics.api_rate_history),
                    cache_hit_rate=cache_hit_rate
                )
            )

        # Emit cache metrics
        if self.api_client and self.api_client.cache:
            cache_data = self.api_client.cache.get_metrics()
            await self.event_bus.publish(
                CacheMetricsEvent(
                    existing=self.session_stats['cache_existing'],
                    added=self.session_stats['cache_added'],
                    hits=cache_data.get('hits', 0),
                    misses=cache_data.get('misses', 0),
                    hit_rate=cache_data.get('hit_rate', 0.0)
                )
            )

        # Emit gamelist stats
        from ..ui.events import GamelistUpdateEvent
        await self.event_bus.publish(
            GamelistUpdateEvent(
                system='current',  # Generic system identifier during processing
                existing=self.session_stats['gamelist_existing'],
                added=self.session_stats['gamelist_added'],
                updated=self.session_stats['gamelist_updated']
            )
        )

        # Emit media stats
        await self.event_bus.publish(
            MediaStatsEvent(
                by_type=self.session_stats['media_by_type'],
                total_validated=self.session_stats['media_validated'],
                total_skipped=self.session_stats['media_skipped'],
                total_failed=self.session_stats['media_failed']
            )
        )

        # Emit processing summary (categorized results mirroring summary log format)
        if results:
            successful = []
            skipped = []
            failed = []
            
            for result in results:
                rom_name = result.rom_path.name
                if result.success and not result.error:
                    successful.append(rom_name)
                elif hasattr(result, 'skipped') and result.skipped:
                    skip_reason = getattr(result, 'skip_reason', 'Unknown reason')
                    skipped.append((rom_name, skip_reason))
                elif not result.success:
                    error_msg = result.error or 'Unknown error'
                    failed.append((rom_name, error_msg))
            
            from ..ui.events import ProcessingSummaryEvent
            await self.event_bus.publish(
                ProcessingSummaryEvent(
                    successful=sorted(successful, key=str.lower),
                    skipped=sorted(skipped, key=lambda x: x[0].lower()),
                    failed=sorted(failed, key=lambda x: x[0].lower())
                )
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
        print(
            f"   Match ratio: {validation_result.match_ratio:.1%} "
            f"(threshold: {self.integrity_validator.threshold:.1%})"
        )
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
                    for result in sorted(successful_results, key=lambda r: r.rom_path.name.lower()):
                        f.write(f"{result.rom_path.name}\n")
                    f.write("\n")

                # Skipped results
                skipped_results = [r for r in results if hasattr(r, 'skipped') and r.skipped]
                if skipped_results:
                    f.write("=== Skipped ===\n")
                    for result in sorted(skipped_results, key=lambda r: r.rom_path.name.lower()):
                        reason = getattr(result, 'skip_reason', 'Unknown reason')
                        f.write(f"{result.rom_path.name} - {reason}\n")
                    f.write("\n")

                # Failed results
                failed_results = [r for r in results if not r.success]
                if failed_results:
                    f.write("=== Failed ===\n")
                    for result in sorted(failed_results, key=lambda r: r.rom_path.name.lower()):
                        f.write(f"{result.rom_path.name},{result.error}\n")
                    f.write("\n")

            logger.info(f"Summary log written: {summary_path}")
        except Exception as e:
            logger.warning(f"Failed to write summary log: {e}")
