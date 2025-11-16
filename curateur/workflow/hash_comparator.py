"""
Hash Comparator - ROM hash comparison for change detection

Compares stored ROM hashes with recalculated hashes to detect file changes.
Used in update mode to determine if ROMs have been modified since last scraping.
"""

from pathlib import Path
from typing import Dict, NamedTuple, Optional, Set
import logging

logger = logging.getLogger(__name__)


class HashComparison(NamedTuple):
    """Result of hash comparison"""
    rom_basename: str
    has_changed: bool
    stored_hash: Optional[str]
    current_hash: Optional[str]
    hash_type: str  # 'md5', 'crc', or 'none'


class HashComparator:
    """
    Compares ROM hashes to detect file changes
    
    Use cases:
    - Update mode: Re-scrape only changed ROMs
    - Verification: Confirm ROM integrity
    - Change detection: Track ROM modifications
    
    Hash priority:
    1. MD5 (most reliable, stored by ScreenScraper)
    2. CRC32 (faster, commonly available)
    3. None (if no hash available, assume changed)
    """
    
    def __init__(self, hash_calculator):
        """
        Initialize hash comparator
        
        Args:
            hash_calculator: HashCalculator instance for computing hashes
        """
        self.hash_calculator = hash_calculator
        logger.info("Hash Comparator initialized")
    
    def compare_rom_hash(self, rom_path: Path, stored_hash: Optional[str],
                        hash_type: str = 'md5') -> HashComparison:
        """
        Compare stored hash with current ROM file hash
        
        Args:
            rom_path: Path to ROM file
            stored_hash: Hash value from gamelist (or None)
            hash_type: Type of hash ('md5' or 'crc')
        
        Returns:
            HashComparison result
        """
        rom_basename = rom_path.stem
        
        # If no stored hash, assume changed
        if not stored_hash:
            logger.debug(f"{rom_basename}: No stored hash, marking as changed")
            return HashComparison(
                rom_basename=rom_basename,
                has_changed=True,
                stored_hash=None,
                current_hash=None,
                hash_type='none'
            )
        
        # Calculate current hash
        if hash_type == 'md5':
            current_hash = self.hash_calculator.calculate_md5(rom_path)
        elif hash_type == 'crc':
            current_hash = self.hash_calculator.calculate_crc(rom_path)
        else:
            logger.warning(f"Unknown hash type: {hash_type}, assuming changed")
            return HashComparison(
                rom_basename=rom_basename,
                has_changed=True,
                stored_hash=stored_hash,
                current_hash=None,
                hash_type='none'
            )
        
        # Compare hashes
        has_changed = (current_hash != stored_hash)
        
        if has_changed:
            logger.info(
                f"{rom_basename}: Hash mismatch - "
                f"stored={stored_hash[:8]}... current={current_hash[:8]}..."
            )
        else:
            logger.debug(f"{rom_basename}: Hash match ({hash_type})")
        
        return HashComparison(
            rom_basename=rom_basename,
            has_changed=has_changed,
            stored_hash=stored_hash,
            current_hash=current_hash,
            hash_type=hash_type
        )
    
    def compare_batch(self, rom_paths: list, stored_hashes: Dict[str, str],
                     hash_type: str = 'md5') -> Dict[str, HashComparison]:
        """
        Compare hashes for multiple ROMs
        
        Args:
            rom_paths: List of ROM file paths
            stored_hashes: Dict mapping basename to stored hash
            hash_type: Type of hash to compare
        
        Returns:
            Dict mapping basename to HashComparison
        """
        results = {}
        
        for rom_path in rom_paths:
            basename = rom_path.stem
            stored_hash = stored_hashes.get(basename)
            
            comparison = self.compare_rom_hash(rom_path, stored_hash, hash_type)
            results[basename] = comparison
        
        # Log summary
        changed_count = sum(1 for c in results.values() if c.has_changed)
        logger.info(
            f"Hash comparison complete: {changed_count}/{len(results)} ROMs changed"
        )
        
        return results
    
    def get_changed_roms(self, comparisons: Dict[str, HashComparison]) -> Set[str]:
        """
        Extract basenames of ROMs that have changed
        
        Args:
            comparisons: Dict of HashComparison results
        
        Returns:
            Set of basenames for changed ROMs
        """
        return {
            basename for basename, comp in comparisons.items()
            if comp.has_changed
        }
    
    def get_unchanged_roms(self, comparisons: Dict[str, HashComparison]) -> Set[str]:
        """
        Extract basenames of ROMs that haven't changed
        
        Args:
            comparisons: Dict of HashComparison results
        
        Returns:
            Set of basenames for unchanged ROMs
        """
        return {
            basename for basename, comp in comparisons.items()
            if not comp.has_changed
        }
    
    def should_rescrape(self, comparison: HashComparison, update_policy: str) -> bool:
        """
        Determine if ROM should be re-scraped based on hash and policy
        
        Args:
            comparison: HashComparison result
            update_policy: 'always' | 'changed_only' | 'never'
        
        Returns:
            bool: True if ROM should be re-scraped
        """
        if update_policy == 'always':
            return True
        elif update_policy == 'changed_only':
            return comparison.has_changed
        elif update_policy == 'never':
            return False
        else:
            logger.warning(f"Unknown update policy: {update_policy}, using 'changed_only'")
            return comparison.has_changed
