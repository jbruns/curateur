"""
Textual UI for Curateur

Event-driven terminal UI using the Textual framework. Displays real-time
scraping progress across three tabs: Overview, Details, and Systems.
"""

import logging
from datetime import datetime
from typing import Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Header,
    Footer,
    TabbedContent,
    TabPane,
    Static,
    ProgressBar,
    Rule,
)
from textual.reactive import reactive
from rich.text import Text

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
# Overview Tab Widgets
# ============================================================================


class OverallProgressWidget(Container):
    """Displays overall run progress with progress bar."""

    # Reactive properties updated by events
    systems_complete = reactive(0)
    systems_total = reactive(0)
    processed = reactive(0)
    total_roms = reactive(0)
    successful = reactive(0)
    skipped = reactive(0)
    failed = reactive(0)

    def compose(self) -> ComposeResult:
        yield Static(id="overall-progress-header")
        yield ProgressBar(id="overall-progress-bar", total=100, show_eta=False)

    def on_mount(self) -> None:
        """Initialize overall progress display."""
        self.border_title = "Overall Progress"
        self.update_display()

    def watch_processed(self, old_value: int, new_value: int) -> None:
        """Update display when processed count changes."""
        self.update_display()

    def watch_successful(self, old_value: int, new_value: int) -> None:
        """Update display when successful count changes."""
        self.update_display()

    def watch_systems_complete(self, old_value: int, new_value: int) -> None:
        """Update display when systems complete count changes."""
        self.update_display()

    def update_display(self) -> None:
        """Render overall progress."""
        progress_pct = (self.processed / self.total_roms * 100) if self.total_roms > 0 else 0

        # Header text
        header = Text()
        header.append(f"Systems: {self.systems_complete}/{self.systems_total}\n", style="white")
        header.append(f"ROMs: {self.processed}/{self.total_roms} ", style="cyan")
        header.append(f"({progress_pct:.1f}%)", style="bright_green")
        header.append("\n")

        # Status counts with glyphs
        header.append(f"✓ {self.successful} ", style="bright_green")
        header.append(f"⊝ {self.skipped} ", style="dim yellow")
        header.append(f"✗ {self.failed}", style="red")

        self.query_one("#overall-progress-header", Static).update(header)

        # Update progress bar
        progress_bar = self.query_one("#overall-progress-bar", ProgressBar)
        progress_bar.update(total=self.total_roms if self.total_roms > 0 else 100, progress=self.processed)


class CurrentSystemOperations(Container):
    """Displays detailed progress for the current system."""

    # Reactive properties
    system_name = reactive("")
    hash_completed = reactive(0)
    hash_total = reactive(0)
    hash_skipped = reactive(0)
    hash_in_progress = reactive(False)
    metadata_in_flight = reactive(0)
    metadata_total = reactive(0)
    search_in_flight = reactive(0)
    search_total = reactive(0)
    media_in_flight = reactive(0)
    media_downloaded = reactive(0)
    media_failed = reactive(0)

    def compose(self) -> ComposeResult:
        yield Static(id="hashing-content")
        yield Rule(line_style="heavy")
        yield Static(id="api-content")
        yield Rule(line_style="heavy")
        yield Static(id="media-content")

    def on_mount(self) -> None:
        """Initialize system operations display."""
        self.border_title = "Current System"
        self.update_display()

    def watch_system_name(self, old_value: str, new_value: str) -> None:
        """Update border title when system changes."""
        self.border_title = new_value if new_value else "Current System"

    def watch_hash_completed(self, old_value: int, new_value: int) -> None:
        """Update display when hashing progress changes."""
        self.update_hashing()

    def watch_metadata_in_flight(self, old_value: int, new_value: int) -> None:
        """Update display when API activity changes."""
        self.update_api()

    def watch_media_in_flight(self, old_value: int, new_value: int) -> None:
        """Update display when media downloads change."""
        self.update_media()

    def update_display(self) -> None:
        """Render all sections."""
        self.update_hashing()
        self.update_api()
        self.update_media()

    def update_hashing(self) -> None:
        """Update hashing section."""
        hash_pct = (self.hash_completed / self.hash_total * 100) if self.hash_total > 0 else 0
        hash_content = Text()
        hash_content.append("Hashing", style="bold cyan")

        if self.hash_in_progress:
            spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            spinner = spinner_chars[self.hash_completed % len(spinner_chars)]
            hash_content.append(f" {spinner}", style="bright_magenta")

        hash_content.append(f"\n{self.hash_completed}/{self.hash_total} ", style="white")
        hash_content.append(f"({hash_pct:.1f}%)", style="bright_green")

        if self.hash_skipped > 0:
            hash_content.append(f" ⊝ {self.hash_skipped}", style="dim yellow")

        self.query_one("#hashing-content", Static).update(hash_content)

    def update_api(self) -> None:
        """Update API section."""
        api_content = Text()
        api_content.append("API\n", style="bold cyan")

        # Metadata requests
        spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        metadata_spinner = spinner_chars[self.metadata_total % len(spinner_chars)]
        api_content.append("Metadata: ", style="dim")
        if self.metadata_in_flight > 0:
            api_content.append(f"{metadata_spinner} {self.metadata_in_flight} ", style="yellow")
        else:
            api_content.append("Idle ", style="dim")
        api_content.append(f"✓ {self.metadata_total}\n", style="bright_green")

        # Search requests
        search_spinner = spinner_chars[self.search_total % len(spinner_chars)]
        api_content.append("Search: ", style="dim")
        if self.search_in_flight > 0:
            api_content.append(f"{search_spinner} {self.search_in_flight} ", style="yellow")
        else:
            api_content.append("Idle ", style="dim")
        api_content.append(f"✓ {self.search_total}", style="bright_green")

        self.query_one("#api-content", Static).update(api_content)

    def update_media(self) -> None:
        """Update media section."""
        media_content = Text()
        media_content.append("Media\n", style="bold cyan")

        if self.media_in_flight > 0:
            media_content.append(f"⬇ {self.media_in_flight} ", style="yellow")
        media_content.append(f"✓ {self.media_downloaded} ", style="bright_green")
        media_content.append(f"✗ {self.media_failed}", style="red")

        self.query_one("#media-content", Static).update(media_content)


