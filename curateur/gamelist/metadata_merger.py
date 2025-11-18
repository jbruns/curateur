"""
Metadata Merger - Intelligent merging of API data with user edits

Preserves user-editable fields while updating scraper-managed fields.
Implements field categorization and merge strategies.
"""

from typing import List, Set
from dataclasses import dataclass, replace
import logging

from .game_entry import GameEntry

logger = logging.getLogger(__name__)


@dataclass
class MergeResult:
    """Result of metadata merge operation"""
    merged_entry: GameEntry
    preserved_fields: Set[str]
    updated_fields: Set[str]
    conflicts: Set[str]


class MetadataMerger:
    """
    Merges API response data with existing gamelist metadata
    
    Field Categories:
    - User-editable: favorite, playcount, lastplayed, hidden, kidgame
    - Scraper-managed: name, desc, rating, releasedate, developer, publisher, 
                       genre, players, media paths
    - Provider: screenscraper_id
    - Required: path
    
    Merge Strategy:
    1. Preserve all user-editable fields from existing entry
    2. Update scraper-managed fields from API response
    3. Keep provider fields unchanged
    4. Preserve custom/unknown fields (in extra_fields)
    """
    
    # Field categorization
    USER_FIELDS = {
        'favorite', 'playcount', 'lastplayed', 'hidden', 'kidgame'
    }
    
    SCRAPED_FIELDS = {
        'name', 'desc', 'rating', 'releasedate', 'developer',
        'publisher', 'genre', 'players'
    }
    
    PROVIDER_FIELDS = {
        'screenscraper_id'
    }
    
    REQUIRED_FIELDS = {
        'path'
    }
    
    def __init__(self, merge_strategy: str = 'preserve_user'):
        """
        Initialize metadata merger
        
        Args:
            merge_strategy: Merge strategy ('preserve_user', 'update_all', etc.)
        """
        self.merge_strategy = merge_strategy
        logger.info(f"Metadata Merger initialized (strategy={self.merge_strategy})")
    
    def merge_entries(self, existing: GameEntry, scraped: GameEntry) -> MergeResult:
        """
        Merge scraped data with existing gamelist entry
        
        Args:
            existing: Existing GameEntry from gamelist.xml
            scraped: Newly scraped GameEntry from API
        
        Returns:
            MergeResult with merged entry and change tracking
        """
        preserved_fields = set()
        updated_fields = set()
        conflicts = set()
        
        # Build merged entry dict
        merged_data = {}
        
        # Path is always from existing (required field)
        merged_data['path'] = existing.path
        preserved_fields.add('path')
        
        # Process all fields
        for field_name in dir(existing):
            # Skip private/magic methods and non-field attributes
            if field_name.startswith('_') or field_name in ('from_api_response',):
                continue
            
            # Skip methods
            attr = getattr(existing, field_name, None)
            if callable(attr):
                continue
            
            # Already handled path
            if field_name == 'path':
                continue
            
            existing_value = getattr(existing, field_name, None)
            scraped_value = getattr(scraped, field_name, None)
            
            category = self._get_field_category(field_name)
            
            if category == 'user':
                # Preserve user fields from existing
                merged_data[field_name] = existing_value
                if existing_value is not None or (field_name in self.USER_FIELDS and existing_value is not None):
                    preserved_fields.add(field_name)
            elif category == 'scraped':
                # Update scraped fields from new data
                if scraped_value is not None:
                    if existing_value is not None and existing_value != scraped_value:
                        conflicts.add(field_name)
                    merged_data[field_name] = scraped_value
                    updated_fields.add(field_name)
                elif existing_value is not None:
                    # Keep existing if no scraped value
                    merged_data[field_name] = existing_value
                    preserved_fields.add(field_name)
            elif category == 'provider':
                # Keep provider fields (don't overwrite)
                if existing_value is not None:
                    merged_data[field_name] = existing_value
                    preserved_fields.add(field_name)
                elif scraped_value is not None:
                    merged_data[field_name] = scraped_value
                    updated_fields.add(field_name)
            else:
                # Unknown fields - preserve existing
                if existing_value is not None:
                    merged_data[field_name] = existing_value
                    preserved_fields.add(field_name)
                elif scraped_value is not None:
                    merged_data[field_name] = scraped_value
                    updated_fields.add(field_name)
        
        # Handle extra_fields specially
        if hasattr(existing, 'extra_fields') and existing.extra_fields:
            merged_data['extra_fields'] = existing.extra_fields.copy()
            preserved_fields.add('extra_fields')
        elif hasattr(scraped, 'extra_fields') and scraped.extra_fields:
            merged_data['extra_fields'] = scraped.extra_fields.copy()
        else:
            merged_data['extra_fields'] = {}
        
        # Create merged GameEntry
        merged_entry = GameEntry(**merged_data)
        
        logger.debug(
            f"Merge complete: {len(preserved_fields)} preserved, "
            f"{len(updated_fields)} updated, {len(conflicts)} conflicts"
        )
        
        return MergeResult(
            merged_entry=merged_entry,
            preserved_fields=preserved_fields,
            updated_fields=updated_fields,
            conflicts=conflicts
        )
        
    
    def batch_merge(
        self,
        existing_list: List[GameEntry],
        scraped_list: List[GameEntry]
    ) -> List[MergeResult]:
        """
        Merge multiple entries in batch
        
        Args:
            existing_list: List of existing GameEntry objects
            scraped_list: List of newly scraped GameEntry objects
        
        Returns:
            List of MergeResult objects
        """
        # Build lookup by path
        existing_by_path = {entry.path: entry for entry in existing_list}
        
        results = []
        for scraped in scraped_list:
            existing = existing_by_path.get(scraped.path)
            if existing:
                result = self.merge_entries(existing, scraped)
                results.append(result)
        
        logger.info(f"Batch merge: {len(results)} entries merged")
        
        return results
    
    def _get_field_category(self, field_name: str) -> str:
        """
        Get category for a field name
        
        Returns: 'user' | 'scraped' | 'provider' | 'required' | 'unknown'
        """
        if field_name in self.USER_FIELDS:
            return 'user'
        elif field_name in self.SCRAPED_FIELDS:
            return 'scraped'
        elif field_name in self.PROVIDER_FIELDS:
            return 'provider'
        elif field_name in self.REQUIRED_FIELDS:
            return 'required'
        else:
            return 'unknown'
    
    def _detect_user_edits(self, existing: GameEntry, scraped: GameEntry) -> Set[str]:
        """
        Detect which fields user has edited
        
        Args:
            existing: Existing GameEntry
            scraped: Newly scraped GameEntry
        
        Returns:
            Set of field names that appear to be user-edited
        """
        edited = set()
        
        # User fields are always considered user-edited if they have values
        for field in self.USER_FIELDS:
            existing_value = getattr(existing, field, None)
            if existing_value is not None:
                # Check defaults
                if field == 'favorite' and existing_value != False:
                    edited.add(field)
                elif field == 'playcount' and existing_value != 0:
                    edited.add(field)
                elif field == 'hidden' and existing_value != False:
                    edited.add(field)
                elif field == 'lastplayed' and existing_value:
                    edited.add(field)
        
        return edited
    
    def _determine_update_policy(self, field_name: str) -> str:
        """
        Determine update policy for a field
        
        Returns: 'preserve' | 'update'
        """
        category = self._get_field_category(field_name)
        
        if category == 'user' or category == 'provider':
            return 'preserve'
        elif category == 'scraped':
            return 'update'
        elif category == 'required':
            return 'preserve'
        else:
            return 'preserve'  # Unknown fields preserved by default

