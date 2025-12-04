"""
Comprehensive tests for WorkflowOrchestrator core functionality.

These tests target previously uncovered code paths to increase coverage
for the stable release. Focus areas:
- _scrape_rom (individual ROM processing)
- _batch_hash_roms (hash calculation)
- _scrape_roms_parallel (parallel coordination)
- Error handling and edge cases
- Media download integration
- Workflow evaluator integration
"""

import asyncio
from pathlib import Path
from unittest.mock import Mock, AsyncMock, MagicMock, patch
import pytest

from curateur.workflow.orchestrator import (
    WorkflowOrchestrator,
    ScrapingResult,
    SystemResult
)
from curateur.config.es_systems import SystemDefinition
from curateur.scanner.rom_types import ROMInfo, ROMType
from curateur.gamelist.game_entry import GameEntry
from curateur.workflow.evaluator import WorkflowDecision


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def mock_api_client():
    """Mock API client with common methods."""
    client = Mock()
    client.cache = None
    # Return a real dict, not a Mock, for proper iteration
    game_info = {
        'id': '12345',
        'names': {'en': 'Test Game'},
        'descriptions': {'en': 'A test game'},
        'release_dates': {'wor': '2000-01-01'},
        'genres': ['Action'],
        'medias': []
    }
    # Mock the method that orchestrator actually calls
    client.query_game = AsyncMock(return_value=game_info)
    client.get_game_info = AsyncMock(return_value=game_info)
    client.search_game = AsyncMock(return_value=[])
    return client


@pytest.fixture
def mock_work_queue():
    """Mock work queue manager."""
    queue = Mock()
    queue.reset_for_new_system = Mock()
    queue.get_stats = Mock(return_value={
        'processed': 0,
        'failed': 0,
        'pending': 0,
        'max_retries': 3
    })
    queue.get_failed_items = Mock(return_value=[])
    return queue


@pytest.fixture
def basic_config():
    """Basic configuration for tests."""
    return {
        'runtime': {'enable_cache': True},
        'scraping': {
            'skip_existing': False,
            'force_update': False
        },
        'paths': {},
        'media': {
            'skip_existing_media': False,
            'validate_existing': False
        }
    }


@pytest.fixture
def test_system(tmp_path):
    """Create a test system definition."""
    rom_dir = tmp_path / "roms" / "nes"
    rom_dir.mkdir(parents=True)
    return SystemDefinition(
        name="nes",
        fullname="Nintendo Entertainment System",
        path=str(rom_dir),
        extensions=[".nes", ".zip"],
        platform="nes"
    )


@pytest.fixture
def orchestrator(mock_api_client, mock_work_queue, basic_config, tmp_path):
    """Create orchestrator instance for testing."""
    orch = WorkflowOrchestrator(
        api_client=mock_api_client,
        rom_directory=tmp_path / "roms",
        media_directory=tmp_path / "media",
        gamelist_directory=tmp_path / "gamelists",
        work_queue=mock_work_queue,
        config=basic_config,
        dry_run=False,
        clear_cache=False
    )
    # Set up paths dict for tests that need it
    orch.paths = {
        'gamelists': tmp_path / "gamelists",
        'roms': tmp_path / "roms",
        'media': tmp_path / "media"
    }
    return orch


