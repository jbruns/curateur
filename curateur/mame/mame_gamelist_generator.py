"""Main MAME gamelist generator workflow.

Orchestrates parsing, filtering, ROM copying, media organization, and gamelist generation.
"""

import logging
import time
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass

from ..gamelist.game_entry import GameEntry, GamelistMetadata
from ..gamelist.generator import GamelistGenerator
from ..gamelist.xml_writer import GamelistWriter
from ..gamelist.parser import GamelistParser
from ..gamelist.integrity_validator import IntegrityValidator

from .mame_xml_parser import MAMEXMLParser
from .history_parser import HistoryParser
from .ini_parser import BestGamesParser, GenreParser, MultiplayerParser, GameOrNoGameParser
from .mame_metadata_builder import MAMEMetadataBuilder, MAMEMetadataBuilderConfig
from .mame_rom_copier import MAMEROMCopier
from .mame_media_organizer import MAMEMediaOrganizer

logger = logging.getLogger(__name__)


@dataclass
class MAMEConfig:
    """Configuration for MAME gamelist generation."""
    # Source paths
    source_rom_path: Path
    source_chd_path: Optional[Path]
    mame_xml_path: Path
    multimedia_path: Optional[Path]
    extras_path: Path
    
    # Output paths
    target_rom_path: Path
    gamelist_output_path: Path
    media_output_path: Path
    
    # Filtering
    inclusion_list_path: Optional[Path] = None
    minimum_rating: Optional[float] = None
    use_game_or_no_game: bool = False
    favorite_threshold: Optional[float] = None
    
    # Processing options
    auto_sortname_enabled: bool = False
    dry_run: bool = False
    merge_strategy: str = "refresh_metadata"
    validate_output: bool = True


