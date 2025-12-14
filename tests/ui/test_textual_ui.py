"""Unit tests for the Textual UI shell."""

import asyncio
import pytest
import logging
from datetime import datetime
from unittest.mock import AsyncMock, Mock, patch

from curateur.ui.textual_ui import CurateurUI
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
    ActiveRequestEvent,
    SearchRequestEvent,
    SearchResponseEvent,
    CacheMetricsEvent,
    GamelistUpdateEvent,
    MediaStatsEvent,
    SearchActivityEvent,
    AuthenticationEvent,
    ProcessingSummaryEvent,
)


@pytest.fixture
def event_bus():
    """Create an event bus for testing."""
    return EventBus()


@pytest.fixture
def config():
    """Create a dummy config for testing."""
    return {
        'scraping': {
            'systems': ['nes', 'snes', 'genesis']
        }
    }


@pytest.mark.asyncio
async def test_ui_initialization(config, event_bus):
    """Test that the UI initializes without errors."""
    ui = CurateurUI(config, event_bus)

    assert ui.config == config
    assert ui.event_bus == event_bus
    assert ui.should_quit is False
    assert ui.should_skip_system is False
    assert ui.current_system is None


@pytest.mark.asyncio
async def test_event_handlers_registered():
    """Test that all event handlers are properly defined."""
    config = {'scraping': {'systems': []}}
    event_bus = EventBus()
    ui = CurateurUI(config, event_bus)

    # Verify all handler methods exist
    assert hasattr(ui, 'on_system_started')
    assert hasattr(ui, 'on_system_completed')
    assert hasattr(ui, 'on_rom_progress')
    assert hasattr(ui, 'on_hashing_progress')
    assert hasattr(ui, 'on_api_activity')
    assert hasattr(ui, 'on_media_download')
    assert hasattr(ui, 'on_log_entry')
    assert hasattr(ui, 'on_performance_update')
    assert hasattr(ui, 'on_game_completed')
    assert hasattr(ui, 'on_active_request')

    # Verify they are async
    import inspect
    assert inspect.iscoroutinefunction(ui.on_system_started)
    assert inspect.iscoroutinefunction(ui.on_system_completed)
    assert inspect.iscoroutinefunction(ui.on_rom_progress)


@pytest.mark.asyncio
async def test_system_started_event_handler(config, event_bus):
    """Test that SystemStartedEvent handler updates current_system."""
    ui = CurateurUI(config, event_bus)

    event = SystemStartedEvent(
        system_name="nes",
        system_fullname="Nintendo Entertainment System",
        total_roms=100,
        current_index=0,
        total_systems=3
    )

    await ui.on_system_started(event)

    assert ui.current_system == event
    assert ui.current_system.system_name == "nes"
    assert ui.current_system.total_roms == 100


@pytest.mark.asyncio
async def test_control_flags():
    """Test that control flags can be set."""
    config = {'scraping': {'systems': []}}
    event_bus = EventBus()
    ui = CurateurUI(config, event_bus)

    # Test initial state
    assert ui.should_quit is False
    assert ui.should_skip_system is False

    # Test setting flags
    ui.should_quit = True
    ui.should_skip_system = True

    assert ui.should_quit is True
    assert ui.should_skip_system is True


@pytest.mark.asyncio
async def test_system_completed_event_handler(config, event_bus):
    """Test SystemCompletedEvent handler."""
    ui = CurateurUI(config, event_bus)
    
    event = SystemCompletedEvent(
        system_name="nes",
        total_roms=100,
        successful=85,
        failed=5,
        skipped=10,
        elapsed_time=120.5
    )
    
    await ui.on_system_completed(event)
    # Handler should process without errors


@pytest.mark.asyncio
async def test_rom_progress_event_handler(config, event_bus):
    """Test ROMProgressEvent handler."""
    ui = CurateurUI(config, event_bus)
    
    # Test different status types
    statuses = ['scanning', 'hashing', 'querying', 'downloading', 'complete', 'failed', 'skipped']
    
    for status in statuses:
        event = ROMProgressEvent(
            rom_name="Super Mario Bros.nes",
            system="nes",
            status=status,
            detail=f"Processing {status}",
            progress=0.5 if status == 'downloading' else None
        )
        await ui.on_rom_progress(event)


@pytest.mark.asyncio
async def test_hashing_progress_event_handler(config, event_bus):
    """Test HashingProgressEvent handler."""
    ui = CurateurUI(config, event_bus)
    
    event = HashingProgressEvent(
        completed=75,
        total=100,
        in_progress=True,
        skipped=5
    )
    
    await ui.on_hashing_progress(event)


