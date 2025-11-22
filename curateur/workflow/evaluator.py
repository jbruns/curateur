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
from curateur.scanner.rom_types import ROMInfo
from curateur.media.media_types import to_singular

logger = logging.getLogger(__name__)


@dataclass
class WorkflowDecision:
    """
    Decision about what actions to take for a ROM.
    
    Attributes:
        fetch_metadata: Whether to fetch metadata from API
        update_metadata: Whether to update metadata fields in gamelist
        update_media: Whether to process media files
        media_to_download: List of singular media types to download
        media_to_validate: List of singular media types to hash-validate
        clean_disabled_media: Whether to clean up disabled media types
        skip_reason: Reason for skipping (None if not skipped)
    """
    fetch_metadata: bool = False
    update_metadata: bool = False
    update_media: bool = False
    media_to_download: List[str] = field(default_factory=list)
    media_to_validate: List[str] = field(default_factory=list)
    clean_disabled_media: bool = False
    skip_reason: Optional[str] = None


class WorkflowEvaluator:
    """
    Evaluates ROMs to determine workflow actions.
    
    Centralizes all decision logic based on update_policy, hash comparison,
    and configuration settings.
    """
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize evaluator with configuration.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.scraping_config = config.get('scraping', {})
        
        # Extract key settings
        self.update_policy = self.scraping_config.get('update_policy', 'changed_only')
        self.update_metadata = self.scraping_config.get('update_metadata', True)
        self.update_media = self.scraping_config.get('update_media', True)
        self.clean_mismatched_media = self.scraping_config.get('clean_mismatched_media', False)
        self.hash_algorithm = self.scraping_config.get('hash_algorithm', 'crc32')
        
        # Media types (convert to singular for consistency)
        self.enabled_media_types = self._convert_to_singular(
            self.scraping_config.get('media_types', [])
        )
        
        logger.debug(
            f"WorkflowEvaluator initialized: update_policy={self.update_policy}, "
            f"update_metadata={self.update_metadata}, update_media={self.update_media}, "
            f"hash_algorithm={self.hash_algorithm}"
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
    
    def evaluate_rom(
        self,
        rom_info: ROMInfo,
        gamelist_entry: Optional[GameEntry],
        rom_hash: Optional[str]
    ) -> WorkflowDecision:
        """
        Evaluate a ROM to determine workflow actions.
        
        Args:
            rom_info: Information about the ROM file
            gamelist_entry: Existing gamelist entry (None if not in gamelist)
            rom_hash: Calculated hash of the ROM file
        
        Returns:
            WorkflowDecision with actions to take
        """
        decision = WorkflowDecision()
        
        # Step 1: Check update_policy
        if self.update_policy == 'never':
            if gamelist_entry is not None and rom_info.path.exists():
                decision.skip_reason = "update_policy is 'never'; ROM exists in gamelist"
                logger.info(
                    f"Skipping {rom_info.name}: {decision.skip_reason}"
                )
                return decision
        
        # Step 2: Compare ROM hash with gamelist hash
        hash_matches = self._check_hash_match(rom_hash, gamelist_entry)
        
        # Step 3: Determine if we need to fetch metadata
        if self.update_policy == 'always':
            # Always fetch metadata
            decision.fetch_metadata = True
            decision.update_metadata = self.update_metadata
            decision.update_media = self.update_media
            
        elif self.update_policy == 'changed_only':
            if gamelist_entry is None:
                # ROM not in gamelist - full scrape
                decision.fetch_metadata = True
                decision.update_metadata = True
                decision.update_media = True
                
            elif not hash_matches:
                # ROM changed - full scrape
                decision.fetch_metadata = True
                decision.update_metadata = True
                decision.update_media = True
                logger.debug(
                    f"ROM hash changed for {rom_info.name}: "
                    f"stored={self._get_stored_hash(gamelist_entry)}, "
                    f"calculated={rom_hash}"
                )
                
            else:
                # Hash matches - ROM unchanged
                # Check if metadata/media updates are forced
                if self.update_metadata or self.update_media:
                    decision.fetch_metadata = True
                    decision.update_metadata = self.update_metadata
                    decision.update_media = self.update_media
                else:
                    decision.skip_reason = "ROM hash matches; updates disabled"
                    logger.info(
                        f"Skipping {rom_info.name}: {decision.skip_reason}"
                    )
                    return decision
        
        # Step 4: Determine media operations
        if decision.fetch_metadata:
            decision.media_to_download, decision.media_to_validate = \
                self._determine_media_operations(gamelist_entry, hash_matches)
            
            # Set cleanup flag
            decision.clean_disabled_media = self.clean_mismatched_media
        
        logger.debug(
            f"Decision for {rom_info.name}: "
            f"fetch_metadata={decision.fetch_metadata}, "
            f"update_metadata={decision.update_metadata}, "
            f"update_media={decision.update_media}, "
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
        Check if calculated hash matches stored hash.
        
        Args:
            calculated_hash: Hash calculated from ROM file
            gamelist_entry: Gamelist entry with stored hash
        
        Returns:
            True if hashes match, False otherwise
        """
        if calculated_hash is None:
            # No hash calculated (file too large or error)
            return False
        
        if gamelist_entry is None:
            # No gamelist entry
            return False
        
        stored_hash = self._get_stored_hash(gamelist_entry)
        if stored_hash is None:
            # No stored hash
            return False
        
        # Compare (case-insensitive)
        return calculated_hash.upper() == stored_hash.upper()
    
    def _get_stored_hash(self, gamelist_entry: Optional[GameEntry]) -> Optional[str]:
        """
        Extract stored hash for configured algorithm from gamelist entry.
        
        Args:
            gamelist_entry: Gamelist entry
        
        Returns:
            Stored hash value, or None if not present
        """
        if gamelist_entry is None:
            return None
        
        # Hash structure: {'rom': {'crc32': 'ABC123', ...}, 'media': {...}}
        if not hasattr(gamelist_entry, 'hash') or gamelist_entry.hash is None:
            return None
        
        rom_hashes = gamelist_entry.hash.get('rom', {})
        return rom_hashes.get(self.hash_algorithm)
    
    def _determine_media_operations(
        self,
        gamelist_entry: Optional[GameEntry],
        hash_matches: bool
    ) -> tuple[List[str], List[str]]:
        """
        Determine which media to download and which to validate.
        
        Args:
            gamelist_entry: Existing gamelist entry (None if not in gamelist)
            hash_matches: Whether ROM hash matches
        
        Returns:
            Tuple of (media_to_download, media_to_validate)
        """
        media_to_download = []
        media_to_validate = []
        
        if not self.update_media:
            # Media updates disabled - skip all media work
            return media_to_download, media_to_validate
        
        if gamelist_entry is None or not hash_matches:
            # New ROM or changed ROM - download all enabled media types
            media_to_download = self.enabled_media_types.copy()
            return media_to_download, media_to_validate
        
        # ROM unchanged but update_media is True - validate existing media
        # and redownload if hashes don't match
        stored_media_hashes = self._get_stored_media_hashes(gamelist_entry)
        
        for media_type in self.enabled_media_types:
            if media_type in stored_media_hashes:
                # Media exists in gamelist - validate hash
                media_to_validate.append(media_type)
            else:
                # Media missing from gamelist - download
                media_to_download.append(media_type)
        
        return media_to_download, media_to_validate
    
    def _get_stored_media_hashes(self, gamelist_entry: Optional[GameEntry]) -> Dict[str, str]:
        """
        Extract stored media hashes from gamelist entry.
        
        Args:
            gamelist_entry: Gamelist entry
        
        Returns:
            Dict mapping singular media type to hash value
        """
        if gamelist_entry is None:
            return {}
        
        # Hash structure: {'rom': {...}, 'media': {'cover': 'ABC123', ...}}
        if not hasattr(gamelist_entry, 'hash') or gamelist_entry.hash is None:
            return {}
        
        return gamelist_entry.hash.get('media', {})
    
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
