"""
Textual UI for Curateur

Event-driven terminal UI using the Textual framework. Displays real-time
scraping progress across three tabs: Overview, Details, and Systems.
"""

import logging
from datetime import datetime
from typing import Optional, List

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    Header,
    Footer,
    TabbedContent,
    TabPane,
    Static,
    ProgressBar,
    Rule,
    Select,
    Switch,
    Label,
    Button,
    ListView,
    ListItem,
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
    SearchRequestEvent,
    CacheMetricsEvent,
    GamelistUpdateEvent,
    MediaStatsEvent,
    SearchActivityEvent,
    AuthenticationEvent,
)

import asyncio
import types
from datetime import datetime

logger = logging.getLogger(__name__)


# ============================================================================
# Overview Tab Widgets
# ============================================================================


class OverallProgressWidget(Container):
    """Displays overall run progress with progress bar."""

    # Reactive properties updated by events
    current_system_index = reactive(0)  # 1-based index of current system being processed
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

    def watch_current_system_index(self, old_value: int, new_value: int) -> None:
        """Update display when current system index changes."""
        self.update_display()

    def update_display(self) -> None:
        """Render overall progress."""
        progress_pct = (self.processed / self.total_roms * 100) if self.total_roms > 0 else 0

        # Header text
        header = Text()
        header.append(f"Systems: {self.current_system_index}/{self.systems_total}\n", style="white")
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
    search_fallback_count = reactive(0)
    search_unmatched_count = reactive(0)
    media_in_flight = reactive(0)
    media_downloaded = reactive(0)
    media_validated = reactive(0)
    media_skipped = reactive(0)
    media_failed = reactive(0)
    
    # Cache statistics
    cache_hit_rate = reactive(0.0)
    cache_existing = reactive(0)
    cache_new = reactive(0)
    
    # Gamelist statistics
    gamelist_existing = reactive(0)
    gamelist_added = reactive(0)
    gamelist_updated = reactive(0)
    
    # Spinner animation frame counter
    spinner_frame = 0

    def compose(self) -> ComposeResult:
        yield Static(id="hashing-content")
        yield Rule(line_style="heavy")
        yield Static(id="cache-content")
        yield Rule(line_style="heavy")
        yield Static(id="gamelist-content")
        yield Rule(line_style="heavy")
        yield Static(id="api-content")
        yield Rule(line_style="heavy")
        yield Static(id="media-content")

    def on_mount(self) -> None:
        """Initialize system operations display."""
        self.border_title = "Current System"
        self.update_display()
        # Start spinner animation timer (update every 0.2 seconds)
        self.set_interval(0.2, self._update_spinner)

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

    def watch_cache_hit_rate(self, old_value: float, new_value: float) -> None:
        """Update display when cache hit rate changes."""
        self.update_cache()

    def watch_cache_existing(self, old_value: int, new_value: int) -> None:
        """Update display when cache existing count changes."""
        self.update_cache()

    def watch_cache_new(self, old_value: int, new_value: int) -> None:
        """Update display when cache new count changes."""
        self.update_cache()

    def watch_gamelist_existing(self, old_value: int, new_value: int) -> None:
        """Update display when gamelist existing count changes."""
        self.update_gamelist()

    def watch_gamelist_added(self, old_value: int, new_value: int) -> None:
        """Update display when gamelist added count changes."""
        self.update_gamelist()

    def watch_gamelist_updated(self, old_value: int, new_value: int) -> None:
        """Update display when gamelist updated count changes."""
        self.update_gamelist()

    def watch_media_downloaded(self, old_value: int, new_value: int) -> None:
        """Update display when media downloaded count changes."""
        self.update_media()

    def watch_media_validated(self, old_value: int, new_value: int) -> None:
        """Update display when media validated count changes."""
        self.update_media()

    def watch_media_skipped(self, old_value: int, new_value: int) -> None:
        """Update display when media skipped count changes."""
        self.update_media()

    def watch_media_failed(self, old_value: int, new_value: int) -> None:
        """Update display when media failed count changes."""
        self.update_media()

    def update_display(self) -> None:
        """Render all sections."""
        self.update_hashing()
        self.update_cache()
        self.update_gamelist()
        self.update_api()
        self.update_media()

    def _update_spinner(self) -> None:
        """Update spinner frame for animation."""
        if self.hash_in_progress or self.metadata_in_flight > 0 or self.search_in_flight > 0:
            self.spinner_frame = (self.spinner_frame + 1) % 10
            self.update_hashing()
            self.update_api()
    
    def update_hashing(self) -> None:
        """Update hashing section."""
        hash_pct = (self.hash_completed / self.hash_total * 100) if self.hash_total > 0 else 0
        hash_content = Text()
        hash_content.append("Hashing", style="bold cyan")

        if self.hash_in_progress:
            spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            spinner = spinner_chars[self.spinner_frame]
            hash_content.append(f" {spinner}", style="bright_magenta")

        hash_content.append(f"\n{self.hash_completed}/{self.hash_total} ", style="white")
        hash_content.append(f"({hash_pct:.1f}%)", style="bright_green")

        if self.hash_skipped > 0:
            hash_content.append(f" ⊝ {self.hash_skipped}", style="dim yellow")

        self.query_one("#hashing-content", Static).update(hash_content)
    
    def update_cache(self) -> None:
        """Update cache section."""
        cache_content = Text()
        cache_content.append("Cache\n", style="bold cyan")
        cache_content.append(f"{self.cache_hit_rate:.1%} Hit Rate", style="bright_magenta")
        cache_content.append(f"\n✓ {self.cache_existing} ", style="white")
        cache_content.append(f"+ {self.cache_new}", style="bright_green")
        
        self.query_one("#cache-content", Static).update(cache_content)
    
    def update_gamelist(self) -> None:
        """Update gamelist section."""
        gamelist_content = Text()
        gamelist_content.append("Gamelist\n", style="bold cyan")
        gamelist_content.append(f"✓ {self.gamelist_existing} ", style="white")
        gamelist_content.append(f"+ {self.gamelist_added} ", style="bright_green")
        gamelist_content.append(f"↻ {self.gamelist_updated}", style="yellow")
        
        self.query_one("#gamelist-content", Static).update(gamelist_content)

    def update_api(self) -> None:
        """Update API section."""
        api_content = Text()
        api_content.append("API\n", style="bold cyan")

        # Metadata requests
        spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        metadata_spinner = spinner_chars[self.spinner_frame]
        api_content.append("Metadata: ", style="dim")
        if self.metadata_in_flight > 0:
            api_content.append(f"{metadata_spinner} {self.metadata_in_flight} ", style="yellow")
        else:
            api_content.append("Idle ", style="dim")
        api_content.append(f"✓ {self.metadata_total}\n", style="bright_green")

        # Search requests
        search_spinner = spinner_chars[self.spinner_frame]
        api_content.append("Search: ", style="dim")
        if self.search_in_flight > 0:
            api_content.append(f"{search_spinner} {self.search_in_flight} ", style="yellow")
        else:
            api_content.append("Idle ", style="dim")
        api_content.append(f"✓ {self.search_total}", style="bright_green")
        
        # Search fallback and unmatched stats
        if self.search_fallback_count > 0 or self.search_unmatched_count > 0:
            api_content.append("\n", style="dim")
            if self.search_fallback_count > 0:
                api_content.append(f"↻ {self.search_fallback_count} fallback ", style="yellow")
            if self.search_unmatched_count > 0:
                api_content.append(f"✗ {self.search_unmatched_count} unmatched", style="red")

        self.query_one("#api-content", Static).update(api_content)

    def update_media(self) -> None:
        """Update media section."""
        media_content = Text()
        media_content.append("Media\n", style="bold cyan")

        if self.media_in_flight > 0:
            media_content.append(f"⬇ {self.media_in_flight} ", style="yellow")
        media_content.append(f"✓ {self.media_downloaded} ", style="bright_green")
        if self.media_validated > 0:
            media_content.append(f"✔ {self.media_validated} ", style="white")
        if self.media_skipped > 0:
            media_content.append(f"⊝ {self.media_skipped} ", style="dim")
        if self.media_failed > 0:
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
        content = Text()

        if not self.games:
            content.append("No games completed yet", style="dim italic")
        else:
            game = self.games[self.index]
            title = game.get('title', 'Unknown')
            year = game.get('year', 'N/A')
            genre = game.get('genre', 'N/A')
            developer = game.get('developer', 'N/A')
            publisher = game.get('publisher', 'N/A')
            players = game.get('players', 'N/A')
            rating = game.get('rating')
            description = game.get('description', 'No description available')

            # Line 1: Title and year
            content.append("Completed: ", style="bold cyan")
            content.append(f"{title}", style="bright_magenta")
            if year and year != 'N/A':
                content.append(f" ({year})", style="white")
            content.append("\n")

            # Line 2: Genre and developer
            content.append("Genre: ", style="bold cyan")
            content.append(f"{genre}", style="white")
            content.append(" | ", style="dim")
            content.append("Developer: ", style="bold cyan")
            content.append(f"{developer}", style="white")
            content.append("\n")

            # Line 3: Publisher and players
            content.append("Publisher: ", style="bold cyan")
            content.append(f"{publisher}", style="white")
            content.append(" | ", style="dim")
            content.append("Players: ", style="bold cyan")
            content.append(f"{players}", style="white")
            content.append("\n")

            # Line 4: Rating
            content.append("Rating: ", style="bold cyan")
            if rating is not None:
                # Convert ScreenScraper 0-20 scale to X.X/5 format
                rating_out_of_5 = rating / 4.0
                content.append(f"{rating_out_of_5:.1f}/5", style="yellow")
            else:
                content.append("N/A", style="dim")
            content.append("\n\n")

            # Description (truncate if too long)
            max_desc_len = 300
            if len(description) > max_desc_len:
                description = description[:max_desc_len] + "..."
            content.append("Description:\n", style="bold cyan")
            content.append(description, style="white")

            # Navigation hint
            if len(self.games) > 1:
                content.append("\n\n", style="dim")
                content.append(f"[{self.index + 1}/{len(self.games)}] ", style="dim")
                content.append("Press ", style="dim")
                content.append("B", style="bold cyan")
                content.append("/", style="dim")
                content.append("N", style="bold cyan")
                content.append(" to navigate", style="dim")

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
    account_name = reactive("")
    throughput_history = reactive(list)
    api_rate_history = reactive(list)
    quota_used = reactive(0)
    quota_limit = reactive(0)
    threads_in_use = reactive(0)
    threads_limit = reactive(0)
    system_eta = reactive("")

    def compose(self) -> ComposeResult:
        # Order matches mockup: Throughput, API Rate, Account+Threads, Quota, ETA
        yield Static(id="throughput")
        yield Static(id="api-rate")
        yield Static(id="account-info")
        yield Static(id="api-quota")
        yield Static(id="eta-stats")

    def on_mount(self) -> None:
        """Initialize performance panel."""
        self.border_title = "Performance Metrics"
        self.account_name = "Authenticating..."
        self.throughput_history = []
        self.api_rate_history = []
        self.system_eta = "—"
        self.update_display()

    def watch_quota_used(self, old_value: int, new_value: int) -> None:
        """Update display when quota changes."""
        self.update_quota()

    def watch_threads_in_use(self, old_value: int, new_value: int) -> None:
        """Update display when thread usage changes."""
        self.update_account_info()

    def watch_throughput_history(self, old_value: list, new_value: list) -> None:
        """Update display when throughput history changes."""
        self.update_throughput()

    def watch_api_rate_history(self, old_value: list, new_value: list) -> None:
        """Update display when API rate history changes."""
        self.update_api_rate()

    def watch_account_name(self, old_value: str, new_value: str) -> None:
        """Update display when account name changes."""
        self.update_account_info()

    def watch_threads_limit(self, old_value: int, new_value: int) -> None:
        """Update display when thread limit changes."""
        self.update_account_info()

    def watch_system_eta(self, old_value: str, new_value: str) -> None:
        """Update display when system ETA changes."""
        self.update_eta_stats()

    def update_display(self) -> None:
        """Render all metrics."""
        self.update_throughput()
        self.update_api_rate()
        self.update_account_info()
        self.update_quota()
        self.update_eta_stats()

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

    def update_account_info(self) -> None:
        """Update account info line with threads on same line."""
        if self.account_name:
            self.query_one("#account-info", Static).update(
                f"[bold]Logged in as:[/bold] [bright_magenta]{self.account_name}[/bright_magenta] | "
                f"[bold]Threads:[/bold] {self.threads_in_use}/{self.threads_limit}"
            )
        else:
            self.query_one("#account-info", Static).update(
                "[dim italic]Authenticating...[/dim italic]"
            )

    def update_quota(self) -> None:
        """Update quota line."""
        quota_pct = (self.quota_used / self.quota_limit * 100) if self.quota_limit > 0 else 0
        quota_bar = self.create_inline_progress_bar(self.quota_used, self.quota_limit, 30)
        self.query_one("#api-quota", Static).update(
            f"[bold]API Quota:[/bold] {self.quota_used}/{self.quota_limit} ({quota_pct:.1f}%) [yellow]{quota_bar}[/yellow]"
        )

    def update_eta_stats(self) -> None:
        """Update ETA and system stats line."""
        # TODO: Add memory and CPU tracking when implemented
        self.query_one("#eta-stats", Static).update(
            f"[bold]System ETA:[/bold] [yellow]{self.system_eta}[/yellow]"
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
        except Exception:
            pass  # Silently ignore logging errors to prevent feedback loop

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

    # Track active requests by ROM name with start times
    active_requests = reactive(dict)
    request_start_times = {}  # Maps rom_name -> start timestamp

    def compose(self) -> ComposeResult:
        from textual.widgets import DataTable
        yield DataTable(id="active-requests-table")

    def on_mount(self) -> None:
        """Initialize table."""
        from textual.widgets import DataTable
        self.border_title = "Active Requests (0 concurrent)"
        self.active_requests = {}
        self.request_start_times = {}

        table = self.query_one("#active-requests-table", DataTable)
        table.add_columns("ROM", "Stage", "Duration", "Status")
        table.cursor_type = "row"
        
        # Start timer to update durations every 0.5 seconds
        self.set_interval(0.5, self._update_durations)

    def update_request(self, rom_name: str, stage: str, status: str, duration: float = 0.0) -> None:
        """Add or update an active request."""
        from textual.widgets import DataTable
        import time

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
                # Track start time for this request
                self.request_start_times[rom_name] = time.time()

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
                
                # Remove start time tracking
                if rom_name in self.request_start_times:
                    del self.request_start_times[rom_name]

                # Update border title with count
                count = len(self.active_requests)
                self.border_title = f"Active Requests ({count} concurrent)"

        except Exception as e:
            logger.debug(f"Failed to remove active request: {e}")

    def _update_durations(self) -> None:
        """Update duration column for all active requests in real-time."""
        from textual.widgets import DataTable
        import time

        try:
            if not self.active_requests:
                return

            table = self.query_one("#active-requests-table", DataTable)
            current_time = time.time()

            for rom_name, row_key in self.active_requests.items():
                if rom_name in self.request_start_times:
                    elapsed = current_time - self.request_start_times[rom_name]
                    table.update_cell(row_key, "Duration", f"{elapsed:.1f}s")

        except Exception as e:
            logger.debug(f"Failed to update durations: {e}")

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

            # Media Statistics (per-type breakdown)
            media_by_type = stats.get('media_by_type', {})
            if media_by_type:
                content.append("● MEDIA STATISTICS\n", style="bold cyan")
                # Sort media types alphabetically for consistent display
                for media_type in sorted(media_by_type.keys()):
                    type_stats = media_by_type[media_type]
                    successful = type_stats.get('successful', 0)
                    validated = type_stats.get('validated', 0)
                    failed = type_stats.get('failed', 0)
                    
                    # Format media type name (capitalize and replace hyphens)
                    display_name = media_type.replace('-', ' ').replace('_', ' ').title()
                    content.append(f"  {display_name:<15}", style="white")
                    
                    if successful > 0:
                        content.append(f"✓ {successful:>3} ", style="bright_green")
                    if validated > 0:
                        content.append(f"↻ {validated:>3} ", style="dim")
                    if failed > 0:
                        content.append(f"✗ {failed:>3} ", style="red")
                    content.append("\n")
                content.append("\n")

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
# Config Tab
# ============================================================================


class ConfigTab(Container):
    """Config tab with runtime settings controls in two-column layout."""

    def compose(self) -> ComposeResult:
        """Compose the config tab layout."""
        # Warning banner
        yield Static(
            "⚠️  Settings changes are temporary and will revert on restart. "
            "Edit config.yaml for permanent changes.",
            id="config-warning",
            classes="config-warning"
        )

        # Two-column layout
        with Horizontal(id="config-columns"):
            # Left Column: API and Runtime Settings
            with VerticalScroll(id="config-left-column"):
                # API Settings
                with Container(classes="config-section", id="api-settings-section"):
                    with Horizontal(classes="config-row"):
                        yield Label("Max Retries:", classes="config-label")
                        yield Select(
                            [("0", 0), ("1", 1), ("2", 2), ("3", 3), ("4", 4), ("5", 5)],
                            value=3,
                            id="max-retries",
                            allow_blank=False,
                            compact=True
                        )

                    with Horizontal(classes="config-row"):
                        yield Label("Retry Backoff (s):", classes="config-label")
                        yield Select(
                            [("1", 1), ("3", 3), ("5", 5), ("10", 10)],
                            value=5,
                            id="retry-backoff",
                            allow_blank=False,
                            compact=True
                        )

                # Runtime Settings
                with Container(classes="config-section", id="runtime-settings-section"):
                    with Horizontal(classes="config-row"):
                        yield Label("Override Limits:", classes="config-label")
                        yield Switch(value=False, id="override-limits-switch")

                    with Horizontal(classes="config-row"):
                        yield Label("  Max Workers:", classes="config-label")
                        yield Select(
                            [("1", 1), ("2", 2), ("3", 3), ("4", 4), ("5", 5)],
                            value=1,
                            id="max-workers-select",
                            disabled=True,
                            allow_blank=False,
                            compact=True
                        )

            # Right Column: Logging and Search Settings
            with VerticalScroll(id="config-right-column"):
                # Logging Settings
                with Container(classes="config-section", id="logging-settings-section"):
                    with Horizontal(classes="config-row"):
                        yield Label("Log Level:", classes="config-label")
                        yield Select(
                            [("DEBUG", "DEBUG"), ("INFO", "INFO"), ("WARNING", "WARNING"), ("ERROR", "ERROR")],
                            value="INFO",
                            id="log-level-select",
                            allow_blank=False,
                        )

                # Search Settings
                with Container(classes="config-section", id="search-settings-section"):
                    with Horizontal(classes="config-row"):
                        yield Label("Search Fallback:", classes="config-label")
                        yield Switch(value=False, id="search-fallback-switch")

                    with Horizontal(classes="config-row"):
                        yield Label("Confidence:", classes="config-label")
                        yield Select(
                            [("50%", 50), ("60%", 60), ("70%", 70), ("80%", 80), ("90%", 90)],
                            value=70,
                            id="confidence-threshold",
                            allow_blank=False,
                        )

                    with Horizontal(classes="config-row"):
                        yield Label("Max Results:", classes="config-label")
                        yield Select(
                            [("1", 1), ("3", 3), ("5", 5), ("7", 7), ("10", 10)],
                            value=5,
                            id="max-results",
                            allow_blank=False,
                        )

    def on_mount(self) -> None:
        """Set border titles and initialize widget values from config."""
        # Set border titles
        self.query_one("#api-settings-section", Container).border_title = "API Settings"
        self.query_one("#runtime-settings-section", Container).border_title = "Runtime Settings"
        self.query_one("#logging-settings-section", Container).border_title = "Logging Settings"
        self.query_one("#search-settings-section", Container).border_title = "Search Settings"

        # Initialize widget values from app config
        config = self.app.config

        # API Settings
        try:
            max_retries = config.get('api', {}).get('max_retries', 3)
            self.query_one("#max-retries", Select).value = max_retries

            retry_backoff = config.get('api', {}).get('retry_backoff_seconds', 5)
            self.query_one("#retry-backoff", Select).value = retry_backoff
        except Exception as e:
            logger.debug(f"Failed to initialize API settings: {e}")

        # Runtime Settings
        try:
            override = config.get('runtime', {}).get('rate_limit_override_enabled', False)
            self.query_one("#override-limits-switch", Switch).value = override

            if override:
                max_workers = config.get('runtime', {}).get('rate_limit_override', {}).get('max_workers', 1)
                self.query_one("#max-workers-select", Select).value = max_workers
                self.query_one("#max-workers-select", Select).disabled = False
        except Exception as e:
            logger.debug(f"Failed to initialize runtime settings: {e}")

        # Logging Settings
        try:
            log_level = config.get('logging', {}).get('level', 'INFO')
            self.query_one("#log-level-select", Select).value = log_level
        except Exception as e:
            logger.debug(f"Failed to initialize logging settings: {e}")

        # Search Settings
        try:
            search_fallback = config.get('search', {}).get('enable_search_fallback', False)
            self.query_one("#search-fallback-switch", Switch).value = search_fallback

            confidence = int(config.get('search', {}).get('confidence_threshold', 0.7) * 100)
            self.query_one("#confidence-threshold", Select).value = confidence

            max_results = config.get('search', {}).get('max_results', 5)
            self.query_one("#max-results", Select).value = max_results
        except Exception as e:
            logger.debug(f"Failed to initialize search settings: {e}")

    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Handle switch toggle changes."""
        switch_id = event.switch.id
        new_value = event.value

        if switch_id == "override-limits-switch":
            # UI-only: Enable/disable max workers select
            try:
                max_workers_select = self.query_one("#max-workers-select", Select)
                max_workers_select.disabled = not new_value
            except Exception as e:
                logger.debug(f"Failed to toggle max workers: {e}")

        elif switch_id == "search-fallback-switch":
            # Update orchestrator
            try:
                if hasattr(self.app, 'orchestrator') and self.app.orchestrator:
                    self.app.orchestrator.update_search_config(enable_fallback=new_value)
                    self._show_temp_change_notification()
            except Exception as e:
                logger.error(f"Failed to update search fallback: {e}")

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle select dropdown changes."""
        select_id = event.select.id
        new_value = event.value

        # Log Level (already implemented, keep existing logic)
        if select_id == "log-level-select":
            try:
                filterable_logs = self.app.query_one("#filterable-logs", FilterableLogWidget)
                level_map = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}
                filterable_logs.set_log_level(level_map.get(new_value, 20))
                self._show_temp_change_notification()
            except Exception as e:
                logger.debug(f"Failed to update log level: {e}")

        # API Settings
        elif select_id == "max-retries":
            try:
                if hasattr(self.app, 'orchestrator') and self.app.orchestrator and self.app.orchestrator.api_client:
                    self.app.orchestrator.api_client.update_runtime_config(max_retries=new_value)
                    self._show_temp_change_notification()
            except Exception as e:
                logger.error(f"Failed to update max retries: {e}")

        elif select_id == "retry-backoff":
            try:
                if hasattr(self.app, 'orchestrator') and self.app.orchestrator and self.app.orchestrator.api_client:
                    self.app.orchestrator.api_client.update_runtime_config(retry_backoff=new_value)
                    self._show_temp_change_notification()
            except Exception as e:
                logger.error(f"Failed to update retry backoff: {e}")

        # Runtime Settings
        elif select_id == "max-workers-select":
            try:
                if hasattr(self.app, 'orchestrator') and self.app.orchestrator and self.app.orchestrator.throttle_manager:
                    self.app.orchestrator.throttle_manager.update_concurrency_limit(new_value)
                    self._show_temp_change_notification()
            except Exception as e:
                logger.error(f"Failed to update max workers: {e}")

        # Search Settings
        elif select_id == "confidence-threshold":
            try:
                if hasattr(self.app, 'orchestrator') and self.app.orchestrator:
                    # Convert percentage to float (70 -> 0.7)
                    threshold = new_value / 100.0
                    self.app.orchestrator.update_search_config(confidence_threshold=threshold)
                    self._show_temp_change_notification()
            except Exception as e:
                logger.error(f"Failed to update confidence threshold: {e}")

        elif select_id == "max-results":
            try:
                if hasattr(self.app, 'orchestrator') and self.app.orchestrator:
                    self.app.orchestrator.update_search_config(max_results=new_value)
                    self._show_temp_change_notification()
            except Exception as e:
                logger.error(f"Failed to update max results: {e}")

    def _show_temp_change_notification(self) -> None:
        """Show notification that setting change is temporary."""
        self.app.notify(
            "Setting applied (temporary - reverts on restart)",
            severity="information",
            timeout=2
        )


