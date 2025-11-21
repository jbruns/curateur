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
        return f"Downloading media {current}/{total}: {media_type}"
    
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
        return f"{downloaded}/{total} files downloaded"


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
        
        # Worker operation tracking (async tasks) with fixed-size pool
        self.worker_operations: Dict[int, Dict[str, Any]] = {}  # worker_id -> operation state
        self.worker_id_map: Dict[str, int] = {}  # worker_name -> worker_id
        self.max_workers = 10  # Fixed pool size
        self.available_worker_ids: Set[int] = set(range(1, self.max_workers + 1))  # Pool of available IDs
        self.last_ui_update: Dict[int, float] = {}  # worker_id -> last update timestamp
        
        # Log panel tracking
        self.log_buffer: deque = deque(maxlen=8)  # Store last 8 log lines
        
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
        self.current_work_queue_stats = {}
        self.worker_stats = {}
        self.performance_metrics = {}
    
    def _create_layout(self) -> Layout:
        """Create split panel layout"""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="threads", ratio=1),
            Layout(name="logs", size=10),  # 8 lines + 2 for borders/title
            Layout(name="queue", size=3),
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
        
        # Initialize work queue stats
        self.layout["queue"].update(
            Panel(Text("Work Queue: Ready", style="dim"), border_style="yellow")
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
                
                # Update workers panel to refresh spinners
                self._render_threads_panel()
        except asyncio.CancelledError:
            # Task was cancelled (UI stopped) - this is expected
            logger.debug("Background refresh task cancelled")
        except Exception as e:
            logger.error(f"Error in background refresh task: {e}", exc_info=True)
    
    def _get_or_assign_worker_id(self, worker_name: str) -> int:
        """
        Get or assign a worker ID from fixed-size pool (1-10) with recycling
        
        Note: Works with both threading.current_thread().name and async task identifiers.
        Rich Live display is async-compatible (Rich 13.0.0+).
        
        Args:
            worker_name: Worker identifier (thread name or task-{id})
        
        Returns:
            Worker ID from fixed pool (1-10)
        """
        if worker_name not in self.worker_id_map:
            # Check if we have available IDs in the pool
            if not self.available_worker_ids:
                # Pool exhausted - this shouldn't happen with proper cleanup
                logger.warning(f"Worker ID pool exhausted, reusing ID 1 for {worker_name}")
                worker_id = 1
            else:
                # Assign next available ID from pool
                worker_id = min(self.available_worker_ids)
                self.available_worker_ids.remove(worker_id)
                
            self.worker_id_map[worker_name] = worker_id
            logger.debug(f"Assigned worker_id={worker_id} to worker_name='{worker_name}'")
            
            # Initialize worker state
            self.worker_operations[worker_id] = {
                'rom_name': '<idle>',
                'operation': 'idle',
                'details': 'Waiting for work...',
                'progress': None,
                'total_tasks': 0,
                'completed_tasks': 0,
                'status': 'idle',
                'operation_start_time': None,
                'worker_name': worker_name  # Track for cleanup
            }
        
        return self.worker_id_map[worker_name]
    
    def _release_worker_id(self, worker_name: str) -> None:
        """
        Release a worker ID back to the pool when worker completes
        
        Args:
            worker_name: Worker identifier to release
        """
        if worker_name in self.worker_id_map:
            worker_id = self.worker_id_map[worker_name]
            
            # Return ID to available pool
            self.available_worker_ids.add(worker_id)
            
            # Clean up tracking
            del self.worker_id_map[worker_name]
            if worker_id in self.worker_operations:
                del self.worker_operations[worker_id]
            if worker_id in self.last_ui_update:
                del self.last_ui_update[worker_id]
            
            logger.debug(f"Released worker_id={worker_id} from worker_name='{worker_name}'")
    
    def display_system_operation(self, system_name: str, operation: str, details: str) -> None:
        """
        Display a system-level blocking operation (writing gamelist, validating, etc.)
        
        This repurposes worker ID 1 to show system-level operations that block further processing.
        
        Args:
            system_name: System name to display
            operation: Operation name (e.g., Operations.WRITING_GAMELIST)
            details: Operation details
        """
        # Use worker ID 1 for system operations
        worker_id = 1
        
        # Update worker 1's state
        self.update_worker_operation(
            worker_id=worker_id,
            rom_name=system_name.upper(),
            operation=operation,
            details=details,
            progress_pct=None,
            total_tasks=1,
            completed_tasks=0
        )
    
    def clear_system_operation(self) -> None:
        """Clear system-level blocking operation from worker ID 1"""
        self.clear_worker_operation(worker_id=1)
    
    
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
    
    def _truncate_rom_name(self, rom_name: str) -> str:
        """
        Truncate ROM name to 40 characters with ellipsis
        
        Args:
            rom_name: Full ROM name
        
        Returns:
            Truncated name
        """
        if len(rom_name) <= 40:
            return rom_name
        return rom_name[:37] + "..."
    
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
    
    def update_worker_operation(
        self,
        worker_id: int,
        rom_name: str,
        operation: str,
        details: str,
        progress_pct: Optional[float] = None,
        total_tasks: Optional[int] = None,
        completed_tasks: Optional[int] = None
    ) -> None:
        """
        Update worker operation status (async-compatible, synchronous update)
        
        Note: This method is intentionally synchronous. It's safe to call from async code
        as it only updates internal state and triggers Rich Live re-renders, which are
        handled by Rich's async-compatible rendering system.
        
        Args:
            worker_id: Sequential worker ID (1, 2, 3, ...)
            rom_name: ROM filename
            operation: Operation type ('hashing', 'api_fetch', 'downloading', 'verifying', 'idle', 'skipped', 'disabled')
            details: Operation details text
            progress_pct: Optional progress percentage (0-100) for downloads
            total_tasks: Total number of tasks for current ROM
            completed_tasks: Number of completed tasks
        """
        # Check 10ms throttling (100 updates/sec max per worker)
        now = time.time()
        if worker_id in self.last_ui_update:
            if now - self.last_ui_update[worker_id] < 0.01:
                return  # Skip this update
        
        self.last_ui_update[worker_id] = now
        
        # Initialize if needed
        if worker_id not in self.worker_operations:
            logger.debug(f"Initializing worker display for worker_id={worker_id}")
            self.worker_operations[worker_id] = {
                'rom_name': '<idle>',
                'operation': 'idle',
                'details': 'Waiting for work...',
                'progress': None,
                'total_tasks': 0,
                'completed_tasks': 0,
                'status': 'idle',
                'operation_start_time': None,
                'worker_name': None  # Will be set if we know it
            }
        
        # Safely update operation state
        try:
            # Sanitize details to prevent Rich markup issues
            safe_details = self._sanitize_details(details, max_length=60)
            
            # Preserve worker_name when updating
            worker_name = self.worker_operations[worker_id].get('worker_name')
            
            # Update operation state
            self.worker_operations[worker_id].update({
                'rom_name': self._truncate_rom_name(rom_name),
                'operation': operation,
                'details': safe_details,
                'progress': progress_pct,
                'status': 'active' if operation not in ['idle', 'disabled', 'skipped'] else operation,
                'worker_name': worker_name
            })
            
            # Update task progress if provided
            if total_tasks is not None:
                self.worker_operations[worker_id]['total_tasks'] = total_tasks
            if completed_tasks is not None:
                self.worker_operations[worker_id]['completed_tasks'] = completed_tasks
            
            # Track operation start time for elapsed time display
            if operation not in ['idle', 'disabled']:
                if self.worker_operations[worker_id]['operation_start_time'] is None:
                    self.worker_operations[worker_id]['operation_start_time'] = now
            
            self._render_threads_panel()
        except Exception as e:
            logger.error(f"Error updating worker {worker_id}: {e}", exc_info=True)
    
    def clear_worker_operation(self, worker_id: int) -> None:
        """
        Clear worker operation and reset to idle state (async-compatible)
        
        Args:
            worker_id: Worker ID from fixed pool
        """
        try:
            if worker_id not in self.worker_operations:
                return
            
            # Get worker name for potential cleanup
            worker_name = self.worker_operations[worker_id].get('worker_name')
            
            self.worker_operations[worker_id].update({
                'rom_name': '<idle>',
                'operation': 'idle',
                'details': 'Waiting for work...',
                'progress': None,
                'total_tasks': 0,
                'completed_tasks': 0,
                'status': 'idle',
                'operation_start_time': None,
                'worker_name': worker_name
            })
            
            self._render_threads_panel()
        except Exception as e:
            logger.error(f"Error clearing worker {worker_id}: {e}", exc_info=True)
    
    def disable_worker(self, worker_id: int) -> None:
        """
        Mark worker as disabled (for pool rescaling)
        
        Args:
            worker_id: Sequential worker ID
        """
        try:
            if worker_id not in self.worker_operations:
                return
            
            self.worker_operations[worker_id].update({
                'rom_name': '<disabled>',
                'operation': 'disabled',
                'details': 'Pool rescaled',
                'progress': None,
                'total_tasks': 0,
                'completed_tasks': 0,
                'status': 'disabled',
                'operation_start_time': None
            })
            
            self._render_threads_panel()
        except Exception as e:
            logger.error(f"Error disabling worker {worker_id}: {e}", exc_info=True)
    
    def add_log_entry(self, level: str, message: str) -> None:
        """
        Add a log entry to the log buffer (thread-safe)
        
        Args:
            level: Log level (INFO, WARNING, ERROR, etc.)
            message: Log message
        """
        # Sanitize message to prevent Rich markup issues
        safe_message = str(message).replace('[', '\\[').replace(']', '\\]')
        
        # Color code by level
        level_colors = {
            'DEBUG': 'dim',
            'INFO': 'cyan',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'bold red'
        }
        color = level_colors.get(level, 'white')
        
        # Format: [LEVEL] message and create Text object with markup
        formatted_entry = f"[{color}][{level:8}][/{color}] {safe_message}"
        
        # Add to buffer as Text object (automatically removes oldest if full)
        try:
            text_entry = Text.from_markup(formatted_entry)
            self.log_buffer.append(text_entry)
        except Exception as e:
            # Fallback to plain text if markup parsing fails
            logger.debug(f"Failed to parse log markup: {e}")
            self.log_buffer.append(Text(f"[{level:8}] {safe_message}"))
        
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
    
    def _render_threads_panel(self) -> None:
        """Render the workers panel with current operations"""
        try:
            if not self.worker_operations:
                return
            
            # Create table for worker operations
            workers_table = Table(show_header=True, show_edge=False, padding=(0, 1), box=None)
            workers_table.add_column("Worker", style="bold", width=6, no_wrap=True)
            workers_table.add_column("ROM", style="yellow", width=35, no_wrap=True)
            workers_table.add_column("Operation", max_width=70, overflow="ellipsis")
            
            # Sort by worker ID
            for worker_id in sorted(self.worker_operations.keys()):
                op = self.worker_operations[worker_id]
                
                # Worker ID column - just the number
                worker_label = str(worker_id)
                
                # ROM name column
                rom_display = op.get('rom_name', '<unknown>')
                if len(rom_display) > 33:
                    rom_display = rom_display[:30] + "..."
                
                # Operation column - two-line format
                operation_text = ""
                status = op.get('status', 'idle')
                operation = op.get('operation', 'idle')
                details = self._sanitize_details(op.get('details', ''), max_length=50)
                
                if status == 'idle':
                    operation_text = f"[dim]{details}[/dim]"
                elif status == 'disabled':
                    operation_text = f"[dim]{details}[/dim]"
                elif status == 'skipped':
                    operation_text = f"[dim]⊘ {details}[/dim]"
                else:
                    # Color coding by operation type - match full names and partial names
                    color = 'white'  # Default
                    op_lower = operation.lower()
                    if 'hash' in op_lower:
                        color = 'cyan'
                    elif 'fetch' in op_lower or 'metadata' in op_lower or 'api' in op_lower:
                        color = 'yellow'
                    elif 'download' in op_lower:
                        color = 'green'
                    elif 'verif' in op_lower:
                        color = 'blue'
                    elif 'complete' in op_lower:
                        color = 'green'
                    elif 'prepar' in op_lower:
                        color = 'cyan'
                    
                    # Build operation text with progress and details on single line
                    operation_parts = []
                    
                    # Add task progress bar if we have task counts
                    total_tasks = op.get('total_tasks', 0)
                    completed_tasks = op.get('completed_tasks', 0)
                    if total_tasks > 0:
                        try:
                            progress_ratio = completed_tasks / total_tasks
                            percentage = int(progress_ratio * 100)
                            # Compact progress: just percentage
                            operation_parts.append(f"[{percentage}%]")
                        except (ZeroDivisionError, TypeError):
                            pass  # Skip progress display if calculation fails
                    
                    # Add operation details
                    if details:
                        operation_parts.append(details)
                    
                    # Add elapsed time if >5s
                    elapsed_str = self._format_elapsed_time(op.get('operation_start_time'))
                    if elapsed_str:
                        operation_parts.append(f"{elapsed_str}")
                    
                    # Combine on single line with color
                    parts_text = ' '.join(operation_parts)
                    
                    # Use animated spinner from background refresh
                    spinner = self.spinner_frames[self.spinner_state]
                    operation_text = f"[{color}]{spinner} {parts_text}[/{color}]"
                
                workers_table.add_row(worker_label, rom_display, operation_text)
            
            self.layout["threads"].update(
                Panel(workers_table, title="Worker Operations", border_style="green")
            )
        except Exception as e:
            logger.error(f"Error rendering workers panel: {e}", exc_info=True)
            # Don't crash - just skip this render
    
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
        performance_metrics: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Update footer panel with statistics, quota, thread stats, and performance metrics
        
        Args:
            stats: Statistics dict with counts (successful, failed, skipped, etc.)
            api_quota: API quota dict (requests_today, max_requests_per_day)
            thread_stats: Optional thread pool stats (active_threads, max_threads)
            performance_metrics: Optional performance metrics (avg_api_time, avg_rom_time, eta)
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
                "", ""
            )
            
            # API quota row
            requests_today = api_quota.get('requests_today', 0)
            max_requests = api_quota.get('max_requests_per_day', 0)
            
            if max_requests > 0 and requests_today >= 0:
                quota_pct = (requests_today / max_requests) * 100
                quota_style = "red" if quota_pct > 90 else "yellow" if quota_pct > 75 else "green"
                quota_text = f"{requests_today}/{max_requests} ({quota_pct:.1f}%)"
            elif requests_today > 0:
                # Have requests but no max (shouldn't happen with API data)
                quota_style = "dim"
                quota_text = f"{requests_today}"
            else:
                # No data yet
                quota_style = "dim"
                quota_text = "N/A"
            
            footer_table.add_row(
                "API Quota:", Text(quota_text, style=quota_style),
                "", ""
            )
            
            # ScreenScraper worker stats
            if thread_stats and thread_stats.get('max_threads', 0) > 0:
                active_threads = thread_stats.get('active_threads', 0)
                max_threads = thread_stats.get('max_threads', 0)
                footer_table.add_row(
                    "ScreenScraper:", Text(f"{active_threads} active / {max_threads} max workers", style="cyan"),
                    "", ""
                )
            
            # Performance metrics
            if performance_metrics:
                avg_api_time = performance_metrics.get('avg_api_time', 0)
                avg_rom_time = performance_metrics.get('avg_rom_time', 0)
                
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
    
    def update_work_queue_stats(
        self,
        pending: int,
        processed: int,
        failed: int,
        not_found: int,
        retry_count: int
    ) -> None:
        """
        Update work queue statistics display
        
        Args:
            pending: Number of pending work items
            processed: Number of processed items
            failed: Number of failed items (retries exhausted)
            not_found: Number of not-found items (404)
            retry_count: Total number of retry attempts
        """
        try:
            self.current_work_queue_stats = {
                'pending': pending,
                'processed': processed,
                'failed': failed,
                'not_found': not_found,
                'retry_count': retry_count
            }
            
            # Create work queue stats display
            queue_table = Table.grid(padding=(0, 2))
            queue_table.add_column(style="bold")
            queue_table.add_column()
            queue_table.add_column(style="bold")
            queue_table.add_column()
            queue_table.add_column(style="bold")
            queue_table.add_column()
            
            queue_table.add_row(
                "Queue:", Text(str(pending), style="blue"),
                "Processed:", Text(str(processed), style="green"),
                "Failed:", Text(str(failed), style="red" if failed > 0 else "dim")
            )
            queue_table.add_row(
                "Not Found:", Text(str(not_found), style="yellow"),
                "Retries:", Text(str(retry_count), style="cyan"),
                "", ""
            )
            
            self.layout["queue"].update(
                Panel(queue_table, title="Work Queue", border_style="cyan")
            )
        except Exception as e:
            logger.error(f"Error updating work queue stats: {e}", exc_info=True)
            # Show error state in panel
            error_text = Text(f"Error: {str(e)[:40]}", style="red")
            self.layout["queue"].update(
                Panel(error_text, title="Work Queue", border_style="red")
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
