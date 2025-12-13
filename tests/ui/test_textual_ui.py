"""Unit tests for the Textual UI shell."""

import logging
from datetime import datetime
import pytest

from curateur.ui.textual_ui import CurateurUI
from curateur.ui.event_bus import EventBus
from curateur.ui.events import (
    SystemStartedEvent,
    SystemCompletedEvent,
    ROMProgressEvent,
    LogEntryEvent,
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
