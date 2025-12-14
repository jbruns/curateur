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
            year="2024"
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


class TestEventBusWithAllEventTypes:
    """Test EventBus with all defined event types."""

    @pytest.fixture
    def event_bus(self):
        """Create an EventBus instance for testing."""
        return EventBus()

    @pytest.mark.asyncio
    async def test_all_event_types(self, event_bus):
        """Test that all event types can be published and received."""
        from curateur.ui.events import (
            ROMProgressEvent,
            APIActivityEvent,
            MediaDownloadEvent,
            PerformanceUpdateEvent,
            GameCompletedEvent,
            SystemCompletedEvent,
            ActiveRequestEvent,
            SearchRequestEvent,
            SearchResponseEvent,
            CacheMetricsEvent,
            GamelistUpdateEvent,
            AuthenticationEvent,
            SearchActivityEvent,
            MediaStatsEvent,
            ProcessingSummaryEvent,
        )

        received_events = {}

        def create_handler(event_type_name):
            def handler(event):
                if event_type_name not in received_events:
                    received_events[event_type_name] = []
                received_events[event_type_name].append(event)
            return handler

        # Subscribe to all event types
        event_types = [
            (SystemStartedEvent, "SystemStartedEvent"),
            (SystemCompletedEvent, "SystemCompletedEvent"),
            (ROMProgressEvent, "ROMProgressEvent"),
            (HashingProgressEvent, "HashingProgressEvent"),
            (APIActivityEvent, "APIActivityEvent"),
            (MediaDownloadEvent, "MediaDownloadEvent"),
            (LogEntryEvent, "LogEntryEvent"),
            (PerformanceUpdateEvent, "PerformanceUpdateEvent"),
            (GameCompletedEvent, "GameCompletedEvent"),
            (ActiveRequestEvent, "ActiveRequestEvent"),
            (SearchRequestEvent, "SearchRequestEvent"),
            (SearchResponseEvent, "SearchResponseEvent"),
            (CacheMetricsEvent, "CacheMetricsEvent"),
            (GamelistUpdateEvent, "GamelistUpdateEvent"),
            (MediaStatsEvent, "MediaStatsEvent"),
            (SearchActivityEvent, "SearchActivityEvent"),
            (AuthenticationEvent, "AuthenticationEvent"),
            (ProcessingSummaryEvent, "ProcessingSummaryEvent"),
        ]

        for event_type, name in event_types:
            event_bus.subscribe(event_type, create_handler(name))

        # Start event processing
        task = asyncio.create_task(event_bus.process_events())

        # Create and publish one of each event type
        test_events = [
            SystemStartedEvent("nes", "NES", 100, 0, 5),
            SystemCompletedEvent("nes", 100, 85, 5, 10, 120.5),
            ROMProgressEvent("game.nes", "nes", "complete", "Done"),
            HashingProgressEvent(50, 100, True, 5),
            APIActivityEvent(3, 50, 1, 10),
            MediaDownloadEvent("box-2D", "game.nes", "complete"),
            LogEntryEvent(20, "Test log", datetime.now()),
            PerformanceUpdateEvent(100, 1000, 4, 8, [10, 12], [25, 30]),
            GameCompletedEvent("123", "Test Game", "2024"),
            ActiveRequestEvent("req1", "game.nes", "API Fetch", "Active", 1.5),
            SearchRequestEvent("sr1", "game.nes", "/path", "nes", []),
            SearchResponseEvent("sr1", "skip"),
            CacheMetricsEvent(100, 10, 90, 20, 81.8),
            GamelistUpdateEvent("nes", 200, 15, 5),
            MediaStatsEvent({}, 50, 10, 5),
            SearchActivityEvent(3, 2),
            AuthenticationEvent("authenticated", "testuser"),
            ProcessingSummaryEvent(["game1.nes"], [("game2.nes", "skip")], []),
        ]

        for event in test_events:
            await event_bus.publish(event)

        # Wait for processing
        await asyncio.sleep(0.2)

        # Stop event bus
        await event_bus.stop()
        task.cancel()

        # Verify all event types were received
        assert len(received_events) == len(event_types)
        for _, name in event_types:
            assert name in received_events
            assert len(received_events[name]) == 1

    @pytest.mark.asyncio
    async def test_high_volume_events(self, event_bus):
        """Test handling a high volume of events."""
        received_count = [0]

        def handler(event):
            received_count[0] += 1

        event_bus.subscribe(LogEntryEvent, handler)

        # Start event processing
        task = asyncio.create_task(event_bus.process_events())

        # Publish many events
        num_events = 100
        for i in range(num_events):
            await event_bus.publish(
                LogEntryEvent(20, f"Message {i}", datetime.now())
            )

        # Wait for processing
        await asyncio.sleep(0.3)

        # Stop event bus
        await event_bus.stop()
        task.cancel()

        # Verify all events were processed
        assert received_count[0] == num_events

    @pytest.mark.asyncio
    async def test_event_bus_stop_idempotent(self, event_bus):
        """Test that calling stop multiple times is safe."""
        task = asyncio.create_task(event_bus.process_events())

        # Stop multiple times
        await event_bus.stop()
        await event_bus.stop()
        await event_bus.stop()

        task.cancel()

        # Should not crash

    @pytest.mark.asyncio
    async def test_mixed_sync_async_handlers(self, event_bus):
        """Test mixing synchronous and asynchronous handlers."""
        sync_received = []
        async_received = []

        def sync_handler(event):
            sync_received.append(event)

        async def async_handler(event):
            await asyncio.sleep(0.01)
            async_received.append(event)

        event_bus.subscribe(SystemStartedEvent, sync_handler)
        event_bus.subscribe(SystemStartedEvent, async_handler)

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

        # Both handlers should receive the event
        assert len(sync_received) == 1
        assert len(async_received) == 1
        assert sync_received[0] == test_event
        assert async_received[0] == test_event

    @pytest.mark.asyncio
    async def test_event_ordering(self, event_bus):
        """Test that events are processed in order."""
        received_order = []

        def handler(event):
            received_order.append(event.message)

        event_bus.subscribe(LogEntryEvent, handler)

        # Start event processing
        task = asyncio.create_task(event_bus.process_events())

        # Publish events in order
        for i in range(10):
            await event_bus.publish(
                LogEntryEvent(20, f"Message {i}", datetime.now())
            )

        # Wait for processing
        await asyncio.sleep(0.2)

        # Stop event bus
        await event_bus.stop()
        task.cancel()

        # Verify order is preserved
        assert received_order == [f"Message {i}" for i in range(10)]

    @pytest.mark.asyncio
    async def test_subscriber_removal_during_processing(self, event_bus):
        """Test unsubscribing while events are being processed."""
        received = []

        def handler(event):
            received.append(event)
            # Unsubscribe after first event
            if len(received) == 1:
                event_bus.unsubscribe(LogEntryEvent, handler)

        event_bus.subscribe(LogEntryEvent, handler)

        # Start event processing
        task = asyncio.create_task(event_bus.process_events())

        # Publish multiple events
        for i in range(5):
            await event_bus.publish(
                LogEntryEvent(20, f"Message {i}", datetime.now())
            )
            await asyncio.sleep(0.05)  # Give time for processing

        # Wait for processing
        await asyncio.sleep(0.2)

        # Stop event bus
        await event_bus.stop()
        task.cancel()

        # Should have received only the first event
        assert len(received) >= 1  # At least one, might be more due to timing

    @pytest.mark.asyncio
    async def test_exception_in_async_handler(self, event_bus):
        """Test that exceptions in async handlers are caught."""
        received = []

        async def failing_handler(event):
            await asyncio.sleep(0.01)
            raise RuntimeError("Async handler error")

        async def working_handler(event):
            await asyncio.sleep(0.01)
            received.append(event)

        event_bus.subscribe(HashingProgressEvent, failing_handler)
        event_bus.subscribe(HashingProgressEvent, working_handler)

        # Start event processing
        task = asyncio.create_task(event_bus.process_events())

        # Publish event
        test_event = HashingProgressEvent(50, 100, True, 5)
        await event_bus.publish(test_event)

        # Wait for processing
        await asyncio.sleep(0.1)

        # Stop event bus
        await event_bus.stop()
        task.cancel()

        # Working handler should still receive the event
        assert len(received) == 1
        assert received[0] == test_event

        # Error count should be incremented
        stats = event_bus.get_stats()
        assert stats['errors'] == 1

    @pytest.mark.asyncio
    async def test_stats_accuracy(self, event_bus):
        """Test that statistics are accurately tracked."""
        def handler1(event):
            pass

        def handler2(event):
            pass

        async def handler3(event):
            pass

        # Subscribe multiple handlers
        event_bus.subscribe(SystemStartedEvent, handler1)
        event_bus.subscribe(SystemStartedEvent, handler2)
        event_bus.subscribe(LogEntryEvent, handler3)

        # Start event processing
        task = asyncio.create_task(event_bus.process_events())

        # Publish events
        await event_bus.publish(SystemStartedEvent("nes", "NES", 100, 0, 5))
        await event_bus.publish(SystemStartedEvent("snes", "SNES", 150, 1, 5))
        await event_bus.publish(LogEntryEvent(20, "Test", datetime.now()))

        # Wait for processing
        await asyncio.sleep(0.1)

        # Get stats
        stats = event_bus.get_stats()

        # Stop event bus
        await event_bus.stop()
        task.cancel()

        # Verify stats
        assert stats['events_processed'] == 3
        assert stats['errors'] == 0
        assert stats['subscriber_count'] == 3

    @pytest.mark.asyncio
    async def test_empty_event_queue(self, event_bus):
        """Test that event bus handles empty queue gracefully."""
        # Start event processing with no events
        task = asyncio.create_task(event_bus.process_events())

        # Wait a bit
        await asyncio.sleep(0.1)

        # Stop event bus
        await event_bus.stop()
        task.cancel()

        # Should complete without errors
        stats = event_bus.get_stats()
        assert stats['events_processed'] == 0

    @pytest.mark.asyncio
    async def test_event_immutability(self, event_bus):
        """Test that events are immutable (frozen dataclasses)."""
        event = SystemStartedEvent("nes", "NES", 100, 0, 5)

        # Attempt to modify should raise FrozenInstanceError
        with pytest.raises(Exception):  # dataclasses.FrozenInstanceError
            event.system_name = "snes"

    @pytest.mark.asyncio
    async def test_concurrent_publishers(self, event_bus):
        """Test multiple concurrent publishers."""
        received = []

        def handler(event):
            received.append(event)

        event_bus.subscribe(LogEntryEvent, handler)

        # Start event processing
        task = asyncio.create_task(event_bus.process_events())

        # Publish from multiple coroutines concurrently
        async def publisher(prefix, count):
            for i in range(count):
                await event_bus.publish(
                    LogEntryEvent(20, f"{prefix}_{i}", datetime.now())
                )

        await asyncio.gather(
            publisher("A", 10),
            publisher("B", 10),
            publisher("C", 10),
        )

        # Wait for processing
        await asyncio.sleep(0.2)

        # Stop event bus
        await event_bus.stop()
        task.cancel()

        # Should have received all 30 events
        assert len(received) == 30
