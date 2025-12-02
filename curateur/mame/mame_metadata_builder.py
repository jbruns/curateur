"""Build GameEntry objects from MAME metadata sources.

Integrates data from MAME XML, INI files, and history.xml to create complete
game metadata with clone inheritance and filtering support.
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass

from ..gamelist.game_entry import GameEntry
from .mame_xml_parser import MAMEXMLParser, MAMEMachine
from .ini_parser import BestGamesParser, GenreParser, MultiplayerParser, GameOrNoGameParser

logger = logging.getLogger(__name__)


@dataclass
class MAMEMetadataBuilderConfig:
    """Configuration for MAME metadata builder."""
    inclusion_list_path: Optional[Path] = None
    minimum_rating: Optional[float] = None
    use_game_or_no_game: bool = False
    favorite_threshold: Optional[float] = None
    auto_sortname_enabled: bool = False


class MAMEMetadataBuilder:
    """Builds GameEntry objects from MAME metadata sources."""

    def __init__(
        self,
        mame_parser: MAMEXMLParser,
        history_descriptions: Dict[str, str],
        ratings_map: Dict[str, float],
        genres_map: Dict[str, str],
        players_map: Dict[str, str],
        game_filter: Optional[Set[str]] = None
    ):
        """Initialize metadata builder.
        
        Args:
            mame_parser: Parsed MAME XML data
            history_descriptions: Map of shortname to description
            ratings_map: Map of shortname to rating (0.0-1.0)
            genres_map: Map of shortname to genre
            players_map: Map of shortname to player count
            game_filter: Optional set of games from Game or No Game.ini
        """
        self.mame_parser = mame_parser
        self.history_descriptions = history_descriptions
        self.ratings_map = ratings_map
        self.genres_map = genres_map
        self.players_map = players_map
        self.game_filter = game_filter

    def build_game_entries(
        self,
        config: MAMEMetadataBuilderConfig
    ) -> Dict[str, GameEntry]:
        """Build GameEntry objects for filtered games.
        
        Args:
            config: Builder configuration with filtering options
            
        Returns:
            Dictionary mapping shortname to GameEntry
        """
        # Step 1: Get initial set of machines to process
        machines = self._filter_machines(config)
        
        logger.info(f"Building metadata for {len(machines)} games")

        # Step 2: Build base entries
        entries: Dict[str, GameEntry] = {}
        for shortname, machine in machines.items():
            entry = self._build_base_entry(machine, config.auto_sortname_enabled)
            if entry:
                entries[shortname] = entry

        # Step 3: Apply clone inheritance
        self._apply_clone_inheritance(entries, machines)

        # Step 4: Apply favorites based on threshold
        if config.favorite_threshold:
            self._apply_favorite_threshold(entries, config.favorite_threshold)

        logger.info(f"Successfully built {len(entries)} game entries")
        
        # Log statistics
        with_ratings = sum(1 for e in entries.values() if e.rating is not None)
        with_genres = sum(1 for e in entries.values() if e.genre)
        with_players = sum(1 for e in entries.values() if e.players)
        with_desc = sum(1 for e in entries.values() if e.desc)
        favorites = sum(1 for e in entries.values() if e.favorite)
        
        logger.info(f"  - {with_ratings} with ratings")
        logger.info(f"  - {with_genres} with genres")
        logger.info(f"  - {with_players} with player counts")
        logger.info(f"  - {with_desc} with descriptions")
        logger.info(f"  - {favorites} marked as favorites")

        return entries

    def _filter_machines(self, config: MAMEMetadataBuilderConfig) -> Dict[str, MAMEMachine]:
        """Filter machines based on configuration.
        
        Args:
            config: Builder configuration
            
        Returns:
            Dictionary of filtered machines
        """
        all_machines = self.mame_parser.machines
        
        # Start with all machines that are games (not BIOS/devices)
        candidates = {
            name: machine
            for name, machine in all_machines.items()
            if machine.is_game()
        }
        
        logger.info(f"Starting with {len(candidates)} playable games")
        
        # Filter by runnable="no"
        non_runnable = []
        runnable_machines = {}
        for name, machine in candidates.items():
            if machine.runnable != "yes":
                non_runnable.append(name)
            else:
                runnable_machines[name] = machine
        
        if non_runnable:
            logger.warning(f"Skipping {len(non_runnable)} non-runnable games")
            for name in non_runnable[:10]:  # Log first 10
                logger.debug(f"  - {name}: runnable={candidates[name].runnable}")
            if len(non_runnable) > 10:
                logger.debug(f"  ... and {len(non_runnable) - 10} more")
        
        candidates = runnable_machines
        logger.info(f"After runnable filter: {len(candidates)} games")
        
        # Filter by inclusion list (if provided)
        if config.inclusion_list_path:
            inclusion_set = self._load_inclusion_list(config.inclusion_list_path)
            candidates = {
                name: machine
                for name, machine in candidates.items()
                if name in inclusion_set
            }
            logger.info(f"After inclusion list filter: {len(candidates)} games")
        
        # Filter by minimum rating (if provided)
        if config.minimum_rating is not None:
            candidates = {
                name: machine
                for name, machine in candidates.items()
                if self.ratings_map.get(name, 0.0) >= config.minimum_rating
            }
            logger.info(f"After rating filter (>={config.minimum_rating}): {len(candidates)} games")
        
        # Filter by Game or No Game.ini (if enabled)
        if config.use_game_or_no_game and self.game_filter:
            candidates = {
                name: machine
                for name, machine in candidates.items()
                if name in self.game_filter
            }
            logger.info(f"After Game or No Game filter: {len(candidates)} games")
        
        return candidates

    def _load_inclusion_list(self, path: Path) -> Set[str]:
        """Load inclusion list from file.
        
        Args:
            path: Path to plain text file with one shortname per line
            
        Returns:
            Set of lowercase shortnames
        """
        if not path.exists():
            logger.warning(f"Inclusion list file not found: {path}")
            return set()
        
        shortnames = set()
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                shortname = line.strip().lower()
                if shortname and not shortname.startswith('#'):
                    shortnames.add(shortname)
        
        logger.info(f"Loaded {len(shortnames)} games from inclusion list")
        return shortnames

    def _build_base_entry(self, machine: MAMEMachine, auto_sortname_enabled: bool = False) -> Optional[GameEntry]:
        """Build base GameEntry from MAME machine.
        
        Args:
            machine: MAME machine definition
            auto_sortname_enabled: Enable automatic sortname generation for articles
            
        Returns:
            GameEntry or None if creation failed
        """
        shortname = machine.name
        
        # Build release date from year (YYYY0101 format)
        releasedate = None
        if machine.year and machine.year.isdigit():
            releasedate = f"{machine.year}0101T000000"
        
        # Get rating
        rating = self.ratings_map.get(shortname)
        
        # Generate sortname if enabled
        sortname = GameEntry._generate_sortname(machine.description) if auto_sortname_enabled else None
        
        # Create GameEntry
        entry = GameEntry(
            path=f"./{shortname}.zip",
            name=machine.description,
            desc=self.history_descriptions.get(shortname),
            releasedate=releasedate,
            developer=machine.manufacturer,
            genre=self.genres_map.get(shortname),
            players=self.players_map.get(shortname),
            rating=rating,
            sortname=sortname
        )
        
        return entry

    def _apply_clone_inheritance(
        self,
        entries: Dict[str, GameEntry],
        machines: Dict[str, MAMEMachine]
    ):
        """Apply clone-to-parent inheritance for missing metadata.
        
        Args:
            entries: Dictionary of GameEntry objects to update
            machines: Dictionary of MAMEMachine objects
        """
        clones_processed = 0
        missing_parents = []
        
        for shortname, entry in entries.items():
            machine = machines.get(shortname)
            if not machine or not machine.cloneof:
                continue
            
            # This is a clone
            parent_shortname = machine.cloneof
            parent_entry = entries.get(parent_shortname)
            
            if not parent_entry:
                missing_parents.append(f"{shortname} -> {parent_shortname}")
                continue
            
            # Inherit missing fields from parent
            inherited = False
            
            if not entry.name and parent_entry.name:
                entry.name = parent_entry.name
                inherited = True
            
            if not entry.desc and parent_entry.desc:
                entry.desc = parent_entry.desc
                inherited = True
            
            if not entry.releasedate and parent_entry.releasedate:
                entry.releasedate = parent_entry.releasedate
                inherited = True
            
            if not entry.developer and parent_entry.developer:
                entry.developer = parent_entry.developer
                inherited = True
            
            if not entry.genre and parent_entry.genre:
                entry.genre = parent_entry.genre
                inherited = True
            
            if not entry.players and parent_entry.players:
                entry.players = parent_entry.players
                inherited = True
            
            if not entry.rating and parent_entry.rating:
                entry.rating = parent_entry.rating
                inherited = True
            
            if not entry.favorite and parent_entry.favorite:
                entry.favorite = True
                inherited = True
            
            if inherited:
                clones_processed += 1
        
        if clones_processed:
            logger.info(f"Applied inheritance to {clones_processed} clones")
        
        if missing_parents:
            logger.warning(f"Skipped inheritance for {len(missing_parents)} clones (parent not in scope)")
            for clone_parent in missing_parents[:10]:  # Log first 10
                logger.debug(f"  - {clone_parent}")
            if len(missing_parents) > 10:
                logger.debug(f"  ... and {len(missing_parents) - 10} more")

    def _apply_favorite_threshold(self, entries: Dict[str, GameEntry], threshold: float):
        """Apply favorite flag based on rating threshold.
        
        Args:
            entries: Dictionary of GameEntry objects to update
            threshold: Minimum rating to mark as favorite
        """
        favorites_set = 0
        
        for entry in entries.values():
            if entry.rating is not None:
                if entry.rating >= threshold:
                    entry.favorite = True
                    favorites_set += 1
        
        if favorites_set:
            logger.info(f"Marked {favorites_set} games as favorites (rating >= {threshold})")
