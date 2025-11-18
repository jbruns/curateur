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
from ..api.error_handler import SkippableAPIError
from ..api.match_scorer import calculate_match_confidence
from ..ui.prompts import prompt_for_search_match
from ..media.media_downloader import MediaDownloader
from ..gamelist.generator import GamelistGenerator
from ..gamelist.game_entry import GameEntry

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
        dry_run: bool = False,
        enable_search_fallback: bool = False,
        search_confidence_threshold: float = 0.7,
        search_max_results: int = 5,
        interactive_search: bool = False,
        preferred_regions: Optional[List[str]] = None,
        thread_manager: Optional['ThreadPoolManager'] = None,
        performance_monitor: Optional['PerformanceMonitor'] = None,
        console_ui: Optional['ConsoleUI'] = None,
        work_queue: Optional['WorkQueueManager'] = None
    ):
        """
        Initialize workflow orchestrator.
        
        Args:
            api_client: Configured API client
            rom_directory: Root directory for ROMs
            media_directory: Root directory for downloaded media
            gamelist_directory: Root directory for gamelists
            dry_run: If True, simulate actions without making changes
            enable_search_fallback: Enable search when hash lookup fails
            search_confidence_threshold: Minimum confidence score to accept match
            search_max_results: Maximum search results to consider
            interactive_search: Enable interactive prompts for search matches
            preferred_regions: Region preference list for scoring
            thread_manager: Optional ThreadPoolManager for parallel operations
            performance_monitor: Optional PerformanceMonitor for metrics tracking
            console_ui: Optional ConsoleUI for rich display
            work_queue: Optional WorkQueueManager for retry handling
        """
        self.api_client = api_client
        self.rom_directory = rom_directory
        self.media_directory = media_directory
        self.gamelist_directory = gamelist_directory
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
        self.work_queue = work_queue
        
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
        scraped_count = 0
        failed_count = 0
        skipped_count = 0
        
        # Step 2-4: Process each ROM (parallel or sequential)
        if self.thread_manager and not self.dry_run:
            # Use parallel processing
            results = self._scrape_roms_parallel(
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
        
        return SystemResult(
            system_name=system.fullname,
            total_roms=len(rom_entries),
            scraped=scraped_count,
            failed=failed_count,
            skipped=skipped_count,
            results=results
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
                media_root=self.media_directory / system.name,
                preferred_regions=preferred_regions
            )
            
            media_paths = {}
            media_count = 0
            
            for media_type in media_types:
                media_data = game_info.get('media', {}).get(media_type, [])
                
                if media_data:
                    try:
                        # Get first available media URL
                        media_url = media_data[0].get('url') if isinstance(media_data, list) else media_data.get('url')
                        
                        if media_url:
                            media_path = media_downloader.download_media(
                                media_type=media_type,
                                media_url=media_url,
                                game_name=game_info.get('name', rom_info.basename)
                            )
                            
                            if media_path:
                                media_paths[media_type] = str(media_path)
                                media_count += 1
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
    ) -> List[ScrapingResult]:
        """
        Scrape ROMs in parallel using ThreadPoolManager.
        
        Args:
            system: System definition
            rom_entries: List of ROM information from scanner
            media_types: Media types to download
            preferred_regions: Region priority list
            
        Returns:
            List of ScrapingResult
        """
        results = []
        rom_count = 0
        
        # Define scraping function for parallel execution
        def scrape_single_rom(rom_info: ROMInfo) -> dict:
            """Wrapper for parallel API calls"""
            try:
                # Query API
                game_info = None
                
                # Try hash-based lookup first
                try:
                    game_info = self.api_client.query_game(rom_info)
                    if self.performance_monitor:
                        self.performance_monitor.record_api_call()
                    logger.debug(f"Hash lookup successful for {rom_info.filename}")
                except SkippableAPIError as e:
                    logger.debug(f"Hash lookup failed for {rom_info.filename}: {e}")
                    
                    # Try search fallback if enabled
                    if self.enable_search_fallback:
                        logger.info(f"Attempting search fallback for {rom_info.filename}")
                        game_info = self._search_fallback(rom_info, preferred_regions)
                        
                        if game_info:
                            logger.info(f"Search fallback successful for {rom_info.filename}")
                            if self.performance_monitor:
                                self.performance_monitor.record_api_call()
                        else:
                            logger.info(f"Search fallback found no matches for {rom_info.filename}")
                
                return {'rom_info': rom_info, 'game_info': game_info}
                
            except Exception as e:
                return {'rom_info': rom_info, 'error': str(e)}
        
        # Process API calls in parallel
        for rom_info, api_result in self.thread_manager.submit_api_batch(
            scrape_single_rom, rom_entries
        ):
            rom_count += 1
            
            # Update UI if available
            if self.console_ui:
                self.console_ui.update_main({
                    'rom_name': rom_info.filename,
                    'rom_num': rom_count,
                    'total_roms': len(rom_entries),
                    'action': 'scraping',
                    'details': 'Fetching metadata...'
                })
            
            # Handle API result
            if 'error' in api_result:
                # API call failed
                result = ScrapingResult(
                    rom_path=rom_info.path,
                    success=False,
                    error=api_result['error']
                )
                results.append(result)
                continue
            
            game_info = api_result.get('game_info')
            
            if not game_info:
                # Track as unmatched
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
                
                # Log metrics periodically
                if rom_count % 10 == 0:
                    self.performance_monitor.log_metrics()
                
                # Update UI footer with metrics
                if self.console_ui:
                    metrics = self.performance_monitor.get_metrics()
                    self.console_ui.update_footer(
                        stats={
                            'successful': metrics.roms_processed,
                            'failed': len([r for r in results if not r.success])
                        },
                        api_quota={'requests_today': metrics.api_calls, 'max_requests_per_day': 10000}
                    )
            
            result = ScrapingResult(
                rom_path=rom_info.path,
                success=True,
                api_id=str(game_info.get('id', '')),
                media_downloaded=media_count,
                game_info=game_info,
                media_paths=media_paths
            )
            results.append(result)
        
        return results
    
    def _download_media_parallel(
        self,
        system: SystemDefinition,
        rom_info: ROMInfo,
        game_info: dict,
        media_types: List[str],
        preferred_regions: List[str]
    ) -> Tuple[dict, int]:
        """
        Download media files in parallel using ThreadPoolManager.
        
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
            media_root=self.media_directory / system.name,
            preferred_regions=preferred_regions
        )
        
        # Collect media to download
        media_batch = []
        for media_type in media_types:
            media_data = game_info.get('media', {}).get(media_type, [])
            
            if media_data:
                media_url = media_data[0].get('url') if isinstance(media_data, list) else media_data.get('url')
                
                if media_url:
                    media_batch.append({
                        'media_type': media_type,
                        'media_url': media_url,
                        'game_name': game_info.get('name', rom_info.basename)
                    })
        
        if not media_batch:
            return {}, 0
        
        # Define download function for parallel execution
        def download_single_media(media_item: dict) -> Optional[Path]:
            """Wrapper for parallel media downloads"""
            try:
                media_path = media_downloader.download_media(
                    media_type=media_item['media_type'],
                    media_url=media_item['media_url'],
                    game_name=media_item['game_name']
                )
                
                if media_path and self.performance_monitor:
                    self.performance_monitor.record_download()
                
                return media_path
            except Exception as e:
                logger.debug(f"Media download failed: {e}")
                return None
        
        # Download media in parallel
        media_paths = {}
        media_count = 0
        
        for media_item, download_result in self.thread_manager.submit_download_batch(
            download_single_media, media_batch
        ):
            if 'error' not in download_result and download_result:
                media_paths[media_item['media_type']] = str(download_result)
                media_count += 1
        
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
