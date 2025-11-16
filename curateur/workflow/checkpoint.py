"""
Checkpoint management for resume capability

Provides progress tracking and resume functionality for interrupted scraping runs.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, NamedTuple

logger = logging.getLogger(__name__)


class CheckpointData(NamedTuple):
    """Checkpoint data structure"""
    system: str
    timestamp: str
    processed_roms: list[str]
    failed_roms: list[dict]
    api_quota: dict
    stats: dict


class CheckpointManager:
    """
    Manages scraping progress checkpoints for resume capability
    
    Checkpoint file: <gamelists>/<system>/.curateur_checkpoint.json
    
    Features:
    - Configurable save intervals (default: every 100 ROMs)
    - Smart triggering on system boundaries
    - Atomic file writes
    - Progress statistics tracking
    
    Example:
        manager = CheckpointManager('/path/to/gamelists', 'nes', config)
        
        # Try to resume
        if checkpoint := manager.load_checkpoint():
            if prompt_resume_from_checkpoint(checkpoint):
                # Resume from checkpoint
                for rom in roms:
                    if manager.is_processed(rom.filename):
                        continue  # Skip already processed
                    # Process ROM...
                    manager.add_processed_rom(rom.filename, 'full_scrape', True)
                    manager.save_checkpoint()  # Auto-save at intervals
        
        # Clean up on completion
        manager.remove_checkpoint()
    """
    
    def __init__(self, gamelist_dir: str, system_name: str, config: dict):
        """
        Initialize checkpoint manager
        
        Args:
            gamelist_dir: Directory where gamelist.xml is stored
            system_name: System short name (e.g., 'nes', 'snes')
            config: Configuration dictionary
        """
        self.gamelist_dir = Path(gamelist_dir)
        self.checkpoint_file = self.gamelist_dir / ".curateur_checkpoint.json"
        self.system_name = system_name
        self.interval = config.get('scraping', {}).get('checkpoint_interval', 100)
        self.processed_count = 0
        self.data = self._init_checkpoint_data()
    
    def _init_checkpoint_data(self) -> dict:
        """Initialize checkpoint data structure"""
        return {
            'system': self.system_name,
            'timestamp': None,
            'processed_roms': [],
            'failed_roms': [],
            'api_quota': {},
            'stats': {
                'total_roms': 0,
                'processed': 0,
                'successful': 0,
                'failed': 0,
                'skipped': 0,
                'media_only': 0
            }
        }
    
    def load_checkpoint(self) -> Optional[CheckpointData]:
        """
        Load existing checkpoint file
        
        Returns:
            CheckpointData if checkpoint exists and is valid, None otherwise
        """
        if not self.checkpoint_file.exists():
            logger.debug(f"No checkpoint file found: {self.checkpoint_file}")
            return None
        
        try:
            with open(self.checkpoint_file, 'r') as f:
                data = json.load(f)
            
            # Validate checkpoint structure
            if data.get('system') != self.system_name:
                logger.warning(
                    f"Checkpoint system mismatch: expected {self.system_name}, "
                    f"got {data.get('system')}"
                )
                return None
            
            # Restore checkpoint data
            self.data = data
            self.processed_count = data['stats']['processed']
            
            logger.info(
                f"Loaded checkpoint: {self.processed_count} ROMs processed, "
                f"{data['stats']['successful']} successful, "
                f"{data['stats']['failed']} failed"
            )
            
            return CheckpointData(
                system=data['system'],
                timestamp=data['timestamp'],
                processed_roms=data['processed_roms'],
                failed_roms=data['failed_roms'],
                api_quota=data['api_quota'],
                stats=data['stats']
            )
        
        except (json.JSONDecodeError, KeyError) as e:
            logger.error(f"Failed to load checkpoint: {e}")
            return None
    
    def save_checkpoint(self, force: bool = False) -> None:
        """
        Save checkpoint at interval or when forced
        
        Args:
            force: Save immediately regardless of interval
        
        Smart triggering:
        - Every N ROMs (configured interval)
        - At system boundaries (force=True)
        - Before fatal errors (force=True)
        """
        if self.interval == 0:
            return  # Checkpointing disabled
        
        # Check if we should save
        should_save = force or (self.processed_count % self.interval == 0)
        
        if not should_save:
            return
        
        # Update timestamp
        self.data['timestamp'] = datetime.now().isoformat()
        
        # Atomic write: write to temp file, then rename
        temp_file = self.checkpoint_file.with_suffix('.tmp')
        
        try:
            self.gamelist_dir.mkdir(parents=True, exist_ok=True)
            
            with open(temp_file, 'w') as f:
                json.dump(self.data, f, indent=2)
            
            # Atomic rename
            temp_file.replace(self.checkpoint_file)
            
            logger.debug(
                f"Checkpoint saved: {self.processed_count} ROMs processed "
                f"({self.data['stats']['successful']} successful, "
                f"{self.data['stats']['failed']} failed)"
            )
        
        except Exception as e:
            logger.error(f"Failed to save checkpoint: {e}")
            if temp_file.exists():
                temp_file.unlink()
    
    def add_processed_rom(
        self,
        filename: str,
        action: str,
        success: bool,
        reason: Optional[str] = None
    ) -> None:
        """
        Record processed ROM
        
        Args:
            filename: ROM filename
            action: 'full_scrape' | 'media_only' | 'skip' | 'update'
            success: Whether processing succeeded
            reason: Optional failure reason
        """
        # Add to processed list
        if filename not in self.data['processed_roms']:
            self.data['processed_roms'].append(filename)
        
        # Update statistics
        self.data['stats']['processed'] += 1
        self.processed_count += 1
        
        if success:
            self.data['stats']['successful'] += 1
            
            # Count action types
            if action == 'skip':
                self.data['stats']['skipped'] += 1
            elif action == 'media_only':
                self.data['stats']['media_only'] += 1
        else:
            self.data['stats']['failed'] += 1
            self.data['failed_roms'].append({
                'filename': filename,
                'action': action,
                'reason': reason or 'Unknown error'
            })
    
    def is_processed(self, filename: str) -> bool:
        """
        Check if ROM was already processed
        
        Args:
            filename: ROM filename to check
        
        Returns:
            True if ROM was already processed
        """
        return filename in self.data['processed_roms']
    
    def update_api_quota(self, quota_info: dict) -> None:
        """
        Update API quota tracking from response
        
        Args:
            quota_info: Dict with quota fields from API response
                - maxrequestsseconds: Max requests per second
                - maxrequestsperday: Max requests per day
                - requeststoday: Requests used today
        """
        self.data['api_quota'] = {
            'max_requests_per_second': quota_info.get('maxrequestsseconds'),
            'max_requests_per_day': quota_info.get('maxrequestsperday'),
            'requests_today': quota_info.get('requeststoday'),
            'last_updated': datetime.now().isoformat()
        }
    
    def set_total_roms(self, total: int) -> None:
        """
        Set total ROM count for progress tracking
        
        Args:
            total: Total number of ROMs to process
        """
        self.data['stats']['total_roms'] = total
    
    def remove_checkpoint(self) -> None:
        """Remove checkpoint file after successful completion"""
        if self.checkpoint_file.exists():
            try:
                self.checkpoint_file.unlink()
                logger.info("Checkpoint removed after successful completion")
            except Exception as e:
                logger.warning(f"Failed to remove checkpoint: {e}")
    
    def get_stats(self) -> dict:
        """
        Get current checkpoint statistics
        
        Returns:
            Dictionary with checkpoint statistics
        """
        return self.data['stats'].copy()
    
    def get_failed_roms(self) -> list[dict]:
        """
        Get list of failed ROMs
        
        Returns:
            List of failed ROM entries with filename, action, and reason
        """
        return self.data['failed_roms'].copy()


def prompt_resume_from_checkpoint(checkpoint_data: CheckpointData) -> bool:
    """
    Interactive prompt for checkpoint resume
    
    Displays:
    - System name
    - Last checkpoint time
    - Progress statistics
    - Failed ROM count
    
    Args:
        checkpoint_data: Checkpoint data to display
    
    Returns:
        True to resume, False to start fresh
    """
    print("\n" + "=" * 70)
    print("CHECKPOINT FOUND")
    print("=" * 70)
    print(f"System: {checkpoint_data.system}")
    print(f"Last saved: {checkpoint_data.timestamp}")
    print(f"\nProgress:")
    print(f"  Total ROMs: {checkpoint_data.stats['total_roms']}")
    print(f"  Processed: {checkpoint_data.stats['processed']}")
    print(f"  Successful: {checkpoint_data.stats['successful']}")
    print(f"  Failed: {checkpoint_data.stats['failed']}")
    print(f"  Skipped: {checkpoint_data.stats['skipped']}")
    print(f"  Media only: {checkpoint_data.stats['media_only']}")
    
    if checkpoint_data.failed_roms:
        print(f"\nFailed ROMs ({len(checkpoint_data.failed_roms)}):")
        for failed in checkpoint_data.failed_roms[:5]:  # Show first 5
            print(f"  - {failed['filename']}: {failed['reason']}")
        if len(checkpoint_data.failed_roms) > 5:
            print(f"  ... and {len(checkpoint_data.failed_roms) - 5} more")
    
    if checkpoint_data.api_quota.get('requests_today'):
        print(f"\nAPI Quota: {checkpoint_data.api_quota['requests_today']} requests used today")
    
    print("=" * 70)
    
    while True:
        response = input("\nResume from checkpoint? [y/n]: ").strip().lower()
        if response in ('y', 'yes'):
            return True
        elif response in ('n', 'no'):
            return False
        else:
            print("Please enter 'y' or 'n'")
