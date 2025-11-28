"""
Main gamelist generator integration.

Coordinates gamelist creation, parsing, merging, and writing.
"""

import logging
from pathlib import Path
from typing import List, Dict, Optional
from .game_entry import GameEntry, GamelistMetadata
from .xml_writer import GamelistWriter
from .parser import GamelistParser, GamelistMerger
from .path_handler import PathHandler
from .integrity_validator import IntegrityValidator

logger = logging.getLogger(__name__)


class GamelistGenerator:
    """
    Main gamelist generator coordinating all operations.
    
    Features:
    - Parse existing gamelists
    - Merge with new scraped data
    - Preserve user edits
    - Generate properly formatted XML
    """
    
    def __init__(
        self,
        system_name: str,
        full_system_name: str,
        rom_directory: Path,
        media_directory: Path,
        gamelist_directory: Path,
        software_name: str = "curateur",
        merge_strategy: str = "preserve_user_edits",
        auto_favorite_enabled: bool = False,
        auto_favorite_threshold: float = 0.9
    ):
        """
        Initialize gamelist generator.

        Args:
            system_name: System name (e.g., 'nes', 'psx')
            full_system_name: Full system name (e.g., 'Nintendo Entertainment System', 'Sony PlayStation')
            rom_directory: Path to ROM directory
            media_directory: Path to media root directory
            gamelist_directory: Path to gamelist directory
            software_name: Software name for provider metadata
            merge_strategy: Merge strategy ('preserve_user_edits', 'refresh_metadata', 'reset_all')
            auto_favorite_enabled: Enable automatic favorite flag for highly-rated games
            auto_favorite_threshold: Rating threshold (0.0-1.0) for auto-favorite
        """
        self.system_name = system_name
        self.full_system_name = full_system_name
        self.software_name = software_name
        self.rom_directory = rom_directory
        self.merge_strategy = merge_strategy
        self.auto_favorite_enabled = auto_favorite_enabled
        self.auto_favorite_threshold = auto_favorite_threshold

        # Initialize components
        self.path_handler = PathHandler(
            rom_directory,
            media_directory,
            gamelist_directory
        )

        self.parser = GamelistParser()
        self.merger = GamelistMerger(
            merge_strategy=merge_strategy,
            auto_favorite_enabled=auto_favorite_enabled,
            auto_favorite_threshold=auto_favorite_threshold
        )
        self.validator = IntegrityValidator(threshold=0.90)
        
        self.metadata = GamelistMetadata(
            system=full_system_name,
            software=software_name
        )
        
        self.writer = GamelistWriter(self.metadata)
        
        self.gamelist_path = gamelist_directory / "gamelist.xml"
    
    def generate_gamelist(
        self,
        scraped_games: List[Dict],
        media_results: Dict[str, List] = None,
        merge_existing: bool = True,
        validate: bool = True
    ) -> Optional[Dict]:
        """
        Generate or update gamelist.xml.
        
        Args:
            scraped_games: List of dicts with game info and ROM paths
            media_results: Dict mapping ROM path to media download results
            merge_existing: Whether to merge with existing gamelist
            validate: Whether to run integrity validation after writing
            
        Returns:
            Integrity validation result dict or None
            
        Example scraped_games format:
        [
            {
                'rom_path': Path('roms/nes/Mario.nes'),
                'game_info': {...},  # From API response
                'media_paths': {...}  # From media downloader
            },
            ...
        ]
        """
        logger.info(f"Starting gamelist generation: {len(scraped_games)} new games, merge_existing={merge_existing}")

        # Create game entries from scraped data
        try:
            logger.debug("About to call _create_game_entries...")
            new_entries = self._create_game_entries(scraped_games, media_results)
            logger.info(f"Created {len(new_entries)} game entries from scraped data")
        except Exception as e:
            logger.error(f"EXCEPTION in _create_game_entries: {e}", exc_info=True)
            raise

        # Load existing gamelist if merging
        existing_entries = []
        if merge_existing and self.gamelist_path.exists():
            try:
                existing_entries = self.parser.parse_gamelist(self.gamelist_path)
                logger.info(f"Loaded {len(existing_entries)} entries from existing gamelist")
            except Exception as e:
                # If parsing fails, start fresh
                logger.warning(f"Could not parse existing gamelist: {e}")
                existing_entries = []

        # Merge entries (always use merger to apply auto-favorite and other logic)
        final_entries = self.merger.merge_entries(existing_entries, new_entries)
        if existing_entries:
            logger.info(f"Merged entries: {len(final_entries)} total (was {len(existing_entries)} existing, {len(new_entries)} new)")
        else:
            logger.info(f"No existing gamelist, created {len(final_entries)} new entries")

        # Write gamelist
        logger.info(f"Calling writer.write_gamelist with {len(final_entries)} entries to {self.gamelist_path}")
        self.writer.write_gamelist(final_entries, self.gamelist_path)
        
        # Run integrity validation if requested
        if validate:
            # Get list of ROM files in the directory
            rom_files = list(self.rom_directory.glob('*'))
            # Filter out non-ROM files (directories, hidden files, etc.)
            rom_files = [f for f in rom_files if f.is_file() and not f.name.startswith('.')]
            
            validation_result = self.validator.validate(final_entries, rom_files)
            
            return {
                'valid': validation_result.is_valid,
                'integrity_score': validation_result.match_ratio,
                'total_entries': len(final_entries),
                'missing_roms': len(validation_result.missing_roms),
                'orphaned_entries': len(validation_result.orphaned_entries)
            }
        
        return None
    
    def _create_game_entries(
        self,
        scraped_games: List[Dict],
        media_results: Dict[str, List] = None
    ) -> List[GameEntry]:
        """
        Create GameEntry objects from scraped data.
        
        Args:
            scraped_games: List of scraped game dicts
            media_results: Media download results
            
        Returns:
            List of GameEntry objects
        """
        entries = []
        media_results = media_results or {}
        
        for game_data in scraped_games:
            rom_path = game_data['rom_path']
            game_info = game_data['game_info']
            
            # Get relative ROM path
            relative_rom_path = self.path_handler.get_relative_rom_path(rom_path)
            
            # Get media paths from download results
            media_paths = self._extract_media_paths(
                game_data.get('media_paths', {}),
                rom_path
            )
            
            # Create entry
            entry = GameEntry.from_api_response(
                game_info,
                relative_rom_path,
                media_paths
            )
            
            entries.append(entry)
        
        return entries
    
    def _extract_media_paths(
        self,
        media_paths: Dict[str, Path],
        rom_path: Path
    ) -> Dict[str, str]:
        """
        Extract and convert media paths to relative paths.
        
        Args:
            media_paths: Dict of media type to absolute path
            rom_path: ROM path for context
            
        Returns:
            Dict of media type to relative path
        """
        relative_paths = {}
        
        for media_type, abs_path in media_paths.items():
            if abs_path and Path(abs_path).exists():
                rel_path = self.path_handler.get_relative_media_path(abs_path)
                
                # Map media type to gamelist field
                if media_type == 'box-2D':
                    relative_paths['cover'] = rel_path
                elif media_type == 'ss':
                    relative_paths['screenshot'] = rel_path
                elif media_type == 'screenmarquee':
                    relative_paths['screenmarquee'] = rel_path
                elif media_type == 'video':
                    relative_paths['video'] = rel_path
        
        return relative_paths
    
    def add_single_game(
        self,
        rom_path: Path,
        game_info: Dict,
        media_paths: Dict[str, Path] = None
    ) -> GameEntry:
        """
        Add a single game to the gamelist.
        
        Args:
            rom_path: Absolute path to ROM file
            game_info: Game info from API response
            media_paths: Dict of media type to absolute path
            
        Returns:
            Created GameEntry
        """
        # Get relative paths
        relative_rom_path = self.path_handler.get_relative_rom_path(rom_path)
        relative_media_paths = self._extract_media_paths(
            media_paths or {},
            rom_path
        )
        
        # Create entry
        entry = GameEntry.from_api_response(
            game_info,
            relative_rom_path,
            relative_media_paths
        )
        
        # Load existing entries
        existing_entries = []
        if self.gamelist_path.exists():
            try:
                existing_entries = self.parser.parse_gamelist(self.gamelist_path)
            except Exception:
                # Ignore parse errors - treat as empty gamelist and overwrite
                pass
        
        # Merge
        merged_entries = self.merger.merge_entries(existing_entries, [entry])
        
        # Write
        self.writer.write_gamelist(merged_entries, self.gamelist_path)
        
        return entry
    
    def get_existing_entries(self) -> List[GameEntry]:
        """
        Get entries from existing gamelist.
        
        Returns:
            List of GameEntry objects, empty if no gamelist exists
        """
        if not self.gamelist_path.exists():
            return []
        
        try:
            return self.parser.parse_gamelist(self.gamelist_path)
        except Exception:
            return []
    
    def validate_gamelist(self) -> bool:
        """
        Validate generated gamelist.xml.
        
        Returns:
            True if valid, False otherwise
        """
        if not self.gamelist_path.exists():
            return False
        
        return self.writer.validate_output(self.gamelist_path)