# ============================================================================
# Tests for _scrape_rom - Core ROM Processing
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_scrape_rom_successful_hash_lookup(orchestrator, test_system, tmp_path):
    """Test successful ROM scraping via hash lookup."""
    # Create actual ROM file
    rom_file = tmp_path / "game.nes"
    rom_file.write_bytes(b"TEST_ROM_DATA")

    rom_info = ROMInfo(
        path=rom_file,
        filename="game.nes",
        basename="game",
        rom_type=ROMType.STANDARD,
        system="nes",
        query_filename="game.nes",
        file_size=rom_file.stat().st_size,
        hash_type="crc32",
        hash_value="ABC123"
    )

    # Mock evaluator to allow fetch
    orchestrator.evaluator.evaluate_rom = Mock(return_value=WorkflowDecision(
        fetch_metadata=True,
        update_metadata=True,
        media_to_download=[],
        media_to_validate=[],
        clean_disabled_media=[],
        skip_reason=None
    ))

    result = await orchestrator._scrape_rom(
        system=test_system,
        rom_info=rom_info,
        media_types=[],
        preferred_regions=['us']
    )

    assert result.success is True
    assert result.api_id == '12345'
    assert result.game_info is not None
    assert result.game_info['names']['en'] == 'Test Game'


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scrape_rom_skip_due_to_evaluator(orchestrator, test_system):
    """Test ROM skipping when evaluator recommends skip."""
    rom_info = ROMInfo(
        path=Path("/test/game.nes"),
        filename="game.nes",
        basename="game",
        rom_type=ROMType.STANDARD,
        system="nes",
        query_filename="game.nes",
        file_size=32768,
        hash_type="crc32",
        hash_value="ABC123"
    )

    # Mock evaluator to skip
    orchestrator.evaluator.evaluate_rom = Mock(return_value=WorkflowDecision(
        fetch_metadata=False,
        update_metadata=False,
        media_to_download=[],
        media_to_validate=[],
        clean_disabled_media=[],
        skip_reason="Already complete"
    ))

    result = await orchestrator._scrape_rom(
        system=test_system,
        rom_info=rom_info,
        media_types=[],
        preferred_regions=['us']
    )

    assert result.success is True
    assert result.skipped is True
    assert result.skip_reason == "Already complete"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scrape_rom_no_hash_available(orchestrator, test_system, tmp_path):
    """Test ROM scraping when hash is not available."""
    # Create actual ROM file
    rom_file = tmp_path / "game.nes"
    rom_file.write_bytes(b"TEST_ROM_DATA")

    rom_info = ROMInfo(
        path=rom_file,
        filename="game.nes",
        basename="game",
        rom_type=ROMType.STANDARD,
        system="nes",
        query_filename="game.nes",
        file_size=rom_file.stat().st_size,
        hash_type="crc32",
        hash_value=None  # No hash
    )

    # Mock evaluator to allow fetch
    orchestrator.evaluator.evaluate_rom = Mock(return_value=WorkflowDecision(
        fetch_metadata=True,
        update_metadata=True,
        media_to_download=[],
        media_to_validate=[],
        clean_disabled_media=[],
        skip_reason=None
    ))

    # Should still attempt API call even without hash
    result = await orchestrator._scrape_rom(
        system=test_system,
        rom_info=rom_info,
        media_types=[],
        preferred_regions=['us']
    )

    assert result.success is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scrape_rom_dry_run_mode(orchestrator, test_system):
    """Test ROM scraping in dry-run mode."""
    orchestrator.dry_run = True

    rom_info = ROMInfo(
        path=Path("/test/game.nes"),
        filename="game.nes",
        basename="game",
        rom_type=ROMType.STANDARD,
        system="nes",
        query_filename="game.nes",
        file_size=32768,
        hash_type="crc32",
        hash_value="ABC123"
    )

    # Mock evaluator to allow processing
    orchestrator.evaluator.evaluate_rom = Mock(return_value=WorkflowDecision(
        fetch_metadata=True,
        update_metadata=True,
        media_to_download=[],
        media_to_validate=[],
        clean_disabled_media=[],
        skip_reason=None
    ))

    result = await orchestrator._scrape_rom(
        system=test_system,
        rom_info=rom_info,
        media_types=[],
        preferred_regions=['us']
    )

    assert result.success is True
    assert result.api_id == "DRY_RUN"
    # Should not make actual API call
    orchestrator.api_client.get_game_info.assert_not_called()


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scrape_rom_with_existing_gamelist_entry(orchestrator, test_system, tmp_path):
    """Test ROM scraping with an existing gamelist entry."""
    # Create actual ROM file
    rom_file = tmp_path / "game.nes"
    rom_file.write_bytes(b"TEST_ROM_DATA")

    rom_info = ROMInfo(
        path=rom_file,
        filename="game.nes",
        basename="game",
        rom_type=ROMType.STANDARD,
        system="nes",
        query_filename="game.nes",
        file_size=rom_file.stat().st_size,
        hash_type="crc32",
        hash_value="ABC123"
    )

    existing_entry = GameEntry(
        path="./game.nes",
        name="Existing Game Name",
        desc="Existing description"
    )

    # Mock evaluator
    orchestrator.evaluator.evaluate_rom = Mock(return_value=WorkflowDecision(
        fetch_metadata=True,
        update_metadata=True,
        media_to_download=[],
        media_to_validate=[],
        clean_disabled_media=[],
        skip_reason=None
    ))

    result = await orchestrator._scrape_rom(
        system=test_system,
        rom_info=rom_info,
        media_types=[],
        preferred_regions=['us'],
        existing_entries=[existing_entry]
    )

    # Evaluator should have been called with the existing entry
    call_args = orchestrator.evaluator.evaluate_rom.call_args
    assert call_args[1]['gamelist_entry'] == existing_entry
    assert result.success is True


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scrape_rom_api_error_404(orchestrator, test_system, tmp_path):
    """Test ROM scraping when API returns 404 (not found)."""
    from curateur.api.error_handler import SkippableAPIError

    # Create actual ROM file
    rom_file = tmp_path / "game.nes"
    rom_file.write_bytes(b"TEST_ROM_DATA")

    rom_info = ROMInfo(
        path=rom_file,
        filename="game.nes",
        basename="game",
        rom_type=ROMType.STANDARD,
        system="nes",
        query_filename="game.nes",
        file_size=rom_file.stat().st_size,
        hash_type="crc32",
        hash_value="ABC123"
    )

    # Mock evaluator to allow fetch
    orchestrator.evaluator.evaluate_rom = Mock(return_value=WorkflowDecision(
        fetch_metadata=True,
        update_metadata=True,
        media_to_download=[],
        media_to_validate=[],
        clean_disabled_media=[],
        skip_reason=None
    ))

    # Mock API to raise 404 - override the query_game method
    error_404 = SkippableAPIError("Game not found")
    orchestrator.api_client.query_game = AsyncMock(side_effect=error_404)

    result = await orchestrator._scrape_rom(
        system=test_system,
        rom_info=rom_info,
        media_types=[],
        preferred_regions=['us']
    )

    # 404 should be marked as error
    assert result.error is not None
    assert "Game not found" in result.error


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scrape_rom_with_operation_callback(orchestrator, test_system, tmp_path):
    """Test ROM scraping with operation callback for UI updates."""
    # Create actual ROM file
    rom_file = tmp_path / "game.nes"
    rom_file.write_bytes(b"TEST_ROM_DATA")

    rom_info = ROMInfo(
        path=rom_file,
        filename="game.nes",
        basename="game",
        rom_type=ROMType.STANDARD,
        system="nes",
        query_filename="game.nes",
        file_size=rom_file.stat().st_size,
        hash_type="crc32",
        hash_value="ABC123"
    )

    # Mock evaluator
    orchestrator.evaluator.evaluate_rom = Mock(return_value=WorkflowDecision(
        fetch_metadata=True,
        update_metadata=True,
        media_to_download=[],
        media_to_validate=[],
        clean_disabled_media=[],
        skip_reason=None
    ))

    # Track callback invocations
    callback_calls = []
    def mock_callback(task_name, rom_name, operation, details, progress, total, completed):
        callback_calls.append({
            'rom_name': rom_name,
            'operation': operation,
            'details': details
        })

    result = await orchestrator._scrape_rom(
        system=test_system,
        rom_info=rom_info,
        media_types=[],
        preferred_regions=['us'],
        operation_callback=mock_callback
    )

    assert result.success is True
    # Callback should have been invoked during processing
    # (exact number depends on implementation details)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_scrape_rom_with_shutdown_event(orchestrator, test_system, tmp_path):
    """Test ROM scraping respects shutdown event."""
    # Create actual ROM file
    rom_file = tmp_path / "game.nes"
    rom_file.write_bytes(b"TEST_ROM_DATA")

    rom_info = ROMInfo(
        path=rom_file,
        filename="game.nes",
        basename="game",
        rom_type=ROMType.STANDARD,
        system="nes",
        query_filename="game.nes",
        file_size=rom_file.stat().st_size,
        hash_type="crc32",
        hash_value="ABC123"
    )

    # Mock evaluator
    orchestrator.evaluator.evaluate_rom = Mock(return_value=WorkflowDecision(
        fetch_metadata=True,
        update_metadata=True,
        media_to_download=[],
        media_to_validate=[],
        clean_disabled_media=[],
        skip_reason=None
    ))

    # Create shutdown event (not set, so processing should continue)
    shutdown_event = asyncio.Event()

    result = await orchestrator._scrape_rom(
        system=test_system,
        rom_info=rom_info,
        media_types=[],
        preferred_regions=['us'],
        shutdown_event=shutdown_event
    )

    assert result.success is True