# ============================================================================
# Confirmation Dialogs
# ============================================================================


class ConfirmDialog(ModalScreen):
    """Generic confirmation dialog."""

    CSS = """
    ConfirmDialog {
        align: center middle;
    }

    #confirm-dialog {
        width: 60;
        height: 12;
        border: thick $warning;
        background: $surface;
    }

    #confirm-header {
        dock: top;
        height: 3;
        background: $warning;
        color: $text;
        padding: 1 2;
    }

    #confirm-message {
        height: 1fr;
        padding: 2;
        content-align: center middle;
    }

    #confirm-buttons {
        dock: bottom;
        height: 3;
        background: $surface-darken-1;
        padding: 0 2;
    }

    #confirm-buttons Button {
        margin: 0 1;
    }
    """

    def __init__(self, title: str, message: str, confirm_variant: str = "error"):
        """Initialize confirmation dialog.

        Args:
            title: Dialog title
            message: Confirmation message
            confirm_variant: Button variant for confirm button (default: "error")
        """
        super().__init__()
        self.dialog_title = title
        self.dialog_message = message
        self.confirm_variant = confirm_variant

    def compose(self) -> ComposeResult:
        """Compose the dialog layout."""
        with Container(id="confirm-dialog"):
            yield Static(f"[bold]{self.dialog_title}[/bold]", id="confirm-header")
            yield Static(self.dialog_message, id="confirm-message")

            with Horizontal(id="confirm-buttons"):
                yield Button("Yes", variant=self.confirm_variant, id="yes-btn")
                yield Button("No", variant="primary", id="no-btn")

    def on_mount(self) -> None:
        """Focus the No button by default (safer)."""
        self.query_one("#no-btn", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "yes-btn":
            self.dismiss(True)
        elif event.button.id == "no-btn":
            self.dismiss(False)

    def on_key(self, event) -> None:
        """Handle keyboard shortcuts."""
        if event.key == "y":
            self.dismiss(True)
        elif event.key == "n" or event.key == "escape":
            self.dismiss(False)


class QuitConfirmDialog(ModalScreen):
    """Confirmation dialog for quitting the application."""

    CSS = """
    QuitConfirmDialog {
        align: center middle;
    }

    #quit-dialog {
        width: 70;
        height: 18;
        border: thick $error;
        background: $surface;
    }

    #quit-header {
        dock: top;
        height: 3;
        background: $error;
        color: white;
        padding: 1 2;
    }

    #quit-content {
        height: 1fr;
        padding: 2;
    }

    #quit-stats {
        background: $surface-darken-1;
        border: solid $accent;
        padding: 1 2;
        margin: 0 0 1 0;
    }

    #quit-warning {
        color: $warning;
        margin: 1 0;
    }

    #quit-buttons {
        dock: bottom;
        height: 3;
        background: $surface-darken-1;
        padding: 0 2;
    }

    #quit-buttons Button {
        margin: 0 1;
    }
    """

    def __init__(self, current_system: str, processed: int, total: int):
        """Initialize quit confirmation dialog.

        Args:
            current_system: Name of currently processing system
            processed: Number of ROMs processed
            total: Total number of ROMs
        """
        super().__init__()
        self.current_system = current_system
        self.processed = processed
        self.total = total

    def compose(self) -> ComposeResult:
        """Compose the dialog layout."""
        with Container(id="quit-dialog"):
            yield Static("[bold]⚠ Confirm Quit[/bold]", id="quit-header")

            with Container(id="quit-content"):
                with Container(id="quit-stats"):
                    stats = Text()
                    stats.append("Current Progress:\n", style="bold cyan")
                    stats.append(f"  System: ", style="white")
                    stats.append(f"{self.current_system}\n", style="bright_magenta")
                    stats.append(f"  Processed: ", style="white")
                    stats.append(f"{self.processed}/{self.total} ROMs\n", style="cyan")
                    remaining = self.total - self.processed
                    stats.append(f"  Remaining: ", style="white")
                    stats.append(f"{remaining} ROMs", style="yellow")
                    yield Static(stats)

                yield Static(
                    "[bold]Are you sure you want to quit?[/bold]\n\n"
                    "• Unsaved progress will be lost\n"
                    "• The current scraping session will be interrupted",
                    id="quit-warning"
                )

            with Horizontal(id="quit-buttons"):
                yield Button("Quit [Y]", variant="error", id="quit-yes-btn")
                yield Button("Continue Scraping [N]", variant="success", id="quit-no-btn")

    def on_mount(self) -> None:
        """Focus the No button by default (safer)."""
        self.query_one("#quit-no-btn", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "quit-yes-btn":
            self.dismiss(True)
        elif event.button.id == "quit-no-btn":
            self.dismiss(False)

    def on_key(self, event) -> None:
        """Handle keyboard shortcuts."""
        if event.key == "y":
            self.dismiss(True)
        elif event.key == "n" or event.key == "escape":
            self.dismiss(False)


# ============================================================================
# Interactive Search Screen
# ============================================================================


class SearchResultDialog(ModalScreen):
    """Modal dialog for selecting search results during interactive search."""

    CSS = """
    SearchResultDialog {
        align: center middle;
    }

    #search-dialog {
        width: 90;
        height: 30;
        border: thick $primary;
        background: $surface;
    }

    #search-header {
        dock: top;
        height: 3;
        background: $primary;
        color: white;
        padding: 1 2;
    }

    #rom-info {
        dock: top;
        height: 3;
        background: $surface-darken-1;
        padding: 1 2;
    }

    #results-container {
        height: 1fr;
        border: solid $secondary;
        background: $surface-darken-1;
    }

    #result-details {
        dock: right;
        width: 35;
        border-left: solid $accent;
        background: $surface;
        padding: 1 2;
    }

    #search-results {
        width: 1fr;
        padding: 1;
    }

    #action-buttons {
        dock: bottom;
        height: 3;
        background: $surface-darken-1;
        padding: 0 2;
    }

    .result-item {
        padding: 0 1;
        height: 3;
    }

    .result-item:hover {
        background: $accent 20%;
    }

    ListView > .result-item--highlight {
        background: $primary;
    }
    """

    def __init__(self, rom_filename: str, search_results: List[dict]):
        """Initialize search result dialog.

        Args:
            rom_filename: Name of the ROM file being searched
            search_results: List of search result dictionaries
        """
        super().__init__()
        self.rom_filename = rom_filename
        self.search_results = search_results
        self.selected_index = 0

    def compose(self) -> ComposeResult:
        """Compose the dialog layout."""
        with Container(id="search-dialog"):
            yield Static("[bold]Interactive Search - Match Required[/bold]", id="search-header")
            yield Static(f"[bold]ROM File:[/bold] [cyan]{self.rom_filename}[/cyan]", id="rom-info")

            with Horizontal(id="results-container"):
                with Container(id="search-results"):
                    yield ListView(*self._create_result_items(), id="result-list")

                yield Static(id="result-details")

            with Horizontal(id="action-buttons"):
                yield Button("Select [Enter]", variant="primary", id="select-btn")
                yield Button("Skip ROM [S]", variant="warning", id="skip-btn")
                yield Button("Cancel [Esc]", variant="error", id="cancel-btn")

    def _create_result_items(self) -> list:
        """Create ListItem widgets for each search result."""
        items = []
        for idx, result in enumerate(self.search_results):
            confidence_pct = result["confidence"] * 100

            # Confidence color coding
            if confidence_pct >= 90:
                conf_color = "bright_green"
            elif confidence_pct >= 75:
                conf_color = "yellow"
            else:
                conf_color = "red"

            text = Text()
            text.append(f"{idx + 1}. ", style="dim")
            text.append(f"{result['name']}", style="bold cyan")
            text.append(f" ({result['year']}) ", style="white")
            text.append(f"[{result['region']}] ", style="bright_magenta")
            text.append(f"{confidence_pct:.0f}%", style=conf_color)

            item = ListItem(Static(text), classes="result-item")
            items.append(item)

        return items

    def on_mount(self) -> None:
        """Update detail panel when mounted."""
        self.update_details(0)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Update detail panel when selection changes."""
        self.selected_index = event.list_view.index
        self.update_details(self.selected_index)

    def update_details(self, index: int) -> None:
        """Update the detail panel with selected result info.

        Args:
            index: Index of the selected result
        """
        if index < 0 or index >= len(self.search_results):
            return

        result = self.search_results[index]
        details = Text()

        details.append("══ Match Details ══\n\n", style="bold magenta")

        details.append("Game ID: ", style="bold cyan")
        details.append(f"{result['id']}\n", style="white")

        details.append("Title: ", style="bold cyan")
        details.append(f"{result['name']}\n", style="white")

        details.append("Year: ", style="bold cyan")
        details.append(f"{result['year']}\n", style="white")

        details.append("Region: ", style="bold cyan")
        details.append(f"{result['region']}\n", style="bright_magenta")

        details.append("Publisher: ", style="bold cyan")
        details.append(f"{result['publisher']}\n", style="white")

        details.append("Developer: ", style="bold cyan")
        details.append(f"{result['developer']}\n", style="white")

        details.append("Players: ", style="bold cyan")
        details.append(f"{result['players']}\n", style="white")

        confidence_pct = result["confidence"] * 100
        if confidence_pct >= 90:
            conf_style = "bold bright_green"
        elif confidence_pct >= 75:
            conf_style = "bold yellow"
        else:
            conf_style = "bold red"

        details.append("\nConfidence: ", style="bold cyan")
        details.append(f"{confidence_pct:.1f}%", style=conf_style)

        self.query_one("#result-details", Static).update(details)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "select-btn":
            selected_result = self.search_results[self.selected_index]
            self.dismiss(("selected", selected_result))
        elif event.button.id == "skip-btn":
            self.dismiss(("skip", None))
        elif event.button.id == "cancel-btn":
            self.dismiss(("cancel", None))

    def on_key(self, event) -> None:
        """Handle keyboard shortcuts."""
        if event.key == "enter":
            selected_result = self.search_results[self.selected_index]
            self.dismiss(("selected", selected_result))
        elif event.key == "s":
            self.dismiss(("skip", None))
        elif event.key == "escape":
            self.dismiss(("cancel", None))


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

        # Interactive search queue
        self.search_queue = asyncio.Queue()
        self.current_search_dialog = None  # Track active dialog
        self.search_processor_running = False  # Track if processor is running

        # Cumulative metadata tracking
        self.cumulative_metadata_calls = 0
        self.previous_metadata_in_flight = 0

        # Will be set by CLI after orchestrator is created
        self.orchestrator = None

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
            with TabPane("Config", id="config"):
                yield ConfigTab()

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
        self.event_bus.subscribe(SearchRequestEvent, self.on_search_request)
        self.event_bus.subscribe(CacheMetricsEvent, self.on_cache_metrics_event)
        self.event_bus.subscribe(GamelistUpdateEvent, self.on_gamelist_update_event)
        self.event_bus.subscribe(MediaStatsEvent, self.on_media_stats_event)
        self.event_bus.subscribe(SearchActivityEvent, self.on_search_activity_event)
        self.event_bus.subscribe(AuthenticationEvent, self.on_authentication_event)

        # Subscribe orchestrator to search responses (set by CLI after initialization)
        if hasattr(self, 'orchestrator') and self.orchestrator is not None:
            from ..ui.events import SearchResponseEvent
            self.event_bus.subscribe(SearchResponseEvent, self.orchestrator.handle_search_response)

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
            overall_progress.current_system_index = event.current_index + 1  # Convert to 1-based
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

        # Update overall progress widget - system completed
        # (successful/failed/skipped are already updated per-ROM in on_rom_progress)
        # Note: current_system_index is already set when system starts
        try:
            overall_progress = self.query_one("#overall-progress", OverallProgressWidget)
            # No need to update anything here - index already shows current system
            pass
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
                
                # Also update overall success/failed/skipped counters
                if event.status == "complete":
                    overall_progress.successful += 1
                elif event.status == "failed":
                    overall_progress.failed += 1
                elif event.status == "skipped":
                    overall_progress.skipped += 1
            except Exception as e:
                logger.debug(f"Failed to update overall progress: {e}")
            
            # Update system detail panel with real-time stats
            try:
                detail_panel = self.query_one("#system-detail-panel", SystemDetailPanel)
                if self.current_system and event.system == self.current_system.system_name:
                    # Get current stats or initialize
                    current_stats = detail_panel.system_stats.get(event.system, {})
                    
                    # Increment appropriate counter
                    if event.status == "complete":
                        current_stats["successful"] = current_stats.get("successful", 0) + 1
                    elif event.status == "failed":
                        current_stats["failed"] = current_stats.get("failed", 0) + 1
                    elif event.status == "skipped":
                        current_stats["skipped"] = current_stats.get("skipped", 0) + 1
                    
                    # Update summary with current progress
                    total = current_stats.get("successful", 0) + current_stats.get("failed", 0) + current_stats.get("skipped", 0)
                    total_roms = current_stats.get("total_roms", 0)
                    current_stats["summary"] = (
                        f"Processing: {total}/{total_roms} ROMs\n"
                        f"  ✓ {current_stats.get('successful', 0)} successful\n"
                        f"  ✗ {current_stats.get('failed', 0)} failed\n"
                        f"  ⊝ {current_stats.get('skipped', 0)} skipped"
                    )
                    
                    # Update the stats (preserves other fields like fullname, total_roms, status)
                    detail_panel.update_system_stats(event.system, current_stats)
            except Exception as e:
                logger.debug(f"Failed to update system detail panel: {e}")

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

        # Track cumulative metadata calls
        # Detect completion when in-flight count decreases
        if event.metadata_in_flight < self.previous_metadata_in_flight:
            completed = self.previous_metadata_in_flight - event.metadata_in_flight
            self.cumulative_metadata_calls += completed
        self.previous_metadata_in_flight = event.metadata_in_flight

        # Update current system widget
        try:
            current_system = self.query_one("#current-system", CurrentSystemOperations)
            current_system.metadata_in_flight = event.metadata_in_flight
            current_system.metadata_total = self.cumulative_metadata_calls  # Use cumulative count
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
        # Don't log here - creates infinite feedback loop
        
        # Add log to Details tab
        try:
            filterable_logs = self.query_one("#filterable-logs", FilterableLogWidget)
            filterable_logs.append_log(event.level, event.message, event.timestamp)
        except Exception:
            pass  # Silently ignore logging errors to prevent feedback loop

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
                "publisher": event.publisher,
                "players": event.players,
                "rating": event.rating,
                "description": event.description,
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

    async def on_search_request(self, event) -> None:
        """Handle search request from orchestrator.

        Adds to queue and starts processor if not running.

        Args:
            event: SearchRequestEvent with ROM and search results
        """
        logger.info(f"Received search request for {event.rom_name}")
        await self.search_queue.put(event)

        # Start search prompt handler if not already running
        if not self.search_processor_running:
            self.search_processor_running = True
            self.run_worker(self._process_search_queue(), name="search_prompt_processor")

    async def _process_search_queue(self) -> None:
        """Process search requests one at a time.

        Shows dialogs sequentially from queue.
        """
        logger.info("Search queue processor started")
        try:
            while True:
                # Get next search request
                try:
                    request = await asyncio.wait_for(
                        self.search_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    # Check if we should exit
                    if self.should_quit:
                        logger.info("Search queue processor exiting due to quit")
                        break
                    continue

                # Show dialog and wait for user decision
                try:
                    self.current_search_dialog = request
                    await self._show_search_dialog(request)
                except Exception as e:
                    logger.error(f"Error showing search dialog: {e}", exc_info=True)
                finally:
                    self.current_search_dialog = None
        finally:
            self.search_processor_running = False
            logger.info("Search queue processor stopped")

    async def _show_search_dialog(self, request) -> None:
        """Show search result dialog and emit response.

        Args:
            request: SearchRequestEvent with ROM and results
        """
        from ..ui.events import SearchResponseEvent

        # Convert search results to dialog format
        dialog_results = []
        for result in request.search_results:
            game_data = result["game_data"]
            confidence = result["confidence"]

            # Extract display fields
            names = game_data.get('names', {})
            title = names.get('en') or names.get('us') or (list(names.values())[0] if names else 'Unknown')

            dates = game_data.get('dates', {})
            year = list(dates.values())[0] if dates else 'N/A'

            regions = game_data.get('regions', [])
            region = regions[0] if regions else 'Unknown'

            dialog_results.append({
                "id": game_data.get('id', ''),
                "name": title,
                "year": year,
                "region": region,
                "publisher": game_data.get('publisher', 'Unknown'),
                "developer": game_data.get('developer', 'Unknown'),
                "players": game_data.get('players', 'Unknown'),
                "confidence": confidence,
                "_full_data": game_data  # Keep original for return
            })

        # Show dialog
        result = await self.push_screen_wait(
            SearchResultDialog(request.rom_name, dialog_results)
        )

        action, data = result

        # Emit response event
        if action == "selected" and data:
            selected_game = data.get("_full_data")
            response = SearchResponseEvent(
                request_id=request.request_id,
                action="selected",
                selected_game=selected_game
            )
            await self.event_bus.publish(response)

            self.notify(
                f"Selected: {data['name']}",
                severity="information",
                timeout=3
            )
        elif action == "skip":
            response = SearchResponseEvent(
                request_id=request.request_id,
                action="skip",
                selected_game=None
            )
            await self.event_bus.publish(response)

            self.notify(
                f"Skipped: {request.rom_name}",
                severity="warning",
                timeout=2
            )
        else:  # cancel
            response = SearchResponseEvent(
                request_id=request.request_id,
                action="cancel",
                selected_game=None
            )
            await self.event_bus.publish(response)

            self.notify(
                "Search cancelled",
                timeout=2
            )

    async def on_cache_metrics_event(self, event) -> None:
        """Handle cache metrics event."""
        from ..ui.events import CacheMetricsEvent
        if not isinstance(event, CacheMetricsEvent):
            return
        
        logger.debug(
            f"Cache metrics: existing={event.existing}, added={event.added}, "
            f"hits={event.hits}, misses={event.misses}, hit_rate={event.hit_rate:.1f}%"
        )
        
        # Update current system operations widget
        try:
            current_system = self.query_one("#current-system", CurrentSystemOperations)
            current_system.cache_existing = event.existing
            current_system.cache_new = event.added
            current_system.cache_hit_rate = event.hit_rate / 100.0  # Convert percentage to decimal
        except Exception as e:
            logger.debug(f"Failed to update cache metrics: {e}")

    async def on_gamelist_update_event(self, event) -> None:
        """Handle gamelist update event."""
        from ..ui.events import GamelistUpdateEvent
        if not isinstance(event, GamelistUpdateEvent):
            return
        
        logger.debug(
            f"Gamelist update [{event.system}]: existing={event.existing}, "
            f"added={event.added}, updated={event.updated}"
        )
        
        # Update current system operations widget
        try:
            current_system = self.query_one("#current-system", CurrentSystemOperations)
            current_system.gamelist_existing = event.existing
            current_system.gamelist_added = event.added
            current_system.gamelist_updated = event.updated
        except Exception as e:
            logger.debug(f"Failed to update gamelist stats: {e}")

    async def on_authentication_event(self, event) -> None:
        """Handle authentication event."""
        from ..ui.events import AuthenticationEvent
        if not isinstance(event, AuthenticationEvent):
            return
        
        logger.debug(f"Authentication: status={event.status}, username={event.username}")
        
        # Update Performance Panel with account name
        try:
            performance = self.query_one("#performance", PerformancePanel)
            if event.status == 'authenticating':
                performance.account_name = "Authenticating..."
            elif event.status == 'authenticated' and event.username:
                performance.account_name = event.username
            elif event.status == 'failed':
                performance.account_name = "Authentication failed"
        except Exception as e:
            logger.debug(f"Failed to update account name: {e}")
        
        # Show notifications
        if event.status == 'authenticating':
            self.notify("Authenticating with ScreenScraper...", timeout=2)
        elif event.status == 'authenticated':
            self.notify(
                f"Authenticated as {event.username}",
                severity="information",
                timeout=3
            )
        elif event.status == 'failed':
            self.notify(
                "Authentication failed",
                severity="error",
                timeout=5
            )

    async def on_search_activity_event(self, event) -> None:
        """Handle search activity event."""
        from ..ui.events import SearchActivityEvent
        if not isinstance(event, SearchActivityEvent):
            return
        
        logger.debug(
            f"Search activity: fallback={event.fallback_count}, "
            f"unmatched={event.unmatched_count}"
        )
        
        # Update current system operations widget
        try:
            current_system = self.query_one("#current-system", CurrentSystemOperations)
            current_system.search_fallback_count = event.fallback_count
            current_system.search_unmatched_count = event.unmatched_count
        except Exception as e:
            logger.debug(f"Failed to update search activity stats: {e}")

    async def on_media_stats_event(self, event) -> None:
        """Handle media stats event."""
        from ..ui.events import MediaStatsEvent
        if not isinstance(event, MediaStatsEvent):
            return
        
        logger.debug(
            f"Media stats: validated={event.total_validated}, "
            f"skipped={event.total_skipped}, failed={event.total_failed}"
        )
        
        # Update current system operations widget
        try:
            current_system = self.query_one("#current-system", CurrentSystemOperations)
            # Calculate total downloaded from by_type breakdown
            total_downloaded = sum(
                stats.get('successful', 0) for stats in event.by_type.values()
            )
            current_system.media_downloaded = total_downloaded
            current_system.media_validated = event.total_validated
            current_system.media_skipped = event.total_skipped
            current_system.media_failed = event.total_failed
        except Exception as e:
            logger.debug(f"Failed to update media stats: {e}")
        
        # Update Systems tab detail panel with media breakdown
        try:
            detail_panel = self.query_one("#system-detail-panel", SystemDetailPanel)
            if self.current_system:
                system_name = self.current_system.system_name
                if system_name in detail_panel.system_stats:
                    current_stats = dict(detail_panel.system_stats[system_name])
                    current_stats['media_by_type'] = event.by_type
                    detail_panel.update_system_stats(system_name, current_stats)
        except Exception as e:
            logger.debug(f"Failed to update system media breakdown: {e}")

    # ========================================================================
    # Action Handlers
    # ========================================================================

    def action_quit_app(self) -> None:
        """Quit the application with confirmation dialog."""
        logger.info("Quit requested by user")
        
        # Run the dialog in a worker
        self.run_worker(self._handle_quit_dialog(), exclusive=True)
    
    async def _handle_quit_dialog(self) -> None:
        """Handle quit confirmation dialog in worker context."""
        # Gather current progress info for the dialog
        if self.current_system:
            current_system_name = self.current_system.system_fullname
            total_roms = self.current_system.total_roms

            # Get processed count from overall progress widget
            try:
                overall_progress = self.query_one("#overall-progress", OverallProgressWidget)
                processed = overall_progress.processed
            except Exception:
                processed = 0
        else:
            current_system_name = "No active system"
            total_roms = 0
            processed = 0

        # Show confirmation dialog
        result = await self.push_screen_wait(
            QuitConfirmDialog(current_system_name, processed, total_roms)
        )

        if result:
            logger.info("User confirmed quit")
            self.should_quit = True
            self.exit()
        else:
            logger.info("User cancelled quit")
            self.notify("Continuing scraping session", timeout=2)

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
        logger.info("Interactive search dialog requested")
        
        # Run the dialog in a worker
        self.run_worker(self._handle_demo_search_dialog(), exclusive=True)
    
    async def _handle_demo_search_dialog(self) -> None:
        """Handle demo search dialog in worker context."""
        # Create demo search results
        demo_results = [
            {
                "id": "12345",
                "name": "Super Mario Bros.",
                "year": "1985",
                "region": "USA",
                "publisher": "Nintendo",
                "developer": "Nintendo",
                "players": "1-2",
                "confidence": 0.95
            },
            {
                "id": "12346",
                "name": "Super Mario Bros. (Europe)",
                "year": "1987",
                "region": "EUR",
                "publisher": "Nintendo",
                "developer": "Nintendo",
                "players": "1-2",
                "confidence": 0.85
            },
            {
                "id": "12347",
                "name": "Super Mario Bros. (Japan)",
                "year": "1985",
                "region": "JPN",
                "publisher": "Nintendo",
                "developer": "Nintendo",
                "players": "1-2",
                "confidence": 0.75
            }
        ]

        # Show search dialog
        result = await self.push_screen_wait(
            SearchResultDialog("Super Mario Bros. (USA).nes", demo_results)
        )

        # Handle user's selection
        action, data = result
        if action == "selected":
            self.notify(
                f"Selected: {data['name']} (ID: {data['id']})",
                severity="success",
                timeout=3
            )
            logger.info(f"User selected search result: {data['name']}")
        elif action == "skip":
            self.notify("ROM skipped", severity="warning", timeout=2)
            logger.info("User chose to skip ROM")
        elif action == "manual":
            self.notify("Manual search not yet implemented", timeout=2)
            logger.info("User requested manual search")
        elif action == "cancel":
            self.notify("Search cancelled", timeout=2)
            logger.info("User cancelled search")

    async def shutdown(self) -> None:
        """Graceful shutdown of the UI."""
        logger.info("Shutting down Curateur UI...")
        await self.event_bus.stop()
        logger.info("UI shutdown complete")
        # Exit the application if not already exiting
        if self.is_running:
            self.exit()


# ============================================================================
# Standalone Test Runner
# ============================================================================


if __name__ == "__main__":
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
