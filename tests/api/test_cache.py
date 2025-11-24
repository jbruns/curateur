import json
from pathlib import Path

import pytest

from curateur.api.cache import MetadataCache


@pytest.mark.unit
def test_cache_put_and_get_hits(tmp_path: Path):
    gamelist_dir = tmp_path / "gamelists"
    gamelist_dir.mkdir()

    cache = MetadataCache(gamelist_directory=gamelist_dir)
    cache.put("ABC123", {"name": "Example"}, rom_size=100)

    entry = cache.get("ABC123", rom_size=100)
    assert entry is not None
    assert entry["response"]["name"] == "Example"
    metrics = cache.get_metrics()
    assert metrics["hits"] == 1
    assert metrics["misses"] == 0


@pytest.mark.unit
def test_cache_rejects_size_mismatch(tmp_path: Path):
    gamelist_dir = tmp_path / "gamelists"
    gamelist_dir.mkdir()

    cache = MetadataCache(gamelist_directory=gamelist_dir)
    cache.put("HASH", {"name": "Cached"}, rom_size=50)

    entry = cache.get("HASH", rom_size=999)
    assert entry is None
    metrics = cache.get_metrics()
    assert metrics["misses"] == 1  # size mismatch counts as miss


@pytest.mark.unit
def test_cache_cleanup_expired(tmp_path: Path):
    gamelist_dir = tmp_path / "gamelists"
    gamelist_dir.mkdir()

    cache = MetadataCache(gamelist_directory=gamelist_dir, ttl_days=0)
    cache.put("OLD", {"name": "Old"})

    removed = cache.cleanup_expired()
    assert removed == 1
    stats = cache.get_stats()
    assert stats["total_entries"] == 0