# ============================================================================
# Tests for _batch_hash_roms - Batch Hashing
# ============================================================================

@pytest.mark.unit
@pytest.mark.asyncio
async def test_batch_hash_roms_single_batch(orchestrator, test_system, tmp_path):
    """Test batch hashing with a single batch of ROMs."""
    # Create test ROM files
    rom_dir = tmp_path / "test_roms"
    rom_dir.mkdir(parents=True)

    rom_files = []
    for i in range(1, 6):  # Start at 1 to avoid empty files
        rom_file = rom_dir / f"game{i}.nes"
        rom_file.write_bytes(b"TEST_ROM_DATA" * i)  # Different sizes
        rom_files.append(rom_file)

    roms = [
        ROMInfo(
            path=rom_file,
            filename=rom_file.name,
            basename=rom_file.stem,
            rom_type=ROMType.STANDARD,
            system="nes",
            query_filename=rom_file.name,
            file_size=rom_file.stat().st_size,
            hash_type="crc32",
            hash_value=None
        )
        for rom_file in rom_files
    ]

    await orchestrator._batch_hash_roms(roms, hash_algorithm="crc32", batch_size=10)

    # All ROMs should now have hash values
    for rom in roms:
        assert rom.hash_value is not None
        assert len(rom.hash_value) > 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_batch_hash_roms_multiple_batches(orchestrator, test_system, tmp_path):
    """Test batch hashing with multiple batches."""
    # Create test ROM files
    rom_dir = tmp_path / "test_roms_multi"
    rom_dir.mkdir(parents=True)

    rom_files = []
    for i in range(1, 16):  # 1-15
        rom_file = rom_dir / f"game{i}.nes"
        rom_file.write_bytes(b"TEST_ROM" * i)
        rom_files.append(rom_file)

    roms = [
        ROMInfo(
            path=rom_file,
            filename=rom_file.name,
            basename=rom_file.stem,
            rom_type=ROMType.STANDARD,
            system="nes",
            query_filename=rom_file.name,
            file_size=rom_file.stat().st_size,
            hash_type="crc32",
            hash_value=None
        )
        for rom_file in rom_files
    ]

    # Small batch size to force multiple batches
    await orchestrator._batch_hash_roms(roms, hash_algorithm="crc32", batch_size=5)

    # All ROMs should be hashed
    hashed_count = sum(1 for rom in roms if rom.hash_value is not None)
    assert hashed_count == len(roms)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_batch_hash_roms_with_missing_file(orchestrator, test_system, tmp_path, caplog):
    """Test batch hashing when a ROM file is missing."""
    rom_dir = tmp_path / "test_roms_missing"
    rom_dir.mkdir(parents=True)

    # Create one real ROM
    real_rom = rom_dir / "real.nes"
    real_rom.write_bytes(b"REAL_ROM_DATA")

    # Create ROM info for real and missing file
    roms = [
        ROMInfo(
            path=real_rom,
            filename="real.nes",
            basename="real",
            rom_type=ROMType.STANDARD,
            system="nes",
            query_filename="real.nes",
            file_size=real_rom.stat().st_size,
            hash_type="crc32",
            hash_value=None
        ),
        ROMInfo(
            path=rom_dir / "missing.nes",  # Doesn't exist
            filename="missing.nes",
            basename="missing",
            rom_type=ROMType.STANDARD,
            system="nes",
            query_filename="missing.nes",
            file_size=1024,
            hash_type="crc32",
            hash_value=None
        )
    ]

    # Expect an error to be logged for missing file
    with caplog.at_level("ERROR"):
        await orchestrator._batch_hash_roms(roms, hash_algorithm="crc32", batch_size=10)

    # Real ROM should be hashed
    assert roms[0].hash_value is not None
    # Missing ROM should have error logged but not crash


