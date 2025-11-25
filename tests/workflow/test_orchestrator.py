import asyncio
from pathlib import Path

import pytest

from curateur.workflow.orchestrator import WorkflowOrchestrator
from curateur.config.es_systems import SystemDefinition


class DummyAPIClient:
    def __init__(self):
        self.cache = None
        self.cache_cleared = False
        self.calls = []
        self.search_game = None


class DummyWorkQueue:
    def __init__(self):
        self.reset_called = False

    def reset_for_new_system(self):
        self.reset_called = True

    def get_stats(self):
        return {"total": 0}

    def get_failed_items(self):
        return []

    def reset_for_new_system(self):
        self.reset_called = True

    def get_stats(self):
        return {"processed": 0, "failed": 0, "pending": 0, "max_retries": 3}


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scrape_system_no_roms(monkeypatch, tmp_path):
    rom_dir = tmp_path / "roms"
    media_dir = tmp_path / "media"
    gamelist_dir = tmp_path / "gamelists"
    for d in (rom_dir, media_dir, gamelist_dir):
        d.mkdir()

    system = SystemDefinition(
        name="nes",
        fullname="NES",
        path=str(rom_dir),
        extensions=[".nes"],
        platform="nes",
    )

    work_queue = DummyWorkQueue()
    orchestrator = WorkflowOrchestrator(
        api_client=DummyAPIClient(),
        rom_directory=rom_dir,
        media_directory=media_dir,
        gamelist_directory=gamelist_dir,
        work_queue=work_queue,
        config={"runtime": {"enable_cache": False}, "scraping": {}, "paths": {}, "media": {}},
        dry_run=True,
        clear_cache=True,
    )

    monkeypatch.setattr("curateur.workflow.orchestrator.scan_system", lambda *args, **kwargs: [])
    async def fake_scrape(*args, **kwargs):
        return [], []
    monkeypatch.setattr(orchestrator, "_scrape_roms_parallel", fake_scrape)
    monkeypatch.setattr(orchestrator, "_write_summary_log", lambda *args, **kwargs: None)

    result = await orchestrator.scrape_system(system)

    assert result.total_roms == 0
    assert result.scraped == 0
    assert result.failed == 0
    assert result.skipped == 0
    assert work_queue.reset_called is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scrape_system_parse_failure_and_skip(monkeypatch, tmp_path):
    rom_dir = tmp_path / "roms"
    media_dir = tmp_path / "media"
    gamelist_dir = tmp_path / "gamelists"
    for d in (rom_dir, media_dir, gamelist_dir):
        d.mkdir()

    system = SystemDefinition(
        name="nes",
        fullname="NES",
        path=str(rom_dir),
        extensions=[".nes"],
        platform="nes",
    )

    work_queue = DummyWorkQueue()
    orchestrator = WorkflowOrchestrator(
        api_client=DummyAPIClient(),
        rom_directory=rom_dir,
        media_directory=media_dir,
        gamelist_directory=gamelist_dir,
        work_queue=work_queue,
        config={"runtime": {"enable_cache": True}, "scraping": {}, "paths": {}, "media": {}},
        dry_run=False,
        clear_cache=True,
    )

    # Pretend scan finds a ROM
    rom_file = rom_dir / "Alpha.nes"
    rom_file.write_text("rom")
    monkeypatch.setattr(
        "curateur.workflow.orchestrator.scan_system",
        lambda *args, **kwargs: [
            type("R", (), {"path": rom_file, "filename": "Alpha.nes", "basename": "Alpha", "rom_type": None, "system": "nes"})
        ],
    )
    # Parser raises, so existing_entries becomes []
    monkeypatch.setattr("curateur.workflow.orchestrator.GamelistParser.parse_gamelist", lambda self, path: (_ for _ in ()).throw(Exception("bad xml")))

    async def fake_scrape(system, roms, media_types, preferred_regions, existing_entries):
        return [], []

    monkeypatch.setattr(orchestrator, "_scrape_roms_parallel", fake_scrape)
    monkeypatch.setattr(orchestrator, "_write_summary_log", lambda *args, **kwargs: None)

    result = await orchestrator.scrape_system(system)
    assert result.total_roms == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scrape_system_integrity_failure_prompts_skip(monkeypatch, tmp_path):
    rom_dir = tmp_path / "roms"
    media_dir = tmp_path / "media"
    gamelist_dir = tmp_path / "gamelists"
    for d in (rom_dir, media_dir, gamelist_dir):
        d.mkdir()

    system = SystemDefinition(
        name="nes",
        fullname="NES",
        path=str(rom_dir),
        extensions=[".nes"],
        platform="nes",
    )

    work_queue = DummyWorkQueue()
    orchestrator = WorkflowOrchestrator(
        api_client=DummyAPIClient(),
        rom_directory=rom_dir,
        media_directory=media_dir,
        gamelist_directory=gamelist_dir,
        work_queue=work_queue,
        config={"runtime": {"enable_cache": True}, "scraping": {}, "paths": {}, "media": {}},
        dry_run=False,
        clear_cache=False,
    )

    # Scan finds one ROM
    rom_file = rom_dir / "Alpha.nes"
    rom_file.write_text("rom")
    monkeypatch.setattr(
        "curateur.workflow.orchestrator.scan_system",
        lambda *args, **kwargs: [
            type("R", (), {"path": rom_file, "filename": "Alpha.nes", "basename": "Alpha", "rom_type": None, "system": "nes"})
        ],
    )
    # Existing gamelist with bad integrity; prompt returns False to skip
    gamelist = gamelist_dir / "nes" / "gamelist.xml"
    gamelist.parent.mkdir(parents=True, exist_ok=True)
    gamelist.write_text("<gameList></gameList>")

    monkeypatch.setattr(
        orchestrator.integrity_validator,
        "validate",
        lambda entries, roms: type("V", (), {"is_valid": False, "match_ratio": 0.1, "missing_roms": [], "orphaned_entries": []}),
    )
    monkeypatch.setattr(
        orchestrator,
        "_prompt_gamelist_validation_failure",
        lambda system_name, validation_result: False,
    )
    monkeypatch.setattr(orchestrator, "_write_summary_log", lambda *args, **kwargs: None)
    async def fake_scrape(*args, **kwargs):
        return [], []
    monkeypatch.setattr(orchestrator, "_scrape_roms_parallel", fake_scrape)

    result = await orchestrator.scrape_system(system)
    assert result.skipped == 1


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scrape_system_cache_disabled_clear_cache_warning(monkeypatch, tmp_path, caplog):
    rom_dir = tmp_path / "roms"
    media_dir = tmp_path / "media"
    gamelist_dir = tmp_path / "gamelists"
    for d in (rom_dir, media_dir, gamelist_dir):
        d.mkdir()

    system = SystemDefinition(
        name="nes",
        fullname="NES",
        path=str(rom_dir),
        extensions=[".nes"],
        platform="nes",
    )

    orchestrator = WorkflowOrchestrator(
        api_client=DummyAPIClient(),
        rom_directory=rom_dir,
        media_directory=media_dir,
        gamelist_directory=gamelist_dir,
        work_queue=DummyWorkQueue(),
        config={"runtime": {"enable_cache": False}, "scraping": {}, "paths": {}, "media": {}},
        dry_run=True,
        clear_cache=True,
    )

    async def fake_scrape_none(*args, **kwargs):
        return [], []
    monkeypatch.setattr("curateur.workflow.orchestrator.scan_system", lambda *args, **kwargs: [])
    monkeypatch.setattr(orchestrator, "_scrape_roms_parallel", fake_scrape_none)
    monkeypatch.setattr(orchestrator, "_write_summary_log", lambda *args, **kwargs: None)

    with caplog.at_level("WARNING"):
        result = await orchestrator.scrape_system(system)

    assert any("cache is DISABLED" in rec.message or "cache" in rec.message for rec in caplog.records)
    assert result.total_roms == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scrape_system_writes_unmatched_and_not_found(monkeypatch, tmp_path):
    rom_dir = tmp_path / "roms"
    media_dir = tmp_path / "media"
    gamelist_dir = tmp_path / "gamelists"
    for d in (rom_dir, media_dir, gamelist_dir):
        d.mkdir()

    system = SystemDefinition(
        name="nes",
        fullname="NES",
        path=str(rom_dir),
        extensions=[".nes"],
        platform="nes",
    )

    orchestrator = WorkflowOrchestrator(
        api_client=DummyAPIClient(),
        rom_directory=rom_dir,
        media_directory=media_dir,
        gamelist_directory=gamelist_dir,
        work_queue=DummyWorkQueue(),
        config={"runtime": {"enable_cache": True}, "scraping": {}, "paths": {}, "media": {}},
        dry_run=False,
        clear_cache=False,
    )

    orchestrator.unmatched_roms["nes"] = ["Game.nes"]

    monkeypatch.setattr("curateur.workflow.orchestrator.scan_system", lambda *args, **kwargs: [])
    # Return a not-found list of dicts to trigger summary write
    class SimpleRom:
        def __init__(self, filename):
            self.filename = filename
            self.hash_value = None
            self.hash_type = "crc32"
            self.file_size = 0
            self.path = Path(filename)

    async def fake_scrape_not_found(*args, **kwargs):
        return [], [{"rom_info": SimpleRom("Game.nes"), "error": "404"}]
    monkeypatch.setattr(orchestrator, "_scrape_roms_parallel", fake_scrape_not_found)
    monkeypatch.setattr(orchestrator, "_write_summary_log", lambda *args, **kwargs: None)

    result = await orchestrator.scrape_system(system)
    assert len(result.not_found_items) == 1
    nf = result.not_found_items[0]
    assert nf["error"] == "404"
    assert nf["rom_info"].filename == "Game.nes"
    unmatched_file = orchestrator.paths["gamelists"] / system.name / "unmatched_roms.txt"
    not_found_file = orchestrator.paths["gamelists"] / system.name / "nes_not_found.txt"
    assert unmatched_file.exists()
    assert not_found_file.exists()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scrape_system_dry_run_skips_generate(monkeypatch, tmp_path):
    rom_dir = tmp_path / "roms"
    media_dir = tmp_path / "media"
    gamelist_dir = tmp_path / "gamelists"
    for d in (rom_dir, media_dir, gamelist_dir):
        d.mkdir()

    system = SystemDefinition(
        name="nes",
        fullname="NES",
        path=str(rom_dir),
        extensions=[".nes"],
        platform="nes",
    )

    orchestrator = WorkflowOrchestrator(
        api_client=DummyAPIClient(),
        rom_directory=rom_dir,
        media_directory=media_dir,
        gamelist_directory=gamelist_dir,
        work_queue=DummyWorkQueue(),
        config={"runtime": {"enable_cache": True, "dry_run": True}, "scraping": {}, "paths": {}, "media": {}},
        dry_run=True,
        clear_cache=False,
    )

    monkeypatch.setattr("curateur.workflow.orchestrator.scan_system", lambda *args, **kwargs: [])
    async def fake_scrape(*args, **kwargs):
        return [], []
    monkeypatch.setattr(orchestrator, "_scrape_roms_parallel", fake_scrape)
    # ensure _generate_gamelist would raise if called
    monkeypatch.setattr(orchestrator, "_generate_gamelist", lambda *args, **kwargs: (_ for _ in ()).throw(Exception("should not be called")))
    monkeypatch.setattr(orchestrator, "_write_summary_log", lambda *args, **kwargs: None)

    result = await orchestrator.scrape_system(system)
    assert result.scraped == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_write_unmatched_and_not_found_errors(monkeypatch, tmp_path, caplog):
    rom_dir = tmp_path / "roms"
    media_dir = tmp_path / "media"
    gamelist_dir = tmp_path / "gamelists"
    for d in (rom_dir, media_dir, gamelist_dir):
        d.mkdir()

    system = SystemDefinition(
        name="nes",
        fullname="NES",
        path=str(rom_dir),
        extensions=[".nes"],
        platform="nes",
    )

    orchestrator = WorkflowOrchestrator(
        api_client=DummyAPIClient(),
        rom_directory=rom_dir,
        media_directory=media_dir,
        gamelist_directory=gamelist_dir,
        work_queue=DummyWorkQueue(),
        config={"runtime": {"enable_cache": True}, "scraping": {}, "paths": {}, "media": {}},
        dry_run=False,
        clear_cache=False,
    )
    orchestrator.unmatched_roms["nes"] = ["Game.nes"]

    monkeypatch.setattr("curateur.workflow.orchestrator.scan_system", lambda *args, **kwargs: [])
    async def fake_scrape(*args, **kwargs):
        # malformed not_found_items to trigger error in writer
        return [], [{"rom_info": None, "error": None}]
    monkeypatch.setattr(orchestrator, "_scrape_roms_parallel", fake_scrape)
    monkeypatch.setattr(orchestrator, "_write_summary_log", lambda *args, **kwargs: None)
    # Force writing functions to raise
    monkeypatch.setattr(orchestrator, "_write_unmatched_roms", lambda *args, **kwargs: (_ for _ in ()).throw(Exception("fail unmatched")))
    monkeypatch.setattr(orchestrator, "_write_not_found_summary", lambda *args, **kwargs: (_ for _ in ()).throw(Exception("fail notfound")))

    with caplog.at_level("WARNING"):
        result = await orchestrator.scrape_system(system)
    assert result.not_found_items == [{"rom_info": None, "error": None}]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_search_fallback_auto_select(monkeypatch, tmp_path):
    rom_dir = tmp_path / "roms"
    media_dir = tmp_path / "media"
    gamelist_dir = tmp_path / "gamelists"
    for d in (rom_dir, media_dir, gamelist_dir):
        d.mkdir()

    rom_info = type(
        "R",
        (),
        {"filename": "Alpha.nes", "path": rom_dir / "Alpha.nes", "file_size": 1, "hash_value": None, "system": "nes"},
    )

    orchestrator = WorkflowOrchestrator(
        api_client=DummyAPIClient(),
        rom_directory=rom_dir,
        media_directory=media_dir,
        gamelist_directory=gamelist_dir,
        work_queue=DummyWorkQueue(),
        config={"runtime": {"enable_cache": True}, "scraping": {}, "paths": {}, "media": {}},
        dry_run=False,
        clear_cache=False,
        enable_search_fallback=True,
        search_confidence_threshold=0.5,
    )

    async def fake_search(rom_info, shutdown_event=None, max_results=5):
        return [{"names": {"en": "Alpha"}, "romsize": 1}]

    monkeypatch.setattr(orchestrator.api_client, "search_game", fake_search)

    result = await orchestrator._search_fallback(rom_info, preferred_regions=["us"])
    assert result["names"]["en"] == "Alpha"


@pytest.mark.unit
def test_generate_gamelist_returns_none_when_no_scraped_games(tmp_path):
    orchestrator = WorkflowOrchestrator(
        api_client=DummyAPIClient(),
        rom_directory=tmp_path,
        media_directory=tmp_path,
        gamelist_directory=tmp_path,
        work_queue=DummyWorkQueue(),
        config={"runtime": {"enable_cache": True}, "scraping": {}, "paths": {}, "media": {}},
    )
    system = SystemDefinition(
        name="nes",
        fullname="NES",
        path=str(tmp_path),
        extensions=[".nes"],
        platform="nes",
    )
    assert orchestrator._generate_gamelist(system, []) is None
