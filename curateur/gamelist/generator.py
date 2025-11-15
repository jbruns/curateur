"""
Main gamelist generator integration.

Coordinates gamelist creation, parsing, merging, and writing.
"""

from pathlib import Path
from typing import List, Dict, Optional
from .game_entry import GameEntry, GamelistMetadata
from .xml_writer import GamelistWriter
from .parser import GamelistParser, GamelistMerger
from .path_handler import PathHandler


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
        software_name: str = "curateur"
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
        """
        self.system_name = system_name
        self.full_system_name = full_system_name
        self.software_name = software_name
        
        # Initialize components
        self.path_handler = PathHandler(
            rom_directory,
            media_directory,
            gamelist_directory
        )
        
        self.parser = GamelistParser()
        self.merger = GamelistMerger()
        
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
        merge_existing: bool = True
    ) -> Path:
        """
        Generate or update gamelist.xml.
        
        Args:
            scraped_games: List of dicts with game info and ROM paths
            media_results: Dict mapping ROM path to media download results
            merge_existing: Whether to merge with existing gamelist
            
        Returns:
            Path to generated gamelist.xml
            
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
        # Create game entries from scraped data
        new_entries = self._create_game_entries(scraped_games, media_results)
        
        # Load existing gamelist if merging
        existing_entries = []
        if merge_existing and self.gamelist_path.exists():
            try:
                existing_entries = self.parser.parse_gamelist(self.gamelist_path)
            except Exception as e:
                # If parsing fails, start fresh
                print(f"Warning: Could not parse existing gamelist: {e}")
                existing_entries = []
        
        # Merge entries
        if existing_entries:
            final_entries = self.merger.merge_entries(existing_entries, new_entries)
        else:
            final_entries = new_entries
        
        # Write gamelist
        self.writer.write_gamelist(final_entries, self.gamelist_path)
        
        return self.gamelist_path
    
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