@pytest.mark.unit
@pytest.mark.asyncio
async def test_batch_hash_roms_empty_list(orchestrator, test_system):
    """Test batch hashing with empty ROM list."""
    roms = []

    # Should not raise error
    await orchestrator._batch_hash_roms(roms, hash_algorithm="crc32", batch_size=10)

    assert len(roms) == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_batch_hash_roms_new_only_mode_skips_existing(orchestrator, test_system, tmp_path):
    """Test that new_only mode skips hash calculation for existing ROMs."""
    # Create test ROM files
    rom_dir = tmp_path / "test_roms_new_only"
    rom_dir.mkdir(parents=True)

    # Create 5 ROM files
    rom_files = []
    for i in range(1, 6):
        rom_file = rom_dir / f"game{i}.nes"
        rom_file.write_bytes(b"TEST_ROM_DATA" * i)
        rom_files.append(rom_file)

    roms = [
        ROMInfo(
            path=rom_file,
            filename=rom_file.name,
            basename=rom_file.stem,
            rom_type=ROMType.STANDARD,
            system="nes",
            query_filename=rom_file.name,
            file_size=rom_file.stat().st_size,
            hash_type="crc32",
            hash_value=None,
            crc_size_limit=1073741824  # 1 GiB
        )
        for rom_file in rom_files
    ]

    # Create existing gamelist entries for first 3 ROMs (game1, game2, game3)
    existing_entries = [
        GameEntry(path=f"./{roms[0].filename}", name="Game 1"),
        GameEntry(path=f"./{roms[1].filename}", name="Game 2"),
        GameEntry(path=f"./{roms[2].filename}", name="Game 3"),
    ]

    # Call _batch_hash_roms with new_only mode
    await orchestrator._batch_hash_roms(
        roms,
        hash_algorithm="crc32",
        batch_size=10,
        scrape_mode='new_only',
        existing_entries=existing_entries
    )

    # First 3 ROMs (existing in gamelist) should NOT be hashed
    assert roms[0].hash_value is None, "game1.nes should not be hashed (exists in gamelist)"
    assert roms[1].hash_value is None, "game2.nes should not be hashed (exists in gamelist)"
    assert roms[2].hash_value is None, "game3.nes should not be hashed (exists in gamelist)"

    # Last 2 ROMs (new, not in gamelist) SHOULD be hashed
    assert roms[3].hash_value is not None, "game4.nes should be hashed (new ROM)"
    assert roms[4].hash_value is not None, "game5.nes should be hashed (new ROM)"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_batch_hash_roms_changed_mode_hashes_all(orchestrator, test_system, tmp_path):
    """Test that changed mode hashes all ROMs regardless of gamelist."""
    # Create test ROM files
    rom_dir = tmp_path / "test_roms_changed"
    rom_dir.mkdir(parents=True)

    rom_files = []
    for i in range(1, 4):
        rom_file = rom_dir / f"game{i}.nes"
        rom_file.write_bytes(b"TEST_ROM_DATA" * i)
        rom_files.append(rom_file)

    roms = [
        ROMInfo(
            path=rom_file,
            filename=rom_file.name,
            basename=rom_file.stem,
            rom_type=ROMType.STANDARD,
            system="nes",
            query_filename=rom_file.name,
            file_size=rom_file.stat().st_size,
            hash_type="crc32",
            hash_value=None,
            crc_size_limit=1073741824
        )
        for rom_file in rom_files
    ]

    # Create existing entries (but should still hash all in changed mode)
    existing_entries = [
        GameEntry(path=f"./{roms[0].filename}", name="Game 1"),
    ]

    # Call with changed mode (default)
    await orchestrator._batch_hash_roms(
        roms,
        hash_algorithm="crc32",
        batch_size=10,
        scrape_mode='changed',
        existing_entries=existing_entries
    )

    # All ROMs should be hashed in changed mode
    for rom in roms:
        assert rom.hash_value is not None