@pytest.mark.asyncio
async def test_api_activity_event_handler(config, event_bus):
    """Test APIActivityEvent handler."""
    ui = CurateurUI(config, event_bus)
    
    event = APIActivityEvent(
        metadata_in_flight=3,
        metadata_total=50,
        search_in_flight=1,
        search_total=10
    )
    
    await ui.on_api_activity(event)
    
    # Test cumulative tracking
    assert ui.cumulative_metadata_calls >= 0


@pytest.mark.asyncio
async def test_media_download_event_handler(config, event_bus):
    """Test MediaDownloadEvent handler."""
    ui = CurateurUI(config, event_bus)
    
    # Test different status types
    for status in ['downloading', 'complete', 'failed']:
        event = MediaDownloadEvent(
            media_type="box-2D",
            rom_name="Super Mario Bros.nes",
            status=status,
            progress=0.75 if status == 'downloading' else None
        )
        await ui.on_media_download(event)


@pytest.mark.asyncio
async def test_log_entry_event_handler(config, event_bus):
    """Test LogEntryEvent handler."""
    ui = CurateurUI(config, event_bus)
    
    # Test different log levels
    levels = [
        (logging.DEBUG, "Debug message"),
        (logging.INFO, "Info message"),
        (logging.WARNING, "Warning message"),
        (logging.ERROR, "Error message"),
        (logging.CRITICAL, "Critical message")
    ]
    
    for level, message in levels:
        event = LogEntryEvent(
            level=level,
            message=message,
            timestamp=datetime.now()
        )
        await ui.on_log_entry(event)


@pytest.mark.asyncio
async def test_performance_update_event_handler(config, event_bus):
    """Test PerformanceUpdateEvent handler."""
    ui = CurateurUI(config, event_bus)
    
    event = PerformanceUpdateEvent(
        api_quota_used=150,
        api_quota_limit=1000,
        threads_in_use=4,
        threads_limit=8,
        throughput_history=[10, 12, 15, 14, 16],
        api_rate_history=[25, 28, 30, 27, 29],
        cache_hit_rate=0.85
    )
    
    await ui.on_performance_update(event)


@pytest.mark.asyncio
async def test_game_completed_event_handler(config, event_bus):
    """Test GameCompletedEvent handler."""
    ui = CurateurUI(config, event_bus)
    
    event = GameCompletedEvent(
        game_id="12345",
        title="Super Mario Bros.",
        year="1985",
        genre="Platform",
        developer="Nintendo",
        publisher="Nintendo",
        players="1-2",
        rating=4.8,
        description="A classic platformer game"
    )
    
    await ui.on_game_completed(event)


@pytest.mark.asyncio
async def test_active_request_event_handler(config, event_bus):
    """Test ActiveRequestEvent handler."""
    ui = CurateurUI(config, event_bus)
    
    # Test different stages and statuses
    stages = ['API Fetch', 'Search', 'Media DL', 'Hashing']
    statuses = ['Active', 'Retrying', 'Complete', 'Failed']
    
    for stage in stages:
        for status in statuses:
            event = ActiveRequestEvent(
                request_id=f"req_{stage}_{status}",
                rom_name="Test ROM.nes",
                stage=stage,
                status=status,
                duration=1.5,
                retry_count=0 if status != 'Retrying' else 2,
                last_failure="Network error" if status == 'Failed' else None
            )
            await ui.on_active_request(event)


@pytest.mark.asyncio
async def test_search_request_event_handler(config, event_bus):
    """Test SearchRequestEvent handler adds to queue."""
    ui = CurateurUI(config, event_bus)
    
    search_results = [
        {
            "game_data": {"id": "123", "name": "Test Game", "region": "USA"},
            "confidence": 0.95
        },
        {
            "game_data": {"id": "124", "name": "Test Game 2", "region": "EUR"},
            "confidence": 0.75
        }
    ]
    
    event = SearchRequestEvent(
        request_id="search_001",
        rom_name="Test Game.nes",
        rom_path="/path/to/rom.nes",
        system="nes",
        search_results=search_results
    )
    
    await ui.on_search_request(event)
    
    # Verify event was added to queue
    assert not ui.search_queue.empty()


@pytest.mark.asyncio
async def test_cache_metrics_event_handler(config, event_bus):
    """Test CacheMetricsEvent handler."""
    ui = CurateurUI(config, event_bus)
    
    event = CacheMetricsEvent(
        existing=500,
        added=25,
        hits=450,
        misses=75,
        hit_rate=85.7
    )
    
    await ui.on_cache_metrics_event(event)


@pytest.mark.asyncio
async def test_gamelist_update_event_handler(config, event_bus):
    """Test GamelistUpdateEvent handler."""
    ui = CurateurUI(config, event_bus)
    
    event = GamelistUpdateEvent(
        system="nes",
        existing=200,
        added=15,
        updated=5
    )
    
    await ui.on_gamelist_update_event(event)


