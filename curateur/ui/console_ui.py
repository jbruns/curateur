"""
Rich console UI for curateur

Provides modern terminal interface with split panels, live updates, and progress bars.
"""

import asyncio
import logging
import time
from collections import deque
from typing import Optional, Dict, Any, Tuple, Set, Deque
from datetime import timedelta

from curateur import __version__
from curateur.ui.keyboard_listener import KeyboardListener
from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TaskID
from rich.table import Table
from rich.text import Text

logger = logging.getLogger(__name__)

LEVEL_NUMERIC_MAP = {
    'DEBUG': logging.DEBUG,
    'INFO': logging.INFO,
    'WARNING': logging.WARNING,
    'ERROR': logging.ERROR,
    'CRITICAL': logging.CRITICAL
}


def _create_sparkline(data: list, width: int = 30, color: str = "cyan") -> Text:
    """
    Create a sparkline visualization using Unicode block characters

    Args:
        data: List of numeric values to visualize
        width: Maximum width in characters
        color: Color for the sparkline

    Returns:
        Rich Text object with sparkline visualization
    """
    if not data or len(data) == 0:
        return Text("▁" * min(width, 10), style=f"dim {color}")

    # Take last 'width' values
    values = data[-width:]

    # Normalize to 0-7 range (8 block characters)
    min_val = min(values)
    max_val = max(values)

    if max_val == min_val:
        # All values same - show middle bar
        chars = "▄" * len(values)
    else:
        # Map to block characters: ▁▂▃▄▅▆▇█
        blocks = "▁▂▃▄▅▆▇█"
        chars = ""
        for val in values:
            normalized = (val - min_val) / (max_val - min_val)
            block_idx = int(normalized * 7)
            chars += blocks[block_idx]

    return Text(chars, style=color)


# Retro theme color palette
RETRO_THEME = {
    'primary': 'magenta',
    'secondary': 'cyan',
    'accent': 'bright_magenta',
    'success': 'bright_green',
    'muted': 'dim cyan',
    'warning': 'yellow',
    'error': 'red'
}


class Operations:
    """Standardized operation names and format methods for UI display"""

    # Core operations
    HASHING_ROM = "Hashing ROM"
    FETCHING_METADATA = "Fetching metadata"
    SEARCH_FALLBACK = "Search fallback"
    NO_MATCHES = "No matches"
    WRITING_GAMELIST = "Writing gamelist"
    VALIDATING_GAMELIST = "Validating gamelist"

    # ES-DE media types (following ES-DE nomenclature)
    MEDIA_TYPES = {
        'screenshot': 'screenshot',
        'titlescreen': 'titlescreen',
        'cover': 'cover',  # Alias for box2dfront
        'box2dfront': 'box2dfront',
        'box3d': 'box3d',
        'miximage': 'miximage',
        'marquee': 'marquee',
        'wheel': 'wheel',
        'manual': 'manual',
        'video': 'video',
        'bezel': 'bezel',
        'fanart': 'fanart',
        'cartridge': 'cartridge',
        'map': 'map',
        'physicalmedia': 'physicalmedia'
    }

    @staticmethod
    def verifying_media(current: int, total: int, media_type: str) -> str:
        """
        Format verifying media operation

        Args:
            current: Current media item number
            total: Total media items
            media_type: ES-DE media type name

        Returns:
            Formatted operation string
        """
        return f"Verifying media {current}/{total}: {media_type}"

    @staticmethod
    def downloading_media(current: int, total: int, media_type: str) -> str:
        """
        Format downloading media operation

        Args:
            current: Current media item number
            total: Total media items
            media_type: ES-DE media type name

        Returns:
            Formatted operation string
        """
        return f"Downloading media: {current}/{total}... {media_type}"

    @staticmethod
    def media_summary(downloaded: int, total: int) -> str:
        """
        Format media download summary

        Args:
            downloaded: Number of items downloaded
            total: Total media items

        Returns:
            Formatted summary string
        """
        return f"Media: {downloaded}/{total}"


