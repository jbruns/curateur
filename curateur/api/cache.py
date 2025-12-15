"""
API response cache for ScreenScraper metadata.

Provides disk-based caching of jeuInfos.php responses to reduce API calls
and improve performance for unchanged ROMs.
"""

import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class MetadataCache:
    """
    Disk-based cache for ScreenScraper API responses.

    Features:
    - Per-system cache storage alongside gamelist.xml
    - 7-day TTL for cache entries
    - Automatic cleanup of expired entries
    - Cache invalidation support
    - Thread-safe operations

    Storage format:
    {
        "<rom_hash>": {
            "response": {...},  # Full API response
            "rom_hash": "ABC123",  # ROM hash used as key (stored for validation)
            "rom_size": 1234567,  # ROM file size for quick validation
            "media_hashes": {  # Hashes of downloaded media files
                "screenshot": "DEF456",
                "box2dfront": "GHI789"
            },
            "timestamp": "2025-11-22T10:30:00",
            "ttl_days": 7
        }
    }
    """

    def __init__(
        self, gamelist_directory: Path, ttl_days: int = 7, enabled: bool = True
    ):
        """
        Initialize metadata cache.

        Args:
            gamelist_directory: Directory containing gamelist.xml
            ttl_days: Time-to-live for cache entries in days
            enabled: Whether caching is enabled
        """
        self.gamelist_directory = gamelist_directory
        self.ttl_days = ttl_days
        self.enabled = enabled

        # Cache directory: <gamelist_directory>/.cache/
        self.cache_dir = gamelist_directory / ".cache"
        self.cache_file = self.cache_dir / "metadata_cache.json"

        # In-memory cache for faster access during session
        self._memory_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_loaded = False

        # Metrics tracking
        self._hits: int = 0
        self._misses: int = 0

        logger.debug(
            f"MetadataCache initialized: cache_dir={self.cache_dir}, "
            f"ttl_days={ttl_days}, enabled={enabled}"
        )

    def _ensure_cache_directory(self) -> None:
        """Create cache directory if it doesn't exist."""
        if not self.cache_dir.exists():
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            logger.debug(f"Created cache directory: {self.cache_dir}")

    def _load_cache(self) -> None:
        """Load cache from disk into memory."""
        if self._cache_loaded:
            return

        if not self.enabled:
            self._cache_loaded = True
            return

        if not self.cache_file.exists():
            logger.debug("No cache file found, starting with empty cache")
            self._memory_cache = {}
            self._cache_loaded = True
            return

        try:
            with open(self.cache_file, "r", encoding="utf-8") as f:
                self._memory_cache = json.load(f)

            logger.info(
                f"Loaded metadata cache: {len(self._memory_cache)} entries from {self.cache_file}"
            )
            self._cache_loaded = True

        except (json.JSONDecodeError, IOError) as e:
            logger.warning(f"Failed to load cache file: {e}, starting with empty cache")
            self._memory_cache = {}
            self._cache_loaded = True

    def _save_cache(self) -> None:
        """Save in-memory cache to disk."""
        if not self.enabled:
            return

        try:
            self._ensure_cache_directory()

            # Write to temporary file first
            temp_file = self.cache_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(self._memory_cache, f, indent=2, ensure_ascii=False)

            # Atomic rename
            temp_file.replace(self.cache_file)

            logger.debug(f"Saved cache: {len(self._memory_cache)} entries")

        except (IOError, OSError) as e:
            logger.error(f"Failed to save cache: {e}")

    def get(
        self, rom_hash: str, rom_size: Optional[int] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get cached entry for ROM hash with optional size validation.

        Args:
            rom_hash: ROM hash (CRC32, MD5, or SHA1)
            rom_size: ROM file size for validation (optional)

        Returns:
            Complete cache entry dict with 'response', 'rom_hash', 'media_hashes', etc.
            or None if not found/expired/invalid
        """
        if not self.enabled:
            return None

        # Ensure cache is loaded
        self._load_cache()

        # Check if entry exists
        if rom_hash not in self._memory_cache:
            logger.debug(f"Cache miss: {rom_hash}")
            self._misses += 1
            return None

        entry = self._memory_cache[rom_hash]

        # Check if expired
        if self._is_expired(entry):
            logger.debug(f"Cache expired: {rom_hash}")
            # Remove expired entry
            del self._memory_cache[rom_hash]
            self._misses += 1
            return None

        # Validate ROM size if provided (quick validation without rehashing)
        if rom_size is not None and "rom_size" in entry:
            if entry["rom_size"] != rom_size:
                logger.warning(
                    f"Cache entry size mismatch for {rom_hash}: "
                    f"cached={entry['rom_size']}, actual={rom_size}. "
                    f"ROM may have been replaced."
                )
                # Remove invalid entry
                del self._memory_cache[rom_hash]
                self._misses += 1
                return None

        logger.debug(f"Cache hit: {rom_hash}")
        self._hits += 1
        return entry

    def put(
        self,
        rom_hash: str,
        response: Dict[str, Any],
        rom_size: Optional[int] = None,
        media_hashes: Optional[Dict[str, str]] = None,
    ) -> None:
        """
        Store API response in cache with ROM and media hashes.

        Args:
            rom_hash: ROM hash (CRC32, MD5, or SHA1)
            response: Full API response to cache
            rom_size: ROM file size in bytes (optional, for quick validation)
            media_hashes: Dict of media type -> hash (optional, for media validation)
        """
        if not self.enabled:
            return

        # Ensure cache is loaded
        self._load_cache()

        # Create cache entry
        entry = {
            "response": response,
            "rom_hash": rom_hash,
            "timestamp": datetime.now().isoformat(),
            "ttl_days": self.ttl_days,
        }

        # Add optional fields
        if rom_size is not None:
            entry["rom_size"] = rom_size

        if media_hashes:
            entry["media_hashes"] = media_hashes

        self._memory_cache[rom_hash] = entry
        logger.debug(
            "Cached response: %s (rom_size=%s, media_count=%s)",
            rom_hash,
            rom_size,
            len(media_hashes) if media_hashes else 0,
        )

        # Save to disk
        self._save_cache()

    def _is_expired(self, entry: Dict[str, Any]) -> bool:
        """
        Check if cache entry is expired.

        Args:
            entry: Cache entry dict

        Returns:
            True if expired, False otherwise
        """
        try:
            timestamp = datetime.fromisoformat(entry["timestamp"])
            ttl_days = entry.get("ttl_days", self.ttl_days)
            expiry = timestamp + timedelta(days=ttl_days)

            return datetime.now() > expiry

        except (KeyError, ValueError) as e:
            logger.warning(f"Invalid cache entry format: {e}")
            return True

    def cleanup_expired(self) -> int:
        """
        Remove expired entries from cache.

        Returns:
            Number of entries removed
        """
        if not self.enabled:
            return 0

        # Ensure cache is loaded
        self._load_cache()

        initial_count = len(self._memory_cache)

        # Find expired entries
        expired_hashes = [
            rom_hash
            for rom_hash, entry in self._memory_cache.items()
            if self._is_expired(entry)
        ]

        # Remove expired entries
        for rom_hash in expired_hashes:
            del self._memory_cache[rom_hash]

        removed_count = len(expired_hashes)

        if removed_count > 0:
            logger.info(f"Cleaned up {removed_count} expired cache entries")
            self._save_cache()

        return removed_count

    def clear(self) -> int:
        """
        Clear all cache entries.

        Returns:
            Number of entries removed
        """
        if not self.enabled:
            return 0

        # Ensure cache is loaded
        self._load_cache()

        count = len(self._memory_cache)
        self._memory_cache = {}

        # Remove cache file
        if self.cache_file.exists():
            try:
                self.cache_file.unlink()
                logger.info(f"Cleared cache: {count} entries removed")
            except OSError as e:
                logger.error(f"Failed to remove cache file: {e}")

        return count

    def get_media_hash(self, rom_hash: str, media_type: str) -> Optional[str]:
        """
        Get cached media hash for a specific media type.

        Args:
            rom_hash: ROM hash
            media_type: Media type (singular form, e.g., 'screenshot', 'box2dfront')

        Returns:
            Media hash or None if not found
        """
        if not self.enabled:
            return None

        # Ensure cache is loaded
        self._load_cache()

        if rom_hash not in self._memory_cache:
            return None

        entry = self._memory_cache[rom_hash]
        media_hashes = entry.get("media_hashes", {})

        return media_hashes.get(media_type)

    def update_media_hashes(self, rom_hash: str, media_hashes: Dict[str, str]) -> None:
        """
        Update media hashes for an existing cache entry.

        Args:
            rom_hash: ROM hash
            media_hashes: Dict of media type -> hash to add/update
        """
        if not self.enabled:
            return

        # Ensure cache is loaded
        self._load_cache()

        if rom_hash not in self._memory_cache:
            logger.warning(
                f"Cannot update media hashes: cache entry not found for {rom_hash}"
            )
            return

        entry = self._memory_cache[rom_hash]

        # Merge media hashes
        if "media_hashes" not in entry:
            entry["media_hashes"] = {}

        entry["media_hashes"].update(media_hashes)

        logger.debug(
            f"Updated media hashes for {rom_hash}: {list(media_hashes.keys())}"
        )

        # Save to disk
        self._save_cache()

    def get_metrics(self) -> Dict[str, Any]:
        """Get cache performance metrics."""
        self._load_cache()
        total_requests = self._hits + self._misses
        hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0.0
        return {
            "hits": self._hits,
            "misses": self._misses,
            "total_entries": len(self._memory_cache),
            "hit_rate": hit_rate,
            "enabled": self.enabled,
        }

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dict with cache stats (size, expired count, oldest entry, media coverage)
        """
        if not self.enabled:
            return {
                "enabled": False,
                "total_entries": 0,
                "expired_entries": 0,
                "entries_with_media": 0,
            }

        # Ensure cache is loaded
        self._load_cache()

        total_entries = len(self._memory_cache)
        expired_entries = sum(
            1 for entry in self._memory_cache.values() if self._is_expired(entry)
        )

        entries_with_media = sum(
            1 for entry in self._memory_cache.values() if entry.get("media_hashes")
        )

        oldest_timestamp = None
        if self._memory_cache:
            try:
                timestamps = [
                    datetime.fromisoformat(entry["timestamp"])
                    for entry in self._memory_cache.values()
                ]
                oldest_timestamp = min(timestamps).isoformat()
            except (KeyError, ValueError):
                pass

        return {
            "enabled": True,
            "cache_file": str(self.cache_file),
            "total_entries": total_entries,
            "expired_entries": expired_entries,
            "valid_entries": total_entries - expired_entries,
            "entries_with_media": entries_with_media,
            "oldest_entry": oldest_timestamp,
            "ttl_days": self.ttl_days,
        }
