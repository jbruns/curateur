"""
Workflow evaluator for ROM processing decisions.

Centralizes decision logic for determining workflow actions based on
configuration and ROM state (hash comparison, gamelist presence, etc.).
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Any, Optional, List

from curateur.gamelist.game_entry import GameEntry
from curateur.scanner.rom_types import ROMInfo, ROMType
from curateur.media.media_types import to_singular
from curateur.tools.organize_roms import split_base_and_disc
from curateur.config.es_systems import SystemDefinition

logger = logging.getLogger(__name__)


@dataclass
class WorkflowDecision:
    """
    Decision about what actions to take for a ROM.
    
    Attributes:
        fetch_metadata: Whether to fetch metadata from API
        update_metadata: Whether to update metadata fields in gamelist
        media_to_download: List of singular media types to download
        media_to_validate: List of singular media types to hash-validate
        clean_disabled_media: Whether to clean up disabled media types
        skip_reason: Reason for skipping (None if not skipped)
    """
    fetch_metadata: bool = False
    update_metadata: bool = False
    media_to_download: List[str] = field(default_factory=list)
    media_to_validate: List[str] = field(default_factory=list)
    clean_disabled_media: bool = False
    skip_reason: Optional[str] = None


class WorkflowEvaluator:
    """
    Evaluates ROMs to determine workflow actions.
    
    Centralizes all decision logic based on scrape_mode, hash comparison,
    and configuration settings.
    """
    
    def __init__(self, config: Dict[str, Any], cache=None):
        """
        Initialize evaluator with configuration.
        
        Args:
            config: Configuration dictionary
            cache: Optional APICache instance for media hash lookups
        """
        self.config = config
        self.scraping_config = config.get('scraping', {})
        self.media_config = config.get('media', {})
        self.runtime_config = config.get('runtime', {})
        self.cache = cache
        
        
        # Get scrape_mode setting
        self.scrape_mode = self.scraping_config.get('scrape_mode', 'changed')
        self.clean_mismatched_media = self.media_config.get('clean_mismatched_media', False)
        self.hash_algorithm = self.runtime_config.get('hash_algorithm', 'crc32')
        self.validation_mode = self.media_config.get('validation_mode', 'disabled')

        # Get disc filtering setting
        self.filter_non_disc1 = self.scraping_config.get('filter_non_disc1', False)
        
        # Media types (convert to singular for consistency)
        self.enabled_media_types = self._convert_to_singular(
            self.media_config.get('media_types', [])
        )
        
        
        logger.debug(
            f"WorkflowEvaluator initialized: scrape_mode={self.scrape_mode}, "
            f"validation_mode={self.validation_mode}, hash_algorithm={self.hash_algorithm}"
        )
    
    def _convert_to_singular(self, plural_types: List[str]) -> List[str]:
        """Convert plural media type list to singular forms."""
        singular_types = []
        for plural_type in plural_types:
            try:
                singular_types.append(to_singular(plural_type))
            except ValueError:
                logger.warning(f"Unknown media type: {plural_type}")
        return singular_types

    def _should_filter_disc(
        self,
        rom_info: ROMInfo,
        system: SystemDefinition
    ) -> tuple[bool, Optional[str]]:
        """
        Check if ROM should be filtered due to disc number.

        Args:
            rom_info: ROM information
            system: System definition

        Returns:
            Tuple of (should_filter: bool, skip_reason: Optional[str])
        """
        # Only apply filtering if enabled in config
        if not self.filter_non_disc1:
            return False, None

        # Don't filter M3U playlists themselves
        if rom_info.rom_type == ROMType.M3U_PLAYLIST:
            return False, None

        # Don't filter on systems that support M3U (they should use playlists)
        if system.supports_m3u():
            return False, None

        # Extract disc number from filename/basename
        # For DISC_SUBDIR: rom_info.filename is directory name (e.g., "Game (Disc 2).cue")
        # For STANDARD: rom_info.filename is the file (e.g., "Game (Disc 2).bin")
        filename_to_check = rom_info.basename or rom_info.filename
        base_name, disc_number = split_base_and_disc(
            Path(filename_to_check).stem
        )

        # If no disc number detected, don't filter (might be single-disc game)
        if disc_number is None:
            return False, None

        # Filter if disc number > 1
        if disc_number > 1:
            reason = (
                f"filter_non_disc1 enabled; system '{system.name}' doesn't support M3U; "
                f"disc {disc_number} > 1"
            )
            return True, reason

        # Disc 1 or first disc - process normally
        return False, None

    def evaluate_rom(
        self,
        rom_info: ROMInfo,
        gamelist_entry: Optional[GameEntry],
        rom_hash: Optional[str],
        system: SystemDefinition
    ) -> WorkflowDecision:
        """
        Evaluate a ROM to determine workflow actions.

        Args:
            rom_info: Information about the ROM file
            gamelist_entry: Existing gamelist entry (None if not in gamelist)
            rom_hash: Calculated hash of the ROM file
            system: System definition for the ROM

        Returns:
            WorkflowDecision with actions to take
        """
        decision = WorkflowDecision()

        # Check disc filtering (before any other processing)
        should_filter, filter_reason = self._should_filter_disc(rom_info, system)
        if should_filter:
            decision.skip_reason = filter_reason
            logger.debug(f"Filtering {rom_info.filename}: {filter_reason}")
            return decision

        # Step 1: Check scrape_mode for skip condition
        if self.scrape_mode == 'skip':
            if gamelist_entry is not None and rom_info.path.exists():
                decision.skip_reason = "scrape_mode is 'skip'; ROM exists in gamelist"
                logger.info(
                    f"Skipping {rom_info.filename}: {decision.skip_reason}"
                )
                return decision

        # Step 1b: For new_only mode, skip existing ROMs before hash check
        if self.scrape_mode == 'new_only':
            if gamelist_entry is not None:
                decision.skip_reason = "scrape_mode is 'new_only'; ROM exists in gamelist"
                logger.debug(
                    f"Skipping {rom_info.filename}: {decision.skip_reason}"
                )
                return decision

        # Step 2: Compare ROM hash with gamelist hash
        hash_matches = self._check_hash_match(rom_hash, gamelist_entry)
        
        # Step 3: Determine if we need to fetch metadata based on scrape_mode
        if self.scrape_mode == 'force':
            # Force: Always fetch and update metadata
            decision.fetch_metadata = True
            decision.update_metadata = True
            
        elif self.scrape_mode == 'changed':
            if gamelist_entry is None:
                # ROM not in gamelist - full scrape
                decision.fetch_metadata = True
                decision.update_metadata = True
                
            elif not hash_matches:
                # ROM changed - full scrape
                decision.fetch_metadata = True
                decision.update_metadata = True
                logger.debug(
                    f"ROM hash changed for {rom_info.filename}: "
                    f"stored={self._get_stored_hash(gamelist_entry)}, "
                    f"calculated={rom_hash}"
                )
                
            else:
                # Hash matches - ROM unchanged
                # Still need to check media if validation is enabled
                if self.validation_mode != 'disabled':
                    logger.debug(
                        f"ROM unchanged but media validation enabled for {rom_info.filename}"
                    )
                    # Don't fetch new metadata, but validate existing media
                    decision.fetch_metadata = False
                    decision.update_metadata = False
                    # Media operations will be determined below
                else:
                    # No validation - skip entirely
                    decision.skip_reason = "ROM hash matches; scrape_mode is 'changed'"
                    logger.info(
                        f"Skipping {rom_info.filename}: {decision.skip_reason}"
                    )
                    return decision

        elif self.scrape_mode == 'new_only':
            # ROM not in gamelist - full scrape
            # (existing ROMs already handled in Step 1b)
            decision.fetch_metadata = True
            decision.update_metadata = True

        elif self.scrape_mode == 'skip':
            # Skip mode: Only validate media, never fetch metadata
            if gamelist_entry is None:
                # ROM not in gamelist - skip entirely (can't validate without entry)
                decision.skip_reason = "scrape_mode is 'skip'; ROM not in gamelist"
                logger.debug(
                    f"Skipping {rom_info.filename}: {decision.skip_reason}"
                )
                return decision
            else:
                # ROM exists - validate media only (no metadata operations)
                if self.validation_mode == 'disabled':
                    decision.skip_reason = "scrape_mode is 'skip' but validation_mode is 'disabled'"
                    logger.info(
                        f"Skipping {rom_info.filename}: {decision.skip_reason}"
                    )
                    return decision
                else:
                    logger.debug(
                        f"Skip mode: validating media only for {rom_info.filename}"
                    )
                    decision.fetch_metadata = False
                    decision.update_metadata = False
                    # Media operations will be determined below
        
        # Step 4: Determine media operations
        # Do this even if not fetching metadata (for validation-only scenarios)
        if decision.fetch_metadata or self.validation_mode != 'disabled':
            decision.media_to_download, decision.media_to_validate = \
                self._determine_media_operations(gamelist_entry, hash_matches, rom_hash)
            
            # Set cleanup flag
            decision.clean_disabled_media = self.clean_mismatched_media
        
        logger.debug(
            f"Decision for {rom_info.filename}: "
            f"fetch_metadata={decision.fetch_metadata}, "
            f"update_metadata={decision.update_metadata}, "
            f"media_to_download={len(decision.media_to_download)}, "
            f"media_to_validate={len(decision.media_to_validate)}"
        )
        
        return decision
    
    def _check_hash_match(
        self,
        calculated_hash: Optional[str],
        gamelist_entry: Optional[GameEntry]
    ) -> bool:
        """
        Check if calculated hash matches stored hash in cache.
        
        Args:
            calculated_hash: Hash calculated from ROM file
            gamelist_entry: Gamelist entry (for reference, not used for hash)
        
        Returns:
            True if ROM hash exists in cache (indicating ROM is unchanged), False otherwise
        """
        if calculated_hash is None:
            # No hash calculated (file too large or error)
            return False
        
        if not self.cache:
            # No cache available - assume ROM changed
            return False
        
        # Check if this ROM hash exists in the cache
        # If it exists, the ROM is unchanged and we have metadata cached
        cached_data = self.cache.get(calculated_hash)
        return cached_data is not None
    
    def _get_stored_hash(self, gamelist_entry: Optional[GameEntry]) -> Optional[str]:
        """
        Extract stored hash from gamelist entry.
        
        NOTE: Deprecated - hashes now stored in cache, not gamelist.xml.
        
        Args:
            gamelist_entry: Gamelist entry
        
        Returns:
            None (hashes no longer in gamelist)
        """
        return None
    
    def _determine_media_operations(
        self,
        gamelist_entry: Optional[GameEntry],
        hash_matches: bool,
        rom_hash: Optional[str]
    ) -> tuple[List[str], List[str]]:
        """
        Determine which media to download and which to validate.
        
        Args:
            gamelist_entry: Existing gamelist entry (None if not in gamelist)
            hash_matches: Whether ROM hash matches
            rom_hash: ROM hash for cache lookup
        
        Returns:
            Tuple of (media_to_download, media_to_validate)
        """
        media_to_download = []
        media_to_validate = []
        
        if self.validation_mode == 'disabled':
            # Validation disabled - only download missing media
            if gamelist_entry is None or not hash_matches:
                # New ROM or changed ROM - check which media already exists
                # Even with validation disabled, we should skip existing files
                stored_media_hashes = self._get_stored_media_hashes(rom_hash)

                for media_type in self.enabled_media_types:
                    if media_type not in stored_media_hashes:
                        # Media doesn't exist in cache - needs download
                        media_to_download.append(media_type)
                    # If media exists in cache, skip it (validation disabled, so we trust it)
            # For existing unchanged ROMs, skip existing media (no validation)
            return media_to_download, media_to_validate
        
        # Validation enabled (normal or strict)
        if gamelist_entry is None or not hash_matches:
            # New ROM or changed ROM - but we can still validate existing media
            # against fresh API data if validation is enabled
            # Note: We don't have API response yet, so orchestrator will need to
            # handle validation after fetching metadata. For now, queue all for download
            # but orchestrator can skip downloads for media that validates successfully.
            media_to_download = self.enabled_media_types.copy()
            return media_to_download, media_to_validate
        
        # ROM unchanged and validation enabled - validate existing media
        # and redownload if validation fails
        stored_media_hashes = self._get_stored_media_hashes(rom_hash)
        
        for media_type in self.enabled_media_types:
            if media_type in stored_media_hashes:
                # Media exists in cache - add to validation list
                media_to_validate.append(media_type)
            else:
                # Media missing from cache - download
                media_to_download.append(media_type)
        
        return media_to_download, media_to_validate
    
    def _get_stored_media_hashes(self, rom_hash: Optional[str]) -> Dict[str, str]:
        """
        Get stored media hashes from cache.
        
        Args:
            rom_hash: ROM hash to look up in cache
        
        Returns:
            Dict of media type (singular) -> hash from cache
        """
        if not self.cache or not rom_hash:
            return {}
        
        media_hashes = {}
        for media_type in self.enabled_media_types:
            media_hash = self.cache.get_media_hash(rom_hash, media_type)
            if media_hash:
                media_hashes[media_type] = media_hash
        
        return media_hashes
    
    def should_clean_media(self, media_type: str) -> bool:
        """
        Check if a media type should be cleaned up.
        
        Args:
            media_type: Singular media type name
        
        Returns:
            True if media should be removed (not in enabled types)
        """
        return (
            self.clean_mismatched_media and
            media_type not in self.enabled_media_types
        )