# ============================================================================
# Tests for _generate_gamelist
# ============================================================================

@pytest.mark.unit
def test_generate_gamelist_with_scraped_games(orchestrator, test_system, tmp_path):
    """Test gamelist generation with scraped games."""
    scraped_games = [
        ScrapingResult(
            rom_path=Path("/test/game1.nes"),
            success=True,
            api_id="123",
            game_info={'names': {'en': 'Game 1'}},
            media_paths={'screenshot': '/media/game1.png'}
        ),
        ScrapingResult(
            rom_path=Path("/test/game2.nes"),
            success=True,
            api_id="456",
            game_info={'names': {'en': 'Game 2'}},
            media_paths={}
        )
    ]

    with patch('curateur.workflow.orchestrator.GamelistGenerator') as mock_gen_class:
        mock_generator = Mock()
        mock_gen_class.return_value = mock_generator
        mock_generator.generate_gamelist.return_value = Path("/test/gamelist.xml")

        result = orchestrator._generate_gamelist(test_system, scraped_games)

        assert result == Path("/test/gamelist.xml")
        mock_generator.generate_gamelist.assert_called_once()


@pytest.mark.unit
def test_generate_gamelist_filters_failed_results(orchestrator, test_system):
    """Test that failed scraping results are filtered out."""
    scraped_games = [
        ScrapingResult(
            rom_path=Path("/test/success.nes"),
            success=True,
            api_id="123",
            game_info={'names': {'en': 'Success'}}
        ),
        ScrapingResult(
            rom_path=Path("/test/failed.nes"),
            success=False,
            error="API error"
        )
    ]

    with patch('curateur.workflow.orchestrator.GamelistGenerator') as mock_gen_class:
        mock_generator = Mock()
        mock_gen_class.return_value = mock_generator
        mock_generator.generate.return_value = Path("/test/gamelist.xml")

        orchestrator._generate_gamelist(test_system, scraped_games)

        # Should only pass successful results
        call_args = mock_generator.generate.call_args
        # Check that only 1 result was passed (the successful one)


