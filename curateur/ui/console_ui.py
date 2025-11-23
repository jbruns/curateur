"""
Rich console UI for curateur

Provides modern terminal interface with split panels, live updates, and progress bars.
"""

import asyncio
import logging
import time
from collections import deque
from typing import Optional, Dict, Any, Tuple, Set
from datetime import timedelta

from curateur import __version__
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TaskID
from rich.table import Table
from rich.text import Text

logger = logging.getLogger(__name__)


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
    ┌─────────────────────────────────────────┐
    │ Header: System Progress                 │
    ├─────────────────────────────────────────┤
    │ Main: Current Operation                 │
    │  ├─ System: NES (1/5)                  │
    │  ├─ ROM: Star Quest (15/150)           │
    │  ├─ Progress Bar: [████░░] 10%         │
    │  └─ Status: Downloading cover...       │
    ├─────────────────────────────────────────┤
    │ Footer: Statistics & Quota              │
    │  ├─ Success: 145 | Failed: 5           │
    │  └─ API: 1250/10000 requests           │
    └─────────────────────────────────────────┘
    
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
            'hashing': {'active': False, 'current': 0, 'total': 0, 'details': ''},
            'api_fetch': {'active_roms': [], 'max_concurrent': 3, 'cache_hits': 0, 'cache_misses': 0, 'search_fallback': 0},
            'media_download': {'active_roms': [], 'max_concurrent': 3, 'validated': 0, 'by_type': {}},
            'completed': {'count': 0},
            'system_operation': {'active': False, 'operation': '', 'details': ''}
        }
        
        # Additional tracking
        self.unmatched_count = 0
        self.integrity_score = None  # Gamelist integrity percentage
        self.is_throttled = False  # Whether currently rate limited
        self.last_pipeline_update = 0.0
        
        # Log panel tracking
        self.log_buffer: deque = deque(maxlen=16)  # Store last 12 log lines
        
        # Animation tracking for interval-based refresh
        self.spinner_state = 0
        self.spinner_frames = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
        self.refresh_task: Optional[asyncio.Task] = None
        
        # Logging handler tracking (for cleanup)
        self.log_handler: Optional['RichUILogHandler'] = None
        
        # Current state
        self.current_system = ""
        self.current_operation = {}
        self.current_stats = {}
        self.current_quota = {}
        self.worker_stats = {}
        self.performance_metrics = {}
    
    def _create_layout(self) -> Layout:
        """Create split panel layout"""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="threads", size=9),  # 5 stages + 4 for borders/title/padding
            Layout(name="logs", ratio=1),  # Take remaining space
            Layout(name="footer", size=7)
        )
        return layout
    
    def _initialize_panels(self) -> None:
        """Initialize all panels with default content"""
        # Initialize header
        header_text = Text(f"curateur v{__version__}", style="bold magenta")
        header_text.append(" | ", style="dim")
        header_text.append("Initializing...", style="dim")
        self.layout["header"].update(
            Panel(header_text, border_style="cyan")
        )
        
        # Initialize workers panel
        self.layout["threads"].update(
            Panel(Text("Ready to begin processing", style="dim"), 
                  title="Worker Operations", border_style="green")
        )
        
        # Initialize logs panel
        self.layout["logs"].update(
            Panel(Text("Logs will appear here", style="dim"),
                  title="Activity Log", border_style="magenta")
        )
        
        # Initialize footer with default stats
        self.update_footer(
            stats={'successful': 0, 'failed': 0, 'skipped': 0},
            api_quota={'requests_today': 0, 'max_requests_per_day': 0}
        )
    
    def start(self) -> None:
        """Start live display and background refresh task"""
        if self.live is None:
            # Initialize all panels with default content
            self._initialize_panels()
            
            self.live = Live(
                self.layout,
                console=self.console,
                refresh_per_second=10,
                screen=False
            )
            self.live.start()
            logger.debug("Console UI started")
            
            # Start background refresh task for spinner animation
            try:
                loop = asyncio.get_running_loop()
                self.refresh_task = loop.create_task(self._background_refresh())
            except RuntimeError:
                # No event loop running - this is okay for non-async contexts
                logger.debug("No asyncio event loop found, skipping background refresh task")
    
    def stop(self) -> None:
        """Stop live display and background refresh task"""
        # Cancel background refresh task
        if self.refresh_task and not self.refresh_task.done():
            self.refresh_task.cancel()
            self.refresh_task = None
        
        # Remove the RichUILogHandler from root logger to prevent logs going to stopped UI
        if self.log_handler:
            root_logger = logging.getLogger()
            root_logger.removeHandler(self.log_handler)
            self.log_handler = None
        
        if self.live:
            self.live.stop()
            self.live = None
            logger.debug("Console UI stopped")
    
    async def _background_refresh(self) -> None:
        """
        Background task that updates UI every 250ms for spinner animation
        
        This ensures the UI updates even when no progress is being made,
        keeping spinners animated for active operations.
        """
        try:
            while True:
                await asyncio.sleep(0.25)  # 250ms refresh interval
                
                # Increment spinner state
                self.spinner_state = (self.spinner_state + 1) % len(self.spinner_frames)
                
                # Update pipeline panel to refresh spinners
                self._render_pipeline_panel()
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
        self._render_pipeline_panel()
    
    def increment_media_validated(self, media_type: Optional[str] = None) -> None:
        """
        Increment media validation counter
        
        Args:
            media_type: Optional media type (box, screenshot, video, etc.) for breakdown tracking
        """
        self.pipeline_stages['media_download']['validated'] += 1
        
        # Track by type for detailed breakdown
        if media_type:
            by_type = self.pipeline_stages['media_download']['by_type']
            by_type[media_type] = by_type.get(media_type, 0) + 1
        
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
        logger.debug(f"Pipeline stages updated: api_fetch={self.pipeline_stages['api_fetch']['max_concurrent']}, media={self.pipeline_stages['media_download']['max_concurrent']}")
        self._render_pipeline_panel()
    
    def increment_completed(self) -> None:
        """
        Increment completed ROM counter
        """
        self.pipeline_stages['completed']['count'] += 1
        self._render_pipeline_panel()
    
    def set_system_operation(self, operation: str, details: str) -> None:
        """
        Set active system-level operation (writing gamelist, validation, etc.)
        
        Args:
            operation: Operation name (e.g., 'Writing gamelist', 'Validating')
            details: Operation details
        """
        self.pipeline_stages['system_operation']['active'] = True
        self.pipeline_stages['system_operation']['operation'] = operation
        self.pipeline_stages['system_operation']['details'] = details
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
            'hashing': {'active': False, 'current': 0, 'total': 0, 'details': ''},
            'api_fetch': {'active_roms': [], 'max_concurrent': current_max_concurrent, 'cache_hits': 0, 'cache_misses': 0, 'search_fallback': 0},
            'media_download': {'active_roms': [], 'max_concurrent': current_max_concurrent, 'validated': 0, 'by_type': {}},
            'completed': {'count': 0},
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
        
        # Create Text object with styled level prefix and plain message
        # This avoids escaping issues - level uses markup, message is plain text
        text_entry = Text()
        text_entry.append(f"[{level:8}] ", style=color)
        text_entry.append(str(message))
        
        # Add to buffer (automatically removes oldest if full)
        self.log_buffer.append(text_entry)
        
        # Update log panel
        self._render_logs_panel()
    
    def _render_logs_panel(self) -> None:
        """Render the logs panel with recent log entries"""
        try:
            if not self.log_buffer:
                self.layout["logs"].update(
                    Panel(Text("No recent activity", style="dim"),
                          title="Activity Log", border_style="magenta")
                )
                return
            
            # Create text with all log entries (newest at bottom)
            log_text = Text()
            for entry in self.log_buffer:
                # Entry is already a Text object from add_log_entry
                if isinstance(entry, Text):
                    log_text.append(entry)
                    log_text.append("\n")
                else:
                    # Fallback for any string entries
                    log_text.append(str(entry) + "\n")
            
            self.layout["logs"].update(
                Panel(log_text, title="Activity Log", border_style="magenta")
            )
        except Exception as e:
            logger.error(f"Error rendering logs panel: {e}", exc_info=True)
            # Show error state in panel
            self.layout["logs"].update(
                Panel(Text(f"Error rendering logs: {e}", style="red"),
                      title="Activity Log", border_style="magenta")
            )
    
    def _render_pipeline_panel(self) -> None:
        """Render the pipeline stages panel showing concurrent activities"""
        try:
            # Throttle updates to every 100ms
            now = time.time()
            if now - self.last_pipeline_update < 0.1:
                return
            self.last_pipeline_update = now
            
            pipeline_table = Table(show_header=False, show_edge=False, padding=(0, 1), box=None, expand=True)
            pipeline_table.add_column("Stage", style="bold", width=20, no_wrap=True)
            pipeline_table.add_column("Status", overflow="fold", no_wrap=False)
            
            spinner = self.spinner_frames[self.spinner_state]
            
            # 1. HASHING stage
            hashing = self.pipeline_stages['hashing']
            if hashing['active']:
                current = hashing['current']
                total = hashing['total']
                pct = int((current / total * 100)) if total > 0 else 0
                bar_width = 20
                filled = int(bar_width * current / total) if total > 0 else 0
                bar = '█' * filled + '░' * (bar_width - filled)
                details = f" {hashing['details']}" if hashing['details'] else ""
                status_text = f"[cyan]{spinner} [{bar}] {pct}% ({current}/{total} ROMs){details}[/cyan]"
            else:
                status_text = "[dim]Ready[/dim]"
            pipeline_table.add_row("⚡ HASHING", status_text)
            
            # 2. API FETCH stage
            api_fetch = self.pipeline_stages['api_fetch']
            active_roms = api_fetch['active_roms']
            cache_hits = api_fetch.get('cache_hits', 0)
            cache_misses = api_fetch.get('cache_misses', 0)
            search_fallback = api_fetch.get('search_fallback', 0)
            total_requests = cache_hits + cache_misses
            
            if active_roms:
                # Show up to 3 ROM names
                rom_names = ', '.join([self._truncate_rom_name(r, 25) for r in active_roms[:3]])
                if len(active_roms) > 3:
                    rom_names += f" +{len(active_roms) - 3} more"
                
                # Build info string with cache and search fallback stats
                info_parts = []
                if total_requests > 0:
                    hit_rate = int(cache_hits / total_requests * 100)
                    info_parts.append(f"Cache: {cache_hits} hits ({hit_rate}%)")
                if search_fallback > 0:
                    info_parts.append(f"{search_fallback} fallback")
                
                cache_info = f" | {', '.join(info_parts)}" if info_parts else ""
                status_text = f"[yellow]{spinner} [{len(active_roms)}/{api_fetch['max_concurrent']}] {rom_names}{cache_info}[/yellow]"
            elif total_requests > 0 or search_fallback > 0:
                # Show stats even when idle
                info_parts = []
                if total_requests > 0:
                    hit_rate = int(cache_hits / total_requests * 100)
                    info_parts.append(f"Cache: {cache_hits}/{total_requests} hits ({hit_rate}%)")
                if search_fallback > 0:
                    info_parts.append(f"{search_fallback} fallback")
                status_text = f"[dim]Idle | {', '.join(info_parts)}[/dim]"
            else:
                status_text = "[dim]Idle[/dim]"
            pipeline_table.add_row("🔍 API FETCH", status_text)
            
            # 3. MEDIA DOWNLOAD stage
            media_dl = self.pipeline_stages['media_download']
            active_items = media_dl['active_roms']
            validated_count = media_dl.get('validated', 0)
            
            if active_items:
                # Group by ROM and show media types
                rom_media = {}
                for rom, media_type in active_items:
                    if rom not in rom_media:
                        rom_media[rom] = []
                    rom_media[rom].append(media_type)
                
                # Show first ROM with its media types
                if rom_media:
                    first_rom = list(rom_media.keys())[0]
                    media_types = ', '.join(rom_media[first_rom][:3])
                    display = f"{self._truncate_rom_name(first_rom, 20)}: {media_types}"
                    if len(rom_media) > 1:
                        display += f" +{len(rom_media) - 1} more"
                    
                    # Build validated info with breakdown by type
                    validated_info = ""
                    if validated_count > 0:
                        by_type = media_dl.get('by_type', {})
                        if by_type:
                            # Show counts by type (e.g., "2 box, 3 screenshot")
                            type_counts = [f"{count} {mtype}" for mtype, count in sorted(by_type.items())]
                            validated_info = f" | {', '.join(type_counts)}"
                        else:
                            validated_info = f" | {validated_count} validated"
                    
                    status_text = f"[green]{spinner} [{len(active_items)}/{media_dl['max_concurrent']}] {display}{validated_info}[/green]"
                else:
                    status_text = "[dim]Idle[/dim]"
            elif validated_count > 0:
                # Show breakdown by type when idle
                by_type = media_dl.get('by_type', {})
                if by_type:
                    type_counts = [f"{count} {mtype}" for mtype, count in sorted(by_type.items())]
                    status_text = f"[dim]Idle | {', '.join(type_counts)}[/dim]"
                else:
                    status_text = f"[dim]Idle | {validated_count} validated[/dim]"
            else:
                status_text = "[dim]Idle[/dim]"
            pipeline_table.add_row("📥 MEDIA", status_text)
            
            # 4. COMPLETED counter
            completed_count = self.pipeline_stages['completed']['count']
            if completed_count > 0:
                status_text = f"[bold green]✓ {completed_count} ROMs processed[/bold green]"
            else:
                status_text = "[dim]0 ROMs[/dim]"
            pipeline_table.add_row("✅ COMPLETE", status_text)
            
            # 5. SYSTEM OPERATION (always shown)
            sys_op = self.pipeline_stages['system_operation']
            if sys_op['active']:
                operation = sys_op['operation']
                details = sys_op['details']
                status_text = f"[cyan]{spinner} {operation}: {details}[/cyan]"
            else:
                # Show persistent info when idle
                info_parts = []
                if self.integrity_score is not None:
                    integrity_pct = int(self.integrity_score * 100)
                    info_parts.append(f"Integrity: {integrity_pct}%")
                if self.is_throttled:
                    info_parts.append("[yellow]⚠ Rate limited[/yellow]")
                
                if info_parts:
                    status_text = f"[dim]Idle | {' | '.join(info_parts)}[/dim]"
                else:
                    status_text = "[dim]Idle[/dim]"
            pipeline_table.add_row("💾 SYSTEM", status_text)
            
            self.layout["threads"].update(
                Panel(pipeline_table, title="Pipeline Stages", border_style="green")
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
        
        # Build header with version prefix
        header_text = Text(f"curateur v{__version__}", style="bold magenta")
        header_text.append(" | ", style="dim")
        
        progress_text = f"System: {system_name.upper()} ({system_num}/{total_systems})"
        percentage = (system_num - 1) / total_systems * 100 if total_systems > 0 else 0
        
        header_text.append(progress_text, style="bold cyan")
        header_text.append(f" — {percentage:.0f}% complete", style="dim")
        
        self.layout["header"].update(
            Panel(header_text, border_style="cyan")
        )
        
        logger.debug(f"Header updated: {system_name} ({system_num}/{total_systems})")
    
    def update_footer(
        self,
        stats: Dict[str, int],
        api_quota: Dict[str, Any],
        thread_stats: Optional[Dict[str, Any]] = None,
        performance_metrics: Optional[Dict[str, Any]] = None,
        queue_pending: int = 0
    ) -> None:
        """
        Update footer panel with statistics, quota, thread stats, and performance metrics
        
        Args:
            stats: Statistics dict with counts (successful, failed, skipped, etc.)
            api_quota: API quota dict (requests_today, max_requests_per_day)
            thread_stats: Optional thread pool stats (active_threads, max_threads)
            performance_metrics: Optional performance metrics (avg_api_time, avg_rom_time, eta)
            queue_pending: Number of pending items in work queue
        """
        try:
            self.current_stats = stats
            self.current_quota = api_quota
            self.thread_stats = thread_stats or {}
            self.performance_metrics = performance_metrics or {}
            
            # Create footer table
            footer_table = Table.grid(padding=(0, 2))
            footer_table.add_column(style="bold")
            footer_table.add_column()
            footer_table.add_column(style="bold")
            footer_table.add_column()
            
            # Statistics row
            successful = stats.get('successful', 0)
            failed = stats.get('failed', 0)
            skipped = stats.get('skipped', 0)
            
            footer_table.add_row(
                "Success:", Text(str(successful), style="green"),
                "Failed:", Text(str(failed), style="red" if failed > 0 else "dim")
            )
            footer_table.add_row(
                "Skipped:", Text(str(skipped), style="yellow"),
                "Unmatched:", Text(str(self.unmatched_count), style="red" if self.unmatched_count > 0 else "dim")
            )
            footer_table.add_row(
                "Queue:", Text(str(queue_pending), style="blue"),
                "", Text("")  # Empty cell for alignment
            )
            
            # API quota row (with bad requests on same row)
            # Note: Keys match ScreenScraper API field names (lowercase, no underscores)
            requests_today = api_quota.get('requeststoday', 0)
            max_requests = api_quota.get('maxrequestsperday', 0)
            bad_requests_today = api_quota.get('requestskotoday', 0)
            max_bad_requests = api_quota.get('maxrequestskoperday', 0)
            
            # Get quota threshold from config
            quota_threshold = self.config.get('scraping', {}).get('quota_warning_threshold', 0.95)
            
            # Format API quota
            if max_requests > 0 and requests_today >= 0:
                quota_pct = requests_today / max_requests
                # Color code based on percentage: green <80%, yellow 80%-<threshold, red >=threshold
                if quota_pct >= quota_threshold:
                    quota_style = "red"
                elif quota_pct >= 0.80:
                    quota_style = "yellow"
                else:
                    quota_style = "green"
                quota_text = f"{requests_today}/{max_requests} ({quota_pct:.1%})"
            elif requests_today > 0:
                # Have requests but no max (shouldn't happen with API data)
                quota_style = "dim"
                quota_text = f"{requests_today}"
            else:
                # No data yet
                quota_style = "dim"
                quota_text = "N/A"
            
            # Format bad requests
            if max_bad_requests > 0 and bad_requests_today >= 0:
                bad_quota_pct = bad_requests_today / max_bad_requests
                # Use same color thresholds as regular quota
                if bad_quota_pct >= quota_threshold:
                    bad_quota_style = "red"
                elif bad_quota_pct >= 0.80:
                    bad_quota_style = "yellow"
                else:
                    bad_quota_style = "green"
                bad_quota_text = f"{bad_requests_today}/{max_bad_requests} ({bad_quota_pct:.1%})"
            elif bad_requests_today > 0:
                bad_quota_style = "dim"
                bad_quota_text = f"{bad_requests_today}"
            else:
                bad_quota_style = "dim"
                bad_quota_text = "N/A"
            
            footer_table.add_row(
                "API Quota:", Text(quota_text, style=quota_style),
                "Bad Requests:", Text(bad_quota_text, style=bad_quota_style)
            )
            
            # ScreenScraper worker stats
            if thread_stats and thread_stats.get('max_threads', 0) > 0:
                active_threads = thread_stats.get('active_threads', 0)
                max_threads = thread_stats.get('max_threads', 0)
                footer_table.add_row(
                    "API Threads:", Text(f"{active_threads} active / {max_threads} max", style="cyan"),
                    "", ""
                )
            
            # Performance metrics
            avg_api_time = performance_metrics.get('avg_api_time', 0) if performance_metrics else 0
            avg_rom_time = performance_metrics.get('avg_rom_time', 0) if performance_metrics else 0
            
            # Show N/A if no data collected yet (values will be 0 initially)
            if avg_api_time > 0:
                api_time_text = f"{avg_api_time:.0f}ms"
            else:
                api_time_text = "N/A"
            
            if avg_rom_time > 0:
                rom_time_text = f"{avg_rom_time:.1f}s"
            else:
                rom_time_text = "N/A"
            
            footer_table.add_row(
                "Avg API Response:", Text(api_time_text, style="yellow"),
                "Avg ROM Time:", Text(rom_time_text, style="cyan")
            )
            
            # ETA
            if performance_metrics:
                eta = performance_metrics.get('eta')
                if eta and isinstance(eta, timedelta):
                    hours = int(eta.total_seconds() // 3600)
                    minutes = int((eta.total_seconds() % 3600) // 60)
                    
                    # Color code based on time remaining
                    if eta.total_seconds() < 1800:  # <30 minutes
                        eta_style = "green"
                    elif eta.total_seconds() < 7200:  # <2 hours
                        eta_style = "yellow"
                    else:
                        eta_style = "red"
                    
                    eta_text = f"{hours}h {minutes}m remaining"
                    footer_table.add_row(
                        "System ETA:", Text(eta_text, style=eta_style),
                        "", ""
                    )
            
            self.layout["footer"].update(
                Panel(footer_table, title="Statistics", border_style="blue")
            )
        except Exception as e:
            logger.error(f"Error updating footer: {e}", exc_info=True)
            # Show error state in panel
            error_text = Text(f"Error rendering statistics: {str(e)[:50]}", style="red")
            self.layout["footer"].update(
                Panel(error_text, title="Statistics", border_style="red")
            )
    
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
            # Don't emit if UI is stopped (live is None)
            if not self.console_ui.live:
                return
            
            # Format the message
            message = self.format(record)
            
            # Send to console UI's log buffer
            self.console_ui.add_log_entry(record.levelname, message)
        except Exception:
            # Don't let logging errors crash the application
            self.handleError(record)