class MAMEGamelistGenerator:
    """Main workflow orchestrator for MAME gamelist generation."""

    def __init__(self, config: MAMEConfig):
        """Initialize generator with configuration.
        
        Args:
            config: MAME configuration
        """
        self.config = config

    def generate(self) -> bool:
        """Execute full MAME gamelist generation workflow.
        
        Returns:
            True if successful, False if errors occurred
        """
        start_time = time.time()
        
        try:
            # Phase 1: Parse all sources
            logger.info("=" * 60)
            logger.info("Phase 1: Parsing MAME metadata sources")
            logger.info("=" * 60)
            
            parsed_data = self._parse_sources()
            if not parsed_data:
                return False
            
            # Phase 2: Build and filter metadata
            logger.info("\n" + "=" * 60)
            logger.info("Phase 2: Building game metadata")
            logger.info("=" * 60)
            
            game_entries = self._build_metadata(parsed_data)
            if not game_entries:
                logger.error("No games matched filtering criteria")
                return False
            
            shortnames = set(game_entries.keys())
            
            # Phase 3: Copy ROMs and CHDs
            logger.info("\n" + "=" * 60)
            logger.info("Phase 3: Copying ROMs and CHDs")
            logger.info("=" * 60)
            
            copy_success = self._copy_roms_and_chds(shortnames, parsed_data['mame_parser'])
            if not copy_success:
                return False
            
            # Phase 4: Organize media
            logger.info("\n" + "=" * 60)
            logger.info("Phase 4: Organizing media files")
            logger.info("=" * 60)
            
            self._organize_media(shortnames)
            
            # Phase 5: Generate gamelist
            logger.info("\n" + "=" * 60)
            logger.info("Phase 5: Generating gamelist.xml")
            logger.info("=" * 60)
            
            gamelist_success = self._generate_gamelist(game_entries)
            if not gamelist_success:
                return False
            
            # Complete
            elapsed = time.time() - start_time
            logger.info("\n" + "=" * 60)
            logger.info(f"MAME gamelist generation complete in {elapsed:.1f}s")
            logger.info("=" * 60)
            logger.info(f"Gamelist: {self.config.gamelist_output_path}")
            logger.info(f"ROMs: {self.config.target_rom_path}")
            logger.info(f"Media: {self.config.media_output_path}")
            
            return True
            
        except Exception as e:
            logger.error(f"Fatal error during generation: {e}", exc_info=True)
            return False

    def _parse_sources(self) -> Optional[Dict]:
        """Parse all MAME metadata sources.
        
        Returns:
            Dictionary with parsed data, or None if parsing failed
        """
        try:
            # Parse MAME XML
            logger.info(f"Parsing MAME XML: {self.config.mame_xml_path}")
            mame_parser = MAMEXMLParser(self.config.mame_xml_path)
            mame_parser.parse()
            
            # Parse history.xml
            history_descriptions = {}
            history_path = self.config.extras_path / "history" / "history.xml"
            if history_path.exists():
                logger.info(f"Parsing history.xml: {history_path}")
                history_parser = HistoryParser(history_path)
                history_descriptions = history_parser.parse()
            else:
                logger.warning(f"history.xml not found: {history_path}")
            
            # Parse INI files
            folders_path = self.config.extras_path / "folders"
            
            # Ratings from bestgames.ini
            ratings_map = {}
            bestgames_path = folders_path / "bestgames.ini"
            if bestgames_path.exists():
                logger.info(f"Parsing bestgames.ini: {bestgames_path}")
                bestgames_parser = BestGamesParser(bestgames_path)
                bestgames_parser.parse()
                ratings_map = bestgames_parser.get_ratings_map()
            else:
                logger.warning(f"bestgames.ini not found: {bestgames_path}")
            
            # Genres from genre.ini
            genres_map = {}
            genre_path = folders_path / "genre.ini"
            if genre_path.exists():
                logger.info(f"Parsing genre.ini: {genre_path}")
                genre_parser = GenreParser(genre_path)
                genre_parser.parse()
                genres_map = {
                    shortname: genre_parser.get_genre(shortname)
                    for shortname in mame_parser.machines.keys()
                }
                genres_map = {k: v for k, v in genres_map.items() if v}
            else:
                logger.warning(f"genre.ini not found: {genre_path}")
            
            # Player counts from multiplayer.ini
            players_map = {}
            multiplayer_path = folders_path / "multiplayer.ini"
            if multiplayer_path.exists():
                logger.info(f"Parsing multiplayer.ini: {multiplayer_path}")
                multiplayer_parser = MultiplayerParser(multiplayer_path)
                multiplayer_parser.parse()
                players_map = {
                    shortname: multiplayer_parser.get_players(shortname)
                    for shortname in mame_parser.machines.keys()
                }
                players_map = {k: v for k, v in players_map.items() if v}
            else:
                logger.warning(f"multiplayer.ini not found: {multiplayer_path}")
            
            # Game filter from Game or No Game.ini
            game_filter = None
            if self.config.use_game_or_no_game:
                game_or_no_game_path = folders_path / "Game or No Game.ini"
                if game_or_no_game_path.exists():
                    logger.info(f"Parsing Game or No Game.ini: {game_or_no_game_path}")
                    game_parser = GameOrNoGameParser(game_or_no_game_path)
                    game_parser.parse()
                    game_filter = game_parser.get_games()
                else:
                    logger.warning(
                        f"Game or No Game.ini not found: {game_or_no_game_path}, "
                        "assuming all machines are games"
                    )
            
            return {
                'mame_parser': mame_parser,
                'history_descriptions': history_descriptions,
                'ratings_map': ratings_map,
                'genres_map': genres_map,
                'players_map': players_map,
                'game_filter': game_filter
            }
            
        except Exception as e:
            logger.error(f"Error parsing sources: {e}", exc_info=True)
            return None

    def _build_metadata(self, parsed_data: Dict) -> Dict[str, GameEntry]:
        """Build game metadata from parsed sources.
        
        Args:
            parsed_data: Dictionary with parsed data
            
        Returns:
            Dictionary mapping shortname to GameEntry
        """
        builder = MAMEMetadataBuilder(
            mame_parser=parsed_data['mame_parser'],
            history_descriptions=parsed_data['history_descriptions'],
            ratings_map=parsed_data['ratings_map'],
            genres_map=parsed_data['genres_map'],
            players_map=parsed_data['players_map'],
            game_filter=parsed_data['game_filter']
        )
        
        config = MAMEMetadataBuilderConfig(
            inclusion_list_path=self.config.inclusion_list_path,
            minimum_rating=self.config.minimum_rating,
            use_game_or_no_game=self.config.use_game_or_no_game,
            favorite_threshold=self.config.favorite_threshold,
            auto_sortname_enabled=self.config.auto_sortname_enabled
        )
        
        return builder.build_game_entries(config)

    def _copy_roms_and_chds(self, shortnames: set, mame_parser: MAMEXMLParser) -> bool:
        """Copy ROM and CHD files.
        
        Args:
            shortnames: Set of game shortnames
            mame_parser: Parsed MAME XML data
            
        Returns:
            True if successful, False if errors occurred
        """
        copier = MAMEROMCopier(
            source_rom_path=self.config.source_rom_path,
            source_chd_path=self.config.source_chd_path,
            target_rom_path=self.config.target_rom_path,
            mame_parser=mame_parser
        )
        
        stats, errors = copier.copy_roms_and_chds(
            shortnames=shortnames,
            dry_run=self.config.dry_run
        )
        
        if errors:
            logger.error(f"Encountered {len(errors)} errors during copying:")
            for error in errors[:10]:  # Show first 10
                logger.error(f"  - {error}")
            if len(errors) > 10:
                logger.error(f"  ... and {len(errors) - 10} more")
            
            # Fatal errors (disk space) should stop execution
            if any("disk space" in error.lower() for error in errors):
                return False
        
        return True

    def _organize_media(self, shortnames: set):
        """Organize media files.
        
        Args:
            shortnames: Set of game shortnames
        """
        organizer = MAMEMediaOrganizer(
            extras_path=self.config.extras_path,
            multimedia_path=self.config.multimedia_path,
            media_output_path=self.config.media_output_path
        )
        
        organizer.organize_media(
            shortnames=shortnames,
            dry_run=self.config.dry_run
        )

    def _generate_gamelist(self, game_entries: Dict[str, GameEntry]) -> bool:
        """Generate gamelist.xml file.
        
        Args:
            game_entries: Dictionary mapping shortname to GameEntry
            
        Returns:
            True if successful, False if errors occurred
        """
        try:
            # Create metadata for provider element
            metadata = GamelistMetadata(
                system="MAME",
                software="curateur-mame",
                database="MAME Official",
                web="https://www.mamedev.org"
            )
            
            # Check for existing gamelist to merge
            existing_entries = []
            if self.config.gamelist_output_path.exists():
                logger.info(f"Loading existing gamelist: {self.config.gamelist_output_path}")
                parser = GamelistParser()
                try:
                    existing_entries = parser.parse_gamelist(self.config.gamelist_output_path)
                    logger.info(f"Found {len(existing_entries)} existing entries")
                except Exception as e:
                    logger.warning(f"Could not parse existing gamelist: {e}")
            
            # Convert to list
            entries_list = list(game_entries.values())
            
            if self.config.dry_run:
                logger.info(f"Dry run: would generate gamelist with {len(entries_list)} entries")
                return True
            
            # Create output directory
            self.config.gamelist_output_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Write gamelist
            writer = GamelistWriter(metadata)
            writer.write_gamelist(entries_list, self.config.gamelist_output_path)
            
            logger.info(f"Generated gamelist.xml with {len(entries_list)} entries")
            
            # Validate if requested
            if self.config.validate_output:
                logger.info("Validating gamelist integrity...")
                validator = IntegrityValidator(threshold=0.90)
                
                # Get list of ROM files in the target directory
                rom_files = list(self.config.target_rom_path.glob('*.zip'))
                
                validation_result = validator.validate(entries_list, rom_files)
                
                if not validation_result.is_valid:
                    logger.warning("Gamelist validation failed:")
                    logger.warning(f"  Match ratio: {validation_result.match_ratio:.1%}")
                    logger.warning(f"  Missing ROMs: {len(validation_result.missing_roms)}")
                    logger.warning(f"  Orphaned entries: {len(validation_result.orphaned_entries)}")
                else:
                    logger.info(f"Gamelist validation passed (match ratio: {validation_result.match_ratio:.1%})")
            
            return True
            
        except Exception as e:
            logger.error(f"Error generating gamelist: {e}", exc_info=True)
            return False