class GameSpotlightWidget(Static):
    """Displays completed games with navigation."""

    games = reactive(list)
    index = reactive(0)

    def on_mount(self) -> None:
        """Set up spotlight."""
        self.border_title = "Game Spotlight"
        self.games = []
        self.update_display()

    def add_game(self, game: dict) -> None:
        """Add a completed game to the spotlight."""
        self.games = self.games + [game]
        if len(self.games) == 1:
            self.update_display()

    def next_game(self) -> None:
        """Advance to next game."""
        if len(self.games) > 0:
            self.index = (self.index + 1) % len(self.games)

    def prev_game(self) -> None:
        """Go to previous game."""
        if len(self.games) > 0:
            self.index = (self.index - 1) % len(self.games)

    def watch_index(self, old_index: int, new_index: int) -> None:
        """Update display when index changes."""
        self.update_display()

    def update_display(self) -> None:
        """Render current game."""
        if not self.games:
            self.update("■ WAITING FOR COMPLETED GAMES ■")
            return

        game = self.games[self.index]

        # Build display text
        content = Text()
        content.append("Completed: ", style="bold")
        content.append(game.get("title", "Unknown"), style="bold magenta")
        content.append(f" ({game.get('year', 'N/A')})", style="cyan")
        content.append("\n\n")

        # Metadata
        content.append("Genre: ", style="dim")
        content.append(game.get("genre", "Unknown"), style="cyan")
        content.append(" | ", style="dim")
        content.append("Developer: ", style="dim")
        content.append(game.get("developer", "Unknown"), style="bright_green")
        content.append("\n\n")

        # Description
        content.append("Description:\n", style="bold dim")
        desc = game.get("description", "No description available")
        # Truncate if too long
        if len(desc) > 300:
            desc = desc[:297] + "..."
        content.append(desc, style="white")
        content.append("\n")

        # Confidence
        confidence = game.get("confidence", 0.0)
        content.append(f"\nMatch Confidence: {confidence*100:.0f}%", style="bright_magenta")

        # Navigation hint
        nav_text = f"({self.index + 1}/{len(self.games)})"
        content.append("\n\n" + " " * (60 - len(nav_text)), style="dim")
        content.append(nav_text, style="dim")
        content.append(" [N, B] Navigate", style="dim cyan")

        self.update(content)


def create_sparkline(values: list, width: int = 30) -> str:
    """Create a sparkline visualization from a list of values."""
    if not values:
        return "─" * width

    # Pad or trim to width
    if len(values) < width:
        values = [0] * (width - len(values)) + values
    else:
        values = values[-width:]

    # Normalize to 0-7 range for sparkline chars
    min_val = min(values) if values else 0
    max_val = max(values) if values else 1
    val_range = max_val - min_val if max_val > min_val else 1

    sparkline_chars = ["▁", "▂", "▃", "▄", "▅", "▆", "▇", "█"]
    result = ""
    for v in values:
        normalized = int(((v - min_val) / val_range) * 7)
        result += sparkline_chars[normalized]

    return result


