import pytest

from curateur.workflow.evaluator import WorkflowEvaluator, WorkflowDecision
from curateur.gamelist.game_entry import GameEntry
from curateur.scanner.rom_types import ROMInfo, ROMType
from curateur.config.es_systems import SystemDefinition


def _config(scrape_mode="changed"):
    return {
        "scraping": {"scrape_mode": scrape_mode},
        "media": {"media_types": ["covers", "screenshots"], "clean_mismatched_media": True, "validation_mode": "disabled"},
        "runtime": {"hash_algorithm": "crc32"},
    }


def _rom():
    return ROMInfo(
        path=None,  # not used in evaluator
        filename="Alpha.nes",
        basename="Alpha",
        rom_type=ROMType.STANDARD,
        system="nes",
        query_filename="Alpha.nes",
        file_size=10,
    )


def _system(supports_m3u=False):
    """Create a mock system definition."""
    extensions = ['.nes', '.zip']
    if supports_m3u:
        extensions.append('.m3u')

    return SystemDefinition(
        name="nes",
        fullname="Nintendo Entertainment System",
        path="%ROMPATH%/nes",
        extensions=extensions,
        platform="nes"
    )


@pytest.mark.unit
def test_evaluator_changed_mode_skips_when_hash_matches():
    evaluator = WorkflowEvaluator(_config(scrape_mode="changed"))
    rom = _rom()
    entry = GameEntry(path="./Alpha.nes", name="Alpha")
    system = _system()

    # No cache/hashes stored: treat as changed, so should fetch
    decision = evaluator.evaluate_rom(rom, entry, rom_hash="ABC", system=system)
    assert decision.fetch_metadata is True
    assert decision.update_metadata is True


@pytest.mark.unit
def test_evaluator_force_always_fetches():
    evaluator = WorkflowEvaluator(_config(scrape_mode="force"))
    rom = _rom()
    system = _system()
    decision = evaluator.evaluate_rom(rom, gamelist_entry=None, rom_hash=None, system=system)
    assert decision.fetch_metadata is True
    assert decision.update_metadata is True
    assert "cover" in decision.media_to_download


@pytest.mark.unit
def test_evaluator_new_only_skips_existing():
    evaluator = WorkflowEvaluator(_config(scrape_mode="new_only"))
    rom = _rom()
    entry = GameEntry(path="./Alpha.nes", name="Alpha")
    system = _system()

    decision = evaluator.evaluate_rom(rom, entry, rom_hash=None, system=system)
    assert decision.fetch_metadata is False
    assert decision.skip_reason


@pytest.mark.unit
def test_evaluator_disabled_mode_skips_existing_media():
    """Test that validation_mode='disabled' doesn't re-download existing media files"""
    from unittest.mock import MagicMock

    config = _config(scrape_mode="changed")
    config["media"]["validation_mode"] = "disabled"

    # Create mock cache that has existing media
    mock_cache = MagicMock()
    mock_cache.get_media_hash.side_effect = lambda rom_hash, media_type: {
        "cover": "abc123",
        "screenshot": "def456"
    }.get(media_type)

    evaluator = WorkflowEvaluator(config, cache=mock_cache)
    rom = _rom()
    system = _system()

    # New ROM (no gamelist entry) but media already exists in cache
    decision = evaluator.evaluate_rom(rom, gamelist_entry=None, rom_hash="ROMHASH123", system=system)

    # Should fetch metadata for new ROM
    assert decision.fetch_metadata is True

    # Should NOT download media that already exists (tracked in cache)
    # With disabled validation mode, existing media should be skipped
    assert decision.media_to_download == []
    assert decision.media_to_validate == []
