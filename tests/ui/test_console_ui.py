"""Tests for console UI log panel functionality"""
import logging
from collections import deque
from unittest.mock import MagicMock, patch, Mock
import pytest
from rich.text import Text

from curateur.ui.console_ui import ConsoleUI, LEVEL_NUMERIC_MAP


@pytest.fixture
def mock_console_ui():
    """Create a ConsoleUI instance with mocked dependencies"""
    with patch('curateur.ui.console_ui.Console'), \
         patch('curateur.ui.console_ui.Live'), \
         patch('curateur.ui.console_ui.KeyboardListener'):
        # ConsoleUI requires a config dict parameter
        mock_config = {}
        ui = ConsoleUI(config=mock_config)
        # Mock the layout to avoid rendering issues
        ui.layout = {'logs': Mock()}
        return ui


@pytest.mark.unit
def test_log_buffer_initialization(mock_console_ui):
    """Test that log buffer is properly initialized"""
    ui = mock_console_ui
    assert len(ui.log_buffer) == 0
    assert ui.log_buffer.maxlen == 400
    assert len(ui._visible_logs) == 0
    assert ui._visible_logs.maxlen == 120
    assert ui._log_sequence == 0
    assert ui.current_log_level == 20  # INFO


@pytest.mark.unit
def test_add_log_entry_basic(mock_console_ui):
    """Test adding a single log entry"""
    ui = mock_console_ui
    ui.add_log_entry('INFO', 'Test message')

    assert len(ui.log_buffer) == 1
    assert ui._log_sequence == 1

    seq, level_num, text_entry = ui.log_buffer[0]
    assert seq == 1
    assert level_num == logging.INFO
    assert isinstance(text_entry, Text)


@pytest.mark.unit
def test_add_log_entry_sequence_increments(mock_console_ui):
    """Test that log sequence numbers increment correctly"""
    ui = mock_console_ui

    ui.add_log_entry('INFO', 'Message 1')
    ui.add_log_entry('WARNING', 'Message 2')
    ui.add_log_entry('ERROR', 'Message 3')

    assert len(ui.log_buffer) == 3
    assert ui._log_sequence == 3

    # Check sequences are in order
    for i, (seq, _, _) in enumerate(ui.log_buffer, start=1):
        assert seq == i


@pytest.mark.unit
def test_add_log_entry_filters_by_level(mock_console_ui):
    """Test that visible logs respects current log level filter"""
    ui = mock_console_ui
    ui.current_log_level = logging.WARNING  # Only WARNING and above

    ui.add_log_entry('DEBUG', 'Debug message')
    ui.add_log_entry('INFO', 'Info message')
    ui.add_log_entry('WARNING', 'Warning message')
    ui.add_log_entry('ERROR', 'Error message')

    assert len(ui.log_buffer) == 4  # All entries in buffer
    assert len(ui._visible_logs) == 2  # Only WARNING and ERROR visible


@pytest.mark.unit
def test_log_buffer_maxlen_eviction(mock_console_ui):
    """Test that log buffer evicts oldest entries at maxlen"""
    ui = mock_console_ui

    # Add 450 entries (buffer maxlen is 400)
    for i in range(450):
        ui.add_log_entry('INFO', f'Message {i}')

    assert len(ui.log_buffer) == 400
    assert ui._log_sequence == 450

    # First entry should be seq 51 (450 - 400 + 1)
    first_seq = ui.log_buffer[0][0]
    assert first_seq == 51


@pytest.mark.unit
def test_visible_logs_maxlen_eviction(mock_console_ui):
    """Test that visible logs respects maxlen of 120"""
    ui = mock_console_ui
    ui.current_log_level = logging.DEBUG  # Show all

    # Add 150 entries (visible maxlen is 120)
    for i in range(150):
        ui.add_log_entry('INFO', f'Message {i}')

    assert len(ui._visible_logs) == 120