class ConsoleUI:
    """
    Rich-based console interface with split panels

    Layout:
        Header: system progress
        Main: current operation (system/rom/progress/status)
        Footer: statistics & quota

    Example:
        ui = ConsoleUI(config)
        ui.start()

        ui.update_header('nes', 1, 5)
        ui.update_main({
            'rom_name': 'Star Quest',
            'rom_num': 15,
            'total_roms': 150,
            'action': 'scraping',
            'details': 'Fetching metadata...'
        })
        ui.update_footer(
            stats={'successful': 145, 'failed': 5, 'skipped': 30},
            api_quota={'requests_today': 1250, 'max_requests_per_day': 10000}
        )

        ui.stop()
    """

    def __init__(self, config: dict):
        """
        Initialize console UI

        Args:
            config: Configuration dictionary
        """
        self.console = Console()
        self.config = config
        self.layout = self._create_layout()
        self.live: Optional[Live] = None

        # Progress tracking
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=self.console
        )
        self.system_task: Optional[TaskID] = None
        self.rom_task: Optional[TaskID] = None

        # Pipeline stage tracking
        self.pipeline_stages = {
            'scanner': {'count': 0},
            'system': {
                'gamelist_exists': False,
                'existing_entries': 0,
                'added': 0,
                'updated': 0,
                'removed': 0
            },
            'hashing': {
                'active': False,
                'current': 0,
                'total': 0,
                'details': '',
                'completed': 0
            },
            'api_fetch': {
                'active_roms': [],
                'max_concurrent': 3,
                'cache_hits': 0,
                'cache_misses': 0,
                'search_fallback': 0,
                'total_fetches': 0
            },
            'media_download': {
                'active_roms': [],
                'max_concurrent': 3,
                'validated': 0,
                'validation_failed': 0,
                'by_type': {},
                'total_downloads': 0
            },
            'completed': {'success': 0, 'failed': 0},
            'system_operation': {'active': False, 'operation': '', 'details': ''}
        }

        # Additional tracking
        self.unmatched_count = 0
        self.integrity_score = None  # Gamelist integrity percentage
        self.is_throttled = False  # Whether currently rate limited
        self.is_shutting_down = False  # Whether graceful shutdown in progress
        self.last_pipeline_update = 0.0

        # Log panel tracking
        self.log_buffer: Deque[Tuple[int, int, Text]] = deque(maxlen=400)
        self._visible_logs: Deque[Text] = deque(maxlen=120)
        self._visible_log_limit = 120
        self._log_sequence = 0

        # Log filtering state
        self.current_log_level: int = 20  # INFO level
        self.log_level_map = {1: 40, 2: 30, 3: 20, 4: 10}  # ERROR, WARNING, INFO, DEBUG
        self._filtered_logs_cache: Optional[Text] = None
        self._cache_invalidation_pending: bool = False
        self._log_cache_dirty: bool = True
        self._log_cache_level: int = self.current_log_level
        self.last_cache_invalidation: float = 0.0
        self._last_render_sequence: int = 0
        self._skipped_since_render: int = 0

        # Game spotlight state
        self.recent_games: deque = deque(maxlen=10)
        self.recent_games_queue: Optional[asyncio.Queue] = None  # Created in start()
        self.spotlight_index: int = 0
        self.spotlight_cycle_counter: int = 0
        self.spotlight_auto_cycle: bool = True
        self.spotlight_auto_cycle_pause_until: float = 0.0

        # Authentication status
        self.auth_status: Optional[str] = None  # None, 'in_progress', 'complete'

        # Prompt state
        self.prompt_active: bool = False
        self.prompt_message: str = ""
        self.prompt_options: str = ""
        self.prompt_response: Optional[bool] = None  # Set by keyboard listener

        # Animation tracking for interval-based refresh
        self.spinner_state = 0
        self.spinner_frames = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.refresh_task: Optional[asyncio.Task] = None

        # Logging handler tracking (for cleanup)
        self.log_handler: Optional['RichUILogHandler'] = None

        # Keyboard listener for controls (pass self for callback support)
        self.keyboard_listener = KeyboardListener(console_ui=self)
        self.keyboard_listener_enabled = False

        # Current state
        self.current_system = ""
        self.current_system_num = 0
        self.total_systems = 0
        self.current_operation = {}
        self.current_stats = {}
        self.current_quota = {}
        self.worker_stats = {}
        self.performance_metrics = {}

    def _create_layout(self) -> Layout:
        """Create split panel layout"""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=1),
            Layout(name="threads", size=7),  # 5 stages + 2 for borders/title
            Layout(name="spotlight", size=5),
            Layout(name="logs", ratio=1),  # Take remaining space
            Layout(name="footer", size=4)
        )
        return layout

    def _initialize_panels(self) -> None:
        """Initialize all panels with default content"""
        # Initialize header with keyboard controls
        self._render_header()

        # Initialize workers panel
        self.layout["threads"].update(
            Panel(
                Text("Ready to begin processing", style="dim"),
                title="⚡ PIPELINE",
                border_style=RETRO_THEME['success'],
                box=box.ROUNDED
            )
        )

        # Initialize spotlight panel
        self._render_spotlight_panel()

        # Initialize logs panel
        self.layout["logs"].update(
            Panel(
                Text("Logs will appear here", style="dim"),
                title="▣ LOGS [1]ERR [2]WARN [3]INFO* [4]DBG | [N/B] Navigate Spotlight",
                border_style=RETRO_THEME['primary'],
                box=box.ROUNDED
            )
        )

        # Initialize footer with default stats
        self.update_footer(
            stats={'successful': 0, 'failed': 0, 'skipped': 0},
            api_quota={'requests_today': 0, 'max_requests_per_day': 0}
        )

    def start(self) -> None:
        """Start live display and background refresh task"""
        if self.live is None:
            # Initialize async queue for game spotlight
            try:
                self.recent_games_queue = asyncio.Queue()
                logger.debug("Initialized spotlight queue")
            except RuntimeError:
                logger.warning("No event loop available for spotlight queue")

            # Initialize all panels with default content
            self._initialize_panels()

            self.live = Live(
                self.layout,
                console=self.console,
                refresh_per_second=20,  # Increased from 10 to 20 for more responsive updates
                screen=False
            )
            self.live.start()
            logger.debug("Console UI started")

            # Start keyboard listener for controls
            logger.debug("Attempting to start keyboard listener...")
            try:
                if self.keyboard_listener.start():
                    self.keyboard_listener_enabled = True
                    logger.info("Keyboard controls enabled: [P]ause [S]kip [Q]uit [1-4] Log levels [←→] Navigate")
                    # Re-render header to show controls
                    self._render_header()
                else:
                    logger.warning("Keyboard controls unavailable (press Ctrl-C to exit)")
            except Exception as e:
                logger.warning(f"Failed to start keyboard listener: {e}")

            # Start background refresh task for spinner animation
            try:
                loop = asyncio.get_running_loop()
                self.refresh_task = loop.create_task(self._background_refresh())
            except RuntimeError:
                # No event loop running - this is okay for non-async contexts
                logger.debug("No asyncio event loop found, skipping background refresh task")

    def stop(self) -> None:
        """Stop live display and background refresh task"""
        # Stop keyboard listener
        if self.keyboard_listener_enabled:
            self.keyboard_listener.stop()
            self.keyboard_listener_enabled = False

        # Cancel background refresh task
        if self.refresh_task and not self.refresh_task.done():
            self.refresh_task.cancel()
            self.refresh_task = None

        # Keep log handler active to capture shutdown messages
        # Give time for any pending log messages to be processed and rendered
        # This is especially important for logs from async shutdown tasks
        if self.live:
            # Sleep to allow log messages to propagate through handlers
            time.sleep(0.2)  # 200ms delay to capture final logs

            # Force one final render to ensure all buffered logs are visible
            self._render_logs_panel()
            self.live.refresh()

            # Brief pause to let the render complete
            time.sleep(0.05)  # 50ms for render to complete

        # Now stop the Live display with logs visible
        if self.live:
            self.live.stop()
            self.live = None

        # Remove the RichUILogHandler from root logger after UI is stopped
        if self.log_handler:
            root_logger = logging.getLogger()
            root_logger.removeHandler(self.log_handler)
            self.log_handler = None

    async def _background_refresh(self) -> None:
        """
        Background task that updates UI every 200ms for spinner animation and spotlight cycling

        This ensures the UI updates even when no progress is being made,
        keeping spinners animated for active operations and cycling spotlight display.
        """
        try:
            while True:
                await asyncio.sleep(0.2)  # Reduced from 250ms to 200ms for snappier updates

                # Increment spinner state
                self.spinner_state = (self.spinner_state + 1) % len(self.spinner_frames)

                # Drain spotlight queue
                if self.recent_games_queue:
                    try:
                        while True:
                            game_info = self.recent_games_queue.get_nowait()
                            self.recent_games.append(game_info)
                    except asyncio.QueueEmpty:
                        pass

                # Auto-cycle spotlight every 40 cycles (10 seconds)
                self.spotlight_cycle_counter += 1
                if self.spotlight_cycle_counter >= 40 and self.recent_games:
                    self.spotlight_cycle_counter = 0
                    # Check if auto-cycle is enabled (not paused by manual navigation)
                    if time.time() >= self.spotlight_auto_cycle_pause_until:
                        self.spotlight_auto_cycle = True

                    if self.spotlight_auto_cycle and self.recent_games:
                        self.spotlight_index = (self.spotlight_index + 1) % len(self.recent_games)

                # Update header to refresh pause badge
                self._render_header()

                # Update pipeline panel to refresh spinners
                self._render_pipeline_panel()

                # Update spotlight panel
                self._render_spotlight_panel()

                # Update logs panel if cache invalidation is pending
                if self._cache_invalidation_pending:
                    self._render_logs_panel()
        except asyncio.CancelledError:
            # Task was cancelled (UI stopped) - this is expected
            logger.debug("Background refresh task cancelled")
        except Exception as e:
            logger.error(f"Error in background refresh task: {e}", exc_info=True)

    def update_hashing_progress(self, current: int, total: int, details: str = '') -> None:
        """
        Update batch hashing stage progress

        Args:
            current: Number of ROMs hashed so far
            total: Total ROMs to hash
            details: Optional details (e.g., 'batch 1/5')
        """
        self.pipeline_stages['hashing']['active'] = current < total
        self.pipeline_stages['hashing']['current'] = current
        self.pipeline_stages['hashing']['total'] = total
        self.pipeline_stages['hashing']['details'] = details
        # Increment completed count when advancing
        if current > self.pipeline_stages['hashing'].get('_last_current', 0):
            self.pipeline_stages['hashing']['completed'] = current
        self.pipeline_stages['hashing']['_last_current'] = current
        self._render_pipeline_panel()

    def update_api_fetch_stage(self, rom_name: str, action: str, cache_hit: bool = False) -> None:
        """
        Update API fetch stage (add/remove ROM)

        Args:
            rom_name: ROM being processed
            action: 'start' or 'complete'
            cache_hit: Whether this was a cache hit (only for 'complete')
        """
        active_roms = self.pipeline_stages['api_fetch']['active_roms']
        if action == 'start' and rom_name not in active_roms:
            active_roms.append(rom_name)
        elif action == 'complete':
            if rom_name in active_roms:
                active_roms.remove(rom_name)
            # Track cache stats
            if cache_hit:
                self.pipeline_stages['api_fetch']['cache_hits'] += 1
            else:
                self.pipeline_stages['api_fetch']['cache_misses'] += 1
            self.pipeline_stages['api_fetch']['total_fetches'] += 1
        self._render_pipeline_panel()

    def update_media_download_stage(self, rom_name: str, media_type: str, action: str) -> None:
        """
        Update media download stage

        Args:
            rom_name: ROM being processed
            media_type: Media type being downloaded
            action: 'start' or 'complete'
        """
        active_items = self.pipeline_stages['media_download']['active_roms']
        item = (rom_name, media_type)
        if action == 'start' and item not in active_items:
            active_items.append(item)
        elif action == 'complete' and item in active_items:
            active_items.remove(item)
            # Increment total downloads counter when download completes
            self.pipeline_stages['media_download']['total_downloads'] += 1
        self._render_pipeline_panel()

    def increment_media_validated(self, media_type: Optional[str] = None) -> None:
        """
        Increment media validation counter for files that already exist on disk

        Args:
            media_type: Optional media type (box, screenshot, video, etc.) for breakdown tracking
        """
        self.pipeline_stages['media_download']['validated'] += 1
        # Note: Do NOT increment total_downloads here - validated means file already existed

        # Track by type for detailed breakdown
        if media_type:
            by_type = self.pipeline_stages['media_download']['by_type']
            by_type[media_type] = by_type.get(media_type, 0) + 1

        self._render_pipeline_panel()

    def increment_media_validation_failed(self, media_type: Optional[str] = None) -> None:
        """
        Increment media validation failure counter (hash mismatch requiring re-download)

        Args:
            media_type: Optional media type that failed validation
        """
        self.pipeline_stages['media_download']['validation_failed'] += 1

        # Track by type for detailed breakdown
        if media_type:
            by_type = self.pipeline_stages['media_download']['by_type']
            failed_key = f"{media_type}_failed"
            by_type[failed_key] = by_type.get(failed_key, 0) + 1

        self._render_pipeline_panel()

    def increment_search_fallback(self) -> None:
        """
        Increment search fallback counter when hash lookup fails and search is used
        """
        self.pipeline_stages['api_fetch']['search_fallback'] += 1
        self._render_pipeline_panel()

    def increment_unmatched(self) -> None:
        """
        Increment unmatched ROM counter when no API match is found
        """
        self.unmatched_count += 1

    def set_integrity_score(self, score: float) -> None:
        """
        Set gamelist integrity score (0.0 to 1.0)

        Args:
            score: Integrity score as decimal (e.g., 0.95 for 95%)
        """
        self.integrity_score = score
        self._render_pipeline_panel()

    def set_throttle_status(self, is_throttled: bool) -> None:
        """
        Set whether currently being rate limited

        Args:
            is_throttled: True if rate limiting is active
        """
        self.is_throttled = is_throttled
        self._render_pipeline_panel()

    def update_pipeline_concurrency(self, max_threads: int) -> None:
        """
        Update pipeline stage concurrency limits

        Args:
            max_threads: Maximum concurrent API threads from ScreenScraper
        """
        logger.debug(f"Updating pipeline concurrency limits to {max_threads}")
        self.pipeline_stages['api_fetch']['max_concurrent'] = max_threads
        self.pipeline_stages['media_download']['max_concurrent'] = max_threads
        logger.debug(
            "Pipeline stages updated: api_fetch=%s, media=%s",
            self.pipeline_stages['api_fetch']['max_concurrent'],
            self.pipeline_stages['media_download']['max_concurrent']
        )
        self._render_pipeline_panel()

    def add_completed_game(self, game_info: Dict[str, Any]) -> None:
        """
        Add a completed game to the spotlight queue with quality validation

        Only games with complete, quality metadata are queued for display.

        Args:
            game_info: Game metadata from API response
        """
        try:
            # Validate required fields - only name is mandatory
            if not game_info.get('name'):
                logger.debug(f"Skipping spotlight: missing name")
                return

            # Validate descriptions - must have at least one entry with substantial text
            descriptions = game_info.get('descriptions', {})
            if descriptions:
                has_quality_desc = any(len(desc) > 20 for desc in descriptions.values() if desc)
                if not has_quality_desc:
                    logger.debug(f"Skipping spotlight for {game_info['name']}: descriptions too short")
                    return
            # If no descriptions at all, allow it through (optional field)

            # Validate release dates - optional but if present, must have valid year
            release_dates = game_info.get('release_dates', {})
            if release_dates:
                # Try to extract and validate year from any release date
                valid_year = False
                for date_str in release_dates.values():
                    if date_str:
                        try:
                            # Extract year from date string (format: YYYY-MM-DD or just YYYY)
                            year = int(date_str.split('-')[0])
                            if 1970 <= year <= 2030:
                                valid_year = True
                                break
                        except (ValueError, IndexError):
                            continue

                if not valid_year:
                    logger.debug(f"Skipping spotlight for {game_info['name']}: invalid year in release dates")
                    return
            # If no release dates, allow it through (optional field)

            # Genres are optional - no validation needed

            # All validations passed - queue the game
            if self.recent_games_queue:
                try:
                    self.recent_games_queue.put_nowait(game_info)
                    logger.debug(f"Queued game for spotlight: {game_info['name']}")
                except asyncio.QueueFull:
                    # Silently drop oldest - newer games take priority
                    logger.debug(f"Spotlight queue full, dropping: {game_info['name']}")
            else:
                logger.debug(f"Spotlight queue not initialized, cannot add: {game_info['name']}")
        except Exception as e:
            logger.debug(f"Error adding game to spotlight: {e}", exc_info=True)

    def spotlight_next(self) -> None:
        """Navigate to next game in spotlight"""
        if self.recent_games:
            self.spotlight_index = (self.spotlight_index + 1) % len(self.recent_games)
            self.spotlight_auto_cycle = False
            self.spotlight_auto_cycle_pause_until = time.time() + 30.0  # Pause auto-cycle for 30s
            self._render_spotlight_panel()

    def spotlight_prev(self) -> None:
        """Navigate to previous game in spotlight"""
        if self.recent_games:
            self.spotlight_index = (self.spotlight_index - 1) % len(self.recent_games)
            self.spotlight_auto_cycle = False
            self.spotlight_auto_cycle_pause_until = time.time() + 30.0  # Pause auto-cycle for 30s
            self._render_spotlight_panel()

    def set_log_level(self, level_key: int) -> None:
        """
        Set current log filter level

        Args:
            level_key: Key 1-4 corresponding to ERROR/WARNING/INFO/DEBUG
        """
        if level_key in self.log_level_map:
            self.current_log_level = self.log_level_map[level_key]
            self._log_cache_level = self.current_log_level
            self._rebuild_visible_logs()
            self._cache_invalidation_pending = True
            logger.debug(f"Log level filter set to: {self.current_log_level}")
            self._render_logs_panel()
        self._render_pipeline_panel()

    def set_system_info(self, gamelist_exists: bool, existing_entries: int) -> None:
        """
        Set system gamelist information

        Args:
            gamelist_exists: Whether gamelist.xml exists for this system
            existing_entries: Number of existing entries in gamelist.xml
        """
        self.pipeline_stages['system']['gamelist_exists'] = gamelist_exists
        self.pipeline_stages['system']['existing_entries'] = existing_entries
        self._render_pipeline_panel()

    def increment_gamelist_added(self) -> None:
        """Increment count of games added to gamelist"""
        self.pipeline_stages['system']['added'] += 1
        self._render_pipeline_panel()

    def increment_gamelist_updated(self) -> None:
        """Increment count of games updated in gamelist"""
        self.pipeline_stages['system']['updated'] += 1
        self._render_pipeline_panel()

    def increment_gamelist_removed(self) -> None:
        """Increment count of games removed from gamelist"""
        self.pipeline_stages['system']['removed'] += 1
        self._render_pipeline_panel()

    def increment_completed(self, success: bool = True) -> None:
        """
        Increment completed ROM counter

        Args:
            success: True if ROM was successfully scraped, False if failed
        """
        if success:
            self.pipeline_stages['completed']['success'] += 1
        else:
            self.pipeline_stages['completed']['failed'] += 1
        self._render_pipeline_panel()

    def set_system_operation(self, operation: str, details: str) -> None:
        """
        Update system operation indicator
        """
        self.pipeline_stages['system_operation']['active'] = True
        self.pipeline_stages['system_operation']['operation'] = operation
        self.pipeline_stages['system_operation']['details'] = details
        self._render_pipeline_panel()

    def clear_system_operation(self) -> None:
        """
        Clear system operation indicator
        """
        self.pipeline_stages['system_operation']['active'] = False
        self.pipeline_stages['system_operation']['operation'] = ''
        self.pipeline_stages['system_operation']['details'] = ''
        self._render_pipeline_panel()

    def update_scanner(self, count: int) -> None:
        """
        Update scanner stage with count of files found

        Args:
            count: Number of ROM files scanned and queued
        """
        self.pipeline_stages['scanner']['count'] = count
        self._render_pipeline_panel()

    def clear_system_operation(self) -> None:
        """
        Clear system-level operation
        """
        self.pipeline_stages['system_operation']['active'] = False
        self.pipeline_stages['system_operation']['operation'] = ''
        self.pipeline_stages['system_operation']['details'] = ''
        self._render_pipeline_panel()

    def reset_pipeline_stages(self) -> None:
        """
        Reset pipeline stage tracking for new system
        """
        # Preserve max_concurrent values from previous system
        current_max_concurrent = self.pipeline_stages['api_fetch']['max_concurrent']

        self.pipeline_stages = {
            'scanner': {'count': 0},
            'system': {
                'gamelist_exists': False,
                'existing_entries': 0,
                'added': 0,
                'updated': 0,
                'removed': 0
            },
            'hashing': {
                'active': False,
                'current': 0,
                'total': 0,
                'details': '',
                'completed': 0
            },
            'api_fetch': {
                'active_roms': [],
                'max_concurrent': current_max_concurrent,
                'cache_hits': 0,
                'cache_misses': 0,
                'search_fallback': 0,
                'total_fetches': 0
            },
            'media_download': {
                'active_roms': [],
                'max_concurrent': current_max_concurrent,
                'validated': 0,
                'validation_failed': 0,
                'by_type': {},
                'total_downloads': 0
            },
            'completed': {'success': 0, 'failed': 0},
            'system_operation': {'active': False, 'operation': '', 'details': ''}
        }

        # Reset additional tracking for new system
        self.unmatched_count = 0
        self.integrity_score = None

        self._render_pipeline_panel()

    def display_system_operation(self, system_name: str, operation: str, details: str) -> None:
        """
        Display a system-level blocking operation (writing gamelist, validating, etc.)

        Args:
            system_name: System name to display
            operation: Operation name (e.g., Operations.WRITING_GAMELIST)
            details: Operation details
        """
        # Show in pipeline UI
        self.set_system_operation(operation, details)
        logger.info(f"[{system_name.upper()}] {operation}: {details}")


    def _format_elapsed_time(self, start_time: Optional[float]) -> str:
        """
        Format elapsed time for operations >5 seconds

        Args:
            start_time: Operation start timestamp

        Returns:
            Formatted string like (8s) or empty string if <5s or None
        """
        if start_time is None:
            return ""

        elapsed = time.time() - start_time
        if elapsed >= 5.0:
            return f" ({int(elapsed)}s)"
        return ""

    def _truncate_rom_name(self, rom_name: str, max_length: int = 35) -> str:
        """
        Truncate ROM name for display

        Args:
            rom_name: ROM filename
            max_length: Maximum length before truncation

        Returns:
            Truncated ROM name
        """
        if len(rom_name) <= max_length:
            return rom_name
        return rom_name[:max_length-3] + "..."

    def _sanitize_details(self, details: str, max_length: int = 60) -> str:
        """
        Sanitize and truncate operation details for safe Rich rendering

        Args:
            details: Operation details string
            max_length: Maximum length before truncation

        Returns:
            Sanitized and truncated string
        """
        if not details:
            return ""

        # Convert to string and escape Rich markup characters
        safe_details = str(details)
        # Replace brackets that could be interpreted as Rich markup
        safe_details = safe_details.replace('[', '\\[').replace(']', '\\]')

        # Truncate if too long
        if len(safe_details) > max_length:
            safe_details = safe_details[:max_length-3] + "..."

        return safe_details

    def _truncate_rom_name(self, rom_name: str, max_length: int = 35) -> str:
        """
        Truncate ROM name for display

        Args:
            rom_name: ROM filename
            max_length: Maximum length before truncation

        Returns:
            Truncated ROM name
        """
        if len(rom_name) <= max_length:
            return rom_name
        return rom_name[:max_length-3] + "..."

    def add_log_entry(self, level: str, message: str) -> None:
        """
        Add a log entry to the log buffer (thread-safe)

        Args:
            level: Log level (INFO, WARNING, ERROR, etc.)
            message: Log message
        """
        # Color code by level
        level_colors = {
            'DEBUG': 'dim',
            'INFO': 'cyan',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'bold red'
        }
        color = level_colors.get(level, 'white')
        numeric_level = LEVEL_NUMERIC_MAP.get(level, logging.INFO)

        # Create Text object with styled level prefix and plain message
        # This avoids escaping issues - level uses markup, message is plain text
        text_entry = Text()
        text_entry.append(f"[{level:8}] ", style=color)
        text_entry.append(str(message))

        # Track overflow so we can keep visible logs in sync without rebuilding everything
        dropped_entry = None
        if len(self.log_buffer) == self.log_buffer.maxlen:
            dropped_entry = self.log_buffer.popleft()

        self._log_sequence += 1
        entry = (self._log_sequence, numeric_level, text_entry)
        self.log_buffer.append(entry)

        # Keep visible log window aligned with current filter
        if dropped_entry and self._visible_logs and self._visible_logs[0] is dropped_entry[2]:
            self._visible_logs.popleft()
            self._log_cache_dirty = True

        if numeric_level >= self.current_log_level:
            self._visible_logs.append(text_entry)
            # deque already caps length, but we still mark cache dirty if oldest fell off
            self._log_cache_dirty = True

        # Mark cache for invalidation (batched at 50ms intervals)
        self._cache_invalidation_pending = True

        # Note: Don't call _render_logs_panel() here - let background refresh handle it
        # This prevents blocking on every log entry

    def _rebuild_visible_logs(self) -> None:
        """Rebuild the filtered log window based on the current level without parsing strings"""
        filtered_entries = []
        for _, level_num, entry in reversed(self.log_buffer):
            if level_num >= self.current_log_level:
                filtered_entries.append(entry)
                if len(filtered_entries) >= self._visible_log_limit:
                    break
        filtered_entries.reverse()
        self._visible_logs = deque(filtered_entries, maxlen=self._visible_log_limit)
        self._log_cache_dirty = True
        self._last_render_sequence = self.log_buffer[-1][0] if self.log_buffer else 0
        self._skipped_since_render = 0

    def _render_logs_panel(self) -> None:
        """Render the logs panel with filtered log entries and batched cache invalidation"""
        try:
            now = time.time()

            # If filter changed since last render, rebuild visible list first
            if self._log_cache_level != self.current_log_level:
                self._log_cache_level = self.current_log_level
                self._rebuild_visible_logs()
                self._cache_invalidation_pending = True

            # Fast-forward through bursts: if a lot of new lines arrived, rebuild from tail and track skips
            new_filtered = 0
            newest_seq = self._last_render_sequence
            for seq, level_num, _ in self.log_buffer:
                if seq > newest_seq:
                    newest_seq = seq
                if seq > self._last_render_sequence and level_num >= self.current_log_level:
                    new_filtered += 1

            if new_filtered > self._visible_log_limit:
                self._skipped_since_render += new_filtered - self._visible_log_limit
                self._rebuild_visible_logs()
                self._cache_invalidation_pending = True
            else:
                # Append only new visible entries to avoid rebuilding whole buffer
                appended = False
                for seq, level_num, entry in self.log_buffer:
                    if seq <= self._last_render_sequence:
                        continue
                    if level_num >= self.current_log_level:
                        self._visible_logs.append(entry)
                        appended = True
                if appended:
                    self._log_cache_dirty = True

            self._last_render_sequence = newest_seq

            # Batch cache invalidation - only rebuild if 30ms elapsed or cache is dirty
            should_rebuild = (
                (self._cache_invalidation_pending or self._log_cache_dirty or self._filtered_logs_cache is None)
                and (now - self.last_cache_invalidation) > 0.03
            )

            if should_rebuild:
                if not self._visible_logs:
                    self._filtered_logs_cache = Text("No recent activity", style="dim")
                else:
                    log_text = Text()
                    if self._skipped_since_render > 0:
                        log_text.append(f"... skipped {self._skipped_since_render} log lines ...\n", style="dim")
                        self._skipped_since_render = 0
                    for entry in self._visible_logs:
                        log_text.append(entry)
                        log_text.append("\n")
                    self._filtered_logs_cache = log_text

                # Reset cache state
                self._cache_invalidation_pending = False
                self._log_cache_dirty = False
                self.last_cache_invalidation = now

            # Build title with level indicators
            level_indicators = {
                40: "[1]ERR*",
                30: "[2]WARN*",
                20: "[3]INFO*",
                10: "[4]DBG*"
            }

            title_parts = []
            for level_num, indicator in level_indicators.items():
                if level_num == self.current_log_level:
                    title_parts.append(indicator)
                else:
                    title_parts.append(indicator.replace('*', ' '))

            title = f"▣ LOGS {' '.join(title_parts)} | [N/B] Navigate Spotlight"

            self.layout["logs"].update(
                Panel(
                    self._filtered_logs_cache,
                    title=title,
                    border_style=RETRO_THEME['primary'],
                    box=box.ROUNDED
                )
            )
        except Exception as e:
            logger.error(f"Error rendering logs panel: {e}", exc_info=True)
            # Show error state in panel
            self.layout["logs"].update(
                Panel(
                    Text(f"Error rendering logs: {e}", style="red"),
                    title="▣ LOGS",
                    border_style=RETRO_THEME['error'],
                    box=box.ROUNDED
                )
            )

    def _render_spotlight_panel(self) -> None:
        """Render the game spotlight panel with current game metadata"""
        try:
            if not self.recent_games:
                # No games yet - show initialization message
                init_text = Text("■ INITIALIZING GAME DATABASE ■", style=RETRO_THEME['accent'], justify="center")
                self.layout["spotlight"].update(
                    Panel(
                        init_text,
                        title="◈ SPOTLIGHT",
                        border_style=RETRO_THEME['secondary'],
                        box=box.ROUNDED
                    )
                )
                return

            # Get current game
            game = self.recent_games[self.spotlight_index]

            # Build spotlight display
            spotlight_text = Text()

            # Line 1: Title and year
            name = game.get('name', 'Unknown')
            release_dates = game.get('release_dates', {})
            year = None
            for date_str in release_dates.values():
                if date_str:
                    try:
                        year = date_str.split('-')[0]
                        break
                    except IndexError:
                        pass

            title_line = f"Now Scraping: {name}"
            if year:
                title_line += f" ({year})"
            spotlight_text.append(title_line + "\n", style=RETRO_THEME['accent'])

            # Line 2: Genre and developer (if present)
            info_parts = []
            genres = game.get('genres', [])
            if genres:
                genre_str = ', '.join(genres[:3])  # Limit to first 3 genres
                info_parts.append(f"Genre: {genre_str}")

            developer = game.get('developer')
            if developer:
                info_parts.append(f"Developer: {developer}")

            if info_parts:
                spotlight_text.append(' | '.join(info_parts) + "\n", style=RETRO_THEME['secondary'])

            # Line 3: Synopsis (truncated to 100 chars)
            descriptions = game.get('descriptions', {})
            synopsis = None
            # Prefer English description
            for lang in ['en', 'us', 'fr', 'de', 'es']:
                if lang in descriptions and descriptions[lang]:
                    synopsis = descriptions[lang]
                    break

            if not synopsis and descriptions:
                # Take first available
                synopsis = next(iter(descriptions.values()))

            if synopsis:
                truncated = synopsis[:100]
                if len(synopsis) > 100:
                    truncated += "..."
                spotlight_text.append(truncated, style=RETRO_THEME['muted'])

            self.layout["spotlight"].update(
                Panel(
                    spotlight_text,
                    title=f"◈ SPOTLIGHT ({self.spotlight_index + 1}/{len(self.recent_games)})",
                    border_style=RETRO_THEME['secondary'],
                    box=box.ROUNDED
                )
            )
        except Exception as e:
            logger.error(f"Error rendering spotlight panel: {e}", exc_info=True)
            self.layout["spotlight"].update(
                Panel(
                    Text(f"Error rendering spotlight: {e}", style="red"),
                    title="◈ SPOTLIGHT",
                    border_style=RETRO_THEME['error'],
                    box=box.ROUNDED
                )
            )

    def set_auth_status(self, status: str) -> None:
        """
        Set authentication status indicator

        Args:
            status: One of 'in_progress', 'complete', or None to clear
        """
        self.auth_status = status
        self._render_header()

    def _render_header(self) -> None:
        """Render compact single-line header with system progress and inline controls"""
        try:
            # Build compact header: "curateur v{ver} | {SYSTEM} (n/total) pct% | [P]ause [S]kip [Q]uit"
            header_text = Text()
            header_text.append(f"curateur v{__version__}", style=f"bold {RETRO_THEME['primary']}")
            header_text.append(" | ", style="dim")

            # Show shutdown status if in progress
            if self.is_shutting_down:
                header_text.append("⏹ Shutting Down...", style=f"bold {RETRO_THEME['warning']}")
            # Show authentication status if in progress
            elif self.auth_status == 'in_progress':
                header_text.append("🔐 Authenticating with ScreenScraper...", style=f"bold {RETRO_THEME['warning']}")
            elif self.auth_status == 'complete':
                header_text.append("✓ Authenticated", style=f"{RETRO_THEME['success']}")
                header_text.append(" | ", style="dim")
                # Fall through to show system progress

            # System progress (only show if not authenticating or shutting down)
            if self.auth_status != 'in_progress' and not self.is_shutting_down:
                if self.current_system:
                    percentage = (
                        (self.current_system_num - 1) / self.total_systems * 100
                        if self.total_systems > 0
                        else 0
                    )
                    header_text.append(f"{self.current_system.upper()} ", style=f"bold {RETRO_THEME['secondary']}")
                    header_text.append(f"({self.current_system_num}/{self.total_systems}) ", style="dim")
                    header_text.append(f"{percentage:.0f}%", style=RETRO_THEME['success'] if percentage > 0 else "dim")
                else:
                    header_text.append("Initializing...", style="dim")

                # Add pause badge if paused
                if self.keyboard_listener_enabled and self.keyboard_listener.is_paused:
                    header_text.append(" ⏸", style=f"bold {RETRO_THEME['warning']}")

                # Show prompt message if prompting, otherwise show keyboard controls
                if self.prompt_active:
                    header_text.append(" | ", style="dim")
                    header_text.append("⚠️  ", style="yellow")
                    header_text.append(self.prompt_message, style="bold yellow")
                    header_text.append(" ", style="")
                    header_text.append(self.prompt_options, style="dim yellow")
                elif self.keyboard_listener_enabled:
                    header_text.append(" | ", style="dim")
                    header_text.append("[P]", style=f"bold {RETRO_THEME['secondary']}")
                    header_text.append("ause ", style="dim")
                    header_text.append("[S]", style=f"bold {RETRO_THEME['warning']}")
                    header_text.append("kip ", style="dim")
                    header_text.append("[Q]", style=f"bold {RETRO_THEME['error']}")
                    header_text.append("uit", style="dim")

            # Always update header regardless of state
            self.layout["header"].update(header_text)

            # Force immediate refresh when showing prompt
            if self.prompt_active and self.live:
                self.live.refresh()
        except Exception as e:
            logger.error(f"Error rendering header: {e}", exc_info=True)

    @property
    def is_paused(self) -> bool:
        """Check if processing is paused via keyboard control"""
        if self.keyboard_listener_enabled:
            return self.keyboard_listener.is_paused
        return False

    @property
    def skip_requested(self) -> bool:
        """Check if skip system requested via keyboard control"""
        if self.keyboard_listener_enabled:
            return self.keyboard_listener.skip_requested
        return False

    @property
    def quit_requested(self) -> bool:
        """Check if quit requested via keyboard control"""
        if self.keyboard_listener_enabled:
            return self.keyboard_listener.quit_requested
        return False

    def clear_skip_request(self) -> None:
        """Clear skip request flag after handling"""
        if self.keyboard_listener_enabled:
            self.keyboard_listener.clear_skip_request()

    def clear_quit_request(self) -> None:
        """Clear quit request flag after handling"""
        if self.keyboard_listener_enabled:
            self.keyboard_listener.clear_quit_request()

    def set_shutting_down(self) -> None:
        """Set shutdown state and update header display"""
        self.is_shutting_down = True
        self._render_header()

    def _render_pipeline_panel(self) -> None:
        """Render compact 3-column pipeline panel showing stage names, status, and totals"""
        try:
            # Throttle updates to every 50ms (reduced from 100ms for more responsive UI)
            now = time.time()
            if now - self.last_pipeline_update < 0.05:
                return
            self.last_pipeline_update = now

            # Create 3-column table with auto-balanced widths
            pipeline_table = Table(
                show_header=False,
                show_edge=False,
                padding=(0, 1),
                box=None,
                expand=True
            )
            pipeline_table.add_column("Stage", style="bold", overflow="fold")
            pipeline_table.add_column("Status", overflow="fold")
            pipeline_table.add_column("Total", justify="right", overflow="fold")

            spinner = self.spinner_frames[self.spinner_state]

            # Overall Progress Summary
            scanner = self.pipeline_stages['scanner']
            scanner_count = scanner['count']
            completed = self.pipeline_stages['completed']
            success_count = completed['success']
            failed_count = completed['failed']
            total_completed = success_count + failed_count

            if scanner_count > 0:
                progress_pct = int((total_completed / scanner_count * 100)) if scanner_count > 0 else 0
                # Show success/failed/total
                progress_text = f"{success_count}✓ {failed_count}✗ / {scanner_count} ({progress_pct}%)"
                progress_style = RETRO_THEME['success'] if success_count > 0 else "dim"
            else:
                progress_text = "—"
                progress_style = "dim"

            pipeline_table.add_row(
                Text("📊 Progress", style="bold"),
                Text(progress_text, style=progress_style),
                Text("", style="dim")  # Empty totals column for summary row
            )

            # 1. System - show gamelist.xml info and entry modifications
            system_stage = self.pipeline_stages['system']
            gamelist_exists = system_stage['gamelist_exists']
            existing_entries = system_stage['existing_entries']
            added = system_stage['added']
            updated = system_stage['updated']
            removed = system_stage['removed']

            if gamelist_exists:
                if added > 0 or updated > 0 or removed > 0:
                    status = f"→ {existing_entries} existing"
                    style = RETRO_THEME['secondary']
                else:
                    status = f"→ {existing_entries} entries"
                    style = "dim"
            else:
                status = "→ No gamelist.xml - will create"
                style = "dim"

            # Total: added/updated/removed breakdown
            total_parts = []
            if added > 0:
                total_parts.append(f"{added}+")
            if updated > 0:
                total_parts.append(f"{updated}~")
            if removed > 0:
                total_parts.append(f"{removed}-")
            total_text = "/".join(total_parts) if total_parts else "0"

            pipeline_table.add_row(
                Text("📋 System", style="bold"),
                Text(status, style=style),
                Text(total_text, style=RETRO_THEME['secondary'] if total_parts else "dim")
            )

            # 2. Hashing
            hashing = self.pipeline_stages['hashing']
            hashed_count = hashing.get('completed', 0)
            if hashing['active']:
                current = hashing['current']
                total = hashing['total']
                pct = int((current / total * 100)) if total > 0 else 0
                bar_width = 10
                filled = int(bar_width * current / total) if total > 0 else 0
                bar = '█' * filled + '░' * (bar_width - filled)
                status = f"→ {spinner} [{bar}] {pct}% ({current}/{total})"
                style = RETRO_THEME['secondary']
            else:
                status = "→ Ready"
                style = "dim"
            pipeline_table.add_row(
                Text("⚡ Hashing", style="bold"),
                Text(status, style=style),
                Text(f"{hashed_count}", style=RETRO_THEME['secondary'] if hashed_count > 0 else "dim")
            )

            # 3. API Fetch - show cache/API/search breakdown
            api_fetch = self.pipeline_stages['api_fetch']
            active_roms = api_fetch['active_roms']
            cache_hits = api_fetch.get('cache_hits', 0)
            cache_misses = api_fetch.get('cache_misses', 0)
            total_requests = cache_hits + cache_misses
            total_fetches = api_fetch.get('total_fetches', 0)
            search_fallback = api_fetch.get('search_fallback', 0)

            if active_roms:
                rom_name = self._truncate_rom_name(active_roms[0], 20)
                extra = f" +{len(active_roms) - 1}" if len(active_roms) > 1 else ""
                status = f"→ {spinner} [{len(active_roms)}] {rom_name}{extra}"
                style = RETRO_THEME['warning']
            elif total_requests > 0:
                hit_rate = int(cache_hits / total_requests * 100) if total_requests > 0 else 0
                status = f"→ Cache: {cache_hits}/{total_requests} ({hit_rate}%)"
                style = "dim"
            else:
                status = "→ Idle"
                style = "dim"

            # Total: cache/API/search breakdown
            api_hits = cache_misses  # API hits = cache misses
            total_parts = []
            if cache_hits > 0:
                total_parts.append(f"{cache_hits}c")
            if api_hits > 0:
                total_parts.append(f"{api_hits}a")
            if search_fallback > 0:
                total_parts.append(f"{search_fallback}s")
            total_text = "/".join(total_parts) if total_parts else "0"

            pipeline_table.add_row(
                Text("🔍 API Fetch", style="bold"),
                Text(status, style=style),
                Text(total_text, style=RETRO_THEME['warning'] if total_requests > 0 else "dim")
            )

            # 4. Media - show downloads/validate success/validate fail
            media_dl = self.pipeline_stages['media_download']
            active_items = media_dl['active_roms']
            validated_count = media_dl.get('validated', 0)
            validation_failed = media_dl.get('validation_failed', 0)
            total_downloads = media_dl.get('total_downloads', 0)

            if active_items:
                rom_name = self._truncate_rom_name(active_items[0][0], 15)
                media_type = active_items[0][1]
                extra = f" +{len(active_items) - 1}" if len(active_items) > 1 else ""
                status = (
                    f"→ {spinner} "
                    f"[{len(active_items)}] "
                    f"{rom_name}: {media_type}{extra}"
                )
                style = RETRO_THEME['success']
            elif validated_count > 0:
                # Show validation stats: passed/failed
                if validation_failed > 0:
                    status = f"→ {validated_count} ok, {validation_failed} failed"
                    style = RETRO_THEME['warning']
                else:
                    status = f"→ {validated_count} validated"
                    style = "dim"
            else:
                status = "→ Idle"
                style = "dim"

            # Total: downloads/validate-ok/validate-fail
            total_parts = []
            if total_downloads > 0:
                total_parts.append(f"{total_downloads}d")
            if validated_count > 0:
                total_parts.append(f"{validated_count}✓")
            if validation_failed > 0:
                total_parts.append(f"{validation_failed}✗")
            total_text = "/".join(total_parts) if total_parts else "0"

            pipeline_table.add_row(
                Text("📥 Media", style="bold"),
                Text(status, style=style),
                Text(
                    total_text,
                    style=RETRO_THEME['warning']
                    if validation_failed > 0
                    else (RETRO_THEME['success'] if total_downloads > 0 else "dim")
                )
            )

            # 5. Complete - removed from table

            self.layout["threads"].update(
                Panel(
                    pipeline_table,
                    title="⚡ PIPELINE",
                    border_style=RETRO_THEME['success'],
                    box=box.ROUNDED
                )
            )
        except Exception as e:
            logger.error(f"Error rendering pipeline panel: {e}", exc_info=True)

    def update_header(self, system_name: str, system_num: int, total_systems: int) -> None:
        """
        Update header panel with system progress

        Args:
            system_name: Current system short name
            system_num: Current system number (1-indexed)
            total_systems: Total number of systems
        """
        self.current_system = system_name
        self.current_system_num = system_num
        self.total_systems = total_systems

        self._render_header()

        logger.debug(f"Header updated: {system_name} ({system_num}/{total_systems})")

    def update_footer(
        self,
        stats: Dict[str, int],
        api_quota: Dict[str, Any],
        thread_stats: Optional[Dict[str, Any]] = None,
        performance_metrics: Optional[Dict[str, Any]] = None,
        queue_pending: int = 0,
        cache_metrics: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Update footer panel with sparklines and compact metrics

        Two-row format:
        Row 1: Throughput sparkline + current rate | API rate sparkline + current rate | Cache metrics (if enabled)
        Row 2: API quota progress bar + percentage | Active threads + ETA

        Args:
            stats: Statistics dict with counts (successful, failed, skipped, etc.)
            api_quota: API quota dict (requests_today, max_requests_per_day)
            thread_stats: Optional thread pool stats (active_threads, max_threads)
            performance_metrics: Optional performance metrics (throughput_history, api_rate_history, eta)
            queue_pending: Number of pending items in work queue
            cache_metrics: Optional cache metrics (hits, misses, total_entries, hit_rate, enabled)
        """
        try:
            self.current_stats = stats
            self.current_quota = api_quota
            self.thread_stats = thread_stats or {}
            self.performance_metrics = performance_metrics or {}

            # Extract time-series data for sparklines
            throughput_history = performance_metrics.get('throughput_history', []) if performance_metrics else []
            api_rate_history = performance_metrics.get('api_rate_history', []) if performance_metrics else []
            current_throughput = performance_metrics.get('roms_per_hour', 0) if performance_metrics else 0
            current_api_rate = performance_metrics.get('api_calls_per_minute', 0) if performance_metrics else 0

            # Row 1: Sparklines with current rates + cache metrics
            throughput_sparkline = _create_sparkline(
                throughput_history if len(throughput_history) > 0 else [0],
                width=10,
                color=RETRO_THEME['success']
            )
            api_sparkline = _create_sparkline(
                api_rate_history if len(api_rate_history) > 0 else [0],
                width=10,
                color=RETRO_THEME['warning']
            )

            row1_parts = [
                ("Throughput: ", RETRO_THEME['primary']),
                throughput_sparkline,
                (f" {current_throughput:.1f} ROMs/hr", RETRO_THEME['success']),
                ("  |  ", "dim"),
                ("API Rate: ", RETRO_THEME['primary']),
                api_sparkline,
                (f" {current_api_rate:.1f} calls/min", RETRO_THEME['warning'])
            ]

            # Add cache metrics to row 1 if available
            # Use pipeline stage stats for consistency with pipeline view
            api_fetch = self.pipeline_stages.get('api_fetch', {})
            pipeline_cache_hits = api_fetch.get('cache_hits', 0)
            pipeline_cache_misses = api_fetch.get('cache_misses', 0)
            pipeline_total = pipeline_cache_hits + pipeline_cache_misses

            if cache_metrics and cache_metrics.get('enabled') and pipeline_total > 0:
                total_entries = cache_metrics.get('total_entries', 0)
                hit_rate = (pipeline_cache_hits / pipeline_total * 100) if pipeline_total > 0 else 0.0
                hits = pipeline_cache_hits
                misses = pipeline_cache_misses
                total_requests = pipeline_total

                # Color code hit rate
                if hit_rate >= 70:
                    hit_rate_color = RETRO_THEME['success']
                elif hit_rate >= 40:
                    hit_rate_color = RETRO_THEME['warning']
                else:
                    hit_rate_color = RETRO_THEME['error']

                row1_parts.extend([
                    ("  |  ", "dim"),
                    ("Cache: ", RETRO_THEME['primary']),
                    (f"{total_entries} entries, ", RETRO_THEME['accent']),
                    (f"{hit_rate:.0f}%", hit_rate_color),
                    (f" ({hits}/{total_requests})", "dim")
                ])

            row1 = Text.assemble(*row1_parts)

            # Row 2: API quota progress bar + threads + ETA
            # Note: Keys match ScreenScraper API field names (lowercase, no underscores)
            requests_today = api_quota.get('requeststoday', 0)
            max_requests = api_quota.get('maxrequestsperday', 1)
            quota_pct = requests_today / max_requests if max_requests > 0 else 0

            # Get quota threshold from config
            quota_threshold = self.config.get('api', {}).get('quota_warning_threshold', 0.95)

            # Build progress bar (20 chars width)
            bar_width = 20
            filled = int(quota_pct * bar_width)
            bar_char = "█"
            empty_char = "░"
            progress_bar = bar_char * filled + empty_char * (bar_width - filled)

            # Color code quota
            if quota_pct >= quota_threshold:
                quota_color = RETRO_THEME['error']
            elif quota_pct >= 0.80:
                quota_color = RETRO_THEME['warning']
            else:
                quota_color = RETRO_THEME['success']

            # Threads
            active_threads = thread_stats.get('active_threads', 0) if thread_stats else 0
            max_threads = thread_stats.get('max_threads', 0) if thread_stats else 0

            # ETA
            eta_text = "N/A"
            eta_color = "dim"
            if performance_metrics:
                eta = performance_metrics.get('eta')
                if eta and isinstance(eta, timedelta):
                    hours = int(eta.total_seconds() // 3600)
                    minutes = int((eta.total_seconds() % 3600) // 60)
                    eta_text = f"{hours}h {minutes}m"

                    if eta.total_seconds() < 1800:  # <30 min
                        eta_color = RETRO_THEME['success']
                    elif eta.total_seconds() < 7200:  # <2 hr
                        eta_color = RETRO_THEME['warning']
                    else:
                        eta_color = RETRO_THEME['error']

            row2 = Text.assemble(
                ("API Quota: ", RETRO_THEME['primary']),
                (progress_bar, quota_color),
                (f" {quota_pct*100:.0f}% ({requests_today}/{max_requests})", quota_color),
                ("  |  ", "dim"),
                ("Threads: ", RETRO_THEME['primary']),
                (f"{active_threads}/{max_threads}", RETRO_THEME['accent']),
                ("  |  ", "dim"),
                ("ETA: ", RETRO_THEME['primary']),
                (eta_text, eta_color)
            )

            # Combine rows
            footer_content = Text.assemble(row1, "\n", row2)

            self.layout["footer"].update(
                Panel(footer_content, title="📊 Performance", border_style=RETRO_THEME['primary'], box=box.ROUNDED)
            )
        except Exception as e:
            logger.error(f"Error updating footer: {e}", exc_info=True)
            # Show error state in panel
            error_text = Text(f"Error rendering statistics: {str(e)[:50]}", style="red")
            self.layout["footer"].update(
                Panel(error_text, title="Statistics", border_style="red", box=box.ROUNDED)
            )

    async def prompt_confirm(self, message: str, default: str = 'n') -> bool:
        """
        Show confirmation prompt with y/n response in header line

        Uses existing keyboard listener for input capture (no terminal mode changes).

        Args:
            message: Prompt message to display
            default: Default response ('y' or 'n')

        Returns:
            True if user confirms (y/yes), False otherwise

        Example:
            if await ui.prompt_confirm("Skip this system?", default='n'):
                # User confirmed
                skip_system()
        """
        # Set prompt state to update header
        self.prompt_active = True
        self.prompt_message = message
        self.prompt_options = f"[{default.upper()}/n]" if default.lower() == 'y' else f"[y/{default.upper()}]"
        self.prompt_response = None  # Will be set by keyboard listener

        # Force header update to show prompt
        self._render_header()

        try:
            # Wait for keyboard listener to set response
            timeout = 30.0
            elapsed = 0.0

            while elapsed < timeout:
                if self.prompt_response is not None:
                    # Got a response from keyboard listener
                    result = self.prompt_response
                    logger.debug(f"User {'confirmed' if result else 'declined'}: {message}")
                    return result
                await asyncio.sleep(0.05)  # Check every 50ms, yield control to event loop
                elapsed += 0.05

            # Timeout - use default
            logger.info(f"Prompt timed out, using default: {default}")
            return default.lower() == 'y'

        finally:
            # Clear prompt state
            self.prompt_active = False
            self.prompt_message = ""
            self.prompt_options = ""
            self.prompt_response = None

            # Force header update to restore keyboard controls
            self._render_header()

    def show_error(self, message: str) -> None:
        """
        Display error message (pauses live display)

        Args:
            message: Error message to display
        """
        if self.live:
            self.live.stop()

        self.console.print(f"[bold red]ERROR:[/bold red] {message}")

        if self.live:
            self.live.start()

    def show_warning(self, message: str) -> None:
        """
        Display warning message

        Args:
            message: Warning message to display
        """
        if self.live:
            self.live.stop()

        self.console.print(f"[bold yellow]WARNING:[/bold yellow] {message}")

        if self.live:
            self.live.start()

    def show_info(self, message: str) -> None:
        """
        Display info message

        Args:
            message: Info message to display
        """
        if self.live:
            self.live.stop()

        self.console.print(f"[bold cyan]INFO:[/bold cyan] {message}")

        if self.live:
            self.live.start()

    def clear(self) -> None:
        """Clear the console"""
        self.console.clear()

    def print(self, *args, **kwargs) -> None:
        """
        Print to console (pauses live display temporarily)

        Args:
            *args: Arguments to pass to console.print()
            **kwargs: Keyword arguments to pass to console.print()
        """
        if self.live:
            self.live.stop()

        self.console.print(*args, **kwargs)

        if self.live:
            self.live.start()


class RichUILogHandler(logging.Handler):
    """
    Custom logging handler that captures log records and sends them to ConsoleUI's log buffer

    This handler integrates with the Rich UI to display log messages in the scrolling log panel
    instead of outputting them to stderr where they would appear outside the Live display.
    """

    def __init__(self, console_ui: ConsoleUI):
        """
        Initialize the log handler

        Args:
            console_ui: ConsoleUI instance to send log records to
        """
        super().__init__()
        self.console_ui = console_ui

    def emit(self, record: logging.LogRecord) -> None:
        """
        Emit a log record to the ConsoleUI log buffer

        Args:
            record: Log record to emit
        """
        try:
            # Format the message
            message = self.format(record)

            # Send to console UI's log buffer
            # Note: We keep emitting even after live is stopped to capture shutdown logs
            self.console_ui.add_log_entry(record.levelname, message)
        except Exception:
            # Don't let logging errors crash the application
            self.handleError(record)
