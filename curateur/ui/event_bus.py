"""Event bus for thread-safe UI updates.

The EventBus provides a publish-subscribe mechanism for delivering events from
the scraping engine (which runs in async context) to the UI layer. It ensures
thread-safe event delivery and error isolation.
"""

import asyncio
import inspect
import logging
from typing import Callable, Any, Optional
from collections import defaultdict


logger = logging.getLogger(__name__)


class EventBus:
    """Thread-safe event bus for UI updates.

    The event bus allows components to subscribe to specific event types and
    receive notifications when those events are published. Events are processed
    asynchronously in the UI event loop, ensuring thread safety.

    Example:
        >>> bus = EventBus()
        >>> bus.subscribe(SystemStartedEvent, lambda e: print(f"System: {e.system_name}"))
        >>> await bus.publish(SystemStartedEvent("nes", "Nintendo Entertainment System", 100, 0, 5))
    """

    def __init__(self):
        """Initialize the event bus."""
        self._subscribers: dict[type, list[Callable]] = defaultdict(list)
        self._queue: asyncio.Queue = asyncio.Queue()
        self._processing: bool = False
        self._event_count: int = 0
        self._error_count: int = 0

    def subscribe(self, event_type: type, callback: Callable) -> None:
        """Subscribe to events of a specific type.

        Args:
            event_type: The event class to subscribe to
            callback: Function to call when event is published.
                     Can be sync or async.
        """
        self._subscribers[event_type].append(callback)
        logger.debug(f"Subscribed to {event_type.__name__} (total subscribers: {len(self._subscribers[event_type])})")

    def unsubscribe(self, event_type: type, callback: Callable) -> None:
        """Unsubscribe from events of a specific type.

        Args:
            event_type: The event class to unsubscribe from
            callback: The callback function to remove
        """
        if event_type in self._subscribers:
            try:
                self._subscribers[event_type].remove(callback)
                logger.debug(f"Unsubscribed from {event_type.__name__}")
            except ValueError:
                logger.warning(f"Callback not found for {event_type.__name__}")

    async def publish(self, event: Any) -> None:
        """Publish an event (async context).

        This method is safe to call from async code. The event will be
        queued and processed by the event loop.

        Args:
            event: The event instance to publish
        """
        await self._queue.put(event)

    def publish_sync(self, event: Any) -> None:
        """Publish an event from synchronous context.

        This method is safe to call from sync code (e.g., log handlers).
        It schedules the event to be published in the event loop.

        Args:
            event: The event instance to publish
        """
        try:
            # Try to get the running event loop
            loop = asyncio.get_running_loop()
            # Schedule the publish coroutine
            asyncio.run_coroutine_threadsafe(self.publish(event), loop)
        except RuntimeError:
            # No running event loop - this shouldn't happen in production
            # but we'll log it for debugging
            logger.warning(f"No event loop running, cannot publish {type(event).__name__}")

    async def process_events(self) -> None:
        """Process events from the queue.

        This should be called as a background task in the UI event loop.
        It runs continuously, processing events as they arrive.

        Example:
            >>> app.run_worker(event_bus.process_events())
        """
        self._processing = True
        logger.info("Event bus processing started")

        try:
            while self._processing:
                # Wait for next event
                event = await self._queue.get()
                event_type = type(event)
                self._event_count += 1

                # Get all subscribers for this event type
                callbacks = self._subscribers.get(event_type, [])

                if not callbacks:
                    logger.debug(f"No subscribers for {event_type.__name__}")
                    continue

                # Call each subscriber
                for callback in callbacks:
                    try:
                        if inspect.iscoroutinefunction(callback):
                            await callback(event)
                        else:
                            callback(event)
                    except Exception as e:
                        self._error_count += 1
                        logger.error(
                            f"Error in event handler for {event_type.__name__}: {e}",
                            exc_info=True
                        )
                        # Continue processing other handlers

                # Mark task as done
                self._queue.task_done()

        except asyncio.CancelledError:
            logger.info("Event bus processing cancelled")
            raise
        finally:
            self._processing = False

    async def stop(self) -> None:
        """Stop processing events.

        Waits for pending events to be processed before stopping, with a timeout.
        """
        logger.info("Stopping event bus...")
        self._processing = False

        # Wait for queue to be empty with a timeout
        try:
            await asyncio.wait_for(self._queue.join(), timeout=1.0)
            logger.debug("Event queue drained successfully")
        except asyncio.TimeoutError:
            # Queue didn't drain in time - force drain remaining items
            remaining = self._queue.qsize()
            if remaining > 0:
                logger.warning(f"Event queue timeout - {remaining} events remaining, force draining")
                # Drain remaining items without processing
                while not self._queue.empty():
                    try:
                        self._queue.get_nowait()
                        self._queue.task_done()
                    except asyncio.QueueEmpty:
                        break

        logger.info(
            f"Event bus stopped. Processed {self._event_count} events "
            f"with {self._error_count} errors"
        )

    def get_stats(self) -> dict[str, int]:
        """Get event bus statistics.

        Returns:
            Dictionary with 'events_processed', 'errors', 'queue_size', 'subscriber_count'
        """
        return {
            'events_processed': self._event_count,
            'errors': self._error_count,
            'queue_size': self._queue.qsize(),
            'subscriber_count': sum(len(callbacks) for callbacks in self._subscribers.values())
        }

    @property
    def is_processing(self) -> bool:
        """Check if event bus is currently processing events."""
        return self._processing
