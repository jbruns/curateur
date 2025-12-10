"""Logging handler that emits events to the event bus.

This module provides a custom logging handler that converts log records into
LogEntryEvent instances and publishes them to the event bus. This allows the
UI to display log messages in real-time.
"""

import logging
from datetime import datetime
from typing import Optional

from curateur.ui.events import LogEntryEvent
from curateur.ui.event_bus import EventBus


class EventLogHandler(logging.Handler):
    """Log handler that emits LogEntryEvent to the event bus.

    This handler converts Python logging records into LogEntryEvent instances
    and publishes them to the event bus. It is thread-safe and can be called
    from any thread.

    Example:
        >>> event_bus = EventBus()
        >>> handler = EventLogHandler(event_bus)
        >>> handler.setFormatter(logging.Formatter('%(message)s'))
        >>> logging.root.addHandler(handler)
    """

    def __init__(self, event_bus: EventBus, level: int = logging.NOTSET):
        """Initialize the event log handler.

        Args:
            event_bus: The event bus to publish log events to
            level: Minimum logging level to handle
        """
        super().__init__(level)
        self.event_bus = event_bus
        self._event_count = 0

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record as an event.

        This method is called by the logging system for each log message.
        It formats the record and publishes it as a LogEntryEvent.

        Args:
            record: The log record to emit
        """
        try:
            # Format the log message
            message = self.format(record)

            # Create log entry event
            event = LogEntryEvent(
                level=record.levelno,
                message=message,
                timestamp=datetime.fromtimestamp(record.created)
            )

            # Publish to event bus (thread-safe)
            self.event_bus.publish_sync(event)
            self._event_count += 1

        except Exception as e:
            # Don't let logging errors crash the application
            # Use handleError to report the issue through logging's error handling
            self.handleError(record)

    def get_event_count(self) -> int:
        """Get the number of log events emitted.

        Returns:
            Total count of log events published
        """
        return self._event_count


def setup_event_logging(
    event_bus: EventBus,
    level: int = logging.INFO,
    format_string: Optional[str] = None
) -> EventLogHandler:
    """Setup event-based logging.

    Convenience function to create and configure an EventLogHandler.

    Args:
        event_bus: The event bus to publish log events to
        level: Minimum logging level (default: INFO)
        format_string: Optional custom format string

    Returns:
        The configured EventLogHandler instance

    Example:
        >>> event_bus = EventBus()
        >>> handler = setup_event_logging(event_bus, level=logging.DEBUG)
        >>> logging.info("This will appear in the UI")
    """
    # Create handler
    handler = EventLogHandler(event_bus, level=level)

    # Set formatter
    if format_string is None:
        format_string = '%(message)s'

    formatter = logging.Formatter(format_string)
    handler.setFormatter(formatter)

    # Add to root logger
    logging.root.addHandler(handler)

    return handler
