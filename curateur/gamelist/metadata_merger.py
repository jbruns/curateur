"""
Metadata Merger - Intelligent merging of API data with user edits

Implements three merge strategies:
- preserve_user_edits: Truly conservative, changes nothing
- refresh_metadata: Update only curateur-managed fields
- reset_all: Complete clean slate (API data + path only)
"""

from typing import List, Set, Optional
from dataclasses import dataclass, replace
import logging
from copy import deepcopy

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
                       genre, players
    - Provider: screenscraper_id
    - Required: path

    Merge Strategies:
    1. preserve_user_edits: Keep ALL existing fields, only update path (most conservative)
    2. refresh_metadata: Update SCRAPED_FIELDS only, preserve user and provider fields
    3. reset_all: Complete reset - use API data + path only (nuclear option)
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

    def __init__(
        self,
        merge_strategy: str = 'preserve_user_edits',
        auto_favorite_enabled: bool = False,
        auto_favorite_threshold: float = 0.9
    ):
        """
        Initialize metadata merger

        Args:
            merge_strategy: Merge strategy ('preserve_user_edits', 'refresh_metadata', 'reset_all')
            auto_favorite_enabled: Enable automatic favorite flag for highly-rated games
            auto_favorite_threshold: Rating threshold (0.0-1.0) for auto-favorite
        """
        self.merge_strategy = merge_strategy
        self.auto_favorite_enabled = auto_favorite_enabled
        self.auto_favorite_threshold = auto_favorite_threshold
        logger.debug(
            f"Metadata Merger initialized (strategy={self.merge_strategy}, "
            f"auto_favorite={self.auto_favorite_enabled}, threshold={self.auto_favorite_threshold})"
        )

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

        # Apply merge strategy
        if self.merge_strategy == 'preserve_user_edits':
            # Most conservative: keep ALL existing fields, only update path
            merged_data.update(
                self._merge_preserve_user_edits(
                    existing,
                    scraped,
                    preserved_fields,
                    updated_fields,
                    conflicts
                )
            )
        elif self.merge_strategy == 'refresh_metadata':
            # Balanced: update only SCRAPED_FIELDS, preserve user and provider fields
            merged_data.update(
                self._merge_refresh_metadata(
                    existing,
                    scraped,
                    preserved_fields,
                    updated_fields,
                    conflicts
                )
            )
        elif self.merge_strategy == 'reset_all':
            # Nuclear: complete reset to API data + path only
            merged_data.update(self._merge_reset_all(existing, scraped, preserved_fields, updated_fields, conflicts))
        else:
            # Default to preserve_user_edits
            logger.warning(f"Unknown merge strategy '{self.merge_strategy}', using 'preserve_user_edits'")
            merged_data.update(
                self._merge_preserve_user_edits(
                    existing,
                    scraped,
                    preserved_fields,
                    updated_fields,
                    conflicts
                )
            )

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

    def merge_entry_lists(
        self,
        existing_entries: List[GameEntry],
        new_entries: List[GameEntry]
    ) -> List[GameEntry]:
        """
        Merge lists of entries for gamelist generation.

        Args:
            existing_entries: Entries from existing gamelist.xml
            new_entries: Newly scraped entries

        Returns:
            Merged list of GameEntry objects

        Logic:
        - For ROMs in both lists: Update metadata using merge_entries()
        - For ROMs only in new list: Add as new entries (with auto-favorite)
        - For ROMs only in existing list: Keep (user may have manual entries)
        """
        # Build lookup by path
        existing_by_path = {entry.path: entry for entry in existing_entries}
        new_by_path = {entry.path: entry for entry in new_entries}

        merged = []
        processed_paths = set()

        # Process new entries (update or add)
        for path, new_entry in new_by_path.items():
            if path in existing_by_path:
                # Merge: update metadata using strategy-aware merge
                merge_result = self.merge_entries(existing_by_path[path], new_entry)
                merged.append(merge_result.merged_entry)
            else:
                # New entry - apply auto-favorite if strategy allows
                if self.merge_strategy != 'preserve_user_edits' and self.auto_favorite_enabled:
                    if new_entry.rating is not None and new_entry.rating >= self.auto_favorite_threshold:
                        new_entry.favorite = True
                        logger.debug(f"Auto-favoriting new entry: {new_entry.name} (rating={new_entry.rating})")

                merged.append(new_entry)

            processed_paths.add(path)

        # Preserve existing entries not in new list
        for path, existing_entry in existing_by_path.items():
            if path not in processed_paths:
                merged.append(existing_entry)

        return merged

    def _merge_preserve_user_edits(
        self,
        existing: GameEntry,
        scraped: GameEntry,
        preserved_fields: Set[str],
        updated_fields: Set[str],
        conflicts: Set[str]
    ) -> dict:
        """
        Merge strategy: preserve ALL existing fields, make NO changes.

        This is the most conservative strategy - existing entry is untouched.
        Only path is guaranteed to be set (already handled by merge_entries).
        Preserves extra_fields dict.
        """
        merged_data = {}

        # Process all fields from existing entry
        for field_name in dir(existing):
            # Skip private/magic methods and non-field attributes
            if field_name.startswith('_') or field_name in ('from_api_response', 'path'):
                continue

            # Skip methods
            attr = getattr(existing, field_name, None)
            if callable(attr):
                continue

            existing_value = getattr(existing, field_name, None)

            # Preserve everything from existing
            if existing_value is not None:
                merged_data[field_name] = existing_value
                preserved_fields.add(field_name)

        # Preserve extra_fields
        if hasattr(existing, 'extra_fields') and existing.extra_fields:
            merged_data['extra_fields'] = deepcopy(existing.extra_fields)
            preserved_fields.add('extra_fields')
        else:
            merged_data['extra_fields'] = {}

        return merged_data

    def _merge_refresh_metadata(
        self,
        existing: GameEntry,
        scraped: GameEntry,
        preserved_fields: Set[str],
        updated_fields: Set[str],
        conflicts: Set[str]
    ) -> dict:
        """
        Merge strategy: update SCRAPED_FIELDS only, preserve user and provider fields.

        This is the balanced strategy - updates curateur-managed metadata while
        preserving user edits and provider IDs. Applies auto-favorite if enabled.
        Preserves extra_fields dict.
        """
        merged_data = {}

        # Process all fields
        for field_name in dir(existing):
            # Skip private/magic methods and non-field attributes
            if field_name.startswith('_') or field_name in ('from_api_response', 'path'):
                continue

            # Skip methods
            attr = getattr(existing, field_name, None)
            if callable(attr):
                continue

            existing_value = getattr(existing, field_name, None)
            scraped_value = getattr(scraped, field_name, None)

            category = self._get_field_category(field_name)

            if category == 'user' or category == 'provider':
                # Preserve user and provider fields from existing
                merged_data[field_name] = existing_value
                if existing_value is not None:
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
            else:
                # Unknown fields - preserve existing
                if existing_value is not None:
                    merged_data[field_name] = existing_value
                    preserved_fields.add(field_name)

        # Apply auto-favorite logic
        if self.auto_favorite_enabled:
            rating = merged_data.get('rating')
            if rating is not None:
                try:
                    rating_float = float(rating)
                    if rating_float >= self.auto_favorite_threshold:
                        merged_data['favorite'] = True
                        updated_fields.add('favorite')
                        logger.debug(f"Auto-favorite applied (rating={rating_float})")
                except (ValueError, TypeError):
                    pass

        # Preserve extra_fields
        if hasattr(existing, 'extra_fields') and existing.extra_fields:
            merged_data['extra_fields'] = deepcopy(existing.extra_fields)
            preserved_fields.add('extra_fields')
        else:
            merged_data['extra_fields'] = {}

        return merged_data

    def _merge_reset_all(
        self,
        existing: GameEntry,
        scraped: GameEntry,
        preserved_fields: Set[str],
        updated_fields: Set[str],
        conflicts: Set[str]
    ) -> dict:
        """
        Merge strategy: complete reset to API data + path only.

        This is the nuclear option - discards all existing metadata and user edits.
        Uses only scraped data. Applies auto-favorite if enabled.
        Discards extra_fields dict.
        """
        merged_data = {}

        # Use all scraped fields
        for field_name in dir(scraped):
            # Skip private/magic methods and non-field attributes
            if field_name.startswith('_') or field_name in ('from_api_response', 'path'):
                continue

            # Skip methods
            attr = getattr(scraped, field_name, None)
            if callable(attr):
                continue

            scraped_value = getattr(scraped, field_name, None)

            if scraped_value is not None:
                merged_data[field_name] = scraped_value
                updated_fields.add(field_name)

        # Apply auto-favorite logic
        if self.auto_favorite_enabled:
            rating = merged_data.get('rating')
            if rating is not None:
                try:
                    rating_float = float(rating)
                    if rating_float >= self.auto_favorite_threshold:
                        merged_data['favorite'] = True
                        updated_fields.add('favorite')
                        logger.debug(f"Auto-favorite applied (rating={rating_float})")
                except (ValueError, TypeError):
                    pass

        # Discard extra_fields in reset_all mode
        merged_data['extra_fields'] = {}

        return merged_data

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
