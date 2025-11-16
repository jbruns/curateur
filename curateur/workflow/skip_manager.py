"""
Skip Manager - Decision engine for skip/update modes

Implements the Skip Mode Decision Table to determine how each ROM should be processed
based on existing gamelist entries and media files.
"""

from enum import Enum
from pathlib import Path
from typing import Tuple, List, Optional
import logging

logger = logging.getLogger(__name__)


class SkipAction(Enum):
    """Skip mode actions"""
    SKIP = "skip"
    FULL_SCRAPE = "full_scrape"
    MEDIA_ONLY = "media_only"
    UPDATE = "update"
    UPDATE_AND_VERIFY = "update_and_verify"


class SkipManager:
    """
    Manages skip/update decisions for ROMs based on existing gamelist and media
    
    Implements decision table logic:
    - Full scrape: ROM not in gamelist or missing metadata
    - Media only: ROM in gamelist, metadata present, some media missing
      (still requires API call to get media URLs, but reuses metadata)
    - Skip: ROM in gamelist with complete metadata and all enabled media
    - Update: ROM in gamelist but update_mode enabled (verify hashes)
    """
    
    def __init__(self, config: dict, gamelist_parser, media_checker):
        """
        Initialize skip manager
        
        Args:
            config: Configuration dictionary
            gamelist_parser: Parser for reading existing gamelist entries
            media_checker: Checker for media file presence
        """
        self.config = config
        self.gamelist_parser = gamelist_parser
        self.media_checker = media_checker
        self.skip_enabled = config.get('scraping', {}).get('skip_scraped', True)
        self.update_mode = config.get('scraping', {}).get('update_mode', False)
        
        logger.info(f"Skip Manager initialized (skip_enabled={self.skip_enabled}, update_mode={self.update_mode})")
    
    def determine_action(self, rom_info: dict, system_name: str) -> Tuple[SkipAction, List[str], bool]:
        """
        Determine processing action for a ROM
        
        Args:
            rom_info: ROM information dict with 'basename', 'filename', etc.
            system_name: System name (e.g., 'nes', 'psx')
        
        Returns:
            tuple: (action, media_types_to_download, reuse_metadata)
                action: SkipAction enum value
                media_types_to_download: list of media types to process
                reuse_metadata: bool - True if existing metadata should be kept
        """
        rom_basename = rom_info.get('basename')
        
        # Get enabled media types from config
        enabled_media_types = self.config.get('scraping', {}).get('media_types', [])
        
        # Check if ROM exists in gamelist
        gamelist_entry = self.gamelist_parser.find_entry(rom_basename, system_name)
        
        # ROM not in gamelist -> full scrape
        if gamelist_entry is None:
            logger.debug(f"{rom_basename}: Not in gamelist -> full_scrape")
            return (SkipAction.FULL_SCRAPE, enabled_media_types, False)
        
        # Check if metadata is present
        has_metadata = self._has_complete_metadata(gamelist_entry)
        
        # No metadata -> full scrape
        if not has_metadata:
            logger.debug(f"{rom_basename}: Missing metadata -> full_scrape")
            return (SkipAction.FULL_SCRAPE, enabled_media_types, False)
        
        # Update mode always queries API and may update
        if self.update_mode:
            logger.debug(f"{rom_basename}: Update mode -> update")
            return (SkipAction.UPDATE, enabled_media_types, False)
        
        # If skip is disabled, always do full scrape for existing ROMs
        if not self.skip_enabled:
            logger.debug(f"{rom_basename}: Skip disabled -> full_scrape")
            return (SkipAction.FULL_SCRAPE, enabled_media_types, False)
        
        # Check media completeness
        present_media, missing_media = self.check_media_completeness(
            rom_basename, system_name, enabled_media_types
        )
        
        # All media present and skip enabled -> skip
        if not missing_media:
            logger.debug(f"{rom_basename}: Complete ({len(present_media)}/{len(enabled_media_types)} media) -> skip")
            return (SkipAction.SKIP, [], False)
        
        # Some media missing -> media_only (API call but preserve metadata)
        if missing_media:
            logger.debug(f"{rom_basename}: Missing {len(missing_media)} media types -> media_only")
            return (SkipAction.MEDIA_ONLY, missing_media, True)
        
        # Default: full scrape
        logger.debug(f"{rom_basename}: Default -> full_scrape")
        return (SkipAction.FULL_SCRAPE, enabled_media_types, False)
    
    def check_media_completeness(self, rom_basename: str, system_name: str, 
                                 enabled_media_types: List[str]) -> Tuple[List[str], List[str]]:
        """
        Check which enabled media types are present for a ROM
        
        Args:
            rom_basename: ROM basename (without path)
            system_name: System name
            enabled_media_types: List of enabled media types from config
        
        Returns:
            tuple: (present_media_types, missing_media_types)
        """
        present = []
        missing = []
        
        for media_type in enabled_media_types:
            if self.media_checker.media_exists(rom_basename, system_name, media_type):
                present.append(media_type)
            else:
                missing.append(media_type)
        
        return (present, missing)
    
    def should_clean_mismatched_media(self) -> bool:
        """
        Check if media type cleanup is enabled
        
        Returns:
            bool: True if cleanup should be performed
        """
        return self.config.get('scraping', {}).get('clean_mismatched_media', False)
    
    def _has_complete_metadata(self, gamelist_entry: dict) -> bool:
        """
        Check if gamelist entry has complete metadata
        
        Args:
            gamelist_entry: Gamelist entry dict
        
        Returns:
            bool: True if metadata is complete
        """
        # Check for required fields
        required_fields = ['name', 'path']
        
        for field in required_fields:
            if not gamelist_entry.get(field):
                return False
        
        return True
