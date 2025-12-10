"""
Textual UI for Curateur

Event-driven terminal UI using the Textual framework. Displays real-time
scraping progress across three tabs: Overview, Details, and Systems.
"""

import logging
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import (
    Header,
    Footer,
    TabbedContent,
    TabPane,
)
from textual.reactive import reactive

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
)


logger = logging.getLogger(__name__)


# ============================================================================
# Tab Placeholders (to be implemented in later phases)
# ============================================================================


class OverviewTab(Container):
    """Overview tab showing current operations and progress.

    To be implemented in Phase 3.
    """

    def compose(self) -> ComposeResult:
        from textual.widgets import Static
        yield Static("Overview Tab - Implementation in Progress")


class DetailsTab(Container):
    """Details tab showing logs and active requests.

    To be implemented in Phase 4.
    """

    def compose(self) -> ComposeResult:
        from textual.widgets import Static
        yield Static("Details Tab - Implementation in Progress")


class SystemsTab(Container):
    """Systems tab showing system queue and details.

    To be implemented in Phase 5.
    """

    def compose(self) -> ComposeResult:
        from textual.widgets import Static
        yield Static("Systems Tab - Implementation in Progress")


# ============================================================================
# Main Application
# ============================================================================


class CurateurUI(App):
    """Curateur Textual UI Application.

    Event-driven terminal interface for the curateur ROM scraper.
    Receives events from the scraping engine and updates the UI in real-time.
    """

    CSS_PATH = "textual_theme.tcss"

    # Track current active tab
    current_tab = reactive("overview")

    # Control flags for orchestrator
    should_quit = False
    should_skip_system = False

    BINDINGS = [
        Binding("ctrl+q", "quit_app", "Quit", show=True),
        Binding("b", "prev_game", "Back", show=False),
        Binding("n", "next_game", "Next", show=False),
        Binding("ctrl+s", "skip_system", "Skip System", show=True),
        Binding("1", "filter_logs(40)", "1:ERROR", show=False),
        Binding("2", "filter_logs(30)", "2:WARN", show=False),
        Binding("3", "filter_logs(20)", "3:INFO", show=False),
        Binding("4", "filter_logs(10)", "4:DEBUG", show=False),
        Binding("i", "show_search_dialog", "Interactive Search", show=True),
    ]

    def __init__(self, config: dict, event_bus: EventBus):
        """Initialize the Curateur UI.

        Args:
            config: Configuration dictionary from config.yaml
            event_bus: Event bus for receiving scraping events
        """
        super().__init__()
        self.config = config
        self.event_bus = event_bus
        self.current_system = None

    def compose(self) -> ComposeResult:
        """Compose the application layout."""
        yield Header(show_clock=True)

        with TabbedContent(initial="overview"):
            with TabPane("Overview", id="overview"):
                yield OverviewTab()
            with TabPane("Details", id="details"):
                yield DetailsTab()
            with TabPane("Systems", id="systems"):
                yield SystemsTab()

        yield Footer()

    def on_mount(self) -> None:
        """Setup event listeners after UI is mounted."""
        logger.info("Curateur UI mounted, subscribing to events...")

        # Subscribe to all event types
        self.event_bus.subscribe(SystemStartedEvent, self.on_system_started)
        self.event_bus.subscribe(SystemCompletedEvent, self.on_system_completed)
        self.event_bus.subscribe(ROMProgressEvent, self.on_rom_progress)
        self.event_bus.subscribe(HashingProgressEvent, self.on_hashing_progress)
        self.event_bus.subscribe(APIActivityEvent, self.on_api_activity)
        self.event_bus.subscribe(MediaDownloadEvent, self.on_media_download)
        self.event_bus.subscribe(LogEntryEvent, self.on_log_entry)
        self.event_bus.subscribe(PerformanceUpdateEvent, self.on_performance_update)
        self.event_bus.subscribe(GameCompletedEvent, self.on_game_completed)
        self.event_bus.subscribe(ActiveRequestEvent, self.on_active_request)

        # Start event processing in background
        self.run_worker(self.event_bus.process_events(), name="event_processor")

        logger.info("Event subscriptions complete, UI ready")

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Track which tab is currently active."""
        self.current_tab = event.tab.id
        logger.debug(f"Tab activated: {event.tab.id}")

    # ========================================================================
    # Event Handlers (Stubs - to be implemented in later phases)
    # ========================================================================

    async def on_system_started(self, event: SystemStartedEvent) -> None:
        """Handle system started event.

        Phase 3: Will update Overview tab current system display.
        """
        self.current_system = event
        logger.info(
            f"System started: {event.system_fullname} "
            f"({event.current_index + 1}/{event.total_systems})"
        )

    async def on_system_completed(self, event: SystemCompletedEvent) -> None:
        """Handle system completed event.

        Phase 3: Will update Overview tab with final statistics.
        Phase 5: Will update Systems tab tree with completion status.
        """
        logger.info(
            f"System completed: {event.system_name} - "
            f"Success: {event.successful}, Failed: {event.failed}, Skipped: {event.skipped}"
        )

    async def on_rom_progress(self, event: ROMProgressEvent) -> None:
        """Handle ROM progress event.

        Phase 3: Will update Overview tab current operation status.
        """
        logger.debug(f"ROM progress: {event.rom_name} - {event.status}")

    async def on_hashing_progress(self, event: HashingProgressEvent) -> None:
        """Handle hashing progress event.

        Phase 3: Will update Overview tab hashing section.
        """
        logger.debug(
            f"Hashing: {event.completed}/{event.total} "
            f"(skipped: {event.skipped})"
        )

    async def on_api_activity(self, event: APIActivityEvent) -> None:
        """Handle API activity event.

        Phase 3: Will update Overview tab API section.
        """
        logger.debug(
            f"API: metadata {event.metadata_in_flight} in-flight, "
            f"search {event.search_in_flight} in-flight"
        )

    async def on_media_download(self, event: MediaDownloadEvent) -> None:
        """Handle media download event.

        Phase 3: Will update Overview tab media section.
        """
        logger.debug(
            f"Media: {event.media_type} for {event.rom_name} - {event.status}"
        )

    async def on_log_entry(self, event: LogEntryEvent) -> None:
        """Handle log entry event.

        Phase 4: Will add log to Details tab.
        Phase 3: Will show WARNING/ERROR notifications on Overview tab.
        """
        logger.debug(f"Log: [{logging.getLevelName(event.level)}] {event.message}")

        # Show notification on Overview tab for WARNING/ERROR
        if event.level >= logging.WARNING and self.current_tab == "overview":
            severity = "error" if event.level >= logging.ERROR else "warning"
            short_msg = event.message[:60] + "..." if len(event.message) > 60 else event.message
            self.notify(
                f"{logging.getLevelName(event.level)}: {short_msg}",
                severity=severity,
                timeout=5
            )

    async def on_performance_update(self, event: PerformanceUpdateEvent) -> None:
        """Handle performance update event.

        Phase 3: Will update Overview tab performance panel.
        """
        logger.debug(
            f"Performance: quota {event.api_quota_used}/{event.api_quota_limit}, "
            f"threads {event.threads_in_use}/{event.threads_limit}"
        )

    async def on_game_completed(self, event: GameCompletedEvent) -> None:
        """Handle game completed event.

        Phase 3: Will add game to Overview tab spotlight widget.
        """
        logger.debug(f"Game completed: {event.title} ({event.year})")

    async def on_active_request(self, event: ActiveRequestEvent) -> None:
        """Handle active request event.

        Phase 4: Will update Details tab active requests table.
        """
        logger.debug(
            f"Active request: {event.rom_name} - {event.stage} - {event.status}"
        )

    # ========================================================================
    # Action Handlers
    # ========================================================================

    def action_quit_app(self) -> None:
        """Quit the application."""
        logger.info("Quit requested by user")
        self.should_quit = True
        self.exit()

    def action_skip_system(self) -> None:
        """Skip current system."""
        if self.current_system:
            logger.info(f"Skip system requested: {self.current_system.system_fullname}")
            self.should_skip_system = True
            self.notify(
                f"Skipping {self.current_system.system_fullname}",
                severity="warning",
                timeout=3
            )
        else:
            self.notify("No active system to skip", severity="warning", timeout=2)

    def action_prev_game(self) -> None:
        """Navigate to previous game in spotlight."""
        if self.current_tab != "overview":
            self.notify(
                "Game navigation is only available on the Overview tab",
                severity="warning",
                timeout=3
            )
            return

        # Phase 3: Will call spotlight widget method
        logger.debug("Previous game requested")

    def action_next_game(self) -> None:
        """Navigate to next game in spotlight."""
        if self.current_tab != "overview":
            self.notify(
                "Game navigation is only available on the Overview tab",
                severity="warning",
                timeout=3
            )
            return

        # Phase 3: Will call spotlight widget method
        logger.debug("Next game requested")

    def action_filter_logs(self, level: int) -> None:
        """Filter logs by level (only available on Details tab)."""
        if self.current_tab != "details":
            self.notify(
                "Log filtering is only available on the Details tab",
                severity="warning",
                timeout=3
            )
            return

        # Phase 4: Will call log widget method
        level_name = logging.getLevelName(level)
        logger.debug(f"Log filter requested: {level_name}")
        self.notify(f"Log filter set to: {level_name}", timeout=2)

    def action_show_search_dialog(self) -> None:
        """Show interactive search dialog (demo)."""
        # Phase 7: Will implement actual search dialog
        self.notify("Interactive search - Implementation in progress", timeout=3)

    async def shutdown(self) -> None:
        """Graceful shutdown of the UI."""
        logger.info("Shutting down Curateur UI...")
        await self.event_bus.stop()
        logger.info("UI shutdown complete")


# ============================================================================
# Standalone Test Runner
# ============================================================================


if __name__ == "__main__":
    import asyncio
    from datetime import datetime

    # Create event bus for testing
    event_bus = EventBus()

    # Create dummy config
    config = {
        'scraping': {
            'systems': ['nes', 'snes', 'genesis']
        }
    }

    # Create app
    app = CurateurUI(config, event_bus)

    # Override on_mount to add event simulation
    original_on_mount = app.on_mount

    def custom_on_mount():
        original_on_mount()

        # Simulate some events after a delay
        async def simulate_events():
            await asyncio.sleep(2)

            # Simulate system started
            await event_bus.publish(SystemStartedEvent(
                system_name="nes",
                system_fullname="Nintendo Entertainment System",
                total_roms=100,
                current_index=0,
                total_systems=3
            ))

            # Simulate some logs
            await event_bus.publish(LogEntryEvent(
                level=logging.INFO,
                message="Starting ROM scanning...",
                timestamp=datetime.now()
            ))

            await asyncio.sleep(1)

            await event_bus.publish(LogEntryEvent(
                level=logging.WARNING,
                message="API rate limit approaching threshold",
                timestamp=datetime.now()
            ))

        # Run simulation in background using Textual's worker system
        app.run_worker(simulate_events(), name="event_simulator")

    app.on_mount = custom_on_mount

    # Run app
    app.run()