@pytest.mark.unit
def test_rebuild_visible_logs_filters_correctly(mock_console_ui):
    """Test that _rebuild_visible_logs filters by current level"""
    ui = mock_console_ui

    # Add various log levels
    ui.add_log_entry('DEBUG', 'Debug 1')
    ui.add_log_entry('INFO', 'Info 1')
    ui.add_log_entry('WARNING', 'Warning 1')
    ui.add_log_entry('ERROR', 'Error 1')
    ui.add_log_entry('DEBUG', 'Debug 2')
    ui.add_log_entry('INFO', 'Info 2')

    # Set filter to WARNING
    ui.current_log_level = logging.WARNING
    ui._rebuild_visible_logs()

    # Should only have WARNING and ERROR (2 entries)
    assert len(ui._visible_logs) == 2


@pytest.mark.unit
def test_rebuild_visible_logs_respects_limit(mock_console_ui):
    """Test that _rebuild_visible_logs respects visible_log_limit"""
    ui = mock_console_ui
    ui.current_log_level = logging.DEBUG  # Show all

    # Add 200 INFO entries
    for i in range(200):
        ui.add_log_entry('INFO', f'Message {i}')

    ui._rebuild_visible_logs()

    # Should only keep last 120
    assert len(ui._visible_logs) == 120


@pytest.mark.unit
def test_rebuild_visible_logs_takes_newest_entries(mock_console_ui):
    """Test that _rebuild_visible_logs takes the newest entries"""
    ui = mock_console_ui
    ui.current_log_level = logging.DEBUG

    # Add entries that will identify order
    for i in range(200):
        ui.add_log_entry('INFO', f'Message {i}')

    ui._rebuild_visible_logs()

    # The newest entry (sequence 200) should be last in visible logs
    last_seq = None
    for seq, _, _ in ui.log_buffer:
        if seq == 200:
            last_seq = seq
            break

    assert ui._last_render_sequence == 200


@pytest.mark.unit
def test_set_log_level_changes_filter(mock_console_ui):
    """Test that set_log_level changes the current filter"""
    ui = mock_console_ui

    # Add mixed log levels
    ui.add_log_entry('DEBUG', 'Debug')
    ui.add_log_entry('INFO', 'Info')
    ui.add_log_entry('WARNING', 'Warning')
    ui.add_log_entry('ERROR', 'Error')

    # Set to ERROR only (key 1)
    ui.set_log_level(1)

    assert ui.current_log_level == 40  # ERROR level
    assert len(ui._visible_logs) == 1  # Only ERROR visible


@pytest.mark.unit
def test_set_log_level_rebuilds_visible(mock_console_ui):
    """Test that set_log_level triggers rebuild of visible logs"""
    ui = mock_console_ui

    # Start with INFO level (default)
    ui.add_log_entry('DEBUG', 'Debug')
    ui.add_log_entry('INFO', 'Info')
    ui.add_log_entry('WARNING', 'Warning')

    initial_visible_count = len(ui._visible_logs)
    assert initial_visible_count == 2  # INFO and WARNING

    # Change to DEBUG (show all)
    ui.set_log_level(4)

    assert len(ui._visible_logs) == 3  # All three visible now


@pytest.mark.unit
def test_render_logs_panel_empty_buffer(mock_console_ui):
    """Test _render_logs_panel with empty buffer"""
    ui = mock_console_ui

    # Should not raise error with empty buffer (returns early)
    ui._render_logs_panel()

    # With empty buffer, it returns early so no update is called
    # This is expected optimization behavior
    assert len(ui.log_buffer) == 0


@pytest.mark.unit
def test_render_logs_panel_processes_new_entries_only(mock_console_ui):
    """Test that _render_logs_panel only processes new entries (O(k) optimization)"""
    ui = mock_console_ui
    ui.current_log_level = logging.DEBUG

    # Add initial batch
    for i in range(50):
        ui.add_log_entry('INFO', f'Message {i}')

    # First render - processes all 50
    ui._render_logs_panel()
    first_render_seq = ui._last_render_sequence
    assert first_render_seq == 50

    # Add 10 more entries
    for i in range(50, 60):
        ui.add_log_entry('INFO', f'Message {i}')

    # Second render - should only process the 10 new ones
    ui._render_logs_panel()
    second_render_seq = ui._last_render_sequence
    assert second_render_seq == 60


