"""
Change Detector - Tracks and logs metadata changes

Compares before/after states to generate detailed change reports.
Provides transparency for update operations.
"""

from typing import Dict, List, NamedTuple, Any, Optional, Set
import logging

logger = logging.getLogger(__name__)


class FieldChange(NamedTuple):
    """Individual field change"""
    field_name: str
    old_value: Any
    new_value: Any
    change_type: str  # 'added', 'removed', 'modified', 'unchanged'


class ChangeReport(NamedTuple):
    """Complete change report for a ROM"""
    rom_basename: str
    changes: List[FieldChange]
    added_count: int
    removed_count: int
    modified_count: int
    unchanged_count: int


class ChangeDetector:
    """
    Detects and reports metadata changes
    
    Use cases:
    - Audit trail: Log all metadata changes
    - User transparency: Show what was updated
    - Conflict detection: Identify unexpected changes
    - Rollback support: Track changes for potential undo
    
    Change types:
    - added: Field present in new but not old
    - removed: Field present in old but not new
    - modified: Field value changed
    - unchanged: Field value same in both
    """
    
    def __init__(self, config: dict):
        """
        Initialize change detector
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.log_changes = config.get('scraping', {}).get('log_changes', True)
        self.log_unchanged = config.get('scraping', {}).get('log_unchanged_fields', False)
        logger.info(f"Change Detector initialized (log_changes={self.log_changes})")
    
    def detect_changes(self, old_metadata: dict, new_metadata: dict,
                      rom_basename: str) -> ChangeReport:
        """
        Detect changes between old and new metadata
        
        Args:
            old_metadata: Original metadata
            new_metadata: Updated metadata
            rom_basename: ROM basename for logging
        
        Returns:
            ChangeReport with detailed changes
        """
        changes = []
        added_count = 0
        removed_count = 0
        modified_count = 0
        unchanged_count = 0
        
        # Get all field names from both
        all_fields = set(old_metadata.keys()) | set(new_metadata.keys())
        
        for field in sorted(all_fields):
            old_value = old_metadata.get(field)
            new_value = new_metadata.get(field)
            
            # Determine change type
            if old_value is None and new_value is not None:
                change_type = 'added'
                added_count += 1
            elif old_value is not None and new_value is None:
                change_type = 'removed'
                removed_count += 1
            elif old_value != new_value:
                change_type = 'modified'
                modified_count += 1
            else:
                change_type = 'unchanged'
                unchanged_count += 1
            
            # Add to changes list (skip unchanged if not logging them)
            if change_type != 'unchanged' or self.log_unchanged:
                changes.append(FieldChange(
                    field_name=field,
                    old_value=old_value,
                    new_value=new_value,
                    change_type=change_type
                ))
        
        # Log summary if enabled
        if self.log_changes and (added_count + removed_count + modified_count) > 0:
            logger.info(
                f"{rom_basename}: Changes detected - "
                f"{added_count} added, {modified_count} modified, {removed_count} removed"
            )
        
        return ChangeReport(
            rom_basename=rom_basename,
            changes=changes,
            added_count=added_count,
            removed_count=removed_count,
            modified_count=modified_count,
            unchanged_count=unchanged_count
        )
    
    def detect_batch_changes(self, old_entries: Dict[str, dict],
                            new_entries: Dict[str, dict]) -> Dict[str, ChangeReport]:
        """
        Detect changes for multiple ROMs
        
        Args:
            old_entries: Dict mapping basename to old metadata
            new_entries: Dict mapping basename to new metadata
        
        Returns:
            Dict mapping basename to ChangeReport
        """
        reports = {}
        
        for basename in new_entries.keys():
            old_metadata = old_entries.get(basename, {})
            new_metadata = new_entries[basename]
            
            report = self.detect_changes(old_metadata, new_metadata, basename)
            reports[basename] = report
        
        # Log batch summary
        total_changes = sum(
            r.added_count + r.removed_count + r.modified_count
            for r in reports.values()
        )
        
        if self.log_changes and total_changes > 0:
            logger.info(
                f"Batch change detection: {len(reports)} ROMs, {total_changes} total changes"
            )
        
        return reports
    
    def filter_significant_changes(self, report: ChangeReport,
                                   significant_fields: Optional[Set[str]] = None) -> List[FieldChange]:
        """
        Filter to only significant field changes
        
        Args:
            report: ChangeReport to filter
            significant_fields: Set of field names to consider significant
                               (None = all changes significant)
        
        Returns:
            List of significant FieldChanges
        """
        if significant_fields is None:
            # All non-unchanged changes are significant
            return [c for c in report.changes if c.change_type != 'unchanged']
        
        significant = []
        for change in report.changes:
            if change.change_type != 'unchanged' and change.field_name in significant_fields:
                significant.append(change)
        
        return significant
    
    def get_changed_fields(self, report: ChangeReport) -> Set[str]:
        """
        Get set of field names that changed
        
        Args:
            report: ChangeReport to analyze
        
        Returns:
            Set of field names that were added, removed, or modified
        """
        return {
            change.field_name for change in report.changes
            if change.change_type != 'unchanged'
        }
    
    def format_change_summary(self, report: ChangeReport, 
                             include_details: bool = False) -> str:
        """
        Format change report as human-readable string
        
        Args:
            report: ChangeReport to format
            include_details: Include individual field changes
        
        Returns:
            Formatted string
        """
        lines = [f"Changes for {report.rom_basename}:"]
        lines.append(
            f"  {report.added_count} added, {report.modified_count} modified, "
            f"{report.removed_count} removed"
        )
        
        if include_details:
            for change in report.changes:
                if change.change_type == 'unchanged':
                    continue
                
                if change.change_type == 'added':
                    lines.append(f"  + {change.field_name}: {change.new_value}")
                elif change.change_type == 'removed':
                    lines.append(f"  - {change.field_name}: {change.old_value}")
                elif change.change_type == 'modified':
                    lines.append(
                        f"  ~ {change.field_name}: {change.old_value} -> {change.new_value}"
                    )
        
        return '\n'.join(lines)
    
    def generate_audit_log(self, reports: Dict[str, ChangeReport],
                          output_path: Optional[str] = None) -> str:
        """
        Generate audit log of all changes
        
        Args:
            reports: Dict of ChangeReports
            output_path: Optional file path to write log
        
        Returns:
            Formatted audit log string
        """
        lines = ["=" * 70]
        lines.append("METADATA CHANGE AUDIT LOG")
        lines.append("=" * 70)
        lines.append("")
        
        # Overall statistics
        total_roms = len(reports)
        total_added = sum(r.added_count for r in reports.values())
        total_modified = sum(r.modified_count for r in reports.values())
        total_removed = sum(r.removed_count for r in reports.values())
        
        lines.append(f"Total ROMs: {total_roms}")
        lines.append(f"Total changes: {total_added + total_modified + total_removed}")
        lines.append(f"  Added fields: {total_added}")
        lines.append(f"  Modified fields: {total_modified}")
        lines.append(f"  Removed fields: {total_removed}")
        lines.append("")
        lines.append("-" * 70)
        lines.append("")
        
        # Individual ROM changes
        for basename, report in sorted(reports.items()):
            if report.added_count + report.modified_count + report.removed_count == 0:
                continue  # Skip ROMs with no changes
            
            lines.append(self.format_change_summary(report, include_details=True))
            lines.append("")
        
        audit_log = '\n'.join(lines)
        
        # Write to file if path provided
        if output_path:
            try:
                with open(output_path, 'w', encoding='utf-8') as f:
                    f.write(audit_log)
                logger.info(f"Audit log written to {output_path}")
            except Exception as e:
                logger.error(f"Failed to write audit log: {e}")
        
        return audit_log
    
    def has_significant_changes(self, report: ChangeReport,
                               min_changes: int = 1) -> bool:
        """
        Check if report has significant changes
        
        Args:
            report: ChangeReport to check
            min_changes: Minimum number of changes to be significant
        
        Returns:
            bool: True if changes meet threshold
        """
        total_changes = report.added_count + report.modified_count + report.removed_count
        return total_changes >= min_changes
