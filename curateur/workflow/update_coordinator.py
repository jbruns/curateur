"""
Update Coordinator - Orchestrates selective ROM updates

Coordinates hash comparison, metadata merging, and media updates for
update mode operations.
"""

from pathlib import Path
from typing import Dict, List, Optional, NamedTuple, Set
import logging

logger = logging.getLogger(__name__)


class UpdateDecision(NamedTuple):
    """Decision on how to update a ROM"""
    rom_basename: str
    should_update_metadata: bool
    should_update_media: bool
    media_types_to_update: List[str]
    reason: str


class UpdateResult(NamedTuple):
    """Result of update operation"""
    rom_basename: str
    metadata_updated: bool
    media_updated: Dict[str, bool]  # media_type -> success
    errors: List[str]


class UpdateCoordinator:
    """
    Coordinates selective updates based on hash changes and policies
    
    Workflow:
    1. Compare ROM hashes to detect changes
    2. Determine update actions based on policy
    3. Merge metadata preserving user edits
    4. Update media selectively
    5. Track and log all changes
    
    Update Policies:
    - 'always': Update all ROMs regardless of hash
    - 'changed_only': Update only ROMs with changed hashes
    - 'metadata_only': Update metadata but not media
    - 'media_only': Update media but not metadata
    - 'never': Skip all updates (same as skip mode)
    """
    
    def __init__(self, config: dict, hash_comparator, metadata_merger):
        """
        Initialize update coordinator
        
        Args:
            config: Configuration dictionary
            hash_comparator: HashComparator instance
            metadata_merger: MetadataMerger instance
        """
        self.config = config
        self.hash_comparator = hash_comparator
        self.metadata_merger = metadata_merger
        
        self.update_policy = config.get('scraping', {}).get(
            'update_policy', 'changed_only'
        )
        self.update_metadata = config.get('scraping', {}).get(
            'update_metadata', True
        )
        self.update_media = config.get('scraping', {}).get(
            'update_media', True
        )
        
        logger.info(
            f"Update Coordinator initialized "
            f"(policy={self.update_policy}, "
            f"metadata={self.update_metadata}, media={self.update_media})"
        )
    
    def determine_update_action(self, rom_info: dict, existing_entry: dict,
                               system_name: str) -> UpdateDecision:
        """
        Determine what updates are needed for a ROM
        
        Args:
            rom_info: ROM information from scanner
            existing_entry: Existing gamelist entry
            system_name: System name
        
        Returns:
            UpdateDecision with update actions
        """
        rom_basename = rom_info.get('basename')
        
        # Compare hash if available
        rom_path = Path(rom_info.get('path', ''))
        stored_hash = existing_entry.get('hash')
        
        comparison = self.hash_comparator.compare_rom_hash(
            rom_path, stored_hash, hash_type='md5'
        )
        
        # Determine if update needed based on policy
        should_update = self.hash_comparator.should_rescrape(
            comparison, self.update_policy
        )
        
        # Determine what to update
        update_metadata = should_update and self.update_metadata
        update_media = should_update and self.update_media
        
        # Determine which media types need updating
        media_types_to_update = []
        if update_media:
            enabled_types = self.config.get('scraping', {}).get('media_types', [])
            media_types_to_update = enabled_types
        
        # Determine reason
        if not should_update:
            reason = "hash_match" if not comparison.has_changed else "policy_skip"
        elif comparison.has_changed:
            reason = "hash_changed"
        else:
            reason = "policy_update"
        
        logger.debug(
            f"{rom_basename}: Update decision - "
            f"metadata={update_metadata}, media={update_media}, reason={reason}"
        )
        
        return UpdateDecision(
            rom_basename=rom_basename,
            should_update_metadata=update_metadata,
            should_update_media=update_media,
            media_types_to_update=media_types_to_update,
            reason=reason
        )
    
    def execute_update(self, rom_info: dict, existing_entry: dict,
                      api_response: dict, decision: UpdateDecision) -> UpdateResult:
        """
        Execute update based on decision
        
        Args:
            rom_info: ROM information
            existing_entry: Existing gamelist entry
            api_response: API response with new data
            decision: UpdateDecision from determine_update_action
        
        Returns:
            UpdateResult with operation results
        """
        rom_basename = decision.rom_basename
        errors = []
        
        # Update metadata if needed
        metadata_updated = False
        merged_data = existing_entry
        
        if decision.should_update_metadata:
            try:
                merge_result = self.metadata_merger.merge_metadata(
                    existing_entry, api_response
                )
                merged_data = merge_result.merged_data
                metadata_updated = True
                logger.info(
                    f"{rom_basename}: Metadata updated "
                    f"({len(merge_result.updated_fields)} fields)"
                )
            except Exception as e:
                error_msg = f"Metadata merge failed: {e}"
                errors.append(error_msg)
                logger.error(f"{rom_basename}: {error_msg}")
        
        # Update media if needed
        media_results = {}
        
        if decision.should_update_media:
            for media_type in decision.media_types_to_update:
                try:
                    # Placeholder for media download
                    # In real implementation, this would call media downloader
                    media_results[media_type] = True
                    logger.debug(f"{rom_basename}: {media_type} marked for update")
                except Exception as e:
                    error_msg = f"{media_type} update failed: {e}"
                    errors.append(error_msg)
                    logger.error(f"{rom_basename}: {error_msg}")
                    media_results[media_type] = False
        
        return UpdateResult(
            rom_basename=rom_basename,
            metadata_updated=metadata_updated,
            media_updated=media_results,
            errors=errors
        )
    
    def coordinate_batch_update(self, rom_infos: List[dict],
                               existing_entries: Dict[str, dict],
                               api_responses: Dict[str, dict],
                               system_name: str) -> Dict[str, UpdateResult]:
        """
        Coordinate updates for multiple ROMs
        
        Args:
            rom_infos: List of ROM information dicts
            existing_entries: Dict mapping basename to existing entry
            api_responses: Dict mapping basename to API response
            system_name: System name
        
        Returns:
            Dict mapping basename to UpdateResult
        """
        results = {}
        
        for rom_info in rom_infos:
            basename = rom_info.get('basename')
            existing = existing_entries.get(basename, {})
            api_data = api_responses.get(basename, {})
            
            # Determine update action
            decision = self.determine_update_action(rom_info, existing, system_name)
            
            # Execute update if needed
            if decision.should_update_metadata or decision.should_update_media:
                result = self.execute_update(rom_info, existing, api_data, decision)
                results[basename] = result
            else:
                # No update needed
                results[basename] = UpdateResult(
                    rom_basename=basename,
                    metadata_updated=False,
                    media_updated={},
                    errors=[]
                )
        
        # Log summary
        metadata_count = sum(1 for r in results.values() if r.metadata_updated)
        media_count = sum(
            1 for r in results.values()
            if any(r.media_updated.values())
        )
        error_count = sum(1 for r in results.values() if r.errors)
        
        logger.info(
            f"Batch update complete: {len(results)} ROMs, "
            f"{metadata_count} metadata updates, {media_count} media updates, "
            f"{error_count} errors"
        )
        
        return results
    
    def get_update_statistics(self, results: Dict[str, UpdateResult]) -> dict:
        """
        Calculate statistics from update results
        
        Args:
            results: Dict of UpdateResult instances
        
        Returns:
            Dict with statistics
        """
        stats = {
            'total_roms': len(results),
            'metadata_updated': 0,
            'media_updated': 0,
            'no_changes': 0,
            'errors': 0,
            'media_by_type': {}
        }
        
        for result in results.values():
            if result.metadata_updated:
                stats['metadata_updated'] += 1
            
            if any(result.media_updated.values()):
                stats['media_updated'] += 1
            
            if not result.metadata_updated and not result.media_updated:
                stats['no_changes'] += 1
            
            if result.errors:
                stats['errors'] += 1
            
            # Count media by type
            for media_type, success in result.media_updated.items():
                if success:
                    stats['media_by_type'][media_type] = \
                        stats['media_by_type'].get(media_type, 0) + 1
        
        return stats
    
    def filter_update_needed(self, rom_infos: List[dict],
                            existing_entries: Dict[str, dict],
                            system_name: str) -> List[dict]:
        """
        Filter ROMs that need updates based on policy
        
        Args:
            rom_infos: List of ROM information dicts
            existing_entries: Dict mapping basename to existing entry
            system_name: System name
        
        Returns:
            List of ROM infos that need updates
        """
        update_needed = []
        
        for rom_info in rom_infos:
            basename = rom_info.get('basename')
            existing = existing_entries.get(basename, {})
            
            decision = self.determine_update_action(rom_info, existing, system_name)
            
            if decision.should_update_metadata or decision.should_update_media:
                update_needed.append(rom_info)
        
        logger.info(
            f"Update filter: {len(update_needed)}/{len(rom_infos)} ROMs need updates"
        )
        
        return update_needed