class PerformancePanel(Container):
    """Displays performance metrics."""

    # Reactive properties
    throughput_history = reactive(list)
    api_rate_history = reactive(list)
    quota_used = reactive(0)
    quota_limit = reactive(0)
    threads_in_use = reactive(0)
    threads_limit = reactive(0)
    cache_hit_rate = reactive(0.0)

    def compose(self) -> ComposeResult:
        yield Static(id="throughput")
        yield Static(id="api-rate")
        yield Static(id="threads-info")
        yield Static(id="api-quota")

    def on_mount(self) -> None:
        """Initialize performance panel."""
        self.border_title = "Performance Metrics"
        self.throughput_history = []
        self.api_rate_history = []
        self.update_display()

    def watch_quota_used(self, old_value: int, new_value: int) -> None:
        """Update display when quota changes."""
        self.update_quota()

    def watch_threads_in_use(self, old_value: int, new_value: int) -> None:
        """Update display when thread usage changes."""
        self.update_threads()

    def watch_throughput_history(self, old_value: list, new_value: list) -> None:
        """Update display when throughput history changes."""
        self.update_throughput()

    def watch_api_rate_history(self, old_value: list, new_value: list) -> None:
        """Update display when API rate history changes."""
        self.update_api_rate()

    def update_display(self) -> None:
        """Render all metrics."""
        self.update_throughput()
        self.update_api_rate()
        self.update_threads()
        self.update_quota()

    def update_throughput(self) -> None:
        """Update throughput line."""
        spark = create_sparkline(self.throughput_history, width=30)
        current = self.throughput_history[-1] if self.throughput_history else 0
        self.query_one("#throughput", Static).update(
            f"[bold]Throughput:[/bold] [green]{spark}[/green] [cyan]{current:.1f} ROMs/hr[/cyan]"
        )

    def update_api_rate(self) -> None:
        """Update API rate line."""
        spark = create_sparkline(self.api_rate_history, width=30)
        current = self.api_rate_history[-1] if self.api_rate_history else 0
        self.query_one("#api-rate", Static).update(
            f"[bold]API Rate:[/bold]   [yellow]{spark}[/yellow] [cyan]{current:.1f} calls/min[/cyan]"
        )

    def update_threads(self) -> None:
        """Update threads line."""
        self.query_one("#threads-info", Static).update(
            f"[bold]Threads:[/bold] {self.threads_in_use}/{self.threads_limit} | "
            f"[bold]Cache Hit Rate:[/bold] {self.cache_hit_rate:.1%}"
        )

    def update_quota(self) -> None:
        """Update quota line."""
        quota_pct = (self.quota_used / self.quota_limit * 100) if self.quota_limit > 0 else 0
        quota_bar = self.create_inline_progress_bar(self.quota_used, self.quota_limit, 30)
        self.query_one("#api-quota", Static).update(
            f"[bold]API Quota:[/bold] {self.quota_used}/{self.quota_limit} ({quota_pct:.1f}%) [yellow]{quota_bar}[/yellow]"
        )

    @staticmethod
    def create_inline_progress_bar(progress: int, total: int, width: int = 30) -> str:
        """Create an inline progress bar using block characters."""
        if total == 0:
            filled = 0
        else:
            filled = int((progress / total) * width)
        bar = "█" * filled + "░" * (width - filled)
        return bar


# ============================================================================
# Details Tab Widgets
# ============================================================================


class FilterableLogWidget(Container):
    """Log viewer with filtering capabilities."""

    # Reactive properties
    log_level = reactive(logging.INFO)
    filter_text = reactive("")

    def compose(self) -> ComposeResult:
        from textual.widgets import Input, RichLog
        yield Input(placeholder="Filter logs (regex)...", id="log-filter")
        yield RichLog(id="logs", highlight=True, wrap=True, markup=True)

    def on_mount(self) -> None:
        """Initialize log widget."""
        self.border_title = "Logs (Filter: 1-ERROR, 2-WARNING, 3-INFO, 4-DEBUG)"

    def append_log(self, level: int, message: str, timestamp: datetime = None) -> None:
        """Append a single log entry."""
        # Check filter
        if self.filter_text:
            try:
                import re
                if not re.search(self.filter_text, message, re.IGNORECASE):
                    return
            except Exception:
                pass  # Invalid regex, skip filtering

        # Check log level
        if level < self.log_level:
            return

        from textual.widgets import RichLog
        try:
            log_widget = self.query_one("#logs", RichLog)

            # Color by level
            level_name = logging.getLevelName(level)
            colors = {
                "DEBUG": "dim white",
                "INFO": "cyan",
                "WARNING": "yellow",
                "ERROR": "red",
                "CRITICAL": "bold red",
            }
            color = colors.get(level_name, "white")

            # Format timestamp
            if timestamp:
                time_str = timestamp.strftime("%H:%M:%S")
            else:
                from datetime import datetime
                time_str = datetime.now().strftime("%H:%M:%S")

            text = Text()
            text.append(f"[{time_str}] ", style="dim")
            text.append(f"[{level_name:8}] ", style=color)
            text.append(message)

            log_widget.write(text)
        except Exception as e:
            logger.debug(f"Failed to append log: {e}")

    def on_input_changed(self, event) -> None:
        """Handle filter text changes."""
        from textual.widgets import Input
        if isinstance(event.input, Input) and event.input.id == "log-filter":
            self.filter_text = event.value
            # Note: We don't reload logs, just filter new ones as they come

    def set_log_level(self, level: int) -> None:
        """Set log level filter."""
        self.log_level = level
        level_name = logging.getLevelName(level)
        self.border_title = f"Logs (Current: {level_name})"

    def clear_logs(self) -> None:
        """Clear all logs."""
        from textual.widgets import RichLog
        try:
            log_widget = self.query_one("#logs", RichLog)
            log_widget.clear()
        except Exception as e:
            logger.debug(f"Failed to clear logs: {e}")


