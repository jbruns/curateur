"""
Metadata Merger - Intelligent merging of API data with user edits

Preserves user-editable fields while updating scraper-managed fields.
Implements field categorization and merge strategies.
"""

from typing import Dict, List, Optional, Set, NamedTuple
import logging

logger = logging.getLogger(__name__)


class MergeResult(NamedTuple):
    """Result of metadata merge operation"""
    merged_data: dict
    preserved_fields: List[str]
    updated_fields: List[str]
    conflicts: List[str]


class MetadataMerger:
    """
    Merges API response data with existing gamelist metadata
    
    Field Categories:
    - User-editable: favorite, playcount, lastplayed, hidden, custom fields
    - Scraper-managed: name, desc, rating, releasedate, developer, publisher, 
                       genre, players, media paths, hash
    - Protected: id (ScreenScraper game ID)
    
    Merge Strategy:
    1. Preserve all user-editable fields from existing entry
    2. Update scraper-managed fields from API response
    3. Keep protected fields unchanged
    4. Merge custom/unknown fields (prefer existing)
    """
    
    # Field categorization
    USER_EDITABLE_FIELDS = {
        'favorite', 'playcount', 'lastplayed', 'hidden',
        'kidgame', 'manual'  # ES-DE user-controllable fields
    }
    
    SCRAPER_MANAGED_FIELDS = {
        'name', 'desc', 'rating', 'releasedate', 'developer',
        'publisher', 'genre', 'players', 'hash',
        # Media paths
        'image', 'thumbnail', 'marquee', 'video',
        'fanart', 'boxart', 'boxback', 'titlescreen',
        'cartridge', 'mix', 'manual'
    }
    
    PROTECTED_FIELDS = {
        'id',  # ScreenScraper game ID
        'source',  # Source scraper name
    }
    
    ALWAYS_KEEP_FIELDS = {
        'path',  # ROM file path - never changes
    }
    
    def __init__(self, config: dict):
        """
        Initialize metadata merger
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.merge_strategy = config.get('scraping', {}).get(
            'merge_strategy', 'preserve_user_edits'
        )
        logger.info(f"Metadata Merger initialized (strategy={self.merge_strategy})")
    
    def merge_metadata(self, existing_entry: dict, api_data: dict) -> MergeResult:
        """
        Merge API data with existing gamelist entry
        
        Args:
            existing_entry: Existing metadata from gamelist.xml
            api_data: New metadata from API response
        
        Returns:
            MergeResult with merged data and change tracking
        """
        merged = {}
        preserved_fields = []
        updated_fields = []
        conflicts = []
        
        # Start with existing entry as base
        all_fields = set(existing_entry.keys()) | set(api_data.keys())
        
        for field in all_fields:
            existing_value = existing_entry.get(field)
            api_value = api_data.get(field)
            
            # Always keep fields
            if field in self.ALWAYS_KEEP_FIELDS:
                merged[field] = existing_value
                preserved_fields.append(field)
                continue
            
            # Protected fields (never update)
            if field in self.PROTECTED_FIELDS:
                if existing_value is not None:
                    merged[field] = existing_value
                    preserved_fields.append(field)
                elif api_value is not None:
                    merged[field] = api_value
                    updated_fields.append(field)
                continue
            
            # User-editable fields (always preserve)
            if field in self.USER_EDITABLE_FIELDS:
                if existing_value is not None:
                    merged[field] = existing_value
                    preserved_fields.append(field)
                elif api_value is not None:
                    merged[field] = api_value
                    updated_fields.append(field)
                continue
            
            # Scraper-managed fields (update from API)
            if field in self.SCRAPER_MANAGED_FIELDS:
                if api_value is not None:
                    # Check for conflicts (both have values but different)
                    if existing_value is not None and existing_value != api_value:
                        conflicts.append(field)
                    merged[field] = api_value
                    updated_fields.append(field)
                elif existing_value is not None:
                    # Keep existing if no API value
                    merged[field] = existing_value
                    preserved_fields.append(field)
                continue
            
            # Unknown/custom fields (preserve existing, use API as fallback)
            if existing_value is not None:
                merged[field] = existing_value
                preserved_fields.append(field)
            elif api_value is not None:
                merged[field] = api_value
                updated_fields.append(field)
        
        logger.debug(
            f"Merge complete: {len(preserved_fields)} preserved, "
            f"{len(updated_fields)} updated, {len(conflicts)} conflicts"
        )
        
        return MergeResult(
            merged_data=merged,
            preserved_fields=preserved_fields,
            updated_fields=updated_fields,
            conflicts=conflicts
        )
    
    def is_user_edited(self, existing_entry: dict, original_scraped_entry: dict) -> bool:
        """
        Detect if user has edited any fields
        
        Args:
            existing_entry: Current gamelist entry
            original_scraped_entry: Original scraped entry (from last scrape)
        
        Returns:
            bool: True if user-editable fields differ from original
        """
        for field in self.USER_EDITABLE_FIELDS:
            existing_value = existing_entry.get(field)
            original_value = original_scraped_entry.get(field)
            
            # Field added by user
            if existing_value is not None and original_value is None:
                return True
            
            # Field modified by user
            if existing_value != original_value:
                return True
        
        return False
    
    def merge_batch(self, existing_entries: Dict[str, dict],
                   api_responses: Dict[str, dict]) -> Dict[str, MergeResult]:
        """
        Merge multiple entries in batch
        
        Args:
            existing_entries: Dict mapping basename to existing entry
            api_responses: Dict mapping basename to API response
        
        Returns:
            Dict mapping basename to MergeResult
        """
        results = {}
        
        for basename in api_responses.keys():
            existing = existing_entries.get(basename, {})
            api_data = api_responses[basename]
            
            result = self.merge_metadata(existing, api_data)
            results[basename] = result
        
        # Log summary
        total_preserved = sum(len(r.preserved_fields) for r in results.values())
        total_updated = sum(len(r.updated_fields) for r in results.values())
        total_conflicts = sum(len(r.conflicts) for r in results.values())
        
        logger.info(
            f"Batch merge: {len(results)} entries, "
            f"{total_updated} fields updated, {total_preserved} preserved, "
            f"{total_conflicts} conflicts"
        )
        
        return results
    
    def get_field_category(self, field_name: str) -> str:
        """
        Get category for a field name
        
        Returns: 'user_editable' | 'scraper_managed' | 'protected' | 'custom'
        """
        if field_name in self.USER_EDITABLE_FIELDS:
            return 'user_editable'
        elif field_name in self.SCRAPER_MANAGED_FIELDS:
            return 'scraper_managed'
        elif field_name in self.PROTECTED_FIELDS:
            return 'protected'
        else:
            return 'custom'
    
    def should_update_field(self, field_name: str, has_existing_value: bool,
                           has_api_value: bool) -> bool:
        """
        Determine if a field should be updated based on merge policy
        
        Args:
            field_name: Name of field
            has_existing_value: Whether existing entry has this field
            has_api_value: Whether API response has this field
        
        Returns:
            bool: True if field should be updated
        """
        category = self.get_field_category(field_name)
        
        # User-editable: never update if exists
        if category == 'user_editable' and has_existing_value:
            return False
        
        # Scraper-managed: update if API has value
        if category == 'scraper_managed' and has_api_value:
            return True
        
        # Protected: never update if exists
        if category == 'protected' and has_existing_value:
            return False
        
        # Custom: update only if no existing value
        if category == 'custom':
            return has_api_value and not has_existing_value
        
        return False
