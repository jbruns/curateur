"""
Workflow orchestrator for curateur scraping operations.

Coordinates the complete scraping workflow:
1. Scan ROMs
2. Query API for metadata
3. Download media
4. Generate gamelist
"""

from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass

from ..config.es_systems import SystemDefinition
from ..scanner.rom_scanner import scan_system
from ..api.client import APIClient
from ..media.downloader import MediaDownloader
from ..gamelist.generator import GamelistGenerator
from ..gamelist.game_entry import GameEntry


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
        api_client: APIClient,
        rom_directory: Path,
        media_directory: Path,
        gamelist_directory: Path,
        dry_run: bool = False
    ):
        """
        Initialize workflow orchestrator.
        
        Args:
            api_client: Configured API client
            rom_directory: Root directory for ROMs
            media_directory: Root directory for downloaded media
            gamelist_directory: Root directory for gamelists
            dry_run: If True, simulate actions without making changes
        """
        self.api_client = api_client
        self.rom_directory = rom_directory
        self.media_directory = media_directory
        self.gamelist_directory = gamelist_directory
        self.dry_run = dry_run
    
    def scrape_system(
        self,
        system: SystemDefinition,
        media_types: List[str] = None,
        preferred_regions: List[str] = None
    ) -> SystemResult:
        """
        Scrape a single system.
        
        Args:
            system: System definition
            media_types: Media types to download (default: ['box-2D', 'ss'])
            preferred_regions: Region priority list (default: ['us', 'wor', 'eu'])
            
        Returns:
            SystemResult with scraping statistics
        """
        if media_types is None:
            media_types = ['box-2D', 'ss']
        
        if preferred_regions is None:
            preferred_regions = ['us', 'wor', 'eu']
        
        # Step 1: Scan ROMs
        system_rom_dir = self.rom_directory / system.name
        
        if not system_rom_dir.exists():
            return SystemResult(
                system_name=system.fullname,
                total_roms=0,
                scraped=0,
                failed=0,
                skipped=0,
                results=[]
            )
        
        rom_entries = scan_system(system, system_rom_dir)
        
        results = []
        scraped_count = 0
        failed_count = 0
        skipped_count = 0
        
        # Step 2-4: Process each ROM
        for rom_entry in rom_entries:
            result = self._scrape_rom(
                system,
                rom_entry,
                media_types,
                preferred_regions
            )
            
            results.append(result)
            
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
        rom_entry: dict,
        media_types: List[str],
        preferred_regions: List[str]
    ) -> ScrapingResult:
        """
        Scrape a single ROM.
        
        Args:
            system: System definition
            rom_entry: ROM entry from scanner
            media_types: Media types to download
            preferred_regions: Region priority list
            
        Returns:
            ScrapingResult
        """
        rom_path = rom_entry['path']
        
        try:
            # Step 2: Query API
            if self.dry_run:
                return ScrapingResult(
                    rom_path=rom_path,
                    success=True,
                    api_id="DRY_RUN"
                )
            
            # Get game info from API
            game_info = self.api_client.get_game_info(
                system_id=system.platform,
                rom_name=rom_entry['display_name'],
                rom_size=rom_entry.get('size', 0),
                crc32=rom_entry.get('crc32')
            )
            
            if not game_info:
                return ScrapingResult(
                    rom_path=rom_path,
                    success=False,
                    error="No game info found from API"
                )
            
            # Step 3: Download media
            media_downloader = MediaDownloader(
                media_directory=self.media_directory / system.name,
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
                                game_name=game_info.get('name', rom_entry['display_name'])
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
            return ScrapingResult(
                rom_path=rom_path,
                success=False,
                error=str(e)
            )
    
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