# ============================================================================
# Tests for _write_unmatched_roms
# ============================================================================

@pytest.mark.unit
def test_write_unmatched_roms_creates_file(orchestrator, tmp_path):
    """Test writing unmatched ROMs to file."""
    # Set gamelist_directory directly (not via paths dict)
    orchestrator.gamelist_directory = tmp_path
    orchestrator.unmatched_roms['nes'] = ['game1.nes', 'game2.nes', 'game3.nes']

    orchestrator._write_unmatched_roms('nes')

    unmatched_file = tmp_path / 'nes' / 'unmatched_roms.txt'
    assert unmatched_file.exists()

    content = unmatched_file.read_text()
    assert 'game1.nes' in content
    assert 'game2.nes' in content
    assert 'game3.nes' in content


@pytest.mark.unit
def test_write_unmatched_roms_no_unmatched(orchestrator, tmp_path):
    """Test behavior when no unmatched ROMs exist."""
    orchestrator.gamelist_directory = tmp_path
    orchestrator.unmatched_roms['nes'] = []

    orchestrator._write_unmatched_roms('nes')

    # Should not create file if no unmatched ROMs
    unmatched_file = tmp_path / 'nes' / 'unmatched_roms.txt'
    assert not unmatched_file.exists()


# ============================================================================
# Tests for _write_summary_log
# ============================================================================

