"""Tests for HeadlessLogger"""
import logging
import pytest

from curateur.ui.headless_logger import HeadlessLogger


@pytest.mark.unit
def test_headless_logger_initialization():
    """Test basic initialization"""
    logger = HeadlessLogger(config={})
    assert logger.is_paused is False
    assert logger.quit_requested is False
    assert logger.skip_requested is False
    assert logger.stats['successful'] == 0
    assert logger.stats['failed'] == 0
    assert logger.stats['skipped'] == 0
    assert logger.stats['unmatched'] == 0
    assert logger.stats['search_fallback'] == 0
    assert logger.log_handler is None
    assert logger.current_system is None
    assert logger.total_systems == 0


@pytest.mark.unit
def test_headless_logger_stats_tracking():
    """Test that stats are tracked correctly"""
    logger = HeadlessLogger(config={})

    logger.increment_completed(success=True)
    assert logger.stats['successful'] == 1
    assert logger.processed_in_system == 1

    logger.increment_completed(success=False)
    assert logger.stats['failed'] == 1
    assert logger.processed_in_system == 2

    logger.increment_completed(skipped=True)
    assert logger.stats['skipped'] == 1
    assert logger.processed_in_system == 3

    logger.increment_unmatched()
    assert logger.stats['unmatched'] == 1

    logger.increment_search_fallback()
    assert logger.stats['search_fallback'] == 1


@pytest.mark.unit
def test_headless_logger_no_ops():
    """Test that no-op methods don't raise errors"""
    logger = HeadlessLogger(config={})

    # All these should be no-ops
    logger.start()
    logger.stop()
    logger.reset_pipeline_stages()
    logger.clear_system_operation()
    logger.update_hashing_progress(1, 10, "test")
    logger.update_api_fetch_stage("rom.zip", "start")
    logger.update_media_download_stage("rom.zip", "screenshot", "start")
    logger.increment_media_validated("screenshot")
    logger.increment_media_validation_failed("screenshot")
    logger.increment_gamelist_added()
    logger.increment_gamelist_updated()
    logger.add_completed_game({})
    logger.spotlight_next()
    logger.spotlight_prev()
    logger.set_log_level(3)
    logger.add_log_entry("INFO", "test")
    logger.clear_skip_request()
    logger.clear_quit_request()
    logger.set_shutting_down()
    logger.update_footer({})
    logger.show_error("test")
    logger.show_warning("test")
    logger.show_info("test")
    logger.clear()
    logger.print("test")

    # No errors = success


@pytest.mark.unit
def test_headless_logger_prompt_returns_default():
    """Test that prompts return default without interaction"""
    logger = HeadlessLogger(config={})

    assert logger.prompt_confirm("Test?", default='y') is True
    assert logger.prompt_confirm("Test?", default='n') is False
    assert logger.prompt_confirm("Test?", default='Y') is True
    assert logger.prompt_confirm("Test?", default='N') is False


@pytest.mark.unit
def test_headless_logger_system_tracking():
    """Test system-level tracking"""
    logger = HeadlessLogger(config={})

    logger.update_header("nes", 1, 5)
    assert logger.current_system == "nes"
    assert logger.current_system_index == 1
    assert logger.total_systems == 5
    assert logger.processed_in_system == 0

    logger.update_scanner(150)
    assert logger.total_roms_in_system == 150


@pytest.mark.unit
def test_headless_logger_properties_are_always_false():
    """Test that pause/quit/skip properties are always False"""
    logger = HeadlessLogger(config={})

    # Properties should always be False
    assert logger.is_paused is False
    assert logger.quit_requested is False
    assert logger.skip_requested is False

    # Calling clear methods shouldn't change anything
    logger.clear_skip_request()
    logger.clear_quit_request()

    assert logger.is_paused is False
    assert logger.quit_requested is False
    assert logger.skip_requested is False


@pytest.mark.unit
def test_headless_logger_system_info_methods():
    """Test system info logging methods"""
    logger = HeadlessLogger(config={})

    # These should not raise errors
    logger.set_system_info(gamelist_exists=True, existing_entries=100)
    logger.set_system_info(gamelist_exists=False, existing_entries=0)
    logger.set_integrity_score(1.0)
    logger.set_integrity_score(0.95)
    logger.display_system_operation("nes", "Scanning", "150 ROMs")
    logger.set_system_operation("Hashing", "batch 1/5")


@pytest.mark.unit
def test_headless_logger_pipeline_methods():
    """Test pipeline/performance methods"""
    logger = HeadlessLogger(config={})

    # These should not raise errors
    logger.update_pipeline_concurrency(4)
    logger.set_throttle_status(True)
    logger.set_throttle_status(False)
    logger.set_auth_status('in_progress')
    logger.set_auth_status('complete')
    logger.set_auth_status('unknown')


@pytest.mark.unit
def test_headless_logger_reset_between_systems():
    """Test that reset_pipeline_stages resets processed count"""
    logger = HeadlessLogger(config={})

    # Process some ROMs
    logger.increment_completed(success=True)
    logger.increment_completed(success=True)
    assert logger.processed_in_system == 2

    # Reset for new system
    logger.reset_pipeline_stages()
    assert logger.processed_in_system == 0

    # Global stats should not be reset
    assert logger.stats['successful'] == 2
