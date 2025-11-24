from pathlib import Path

import pytest

from curateur.workflow.checkpoint import CheckpointManager, prompt_resume_from_checkpoint


def _config(checkpoint_interval=1):
    return {"runtime": {"checkpoint_interval": checkpoint_interval}}


@pytest.mark.unit
def test_checkpoint_save_and_load(tmp_path):
    gamelist_dir = tmp_path / "gamelists"
    mgr = CheckpointManager(str(gamelist_dir), "nes", _config(checkpoint_interval=1))

    mgr.add_processed_rom("alpha.zip", action="full_scrape", success=True)
    mgr.save_checkpoint(force=False)

    loaded = mgr.load_checkpoint()
    assert loaded is not None
    assert loaded.system == "nes"
    assert "alpha.zip" in loaded.processed_roms


@pytest.mark.unit
def test_checkpoint_disable_interval(tmp_path):
    gamelist_dir = tmp_path / "gamelists"
    mgr = CheckpointManager(str(gamelist_dir), "nes", _config(checkpoint_interval=0))
    mgr.add_processed_rom("alpha.zip", action="full_scrape", success=True)
    mgr.save_checkpoint()
    assert not mgr.checkpoint_file.exists()


@pytest.mark.unit
def test_prompt_resume_from_checkpoint(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "y")
    from types import SimpleNamespace

    fake_data = SimpleNamespace(
        system="nes",
        timestamp="now",
        stats={"total_roms": 1, "processed": 1, "successful": 1, "failed": 0, "skipped": 0, "media_only": 0},
        failed_roms=[],
        api_quota={"requests_today": 0, "max_requests_per_day": 0},
    )
    assert prompt_resume_from_checkpoint(fake_data) is True