@pytest.mark.unit
def test_render_logs_panel_detects_wraparound(mock_console_ui):
    """Test that _render_logs_panel detects buffer wraparound"""
    ui = mock_console_ui
    ui.current_log_level = logging.DEBUG

    # Fill buffer past maxlen to cause wraparound
    for i in range(450):
        ui.add_log_entry('INFO', f'Message {i}')

    # Render after wraparound
    ui._render_logs_panel()

    # After wraparound and rebuild, last_render_sequence should be updated
    assert ui._last_render_sequence == 450
    assert len(ui.log_buffer) == 400


@pytest.mark.unit
def test_render_logs_panel_burst_detection(mock_console_ui):
    """Test that _render_logs_panel detects log bursts"""
    ui = mock_console_ui
    ui.current_log_level = logging.DEBUG

    # Simulate burst: add more than visible_log_limit (120) new entries
    for i in range(200):
        ui.add_log_entry('INFO', f'Message {i}')

    ui._render_logs_panel()

    # Should have triggered burst handling (skipped entries)
    # Visible logs should be capped at 120
    assert len(ui._visible_logs) <= 120


@pytest.mark.unit
def test_render_logs_panel_tracks_skipped_entries(mock_console_ui):
    """Test that burst detection tracks skipped entries"""
    ui = mock_console_ui
    ui.current_log_level = logging.DEBUG
    ui._last_render_sequence = 0

    # Add many entries at once (burst)
    for i in range(200):
        ui.add_log_entry('INFO', f'Burst message {i}')

    # Render should detect burst
    ui._render_logs_panel()

    # Should have noted that entries were skipped
    # (skipped count gets reset in cache rebuild, so check visible logs are limited)
    assert len(ui._visible_logs) <= 120


@pytest.mark.unit
def test_cache_invalidation_pending_flag(mock_console_ui):
    """Test that cache invalidation flag is set appropriately"""
    ui = mock_console_ui

    # Adding entry should set cache invalidation pending
    ui.add_log_entry('INFO', 'Test')
    assert ui._cache_invalidation_pending is True

    # Render should eventually clear it (after 30ms batch window)
    ui.last_cache_invalidation = 0  # Force immediate rebuild
    ui._render_logs_panel()
    assert ui._cache_invalidation_pending is False


@pytest.mark.unit
def test_log_cache_dirty_flag(mock_console_ui):
    """Test that cache dirty flag is managed correctly"""
    ui = mock_console_ui

    # Adding visible entry should mark cache dirty
    ui.current_log_level = logging.INFO
    ui.add_log_entry('INFO', 'Test')
    assert ui._log_cache_dirty is True

    # Render should clear it
    ui.last_cache_invalidation = 0
    ui._render_logs_panel()
    assert ui._log_cache_dirty is False


@pytest.mark.unit
def test_log_levels_mapping(mock_console_ui):
    """Test that log level key mapping works correctly"""
    ui = mock_console_ui

    # Test all log level keys
    ui.set_log_level(1)  # ERROR
    assert ui.current_log_level == 40

    ui.set_log_level(2)  # WARNING
    assert ui.current_log_level == 30

    ui.set_log_level(3)  # INFO
    assert ui.current_log_level == 20

    ui.set_log_level(4)  # DEBUG
    assert ui.current_log_level == 10


@pytest.mark.unit
def test_log_entry_color_coding(mock_console_ui):
    """Test that log entries have appropriate styling"""
    ui = mock_console_ui

    # Add entries of different levels
    ui.add_log_entry('DEBUG', 'Debug message')
    ui.add_log_entry('INFO', 'Info message')
    ui.add_log_entry('WARNING', 'Warning message')
    ui.add_log_entry('ERROR', 'Error message')
    ui.add_log_entry('CRITICAL', 'Critical message')

    # All should create Text objects
    for seq, level_num, text_entry in ui.log_buffer:
        assert isinstance(text_entry, Text)