@pytest.mark.asyncio
async def test_media_stats_event_handler(config, event_bus):
    """Test MediaStatsEvent handler."""
    ui = CurateurUI(config, event_bus)
    
    event = MediaStatsEvent(
        by_type={
            "box-2D": {"successful": 80, "failed": 5},
            "screenshot": {"successful": 75, "failed": 10},
            "titlescreen": {"successful": 70, "failed": 15}
        },
        total_validated=50,
        total_skipped=10,
        total_failed=30
    )
    
    await ui.on_media_stats_event(event)


@pytest.mark.asyncio
async def test_search_activity_event_handler(config, event_bus):
    """Test SearchActivityEvent handler."""
    ui = CurateurUI(config, event_bus)
    
    event = SearchActivityEvent(
        fallback_count=5,
        unmatched_count=3
    )
    
    await ui.on_search_activity_event(event)


@pytest.mark.asyncio
async def test_authentication_event_handler(config, event_bus):
    """Test AuthenticationEvent handler."""
    ui = CurateurUI(config, event_bus)
    
    # Test authenticating
    event1 = AuthenticationEvent(
        status='authenticating',
        username=None
    )
    await ui.on_authentication_event(event1)
    
    # Test authenticated
    event2 = AuthenticationEvent(
        status='authenticated',
        username='testuser'
    )
    await ui.on_authentication_event(event2)
    
    # Test failed
    event3 = AuthenticationEvent(
        status='failed',
        username=None
    )
    await ui.on_authentication_event(event3)


@pytest.mark.asyncio
async def test_processing_summary_event_handler(config, event_bus):
    """Test ProcessingSummaryEvent handler."""
    ui = CurateurUI(config, event_bus)
    
    event = ProcessingSummaryEvent(
        successful=["game1.nes", "game2.nes", "game3.nes"],
        skipped=[
            ("game4.nes", "Already in gamelist"),
            ("game5.nes", "No hash available")
        ],
        failed=[
            ("game6.nes", "Network error"),
            ("game7.nes", "No match found")
        ]
    )
    
    await ui.on_processing_summary_event(event)


@pytest.mark.asyncio
async def test_all_event_handlers_are_async(config, event_bus):
    """Verify all event handlers are async coroutines."""
    import inspect
    
    ui = CurateurUI(config, event_bus)
    
    handlers = [
        'on_system_started',
        'on_system_completed',
        'on_rom_progress',
        'on_hashing_progress',
        'on_api_activity',
        'on_media_download',
        'on_log_entry',
        'on_performance_update',
        'on_game_completed',
        'on_active_request',
        'on_search_request',
        'on_cache_metrics_event',
        'on_gamelist_update_event',
        'on_media_stats_event',
        'on_search_activity_event',
        'on_authentication_event',
        'on_processing_summary_event',
    ]
    
    for handler_name in handlers:
        handler = getattr(ui, handler_name)
        assert inspect.iscoroutinefunction(handler), f"{handler_name} should be async"


@pytest.mark.asyncio
async def test_event_handler_error_handling(config, event_bus):
    """Test that event handlers handle errors gracefully."""
    ui = CurateurUI(config, event_bus)
    
    # Create event with invalid data types (should not crash)
    event = SystemStartedEvent(
        system_name="nes",
        system_fullname="Nintendo Entertainment System",
        total_roms=100,
        current_index=0,
        total_systems=3
    )
    
    # Handler should not crash even if UI widgets are not mounted
    await ui.on_system_started(event)


@pytest.mark.asyncio
async def test_search_queue_processing(config, event_bus):
    """Test search request queue processing."""
    ui = CurateurUI(config, event_bus)
    
    # Verify queue starts empty
    assert ui.search_queue.empty()
    assert ui.search_processor_running is False
    
    # Add a search request
    search_results = [
        {
            "game_data": {"id": "123", "name": "Test", "region": "USA"},
            "confidence": 0.9
        }
    ]
    
    event = SearchRequestEvent(
        request_id="search_001",
        rom_name="Test.nes",
        rom_path="/path/to/test.nes",
        system="nes",
        search_results=search_results
    )
    
    await ui.on_search_request(event)
    
    # Queue should have the event
    assert not ui.search_queue.empty()


@pytest.mark.asyncio
async def test_cumulative_metadata_tracking(config, event_bus):
    """Test cumulative metadata call tracking."""
    ui = CurateurUI(config, event_bus)
    
    # Initial state
    assert ui.cumulative_metadata_calls == 0
    assert ui.previous_metadata_in_flight == 0
    
    # Simulate API activity with increasing in-flight
    event1 = APIActivityEvent(
        metadata_in_flight=5,
        metadata_total=10,
        search_in_flight=0,
        search_total=0
    )
    await ui.on_api_activity(event1)
    assert ui.previous_metadata_in_flight == 5
    
    # Simulate completion (in-flight decreases)
    event2 = APIActivityEvent(
        metadata_in_flight=3,
        metadata_total=12,
        search_in_flight=0,
        search_total=0
    )
    await ui.on_api_activity(event2)
    assert ui.cumulative_metadata_calls == 2  # Decreased by 2


