"""Unit tests for UI widget updates from events.

These tests verify that UI widgets correctly update their state
when events are received and handled. Widget-specific tests that require
DOM mounting are tested via integration tests.
"""

import pytest
from datetime import datetime

from curateur.ui.textual_ui import (
    CurateurUI,
    create_sparkline,
    PerformancePanel,
)
from curateur.ui.event_bus import EventBus
from curateur.ui.events import (
    SystemStartedEvent,
    SystemCompletedEvent,
    ROMProgressEvent,
    HashingProgressEvent,
    APIActivityEvent,
    MediaDownloadEvent,
    LogEntryEvent,
    PerformanceUpdateEvent,
    GameCompletedEvent,
    CacheMetricsEvent,
    GamelistUpdateEvent,
    MediaStatsEvent,
    SearchActivityEvent,
    AuthenticationEvent,
)


@pytest.fixture
def config():
    """Create test configuration."""
    return {
        'scraping': {
            'systems': ['nes', 'snes', 'genesis']
        }
    }


@pytest.fixture
def event_bus():
    """Create event bus."""
    return EventBus()


class TestSparkline:
    """Test sparkline visualization."""

    def test_empty_values(self):
        """Test sparkline with empty values."""
        result = create_sparkline([], width=10)
        assert len(result) == 10
        assert result == "─" * 10

    def test_sparkline_width(self):
        """Test sparkline respects width parameter."""
        values = [1, 2, 3, 4, 5]
        result = create_sparkline(values, width=20)
        assert len(result) == 20

    def test_sparkline_normalization(self):
        """Test sparkline normalizes values."""
        values = [0, 50, 100]
        result = create_sparkline(values, width=3)
        
        # Should use sparkline characters
        assert all(c in "▁▂▃▄▅▆▇█" for c in result)

    def test_sparkline_padding(self):
        """Test sparkline pads short value lists."""
        values = [5, 10]
        result = create_sparkline(values, width=10)
        assert len(result) == 10

    def test_sparkline_trimming(self):
        """Test sparkline trims long value lists."""
        values = list(range(50))
        result = create_sparkline(values, width=20)
        assert len(result) == 20


class TestInlineProgressBar:
    """Test inline progress bar."""

    def test_inline_progress_bar(self):
        """Test inline progress bar creation."""
        bar = PerformancePanel.create_inline_progress_bar(500, 1000, 30)
        
        # Should be 30 characters long
        assert len(bar) == 30
        
        # Should contain filled and unfilled blocks
        assert '█' in bar or '░' in bar

    def test_zero_total(self):
        """Test inline progress bar with zero total."""
        bar = PerformancePanel.create_inline_progress_bar(0, 0, 20)
        assert len(bar) == 20

    def test_full_progress(self):
        """Test inline progress bar at 100%."""
        bar = PerformancePanel.create_inline_progress_bar(1000, 1000, 20)
        assert len(bar) == 20
        assert bar.count('█') == 20


@pytest.mark.asyncio
async def test_ui_consumes_all_event_types(config, event_bus):
    """Integration test: verify UI can consume all event types."""
    ui = CurateurUI(config, event_bus)
    
    # Create one of each event type
    events = [
        SystemStartedEvent("nes", "NES", 100, 0, 3),
        SystemCompletedEvent("nes", 100, 85, 5, 10, 120.0),
        ROMProgressEvent("game.nes", "nes", "complete"),
        HashingProgressEvent(50, 100, True, 5),
        APIActivityEvent(3, 50, 1, 10),
        MediaDownloadEvent("box-2D", "game.nes", "complete"),
        LogEntryEvent(20, "Test message", datetime.now()),
        PerformanceUpdateEvent(100, 1000, 4, 8, [10, 12], [25, 30]),
        GameCompletedEvent("123", "Test Game", "2024"),
        CacheMetricsEvent(500, 25, 450, 75, 85.7),
        GamelistUpdateEvent("nes", 200, 15, 5),
        MediaStatsEvent({}, 50, 10, 5),
        SearchActivityEvent(3, 2),
        AuthenticationEvent("authenticated", "testuser"),
    ]
    
    # All handlers should process without errors
    for event in events:
        if isinstance(event, SystemStartedEvent):
            await ui.on_system_started(event)
        elif isinstance(event, SystemCompletedEvent):
            await ui.on_system_completed(event)
        elif isinstance(event, ROMProgressEvent):
            await ui.on_rom_progress(event)
        elif isinstance(event, HashingProgressEvent):
            await ui.on_hashing_progress(event)
        elif isinstance(event, APIActivityEvent):
            await ui.on_api_activity(event)
        elif isinstance(event, MediaDownloadEvent):
            await ui.on_media_download(event)
        elif isinstance(event, LogEntryEvent):
            await ui.on_log_entry(event)
        elif isinstance(event, PerformanceUpdateEvent):
            await ui.on_performance_update(event)
        elif isinstance(event, GameCompletedEvent):
            await ui.on_game_completed(event)
        elif isinstance(event, CacheMetricsEvent):
            await ui.on_cache_metrics_event(event)
        elif isinstance(event, GamelistUpdateEvent):
            await ui.on_gamelist_update_event(event)
        elif isinstance(event, MediaStatsEvent):
            await ui.on_media_stats_event(event)
        elif isinstance(event, SearchActivityEvent):
            await ui.on_search_activity_event(event)
        elif isinstance(event, AuthenticationEvent):
            await ui.on_authentication_event(event)


@pytest.mark.asyncio
async def test_event_data_flow_integrity(config, event_bus):
    """Test that event data flows correctly through UI handlers."""
    ui = CurateurUI(config, event_bus)
    
    # Test SystemStartedEvent data flow
    system_event = SystemStartedEvent(
        system_name="nes",
        system_fullname="Nintendo Entertainment System",
        total_roms=100,
        current_index=0,
        total_systems=3
    )
    
    await ui.on_system_started(system_event)
    
    # Verify data is stored correctly
    assert ui.current_system == system_event
    assert ui.current_system.system_name == "nes"
    assert ui.current_system.total_roms == 100
    
    # Test cumulative tracking
    api_event1 = APIActivityEvent(5, 10, 0, 0)
    await ui.on_api_activity(api_event1)
    
    api_event2 = APIActivityEvent(3, 12, 0, 0)
    await ui.on_api_activity(api_event2)
    
    # Cumulative should track completed calls
    assert ui.cumulative_metadata_calls == 2  # 5 -> 3 = 2 completed


@pytest.mark.asyncio
async def test_ui_state_consistency(config, event_bus):
    """Test that UI maintains consistent state across events."""
    ui = CurateurUI(config, event_bus)
    
    # Simulate a full system processing workflow
    
    # 1. System starts
    await ui.on_system_started(
        SystemStartedEvent("nes", "NES", 100, 0, 3)
    )
    assert ui.current_system is not None
    
    # 2. Hashing progresses
    await ui.on_hashing_progress(
        HashingProgressEvent(50, 100, True, 5)
    )
    
    # 3. API activity occurs
    await ui.on_api_activity(
        APIActivityEvent(3, 50, 1, 10)
    )
    
    # 4. Media downloads
    await ui.on_media_download(
        MediaDownloadEvent("box-2D", "game.nes", "complete")
    )
    
    # 5. Game completes
    await ui.on_game_completed(
        GameCompletedEvent("123", "Test Game", "2024")
    )
    
    # 6. System completes
    await ui.on_system_completed(
        SystemCompletedEvent("nes", 100, 85, 5, 10, 120.0)
    )
    
    # UI should still have system reference
    assert ui.current_system is not None