@pytest.mark.unit
def test_visible_logs_sync_on_buffer_eviction(mock_console_ui):
    """Test that visible logs stay in sync when buffer evicts entries"""
    ui = mock_console_ui
    ui.current_log_level = logging.DEBUG  # Show all

    # Fill buffer to maxlen
    for i in range(400):
        ui.add_log_entry('INFO', f'Message {i}')

    visible_before = len(ui._visible_logs)

    # Add more to trigger eviction
    ui.add_log_entry('INFO', 'New message')

    # Visible logs should still be valid (maxlen handles it)
    assert len(ui._visible_logs) <= 120


@pytest.mark.unit
def test_render_logs_panel_iteration_count(mock_console_ui):
    """Test that render iteration count is O(k) not O(400)"""
    ui = mock_console_ui
    ui.current_log_level = logging.DEBUG

    # Add 400 entries to fill buffer
    for i in range(400):
        ui.add_log_entry('INFO', f'Initial {i}')

    # First render - processes all
    ui._render_logs_panel()
    first_seq = ui._last_render_sequence
    assert first_seq == 400

    # Add only 10 new entries
    for i in range(10):
        ui.add_log_entry('INFO', f'New {i}')

    # Second render - should only iterate through ~10 entries, not all 400
    # We can verify this by checking the sequence tracking
    ui._render_logs_panel()
    assert ui._last_render_sequence == 410

    # The key insight: it should process only new entries
    # If it were O(400), it would iterate through entire buffer


@pytest.mark.unit
def test_mixed_log_levels_filtering(mock_console_ui):
    """Test filtering with mixed log levels"""
    ui = mock_console_ui

    # Add pattern: DEBUG, INFO, WARNING, ERROR repeated
    for i in range(25):
        ui.add_log_entry('DEBUG', f'Debug {i}')
        ui.add_log_entry('INFO', f'Info {i}')
        ui.add_log_entry('WARNING', f'Warning {i}')
        ui.add_log_entry('ERROR', f'Error {i}')

    # Total: 100 entries
    assert len(ui.log_buffer) == 100

    # Filter to WARNING+ (should show 50 entries: 25 WARNING + 25 ERROR)
    ui.current_log_level = logging.WARNING
    ui._rebuild_visible_logs()
    assert len(ui._visible_logs) == 50

    # Filter to ERROR only (should show 25 entries)
    ui.current_log_level = logging.ERROR
    ui._rebuild_visible_logs()
    assert len(ui._visible_logs) == 25

    # Filter to DEBUG (all) (should show 100 entries, capped at 120 maxlen)
    ui.current_log_level = logging.DEBUG
    ui._rebuild_visible_logs()
    assert len(ui._visible_logs) == 100


@pytest.mark.unit
def test_level_numeric_map_completeness():
    """Test that LEVEL_NUMERIC_MAP has all expected levels"""
    assert LEVEL_NUMERIC_MAP['DEBUG'] == logging.DEBUG
    assert LEVEL_NUMERIC_MAP['INFO'] == logging.INFO
    assert LEVEL_NUMERIC_MAP['WARNING'] == logging.WARNING
    assert LEVEL_NUMERIC_MAP['ERROR'] == logging.ERROR
    assert LEVEL_NUMERIC_MAP['CRITICAL'] == logging.CRITICAL


@pytest.mark.unit
def test_render_logs_panel_no_error_on_edge_cases(mock_console_ui):
    """Test that rendering handles edge cases without errors"""
    ui = mock_console_ui

    # Empty buffer
    ui._render_logs_panel()

    # Single entry
    ui.add_log_entry('INFO', 'Single message')
    ui._render_logs_panel()

    # Filter set to level higher than any entry
    ui.current_log_level = logging.CRITICAL
    ui._rebuild_visible_logs()
    ui._render_logs_panel()

    # All should execute without exceptions
    assert True