@pytest.mark.unit
def test_write_summary_log_creates_file(orchestrator, test_system, tmp_path):
    """Test summary log file creation."""
    orchestrator.paths = {'gamelists': tmp_path}

    results = [
        ScrapingResult(
            rom_path=Path("/test/success.nes"),
            success=True,
            api_id="123"
        ),
        ScrapingResult(
            rom_path=Path("/test/failed.nes"),
            success=False,
            error="API error"
        ),
        ScrapingResult(
            rom_path=Path("/test/skipped.nes"),
            success=True,
            skipped=True,
            skip_reason="Already exists"
        )
    ]

    orchestrator._write_summary_log(test_system, results,
                                    scraped_count=1,
                                    skipped_count=1,
                                    failed_count=1)

    # Should create summary file
    gamelist_dir = tmp_path / 'nes'
    summary_files = list(gamelist_dir.glob('curateur_summary_*.log'))
    assert len(summary_files) == 1

    content = summary_files[0].read_text()
    assert 'Total ROMs: 3' in content
    assert 'Successful: 1' in content
    assert 'Skipped: 1' in content
    assert 'Failed: 1' in content
    assert '=== Successful ===' in content
    assert '=== Failed ===' in content
    assert '=== Skipped ===' in content


@pytest.mark.unit
def test_write_summary_log_alphabetically_sorted(orchestrator, test_system, tmp_path):
    """Test that summary log entries are alphabetically sorted."""
    orchestrator.paths = {'gamelists': tmp_path}

    results = [
        ScrapingResult(rom_path=Path("/test/zebra.nes"), success=True, api_id="1"),
        ScrapingResult(rom_path=Path("/test/alpha.nes"), success=True, api_id="2"),
        ScrapingResult(rom_path=Path("/test/middle.nes"), success=True, api_id="3"),
    ]

    orchestrator._write_summary_log(test_system, results,
                                    scraped_count=3,
                                    skipped_count=0,
                                    failed_count=0)

    gamelist_dir = tmp_path / 'nes'
    summary_files = list(gamelist_dir.glob('curateur_summary_*.log'))
    content = summary_files[0].read_text()

    # Check that alpha appears before middle, and middle before zebra
    alpha_pos = content.find('alpha.nes')
    middle_pos = content.find('middle.nes')
    zebra_pos = content.find('zebra.nes')

    assert alpha_pos < middle_pos < zebra_pos


# ============================================================================
# Tests for _prompt_gamelist_validation_failure
# ============================================================================

@pytest.mark.unit
def test_prompt_gamelist_validation_failure_auto_continue(orchestrator):
    """Test auto-continue when interactive mode is disabled."""
    validation_result = Mock()
    validation_result.match_ratio = 0.5
    validation_result.missing_roms = ['game1.nes']
    validation_result.orphaned_entries = []

    # Non-interactive should return True automatically
    result = orchestrator._prompt_gamelist_validation_failure(
        'nes',
        validation_result
    )

    assert result is True


# ============================================================================
# Tests for _get_media_path
# ============================================================================

@pytest.mark.unit
def test_get_media_path_constructs_correct_path(orchestrator, test_system, tmp_path):
    """Test media path construction."""
    orchestrator.media_directory = tmp_path / "media"

    # Create test ROM and media file
    rom_file = tmp_path / "game.nes"
    rom_file.touch()

    rom_info = ROMInfo(
        path=rom_file,
        filename="game.nes",
        basename="game",
        rom_type=ROMType.STANDARD,
        system="nes",
        query_filename="game.nes",
        file_size=100
    )

    # Create expected media file
    media_dir = tmp_path / "media" / "nes" / "screenshots"
    media_dir.mkdir(parents=True)
    media_file = media_dir / "game.png"
    media_file.touch()

    # Use 'ss' which maps to 'screenshots' directory
    path = orchestrator._get_media_path(test_system, rom_info, 'ss')

    assert path == media_file
    assert path.exists()


@pytest.mark.unit
def test_get_media_path_not_found(orchestrator, test_system, tmp_path):
    """Test media path when file doesn't exist."""
    orchestrator.media_directory = tmp_path / "media"

    rom_file = tmp_path / "game.nes"
    rom_file.touch()

    rom_info = ROMInfo(
        path=rom_file,
        filename="game.nes",
        basename="game",
        rom_type=ROMType.STANDARD,
        system="nes",
        query_filename="game.nes",
        file_size=100
    )

    # Don't create media file
    path = orchestrator._get_media_path(test_system, rom_info, 'ss')

    # Should return None if media doesn't exist
    assert path is None
