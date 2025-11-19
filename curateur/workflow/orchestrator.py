"""
Workflow orchestrator for curateur scraping operations.

Coordinates the complete scraping workflow:
1. Scan ROMs
2. Query API for metadata
3. Download media
4. Generate gamelist
"""

import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from ..config.es_systems import SystemDefinition
from ..scanner.rom_scanner import scan_system
from ..scanner.rom_types import ROMInfo
from ..api.client import ScreenScraperClient
from ..api.error_handler import SkippableAPIError, categorize_error, ErrorCategory
from ..api.match_scorer import calculate_match_confidence
from ..ui.prompts import prompt_for_search_match
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
    
    def scrape_system(
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
            results, not_found_items = self._scrape_roms_parallel(
                system,
                rom_entries,
                media_types,
                preferred_regions
            )
        else:
            # Use sequential processing
            for rom_info in rom_entries:
                result = self._scrape_rom(
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
                self._generate_gamelist(system, results)
            except Exception as e:
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
    
    def _scrape_rom(
        self,
        system: SystemDefinition,
        rom_info: ROMInfo,
        media_types: List[str],
        preferred_regions: List[str]
    ) -> ScrapingResult:
        """
        Scrape a single ROM.
        
        Args:
            system: System definition
            rom_info: ROM information from scanner
            media_types: Media types to download
            preferred_regions: Region priority list
            
        Returns:
            ScrapingResult
        """
        rom_path = rom_info.path
        
        try:
            # Step 2: Query API (hash-based lookup)
            if self.dry_run:
                return ScrapingResult(
                    rom_path=rom_path,
                    success=True,
                    api_id="DRY_RUN"
                )
            
            game_info = None
            
            # Try hash-based lookup first
            try:
                game_info = self.api_client.query_game(rom_info)
                logger.debug(f"Hash lookup successful for {rom_info.filename}")
            except SkippableAPIError as e:
                logger.debug(f"Hash lookup failed for {rom_info.filename}: {e}")
                
                # Try search fallback if enabled
                if self.enable_search_fallback:
                    logger.info(f"Attempting search fallback for {rom_info.filename}")
                    game_info = self._search_fallback(rom_info, preferred_regions)
                    
                    if game_info:
                        logger.info(f"Search fallback successful for {rom_info.filename}")
                    else:
                        logger.info(f"Search fallback found no matches for {rom_info.filename}")
            
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
                            elif not result.success:
                                # Log media download failures
                                logger.warning(
                                    f"Failed to download {result.media_type} for {rom_info.filename}: {result.error}"
                                )
            except Exception:
                # Log but don't fail the entire ROM for media errors
                pass
            
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
    
    def _scrape_roms_parallel(
        self,
        system: SystemDefinition,
        rom_entries: List[ROMInfo],
        media_types: List[str],
        preferred_regions: List[str]
    ) -> Tuple[List[ScrapingResult], List[dict]]:
        """
        Scrape ROMs in parallel using WorkQueueManager and ThreadPoolManager.
        
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
        
        # Populate work queue with all ROM entries
        for rom_info in rom_entries:
            rom_info_dict = {
                'filename': rom_info.filename,
                'path': str(rom_info.path),
                'system': rom_info.system,
                'file_size': rom_info.file_size,
                'crc32': rom_info.crc32,
                'query_filename': rom_info.query_filename,
                'basename': rom_info.basename,
                'rom_type': rom_info.rom_type.value  # Serialize enum as string
            }
            self.work_queue.add_work(rom_info_dict, 'full_scrape', Priority.NORMAL)
        
        # Define work item processor
        def process_work_item(work_item) -> dict:
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
                crc32=rom_info_dict.get('crc32')
            )
            
            try:
                # Query API
                game_info = None
                
                # Try hash-based lookup first
                try:
                    game_info = self.api_client.query_game(rom_info)
                    if self.performance_monitor:
                        self.performance_monitor.record_api_call()
                    logger.debug(f"Hash lookup successful for {rom_info.filename}")
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
                                game_info = self._search_fallback(rom_info, preferred_regions)
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
        
        # Work queue consumption loop
        while not self.work_queue.is_empty():
            work_item = self.work_queue.get_work(timeout=0.1)
            if not work_item:
                continue
            
            rom_count += 1
            rom_info_dict = work_item.rom_info
            
            # Update UI if available
            if self.console_ui:
                self.console_ui.update_main({
                    'rom_name': rom_info_dict['filename'],
                    'rom_num': rom_count,
                    'total_roms': len(rom_entries),
                    'action': 'scraping',
                    'details': 'Fetching metadata...'
                })
                
                # Update work queue stats in UI
                queue_stats = self.work_queue.get_stats()
                self.console_ui.update_work_queue_stats(
                    pending=queue_stats['pending'],
                    processed=queue_stats['processed'],
                    failed=queue_stats['failed'],
                    not_found=len(not_found_items),
                    retry_count=sum(item['retry_count'] for item in self.work_queue.get_failed_items())
                )
            
            # Process the work item
            try:
                api_result = process_work_item(work_item)
                
                # Handle result based on category
                if api_result['category'] == 'not_found':
                    # 404 - track separately and mark processed
                    not_found_items.append({
                        'rom_info': api_result['rom_info'],
                        'error': api_result['error']
                    })
                    self.work_queue.mark_processed(work_item)
                    continue
                
                elif api_result['category'] == 'retryable':
                    # Retry with higher priority
                    self.work_queue.retry_failed(work_item, api_result['error'])
                    continue
                
                elif api_result['category'] == 'success':
                    game_info = api_result.get('game_info')
                    rom_info = api_result['rom_info']
                    
                    if not game_info:
                        # No game info but not an error - mark as unmatched
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
                        continue
                    
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
    
    def _search_fallback(
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
            results = self.api_client.search_game(
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

