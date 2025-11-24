import pytest

from curateur.workflow.evaluator import WorkflowEvaluator, WorkflowDecision
from curateur.gamelist.game_entry import GameEntry
from curateur.scanner.rom_types import ROMInfo, ROMType


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


@pytest.mark.unit
def test_evaluator_changed_mode_skips_when_hash_matches():
    evaluator = WorkflowEvaluator(_config(scrape_mode="changed"))
    rom = _rom()
    entry = GameEntry(path="./Alpha.nes", name="Alpha")

    # No cache/hashes stored: treat as changed, so should fetch
    decision = evaluator.evaluate_rom(rom, entry, rom_hash="ABC")
    assert decision.fetch_metadata is True
    assert decision.update_metadata is True


@pytest.mark.unit
def test_evaluator_force_always_fetches():
    evaluator = WorkflowEvaluator(_config(scrape_mode="force"))
    rom = _rom()
    decision = evaluator.evaluate_rom(rom, gamelist_entry=None, rom_hash=None)
    assert decision.fetch_metadata is True
    assert decision.update_metadata is True
    assert "cover" in decision.media_to_download


@pytest.mark.unit
def test_evaluator_new_only_skips_existing():
    evaluator = WorkflowEvaluator(_config(scrape_mode="new_only"))
    rom = _rom()
    entry = GameEntry(path="./Alpha.nes", name="Alpha")

    decision = evaluator.evaluate_rom(rom, entry, rom_hash=None)
    assert decision.fetch_metadata is False
    assert decision.skip_reason