class ActiveRequestsTable(Container):
    """Table showing currently active requests."""

    # Track active requests by ROM name
    active_requests = reactive(dict)

    def compose(self) -> ComposeResult:
        from textual.widgets import DataTable
        yield DataTable(id="active-requests-table")

    def on_mount(self) -> None:
        """Initialize table."""
        from textual.widgets import DataTable
        self.border_title = "Active Requests (0 concurrent)"
        self.active_requests = {}

        table = self.query_one("#active-requests-table", DataTable)
        table.add_columns("ROM", "Stage", "Duration", "Status")
        table.cursor_type = "row"

    def update_request(self, rom_name: str, stage: str, status: str, duration: float = 0.0) -> None:
        """Add or update an active request."""
        from textual.widgets import DataTable

        try:
            table = self.query_one("#active-requests-table", DataTable)

            # Update or add request
            if rom_name in self.active_requests:
                # Update existing row
                row_key = self.active_requests[rom_name]
                table.update_cell(row_key, "ROM", rom_name)
                table.update_cell(row_key, "Stage", stage)
                table.update_cell(row_key, "Duration", f"{duration:.1f}s")
                table.update_cell(row_key, "Status", status)
            else:
                # Add new row
                row_key = table.add_row(
                    rom_name,
                    stage,
                    f"{duration:.1f}s",
                    status
                )
                self.active_requests = {**self.active_requests, rom_name: row_key}

            # Update border title with count
            count = len(self.active_requests)
            self.border_title = f"Active Requests ({count} concurrent)"

        except Exception as e:
            logger.debug(f"Failed to update active request: {e}")

    def remove_request(self, rom_name: str) -> None:
        """Remove a completed request."""
        from textual.widgets import DataTable

        try:
            if rom_name in self.active_requests:
                table = self.query_one("#active-requests-table", DataTable)
                row_key = self.active_requests[rom_name]
                table.remove_row(row_key)

                # Update dictionary
                new_requests = dict(self.active_requests)
                del new_requests[rom_name]
                self.active_requests = new_requests

                # Update border title with count
                count = len(self.active_requests)
                self.border_title = f"Active Requests ({count} concurrent)"

        except Exception as e:
            logger.debug(f"Failed to remove active request: {e}")

    def clear_all(self) -> None:
        """Clear all active requests."""
        from textual.widgets import DataTable

        try:
            table = self.query_one("#active-requests-table", DataTable)
            table.clear()
            self.active_requests = {}
            self.border_title = "Active Requests (0 concurrent)"
        except Exception as e:
            logger.debug(f"Failed to clear active requests: {e}")


# ============================================================================
# Systems Tab Widgets
# ============================================================================


class SystemDetailPanel(Container):
    """Detailed statistics panel for selected system."""

    # Reactive property for selected system
    selected_system = reactive("")

    # Track system statistics
    system_stats = reactive(dict)

    def compose(self) -> ComposeResult:
        from textual.containers import VerticalScroll
        with VerticalScroll():
            yield Static(id="system-detail-content")

    def on_mount(self) -> None:
        """Initialize detail panel."""
        self.border_title = "System Details"
        self.system_stats = {}
        self.update_details()

    def watch_selected_system(self, old: str, new: str) -> None:
        """Update detail panel when system changes."""
        self.update_details()

    def watch_system_stats(self, old: dict, new: dict) -> None:
        """Update display when stats change."""
        self.update_details()

    def update_system_stats(self, system_name: str, stats: dict) -> None:
        """Update statistics for a system."""
        new_stats = dict(self.system_stats)
        new_stats[system_name] = stats
        self.system_stats = new_stats

        # Update display if this is the selected system
        if system_name == self.selected_system:
            self.update_details()

    def update_details(self) -> None:
        """Render details for the selected system."""
        content = Text()

        if not self.selected_system:
            content.append("No system selected", style="dim")
            self.border_title = "System Details"
        elif self.selected_system not in self.system_stats:
            content.append(f"Waiting for {self.selected_system} to start...", style="dim")
            self.border_title = self.selected_system
        else:
            stats = self.system_stats[self.selected_system]
            self.border_title = stats.get("fullname", self.selected_system)

            # ROM Statistics
            content.append("● ROM STATISTICS\n", style="bold cyan")
            content.append(f"  Total:      {stats.get('total_roms', 0):>4}\n", style="white")
            content.append(f"  Successful: {stats.get('successful', 0):>4}\n", style="bright_green")
            content.append(f"  Failed:     {stats.get('failed', 0):>4}\n", style="red")
            content.append(f"  Skipped:    {stats.get('skipped', 0):>4}\n\n", style="yellow")

            # Processing Status
            status = stats.get('status', 'pending')
            content.append("● STATUS\n", style="bold cyan")
            if status == "complete":
                content.append(f"  ✓ Complete", style="bright_green")
            elif status == "in_progress":
                content.append(f"  ⚡ In Progress", style="yellow")
            else:
                content.append(f"  ⏸ Pending", style="dim")

            if stats.get('duration'):
                content.append(f" ({stats['duration']:.1f}s)", style="dim")
            content.append("\n\n")

            # Summary
            if stats.get('summary'):
                content.append("● SUMMARY\n", style="bold cyan")
                content.append(stats['summary'], style="dim white")

        try:
            self.query_one("#system-detail-content", Static).update(content)
        except Exception as e:
            logger.debug(f"Failed to update system details: {e}")


