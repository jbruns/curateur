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
        throttle_manager: Optional['ThrottleManager'] = None
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
        
        # Phase D components (optional)
        self.thread_manager = thread_manager
        self.performance_monitor = performance_monitor
        self.console_ui = console_ui
        self.throttle_manager = throttle_manager
        
        # Initialize workflow evaluator
        self.evaluator = WorkflowEvaluator(self.config)
        
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
        logger.info(f"System ID: {system.screenscraper_id}")
        logger.info(f"ROM path: {system.rom_path}")
        
        # Initialize checkpoint manager for this system
        gamelist_dir = self.paths['gamelists'] / system.name
        self.checkpoint_manager = CheckpointManager(
            str(gamelist_dir),
            system.name,
            self.config
        )
        
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
        rom_entries = scan_system(
            system,
            rom_root=self.rom_directory,
            crc_size_limit=1073741824
        )
        logger.info(f"ROM scan complete: {len(rom_entries)} files found")
        
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
        
        # Step 2-4: Process ROMs (parallel with 1-N workers)
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
                        details="Generating gamelist.xml..."
                    )
                
                logger.info(f"Committing gamelist: {scraped_count} entries")
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
            # Step 1: Hash ROM if not already done
            if not rom_info.hash_value:
                emit(Operations.HASHING_ROM, "Hashing ROM...")
                
                # Determine which file to hash based on ROM type
                from ..scanner.rom_types import ROMType
                from ..scanner.m3u_parser import get_disc1_file
                
                if rom_info.rom_type == ROMType.STANDARD:
                    hash_file = rom_info.path
                elif rom_info.rom_type == ROMType.M3U_PLAYLIST:
                    hash_file = get_disc1_file(rom_info.path)
                elif rom_info.rom_type == ROMType.DISC_SUBDIR:
                    # Use contained file that was stored during scanning
                    if rom_info.contained_file:
                        hash_file = rom_info.contained_file
                    else:
                        # Fallback: use get_contained_file which doesn't need extensions
                        from ..scanner.disc_handler import get_contained_file
                        hash_file = get_contained_file(rom_info.path)
                else:
                    hash_file = rom_info.path
                
                # Calculate hash using configured algorithm
                hash_algorithm = self.config.get('scraping', {}).get('hash_algorithm', 'crc32')
                logger.info(f"Hashing ROM: {rom_info.name}")
                rom_info.hash_value = calculate_hash(
                    hash_file,
                    algorithm=hash_algorithm,
                    size_limit=rom_info.crc_size_limit
                )
                
                if rom_info.hash_value:
                    logger.info(f"Hash calculated: {hash_algorithm.upper()}={rom_info.hash_value}")
                else:
                    logger.info("Hash calculation skipped (file size exceeds limit)")
                
                # Don't emit completion - move directly to next operation
                completed_tasks += 1
            else:
                # Hash already calculated
                completed_tasks += 1
            
            rom_hash = rom_info.hash_value
            
            # Step 2: Look up existing gamelist entry for this ROM
            gamelist_entry = None
            if existing_entries:
                rom_relative_path = f"./{rom_info.name}"
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
                f"Evaluator decision for {rom_info.name}: "
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
                logger.info(f"Skipping {rom_info.name}: {decision.skip_reason}")
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
                # Emit UI event
                if operation_callback:
                    emit(Operations.FETCHING_METADATA, "Fetching metadata...")
                
                logger.info(
                    f"Fetching metadata: {rom_info.name} "
                    f"(hash={rom_hash}, size={rom_info.path.stat().st_size})"
                )
                logger.debug(
                    f"API request: hash={rom_hash}, "
                    f"size={rom_info.size}, "
                    f"system_id={system.screenscraper_id}"
                )
                
                api_start = time.time()
                
                try:
                    game_info = await self.api_client.query_game(rom_info)
                    api_duration = time.time() - api_start
                    
                    # Record API timing
                    if hasattr(self, 'performance_monitor') and self.performance_monitor:
                        self.performance_monitor.record_api_call(api_duration)
                    
                    if game_info:
                        # Count non-empty fields
                        field_count = len([k for k in game_info.keys() if game_info.get(k)])
                        logger.info(
                            f"Metadata processed: {field_count} fields, "
                            f"{len(game_info.get('names', {}))} names, "
                            f"{len(game_info.get('descriptions', {}))} descriptions, "
                            f"language={self.config.get('scraping', {}).get('preferred_language', 'en')}"
                        )
                        logger.debug(
                            f"Metadata fields: name={game_info.get('name', 'N/A')[:50]}, "
                            f"desc={game_info.get('desc', 'N/A')[:50]}..."
                        )
                    
                    logger.debug(f"Hash lookup successful for {rom_info.filename}")
                    # Increment task counter but don't emit completion status
                    completed_tasks += 1
                    
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
                    else:
                        raise
            
            if not game_info and decision.fetch_metadata:
                # Track as unmatched
                system_name = system.name
                if system_name not in self.unmatched_roms:
                    self.unmatched_roms[system_name] = []
                self.unmatched_roms[system_name].append(rom_info.filename)
                
                return ScrapingResult(
                    rom_path=rom_info.path,
                    success=False,
                    error="No game info found from API"
                )
            
            # Step 5: Process media with hash validation
            media_paths = {}
            media_count = 0
            media_hashes = {}
            hash_algorithm = self.config.get('scraping', {}).get('hash_algorithm', 'crc32')
            
            if game_info:
                media_downloader = MediaDownloader(
                    media_root=self.media_directory,
                    client=self.api_client.client,
                    preferred_regions=preferred_regions,
                    enabled_media_types=media_types
                )
                
                # Get media list from game_info
                media_dict = game_info.get('media', {})
                media_list = []
                if media_dict:
                    for media_type, media_items in media_dict.items():
                        media_list.extend(media_items)
                
                # Download media files (from decision.media_to_download)
                if decision.media_to_download and media_list:
                    for idx, media_type_singular in enumerate(decision.media_to_download, 1):
                        # Emit UI event
                        if operation_callback:
                            emit("Downloading media", f"{media_type_singular} ({idx}/{len(decision.media_to_download)})")
                        
                        logger.info(
                            f"Downloading media {idx}/{len(decision.media_to_download)}: "
                            f"{media_type_singular} for {rom_info.name}"
                        )
                        logger.debug(
                            f"Media selection preferences: regions={preferred_regions}, "
                            f"language={self.config.get('scraping', {}).get('preferred_language', 'en')}"
                        )
                        
                        # Convert singular to plural for MediaDownloader
                        from ..media.media_types import to_plural
                        media_type_plural = to_plural(media_type_singular)
                        
                        # Filter media list for this type
                        type_media_list = [m for m in media_list if m.get('type') == media_type_plural]
                        
                        if type_media_list:
                            # Download using existing MediaDownloader logic
                            download_results, _ = await media_downloader.download_media_for_game(
                                media_list=type_media_list,
                                rom_path=str(rom_info.path),
                                system=system.name,
                                shutdown_event=shutdown_event
                            )
                            
                            for result in download_results:
                                if result.success and result.file_path:
                                    media_paths[media_type_singular] = result.file_path
                                    media_count += 1
                                    completed_tasks += 1
                                    
                                    # Calculate hash for downloaded media
                                    media_path = Path(result.file_path)
                                    if media_path.exists():
                                        media_hash = calculate_hash(
                                            media_path,
                                            algorithm=hash_algorithm,
                                            size_limit=0  # No size limit for media
                                        )
                                        if media_hash:
                                            media_hashes[media_type_singular] = media_hash
                                            logger.info(
                                                f"Media downloaded: {media_type_singular}, "
                                                f"hash={media_hash}"
                                            )
                
                # Validate existing media (from decision.media_to_validate)
                if decision.media_to_validate:
                    for media_type_singular in decision.media_to_validate:
                        # Emit UI event
                        if operation_callback:
                            emit(Operations.HASHING_MEDIA, media_type_singular)
                        
                        logger.info(f"Hashing media: {media_type_singular} for {rom_info.name}")
                        
                        # Get media file path
                        media_path = self._get_media_path(system, rom_info, media_type_singular)
                        
                        if media_path and media_path.exists():
                            # Calculate hash
                            media_hash = calculate_hash(
                                media_path,
                                algorithm=hash_algorithm,
                                size_limit=0  # No size limit for media
                            )
                            
                            # Compare with stored hash
                            stored_hash = None
                            if gamelist_entry and gamelist_entry.hash:
                                stored_hash = gamelist_entry.hash.get('media', {}).get(media_type_singular)
                            
                            if media_hash != stored_hash:
                                logger.info(
                                    f"Media hash mismatch for {media_type_singular}: "
                                    f"stored={stored_hash}, calculated={media_hash}"
                                )
                                
                                # Re-download media
                                from ..media.media_types import to_plural
                                media_type_plural = to_plural(media_type_singular)
                                type_media_list = [m for m in media_list if m.get('type') == media_type_plural]
                                
                                if type_media_list:
                                    download_results, _ = await media_downloader.download_media_for_game(
                                        media_list=type_media_list,
                                        rom_path=str(rom_info.path),
                                        system=system.name,
                                        shutdown_event=shutdown_event
                                    )
                                    
                                    for result in download_results:
                                        if result.success and result.file_path:
                                            media_paths[media_type_singular] = result.file_path
                                            media_hashes[media_type_singular] = media_hash
                            else:
                                logger.info(
                                    f"Media hash validated: {media_type_singular} "
                                    f"(hash={media_hash})"
                                )
                                media_hashes[media_type_singular] = media_hash
            
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
                                f"Cleaned disabled media: {media_type_singular} for {rom_info.name} "
                                f"(moved to CLEANUP/{system.name}/{media_type_plural})"
                            )
                        else:
                            logger.info(
                                f"Would clean disabled media: {media_type_singular} for {rom_info.name}"
                            )
            
            # Step 6: Create or update GameEntry with hashes
            if decision.update_metadata and game_info:
                # Create entry from API response
                game_entry = GameEntry.from_api_response(
                    game_info=game_info,
                    rom_path=f"./{rom_info.name}",
                    media_paths=media_paths
                )
                
                # Add hash information
                game_entry.hash = {
                    'rom': {hash_algorithm: rom_hash} if rom_hash else {},
                    'media': media_hashes
                }
                
                # Merge with existing entry if present
                if gamelist_entry and decision.update_metadata:
                    merge_strategy = self.config.get('scraping', {}).get('merge_strategy', 'preserve_user_edits')
                    merger = MetadataMerger(merge_strategy=merge_strategy)
                    
                    merge_result = merger.merge_entries(gamelist_entry, game_entry)
                    
                    # Update hash in merged entry
                    merge_result.merged_entry.hash = game_entry.hash
                    
                    game_entry = merge_result.merged_entry
                    
                    logger.debug(
                        f"Metadata merged: {len(merge_result.preserved_fields)} preserved, "
                        f"{len(merge_result.updated_fields)} updated"
                    )
                
                # Store hash in checkpoint for resume capability
                if self.checkpoint_manager and game_entry.hash:
                    self.checkpoint_manager.add_game_entry_hash(
                        game_entry.path,
                        game_entry.hash
                    )
                
                return ScrapingResult(
                    rom_path=rom_info.path,
                    success=True,
                    api_id=str(game_info.get('id', '')),
                    media_downloaded=media_count,
                    game_info=game_info,
                    media_paths=media_paths
                )
            
            # Return success even if no updates made
            return ScrapingResult(
                rom_path=rom_info.path,
                success=True,
                api_id=str(game_info.get('id', '')) if game_info else None,
                media_downloaded=media_count,
                game_info=game_info,
                media_paths=media_paths
            )
            
        except Exception as e:
            logger.error(f"Error scraping {rom_info.filename}: {e}")
            
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
        
        # Initialize idle workers in UI if available
        if self.console_ui and self.thread_manager and self.thread_manager.is_initialized():
            max_workers = self.thread_manager.max_concurrent
            for i in range(1, max_workers + 1):
                self.console_ui.clear_worker_operation(i)  # Pass integer, not string
        
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
        
        # Work queue consumption using producer-consumer pattern with workers
        if self.thread_manager and self.thread_manager.is_initialized() and not self.dry_run:
            logger.info(f"Using task pool with {self.thread_manager.max_concurrent} concurrent worker(s)")
            
            # Create UI callback and ROM processor (with existing_entries)
            ui_callback = self._create_ui_callback()
            rom_processor = self._create_rom_processor(system, media_types, preferred_regions, existing_entries)
            
            # Clear any previous results
            self.thread_manager.clear_results()
            
            # Spawn workers that will continuously process from queue
            self.thread_manager.spawn_workers(
                work_queue=self.work_queue,
                rom_processor=rom_processor,
                operation_callback=ui_callback,
                count=self.thread_manager.max_concurrent
            )
            
            logger.info(f"Workers spawned. Waiting for completion...")
            
            # Start background task for periodic UI updates (Work Queue + Statistics)
            ui_update_task = None
            if self.console_ui:
                ui_update_task = asyncio.create_task(
                    self._periodic_ui_update(not_found_items, len(rom_entries))
                )
            
            # Wait for all work to complete and collect results
            worker_results = await self.thread_manager.wait_for_completion()
            
            # Stop periodic UI updates
            if ui_update_task:
                ui_update_task.cancel()
                try:
                    await ui_update_task
                except asyncio.CancelledError:
                    pass
            
            logger.info(f"All workers completed processing ({len(worker_results)} results)")
            
            # Convert worker results to our expected format and record in checkpoint
            for rom_info, result in worker_results:
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
            
            # Mark system complete and stop workers
            self.work_queue.mark_system_complete()
            await self.thread_manager.stop_workers()
            
        else:
            # Fallback: Simple sequential processing
            # Used when: dry-run mode, thread_manager not initialized, or no thread_manager
            logger.info("Using simple sequential processing (no worker pool)")
            
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
    
    async def _periodic_ui_update(
        self,
        not_found_items: list,
        total_roms: int
    ) -> None:
        """Background task to periodically update UI during parallel processing"""
        try:
            while True:
                await asyncio.sleep(0.5)  # Update every 500ms
                
                # Get current results from thread manager (real-time)
                results = []
                if self.thread_manager:
                    worker_results = await self.thread_manager.get_current_results()
                    # Extract just the result objects (worker_results is list of (rom_info, result) tuples)
                    results = [result for _, result in worker_results]
                
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
                'active_threads': stats.get('active_threads', 0),
                'max_threads': stats.get('max_threads', 1)
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


