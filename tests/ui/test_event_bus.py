"""Unit tests for EventBus."""

import asyncio
import pytest
from datetime import datetime

from curateur.ui.event_bus import EventBus
from curateur.ui.events import (
    SystemStartedEvent,
    LogEntryEvent,
    HashingProgressEvent,
    GameCompletedEvent,
)


class TestEventBus:
    """Test cases for EventBus."""

    @pytest.fixture
    def event_bus(self):
        """Create an EventBus instance for testing."""
        return EventBus()

    @pytest.mark.asyncio
    async def test_subscribe_and_publish(self, event_bus):
        """Test basic subscribe and publish functionality."""
        received_events = []

        def handler(event):
            received_events.append(event)

        # Subscribe to SystemStartedEvent
        event_bus.subscribe(SystemStartedEvent, handler)

        # Start event processing
        task = asyncio.create_task(event_bus.process_events())

        # Publish an event
        test_event = SystemStartedEvent(
            system_name="nes",
            system_fullname="Nintendo Entertainment System",
            total_roms=100,
            current_index=0,
            total_systems=5
        )
        await event_bus.publish(test_event)

        # Wait a bit for processing
        await asyncio.sleep(0.1)

        # Stop event bus
        await event_bus.stop()
        task.cancel()

        # Verify event was received
        assert len(received_events) == 1
        assert received_events[0] == test_event

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self, event_bus):
        """Test that multiple subscribers receive the same event."""
        received_1 = []
        received_2 = []

        def handler_1(event):
            received_1.append(event)

        def handler_2(event):
            received_2.append(event)

        # Subscribe multiple handlers to same event type
        event_bus.subscribe(LogEntryEvent, handler_1)
        event_bus.subscribe(LogEntryEvent, handler_2)

        # Start event processing
        task = asyncio.create_task(event_bus.process_events())

        # Publish an event
        test_event = LogEntryEvent(
            level=20,  # INFO
            message="Test log message",
            timestamp=datetime.now()
        )
        await event_bus.publish(test_event)

        # Wait for processing
        await asyncio.sleep(0.1)

        # Stop event bus
        await event_bus.stop()
        task.cancel()

        # Both handlers should receive the event
        assert len(received_1) == 1
        assert len(received_2) == 1
        assert received_1[0] == test_event
        assert received_2[0] == test_event

    @pytest.mark.asyncio
    async def test_async_handler(self, event_bus):
        """Test that async handlers work correctly."""
        received_events = []

        async def async_handler(event):
            await asyncio.sleep(0.01)  # Simulate async work
            received_events.append(event)

        event_bus.subscribe(HashingProgressEvent, async_handler)

        # Start event processing
        task = asyncio.create_task(event_bus.process_events())

        # Publish event
        test_event = HashingProgressEvent(
            completed=50,
            total=100,
            in_progress=True,
            skipped=5
        )
        await event_bus.publish(test_event)

        # Wait for async processing
        await asyncio.sleep(0.1)

        # Stop event bus
        await event_bus.stop()
        task.cancel()

        # Verify async handler was called
        assert len(received_events) == 1
        assert received_events[0] == test_event

    @pytest.mark.asyncio
    async def test_handler_error_isolation(self, event_bus):
        """Test that errors in one handler don't affect others."""
        received_events = []

        def failing_handler(event):
            raise ValueError("Handler error")

        def working_handler(event):
            received_events.append(event)

        # Subscribe both handlers
        event_bus.subscribe(GameCompletedEvent, failing_handler)
        event_bus.subscribe(GameCompletedEvent, working_handler)

        # Start event processing
        task = asyncio.create_task(event_bus.process_events())

        # Publish event
        test_event = GameCompletedEvent(
            game_id="12345",
            title="Test Game",
            year="2024",
            confidence=1.0
        )
        await event_bus.publish(test_event)

        # Wait for processing
        await asyncio.sleep(0.1)

        # Stop event bus
        await event_bus.stop()
        task.cancel()

        # Working handler should still receive the event
        assert len(received_events) == 1
        assert received_events[0] == test_event

        # Error count should be incremented
        stats = event_bus.get_stats()
        assert stats['errors'] == 1

    @pytest.mark.asyncio
    async def test_type_filtering(self, event_bus):
        """Test that only subscribed event types are delivered."""
        system_events = []
        log_events = []

        event_bus.subscribe(SystemStartedEvent, lambda e: system_events.append(e))
        event_bus.subscribe(LogEntryEvent, lambda e: log_events.append(e))

        # Start event processing
        task = asyncio.create_task(event_bus.process_events())

        # Publish different event types
        system_event = SystemStartedEvent("nes", "NES", 100, 0, 5)
        log_event = LogEntryEvent(20, "Test", datetime.now())

        await event_bus.publish(system_event)
        await event_bus.publish(log_event)

        # Wait for processing
        await asyncio.sleep(0.1)

        # Stop event bus
        await event_bus.stop()
        task.cancel()

        # Each handler should only receive its event type
        assert len(system_events) == 1
        assert len(log_events) == 1
        assert system_events[0] == system_event
        assert log_events[0] == log_event

    @pytest.mark.asyncio
    async def test_unsubscribe(self, event_bus):
        """Test unsubscribing from events."""
        received_events = []

        def handler(event):
            received_events.append(event)

        # Subscribe and then unsubscribe
        event_bus.subscribe(SystemStartedEvent, handler)
        event_bus.unsubscribe(SystemStartedEvent, handler)

        # Start event processing
        task = asyncio.create_task(event_bus.process_events())

        # Publish event
        test_event = SystemStartedEvent("nes", "NES", 100, 0, 5)
        await event_bus.publish(test_event)

        # Wait for processing
        await asyncio.sleep(0.1)

        # Stop event bus
        await event_bus.stop()
        task.cancel()

        # Handler should not receive event after unsubscribe
        assert len(received_events) == 0

    @pytest.mark.asyncio
    async def test_get_stats(self, event_bus):
        """Test event bus statistics."""
        def handler(event):
            pass

        event_bus.subscribe(SystemStartedEvent, handler)
        event_bus.subscribe(LogEntryEvent, handler)

        # Start event processing
        task = asyncio.create_task(event_bus.process_events())

        # Publish some events
        await event_bus.publish(SystemStartedEvent("nes", "NES", 100, 0, 5))
        await event_bus.publish(LogEntryEvent(20, "Test", datetime.now()))

        # Wait for processing
        await asyncio.sleep(0.1)

        # Get stats
        stats = event_bus.get_stats()

        # Stop event bus
        await event_bus.stop()
        task.cancel()

        # Verify stats
        assert stats['events_processed'] == 2
        assert stats['errors'] == 0
        assert stats['subscriber_count'] == 2

    def test_publish_sync_without_event_loop(self, event_bus):
        """Test that publish_sync handles missing event loop gracefully."""
        # This should not crash, just log a warning
        test_event = LogEntryEvent(20, "Test", datetime.now())
        event_bus.publish_sync(test_event)

        # No assertion needed - we just want to verify it doesn't crash