# ============================================================================
# Tab Containers
# ============================================================================


class OverviewTab(Container):
    """Overview tab showing current operations and progress."""

    def compose(self) -> ComposeResult:
        with Horizontal():
            # Left column (25% width): Progress and system operations
            with Vertical(id="left-column"):
                yield OverallProgressWidget(id="overall-progress")
                yield CurrentSystemOperations(id="current-system")

            # Right column (75% width): Spotlight and performance
            with Vertical(id="right-column"):
                yield GameSpotlightWidget(id="spotlight")
                yield PerformancePanel(id="performance")


class DetailsTab(Container):
    """Details tab showing logs and active requests."""

    def compose(self) -> ComposeResult:
        yield FilterableLogWidget(id="filterable-logs")
        yield ActiveRequestsTable(id="active-requests")


class SystemsTab(Container):
    """Systems tab showing system queue and details."""

    def compose(self) -> ComposeResult:
        from textual.widgets import Tree
        with Horizontal():
            # Left side: Tree view of systems (30% width)
            tree = Tree("Systems", id="systems-tree")
            tree.show_root = True
            tree.show_guides = True
            yield tree

            # Right side: Detail panel (70% width)
            yield SystemDetailPanel(id="system-detail-panel")

    def on_mount(self) -> None:
        """Initialize systems tree."""
        from textual.widgets import Tree
        tree = self.query_one("#systems-tree", Tree)
        tree.border_title = "System Queue"

        # Initialize with systems from config
        try:
            systems = self.app.config.get('scraping', {}).get('systems', [])
            if systems:
                for system_name in systems:
                    # Add placeholder nodes for configured systems
                    label = f"⏸ {system_name} (0/0)"
                    tree.root.add_leaf(label, data=system_name)

                tree.root.expand()

                # Select first system by default
                if tree.root.children:
                    tree.select_node(tree.root.children[0])
                    detail_panel = self.query_one("#system-detail-panel", SystemDetailPanel)
                    detail_panel.selected_system = systems[0]
        except Exception as e:
            logger.debug(f"Failed to initialize systems tree: {e}")

    def update_system_node(self, system_name: str, fullname: str, successful: int, total: int, status: str = "in_progress") -> None:
        """Update a system node in the tree."""
        from textual.widgets import Tree

        try:
            tree = self.query_one("#systems-tree", Tree)

            # Determine status icon
            if status == "complete":
                if successful == total:
                    icon = "✓"
                else:
                    icon = "✓"  # Complete with some failures
            elif status == "in_progress":
                icon = "⚡"
            else:
                icon = "⏸"

            # Find and update the node
            label = f"{icon} {fullname} ({successful}/{total})"

            # Search for the node with matching data
            for node in tree.root.children:
                if node.data == system_name:
                    node.set_label(label)
                    break
            else:
                # Node doesn't exist, add it
                tree.root.add_leaf(label, data=system_name)

        except Exception as e:
            logger.debug(f"Failed to update system node: {e}")

    def on_tree_node_selected(self, event) -> None:
        """Handle tree selection."""
        from textual.widgets import Tree

        try:
            if hasattr(event, 'node') and event.node.data:
                detail_panel = self.query_one("#system-detail-panel", SystemDetailPanel)
                detail_panel.selected_system = event.node.data
        except Exception as e:
            logger.debug(f"Failed to handle tree selection: {e}")


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
        """Handle system started event."""
        self.current_system = event
        logger.info(
            f"System started: {event.system_fullname} "
            f"({event.current_index + 1}/{event.total_systems})"
        )

        # Update overall progress widget
        try:
            overall_progress = self.query_one("#overall-progress", OverallProgressWidget)
            overall_progress.systems_total = event.total_systems
            overall_progress.total_roms += event.total_roms
        except Exception as e:
            logger.debug(f"Failed to update overall progress: {e}")

        # Update current system widget
        try:
            current_system = self.query_one("#current-system", CurrentSystemOperations)
            current_system.system_name = event.system_fullname
            current_system.hash_total = event.total_roms
            current_system.hash_completed = 0
            current_system.hash_skipped = 0
        except Exception as e:
            logger.debug(f"Failed to update current system: {e}")

        # Update Systems tab
        try:
            systems_tab = self.query_one(SystemsTab)
            systems_tab.update_system_node(
                event.system_name,
                event.system_fullname,
                0,
                event.total_roms,
                "in_progress"
            )

            # Initialize system stats in detail panel
            detail_panel = self.query_one("#system-detail-panel", SystemDetailPanel)
            detail_panel.update_system_stats(event.system_name, {
                "fullname": event.system_fullname,
                "total_roms": event.total_roms,
                "successful": 0,
                "failed": 0,
                "skipped": 0,
                "status": "in_progress",
                "summary": f"Started processing {event.total_roms} ROMs..."
            })
        except Exception as e:
            logger.debug(f"Failed to update Systems tab: {e}")

    async def on_system_completed(self, event: SystemCompletedEvent) -> None:
        """Handle system completed event."""
        logger.info(
            f"System completed: {event.system_name} - "
            f"Success: {event.successful}, Failed: {event.failed}, Skipped: {event.skipped}"
        )

        # Update overall progress widget
        try:
            overall_progress = self.query_one("#overall-progress", OverallProgressWidget)
            overall_progress.systems_complete += 1
            overall_progress.successful += event.successful
            overall_progress.failed += event.failed
            overall_progress.skipped += event.skipped
        except Exception as e:
            logger.debug(f"Failed to update overall progress: {e}")

        # Update Systems tab
        try:
            total_roms = event.successful + event.failed + event.skipped

            # Update tree node
            systems_tab = self.query_one(SystemsTab)
            systems_tab.update_system_node(
                event.system_name,
                event.system_name,  # Use system_name as we don't have fullname
                event.successful,
                total_roms,
                "complete"
            )

            # Update detail panel stats
            detail_panel = self.query_one("#system-detail-panel", SystemDetailPanel)
            detail_panel.update_system_stats(event.system_name, {
                "fullname": event.system_name,
                "total_roms": total_roms,
                "successful": event.successful,
                "failed": event.failed,
                "skipped": event.skipped,
                "status": "complete",
                "duration": event.duration,
                "summary": f"Completed in {event.duration:.1f}s\n"
                          f"  ✓ {event.successful} successful\n"
                          f"  ✗ {event.failed} failed\n"
                          f"  ⊝ {event.skipped} skipped"
            })
        except Exception as e:
            logger.debug(f"Failed to update Systems tab: {e}")

    async def on_rom_progress(self, event: ROMProgressEvent) -> None:
        """Handle ROM progress event."""
        logger.debug(f"ROM progress: {event.rom_name} - {event.status}")

        # Update overall progress when a ROM is complete/failed/skipped
        if event.status in ["complete", "failed", "skipped"]:
            try:
                overall_progress = self.query_one("#overall-progress", OverallProgressWidget)
                overall_progress.processed += 1
            except Exception as e:
                logger.debug(f"Failed to update overall progress: {e}")

    async def on_hashing_progress(self, event: HashingProgressEvent) -> None:
        """Handle hashing progress event."""
        logger.debug(
            f"Hashing: {event.completed}/{event.total} "
            f"(skipped: {event.skipped})"
        )

        # Update current system widget
        try:
            current_system = self.query_one("#current-system", CurrentSystemOperations)
            current_system.hash_completed = event.completed
            current_system.hash_total = event.total
            current_system.hash_skipped = event.skipped
            current_system.hash_in_progress = event.in_progress
        except Exception as e:
            logger.debug(f"Failed to update current system: {e}")

    async def on_api_activity(self, event: APIActivityEvent) -> None:
        """Handle API activity event."""
        logger.debug(
            f"API: metadata {event.metadata_in_flight} in-flight, "
            f"search {event.search_in_flight} in-flight"
        )

        # Update current system widget
        try:
            current_system = self.query_one("#current-system", CurrentSystemOperations)
            current_system.metadata_in_flight = event.metadata_in_flight
            current_system.metadata_total = event.metadata_total
            current_system.search_in_flight = event.search_in_flight
            current_system.search_total = event.search_total
        except Exception as e:
            logger.debug(f"Failed to update current system: {e}")

    async def on_media_download(self, event: MediaDownloadEvent) -> None:
        """Handle media download event."""
        logger.debug(
            f"Media: {event.media_type} for {event.rom_name} - {event.status}"
        )

        # Update current system widget
        try:
            current_system = self.query_one("#current-system", CurrentSystemOperations)
            if event.status == "downloading":
                current_system.media_in_flight += 1
            elif event.status == "complete":
                current_system.media_in_flight = max(0, current_system.media_in_flight - 1)
                current_system.media_downloaded += 1
            elif event.status == "failed":
                current_system.media_in_flight = max(0, current_system.media_in_flight - 1)
                current_system.media_failed += 1
        except Exception as e:
            logger.debug(f"Failed to update current system: {e}")

    async def on_log_entry(self, event: LogEntryEvent) -> None:
        """Handle log entry event."""
        logger.debug(f"Log: [{logging.getLevelName(event.level)}] {event.message}")

        # Add log to Details tab
        try:
            filterable_logs = self.query_one("#filterable-logs", FilterableLogWidget)
            filterable_logs.append_log(event.level, event.message, event.timestamp)
        except Exception as e:
            logger.debug(f"Failed to add log to Details tab: {e}")

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
        """Handle performance update event."""
        logger.debug(
            f"Performance: quota {event.api_quota_used}/{event.api_quota_limit}, "
            f"threads {event.threads_in_use}/{event.threads_limit}"
        )

        # Update performance panel
        try:
            performance = self.query_one("#performance", PerformancePanel)
            performance.quota_used = event.api_quota_used
            performance.quota_limit = event.api_quota_limit
            performance.threads_in_use = event.threads_in_use
            performance.threads_limit = event.threads_limit
            performance.cache_hit_rate = event.cache_hit_rate

            # Update history lists (keep last 30 values)
            if event.throughput_history:
                performance.throughput_history = event.throughput_history[-30:]
            if event.api_rate_history:
                performance.api_rate_history = event.api_rate_history[-30:]
        except Exception as e:
            logger.debug(f"Failed to update performance panel: {e}")

    async def on_game_completed(self, event: GameCompletedEvent) -> None:
        """Handle game completed event."""
        logger.debug(f"Game completed: {event.title} ({event.year})")

        # Add to spotlight widget
        try:
            spotlight = self.query_one("#spotlight", GameSpotlightWidget)
            game = {
                "game_id": event.game_id,
                "title": event.title,
                "year": event.year,
                "genre": event.genre,
                "developer": event.developer,
                "description": event.description,
                "confidence": event.confidence,
            }
            spotlight.add_game(game)
        except Exception as e:
            logger.debug(f"Failed to add game to spotlight: {e}")

    async def on_active_request(self, event: ActiveRequestEvent) -> None:
        """Handle active request event."""
        logger.debug(
            f"Active request: {event.rom_name} - {event.stage} - {event.status}"
        )

        # Update Details tab active requests table
        try:
            active_requests = self.query_one("#active-requests", ActiveRequestsTable)

            if event.status in ["started", "in_progress", "retry"]:
                # Add or update the request
                active_requests.update_request(
                    event.rom_name,
                    event.stage,
                    event.status,
                    event.duration
                )
            elif event.status in ["completed", "failed", "cancelled"]:
                # Remove the request
                active_requests.remove_request(event.rom_name)

        except Exception as e:
            logger.debug(f"Failed to update active requests table: {e}")

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

        try:
            spotlight = self.query_one("#spotlight", GameSpotlightWidget)
            spotlight.prev_game()
        except Exception as e:
            logger.debug(f"Failed to navigate to previous game: {e}")

    def action_next_game(self) -> None:
        """Navigate to next game in spotlight."""
        if self.current_tab != "overview":
            self.notify(
                "Game navigation is only available on the Overview tab",
                severity="warning",
                timeout=3
            )
            return

        try:
            spotlight = self.query_one("#spotlight", GameSpotlightWidget)
            spotlight.next_game()
        except Exception as e:
            logger.debug(f"Failed to navigate to next game: {e}")

    def action_filter_logs(self, level: int) -> None:
        """Filter logs by level (only available on Details tab)."""
        if self.current_tab != "details":
            self.notify(
                "Log filtering is only available on the Details tab",
                severity="warning",
                timeout=3
            )
            return

        # Update log level filter
        try:
            filterable_logs = self.query_one("#filterable-logs", FilterableLogWidget)
            filterable_logs.set_log_level(level)
            level_name = logging.getLevelName(level)
            self.notify(f"Log filter set to: {level_name}", timeout=2)
        except Exception as e:
            logger.debug(f"Failed to set log filter: {e}")

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
    import types
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

    # Store original on_mount
    original_on_mount = app.on_mount

    # Create custom on_mount that includes event simulation
    async def custom_on_mount(self):
        await original_on_mount()

        # Simulate comprehensive event scenario
        async def simulate_events():
            await asyncio.sleep(2)

            # 1. Simulate system started
            await event_bus.publish(SystemStartedEvent(
                system_name="nes",
                system_fullname="Nintendo Entertainment System",
                total_roms=100,
                current_index=0,
                total_systems=3
            ))

            await event_bus.publish(LogEntryEvent(
                level=logging.INFO,
                message="Starting ROM scanning...",
                timestamp=datetime.now()
            ))

            await asyncio.sleep(1)

            # 2. Simulate hashing progress with logs
            await event_bus.publish(LogEntryEvent(
                level=logging.INFO,
                message="Scanning ROM directory...",
                timestamp=datetime.now()
            ))

            for i in range(1, 6):
                await event_bus.publish(HashingProgressEvent(
                    completed=i * 20,
                    total=100,
                    skipped=2,
                    in_progress=True
                ))
                await asyncio.sleep(0.5)

            await event_bus.publish(LogEntryEvent(
                level=logging.INFO,
                message="Hashing completed, starting metadata lookups",
                timestamp=datetime.now()
            ))

            # 3. Simulate API activity
            await event_bus.publish(APIActivityEvent(
                metadata_in_flight=5,
                metadata_total=30,
                search_in_flight=2,
                search_total=10
            ))

            await asyncio.sleep(0.5)

            # 4. Simulate ROM progress with active requests
            roms = [
                "Super Mario Bros.nes",
                "The Legend of Zelda.nes",
                "Metroid.nes",
                "Mega Man 2.nes",
                "Castlevania.nes"
            ]

            for i, rom in enumerate(roms):
                # Start processing
                await event_bus.publish(ActiveRequestEvent(
                    rom_name=rom,
                    stage="metadata",
                    status="started",
                    duration=0.0
                ))

                await asyncio.sleep(0.3)

                # Update with progress
                await event_bus.publish(ActiveRequestEvent(
                    rom_name=rom,
                    stage="metadata",
                    status="in_progress",
                    duration=0.3
                ))

                await asyncio.sleep(0.2)

                # Complete
                await event_bus.publish(ActiveRequestEvent(
                    rom_name=rom,
                    stage="metadata",
                    status="completed",
                    duration=0.5
                ))

                await event_bus.publish(ROMProgressEvent(
                    rom_name=rom,
                    status="complete"
                ))

                await asyncio.sleep(0.3)

            # 5. Simulate media downloads with logs
            await event_bus.publish(LogEntryEvent(
                level=logging.INFO,
                message="Starting media downloads...",
                timestamp=datetime.now()
            ))

            await event_bus.publish(MediaDownloadEvent(
                rom_name="Super Mario Bros.nes",
                media_type="boxart",
                status="downloading",
                url="https://example.com/boxart.jpg"
            ))

            await asyncio.sleep(0.5)

            await event_bus.publish(MediaDownloadEvent(
                rom_name="Super Mario Bros.nes",
                media_type="boxart",
                status="complete",
                url="https://example.com/boxart.jpg"
            ))

            # Simulate a warning
            await event_bus.publish(LogEntryEvent(
                level=logging.WARNING,
                message="Some boxart images not found on server",
                timestamp=datetime.now()
            ))

            # 6. Simulate game completions for spotlight
            games = [
                {
                    "game_id": 1,
                    "title": "Super Mario Bros.",
                    "year": "1985",
                    "genre": "Platform",
                    "developer": "Nintendo",
                    "description": "A classic platform game where Mario must rescue Princess Peach from Bowser. Features eight worlds with four levels each, introducing iconic power-ups like the Super Mushroom and Fire Flower.",
                    "confidence": 0.98
                },
                {
                    "game_id": 2,
                    "title": "The Legend of Zelda",
                    "year": "1986",
                    "genre": "Action-Adventure",
                    "developer": "Nintendo",
                    "description": "An epic adventure game where Link must collect the eight fragments of the Triforce to rescue Princess Zelda. Features open-world exploration and dungeon crawling.",
                    "confidence": 0.95
                },
                {
                    "game_id": 3,
                    "title": "Metroid",
                    "year": "1986",
                    "genre": "Action-Adventure",
                    "developer": "Nintendo",
                    "description": "A sci-fi action game where bounty hunter Samus Aran explores planet Zebes to stop the Space Pirates. Features non-linear exploration and power-up collection.",
                    "confidence": 0.92
                }
            ]

            for game in games:
                await event_bus.publish(GameCompletedEvent(
                    game_id=game["game_id"],
                    title=game["title"],
                    year=game["year"],
                    genre=game["genre"],
                    developer=game["developer"],
                    description=game["description"],
                    confidence=game["confidence"]
                ))
                await asyncio.sleep(1)

            # 7. Simulate performance updates with history
            throughput_data = [10.5, 12.3, 15.8, 18.2, 20.1, 22.5, 25.3, 28.7, 30.2, 32.5]
            api_rate_data = [5.2, 6.8, 8.1, 9.5, 10.2, 11.8, 13.2, 14.5, 15.8, 17.2]

            for i in range(10):
                await event_bus.publish(PerformanceUpdateEvent(
                    throughput_history=throughput_data[:i+1],
                    api_rate_history=api_rate_data[:i+1],
                    api_quota_used=50 + (i * 10),
                    api_quota_limit=1000,
                    threads_in_use=min(8, i + 1),
                    threads_limit=8,
                    cache_hit_rate=0.65 + (i * 0.02)
                ))
                await asyncio.sleep(0.5)

            # 8. Simulate more log events
            await event_bus.publish(LogEntryEvent(
                level=logging.WARNING,
                message="API rate limit approaching threshold",
                timestamp=datetime.now()
            ))

            await asyncio.sleep(1)

            await event_bus.publish(LogEntryEvent(
                level=logging.DEBUG,
                message="Cache statistics: 45 hits, 12 misses (78.9% hit rate)",
                timestamp=datetime.now()
            ))

            await asyncio.sleep(1)

            # 9. Simulate system completion
            await event_bus.publish(LogEntryEvent(
                level=logging.INFO,
                message="System processing complete",
                timestamp=datetime.now()
            ))

            await event_bus.publish(SystemCompletedEvent(
                system_name="nes",
                successful=85,
                failed=5,
                skipped=10,
                duration=120.5
            ))

            await event_bus.publish(LogEntryEvent(
                level=logging.INFO,
                message="Successfully processed 85 ROMs, 5 failed, 10 skipped",
                timestamp=datetime.now()
            ))

        # Run simulation in background using Textual's worker system
        self.run_worker(simulate_events(), name="event_simulator")

    # Bind the custom on_mount method to the app instance
    app.on_mount = types.MethodType(custom_on_mount, app)

    # Run app
    app.run()
