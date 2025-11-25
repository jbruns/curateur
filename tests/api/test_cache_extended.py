from pathlib import Path

import json
import pytest

from curateur.api.cache import MetadataCache


@pytest.mark.unit
def test_cache_loads_invalid_file_gracefully(tmp_path):
    gamelist_dir = tmp_path / "gamelists"
    gamelist_dir.mkdir()
    cache_file = gamelist_dir / ".cache" / "metadata_cache.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text("not json")

    cache = MetadataCache(gamelist_directory=gamelist_dir)
    # Should not raise; starts empty
    assert cache.get("X") is None
    assert cache.get_metrics()["misses"] >= 0


@pytest.mark.unit
def test_cache_clear_and_stats(tmp_path):
    gamelist_dir = tmp_path / "gamelists"
    gamelist_dir.mkdir()
    cache = MetadataCache(gamelist_directory=gamelist_dir)
    cache.put("A", {"name": "A"})
    assert cache.get_stats()["total_entries"] == 1
    removed = cache.clear()
    assert removed == 1
    assert cache.get_stats()["total_entries"] == 0


@pytest.mark.unit
def test_cache_update_media_hashes(tmp_path):
    gamelist_dir = tmp_path / "gamelists"
    gamelist_dir.mkdir()
    cache = MetadataCache(gamelist_directory=gamelist_dir)
    cache.put("A", {"name": "A"})
    cache.update_media_hashes("A", {"screenshot": "HASH"})
    entry = cache.get("A")
    assert entry["media_hashes"]["screenshot"] == "HASH"


@pytest.mark.unit
def test_cache_cleanup_expired(tmp_path):
    gamelist_dir = tmp_path / "gamelists"
    gamelist_dir.mkdir()
    cache = MetadataCache(gamelist_directory=gamelist_dir, ttl_days=0)
    cache.put("A", {"name": "A"})
    removed = cache.cleanup_expired()
    assert removed >= 1