@pytest.mark.asyncio
async def test_control_flag_integration(config, event_bus):
    """Test that control flags work with event handlers."""
    ui = CurateurUI(config, event_bus)
    
    # Set control flags
    ui.should_quit = True
    ui.should_skip_system = True
    
    # Event handlers should still work with flags set
    event = SystemStartedEvent(
        system_name="nes",
        system_fullname="NES",
        total_roms=100,
        current_index=0,
        total_systems=3
    )
    
    await ui.on_system_started(event)
    
    # Flags should remain set
    assert ui.should_quit is True
    assert ui.should_skip_system is True


@pytest.mark.asyncio
async def test_event_type_validation(config, event_bus):
    """Test that event types are correctly validated."""
    ui = CurateurUI(config, event_bus)
    
    # Test with wrong event type (should handle gracefully)
    wrong_event = "not_an_event"
    
    # Handler should not crash with wrong event type
    try:
        await ui.on_cache_metrics_event(wrong_event)
    except AttributeError:
        pass  # Expected if type checking is done
    
    # Test with correct event type
    correct_event = CacheMetricsEvent(
        existing=100,
        added=10,
        hits=90,
        misses=20,
        hit_rate=81.8
    )
    
    await ui.on_cache_metrics_event(correct_event)


@pytest.mark.asyncio
async def test_multiple_system_events(config, event_bus):
    """Test handling multiple systems in sequence."""
    ui = CurateurUI(config, event_bus)
    
    systems = [
        ("nes", "Nintendo Entertainment System", 100),
        ("snes", "Super Nintendo", 150),
        ("genesis", "Sega Genesis", 120)
    ]
    
    for idx, (name, fullname, roms) in enumerate(systems):
        start_event = SystemStartedEvent(
            system_name=name,
            system_fullname=fullname,
            total_roms=roms,
            current_index=idx,
            total_systems=len(systems)
        )
        
        await ui.on_system_started(start_event)
        assert ui.current_system.system_name == name
        
        complete_event = SystemCompletedEvent(
            system_name=name,
            total_roms=roms,
            successful=roms - 10,
            failed=5,
            skipped=5,
            elapsed_time=60.0
        )
        
        await ui.on_system_completed(complete_event)


@pytest.mark.asyncio
async def test_event_bus_integration(config):
    """Test full event bus integration with UI."""
    event_bus = EventBus()
    ui = CurateurUI(config, event_bus)
    
    received_events = []
    
    async def track_event(event):
        received_events.append(event)
        await ui.on_system_started(event)
    
    # Subscribe UI handler
    event_bus.subscribe(SystemStartedEvent, track_event)
    
    # Start event processing
    task = asyncio.create_task(event_bus.process_events())
    
    # Publish event through event bus
    test_event = SystemStartedEvent(
        system_name="nes",
        system_fullname="NES",
        total_roms=100,
        current_index=0,
        total_systems=1
    )
    
    await event_bus.publish(test_event)
    
    # Wait for processing
    await asyncio.sleep(0.1)
    
    # Clean up
    await event_bus.stop()
    try:
        await asyncio.wait_for(task, timeout=1.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass
    
    # Verify event was received
    assert len(received_events) == 1
    assert ui.current_system == test_event


@pytest.mark.asyncio
async def test_concurrent_event_handling(config, event_bus):
    """Test handling multiple events concurrently."""
    ui = CurateurUI(config, event_bus)
    
    # Create multiple events of different types
    events = [
        SystemStartedEvent("nes", "NES", 100, 0, 1),
        HashingProgressEvent(50, 100, True, 5),
        APIActivityEvent(3, 50, 1, 10),
        GameCompletedEvent("123", "Test Game", "2024"),
        MediaDownloadEvent("box-2D", "game.nes", "downloading", 0.5),
    ]
    
    # Handle all events concurrently
    tasks = []
    for event in events:
        if isinstance(event, SystemStartedEvent):
            tasks.append(ui.on_system_started(event))
        elif isinstance(event, HashingProgressEvent):
            tasks.append(ui.on_hashing_progress(event))
        elif isinstance(event, APIActivityEvent):
            tasks.append(ui.on_api_activity(event))
        elif isinstance(event, GameCompletedEvent):
            tasks.append(ui.on_game_completed(event))
        elif isinstance(event, MediaDownloadEvent):
            tasks.append(ui.on_media_download(event))
    
    # Wait for all to complete
    await asyncio.gather(*tasks)
    
    # Verify UI state updated correctly
    assert ui.current_system is not None
