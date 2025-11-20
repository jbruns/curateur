"""
Rich console UI for curateur

Provides modern terminal interface with split panels, live updates, and progress bars.
"""

import logging
import time
from collections import deque
from typing import Optional, Dict, Any, Tuple
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
        
        # Thread operation tracking
        self.thread_operations: Dict[int, Dict[str, Any]] = {}  # thread_id -> operation state
        self.thread_id_map: Dict[str, int] = {}  # thread_name -> thread_id
        self.next_thread_id = 1
        self.thread_history_size = 5
        self.last_ui_update: Dict[int, float] = {}  # thread_id -> last update timestamp
        
        # Current state
        self.current_system = ""
        self.current_operation = {}
        self.current_stats = {}
        self.current_quota = {}
        self.current_work_queue_stats = {}
        self.thread_stats = {}
        self.performance_metrics = {}
    
    def _create_layout(self) -> Layout:
        """Create split panel layout"""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="threads", ratio=1),
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
        
        # Initialize threads panel
        self.layout["threads"].update(
            Panel(Text("Ready to begin processing", style="dim"), 
                  title="Thread Operations", border_style="green")
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
        """Start live display"""
        if self.live is None:
            # Initialize all panels with default content
            self._initialize_panels()
            
            self.live = Live(
                self.layout,
                console=self.console,
                refresh_per_second=30,
                screen=False
            )
            self.live.start()
            logger.debug("Console UI started")
    
    def stop(self) -> None:
        """Stop live display"""
        if self.live:
            self.live.stop()
            self.live = None
            logger.debug("Console UI stopped")
    
    def _get_or_assign_thread_id(self, thread_name: str) -> int:
        """
        Get or assign a sequential thread ID for a thread name
        
        Args:
            thread_name: Actual thread name from threading.current_thread().name
        
        Returns:
            Sequential thread ID (1, 2, 3, ...)
        """
        if thread_name not in self.thread_id_map:
            self.thread_id_map[thread_name] = self.next_thread_id
            logger.debug(f"Assigned thread_id={self.next_thread_id} to thread_name='{thread_name}'")
            self.next_thread_id += 1
            
            # Initialize thread state
            thread_id = self.thread_id_map[thread_name]
            self.thread_operations[thread_id] = {
                'rom_name': '<idle>',
                'operation': 'idle',
                'details': 'Waiting for work...',
                'progress': None,
                'history': deque(maxlen=self.thread_history_size),
                'status': 'idle',
                'operation_start_time': None
            }
            # Add placeholder history entry
            self.thread_operations[thread_id]['history'].append(
                ('└─ No recent activity', time.time())
            )
        
        return self.thread_id_map[thread_name]
    
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
    
    def update_thread_operation(
        self,
        thread_id: int,
        rom_name: str,
        operation: str,
        details: str,
        progress_pct: Optional[float] = None
    ) -> None:
        """
        Update thread operation status
        
        Args:
            thread_id: Sequential thread ID (1, 2, 3, ...)
            rom_name: ROM filename
            operation: Operation type ('hashing', 'api_fetch', 'downloading', 'verifying', 'idle', 'skipped', 'disabled')
            details: Operation details text
            progress_pct: Optional progress percentage (0-100) for downloads
        """
        # Check 10ms throttling (100 updates/sec max per thread)
        now = time.time()
        if thread_id in self.last_ui_update:
            if now - self.last_ui_update[thread_id] < 0.01:
                return  # Skip this update
        
        self.last_ui_update[thread_id] = now
        
        # Initialize if needed
        if thread_id not in self.thread_operations:
            logger.debug(f"Initializing thread display for thread_id={thread_id}")
            self.thread_operations[thread_id] = {
                'rom_name': '<idle>',
                'operation': 'idle',
                'details': 'Waiting for work...',
                'progress': None,
                'history': deque(maxlen=self.thread_history_size),
                'status': 'idle',
                'operation_start_time': None
            }
        
        # Update operation state
        self.thread_operations[thread_id].update({
            'rom_name': self._truncate_rom_name(rom_name),
            'operation': operation,
            'details': details,
            'progress': progress_pct,
            'status': 'active' if operation not in ['idle', 'disabled', 'skipped'] else operation
        })
        
        # Track operation start time for elapsed time display
        if operation not in ['idle', 'disabled']:
            if self.thread_operations[thread_id]['operation_start_time'] is None:
                self.thread_operations[thread_id]['operation_start_time'] = now
        
        self._render_threads_panel()
    
    def add_thread_history(self, thread_id: int, message: str, timestamp: float) -> None:
        """
        Add entry to thread history
        
        Args:
            thread_id: Sequential thread ID
            message: History message (can include Rich markup for colors)
            timestamp: Timestamp of the event
        """
        if thread_id not in self.thread_operations:
            return
        
        self.thread_operations[thread_id]['history'].append((message, timestamp))
        self._render_threads_panel()
    
    def clear_thread_operation(self, thread_id: int) -> None:
        """
        Clear thread operation and reset to idle state
        
        Args:
            thread_id: Sequential thread ID
        """
        if thread_id not in self.thread_operations:
            return
        
        self.thread_operations[thread_id].update({
            'rom_name': '<idle>',
            'operation': 'idle',
            'details': 'Waiting for work...',
            'progress': None,
            'status': 'idle',
            'operation_start_time': None
        })
        self.thread_operations[thread_id]['history'].clear()
        self.thread_operations[thread_id]['history'].append(
            ('└─ No recent activity', time.time())
        )
        
        self._render_threads_panel()
    
    def disable_thread(self, thread_id: int) -> None:
        """
        Mark thread as disabled (for pool rescaling)
        
        Args:
            thread_id: Sequential thread ID
        """
        if thread_id not in self.thread_operations:
            return
        
        self.thread_operations[thread_id].update({
            'rom_name': '<disabled>',
            'operation': 'disabled',
            'details': 'Pool rescaled',
            'progress': None,
            'status': 'disabled',
            'operation_start_time': None
        })
        self.thread_operations[thread_id]['history'].clear()
        
        self._render_threads_panel()
    
    def _render_threads_panel(self) -> None:
        """Render the threads panel with current operations"""
        if not self.thread_operations:
            return
        
        # Create table for thread operations
        threads_table = Table(show_header=True, show_edge=False, padding=(0, 1))
        threads_table.add_column("Thread", style="bold", width=6)
        threads_table.add_column("ROM", style="yellow", width=42)
        threads_table.add_column("Operation", width=50)
        
        # Sort by thread ID
        for thread_id in sorted(self.thread_operations.keys()):
            op = self.thread_operations[thread_id]
            
            # Thread ID column
            thread_label = f"[T{thread_id}]"
            
            # ROM name column
            rom_display = op['rom_name']
            
            # Operation column with progress/spinner and elapsed time
            operation_text = ""
            if op['status'] == 'idle':
                operation_text = f"[dim]{op['details']}[/dim]"
            elif op['status'] == 'disabled':
                operation_text = f"[dim]{op['details']}[/dim]"
            elif op['status'] == 'skipped':
                operation_text = f"[dim]⊘ {op['details']}[/dim]"
            else:
                # Color coding by operation type
                color = {
                    'hashing': 'cyan',
                    'api_fetch': 'yellow',
                    'downloading': 'green',
                    'verifying': 'blue'
                }.get(op['operation'], 'white')
                
                # Add spinner or progress bar
                if op['progress'] is not None:
                    # Progress bar for downloads
                    bar_width = 20
                    filled = int(bar_width * op['progress'] / 100)
                    bar = "█" * filled + "░" * (bar_width - filled)
                    operation_text = f"[{color}]{op['details']} [{bar}] {op['progress']:.0f}%[/{color}]"
                else:
                    # Spinner for other operations
                    operation_text = f"[{color}][⠋] {op['details']}[/{color}]"
                
                # Add elapsed time if >5s
                elapsed_str = self._format_elapsed_time(op['operation_start_time'])
                if elapsed_str:
                    operation_text += f" [dim]{elapsed_str}[/dim]"
            
            threads_table.add_row(thread_label, rom_display, operation_text)
            
            # Add history entries
            for msg, ts in op['history']:
                timestamp_str = time.strftime("%H:%M:%S", time.localtime(ts))
                # Right-align timestamp by padding message
                padded_msg = f"{msg:<50}"
                threads_table.add_row("", "", f"{padded_msg} [dim]{timestamp_str}[/dim]")
        
        self.layout["threads"].update(
            Panel(threads_table, title="Thread Operations", border_style="green")
        )
    
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
        
        # ScreenScraper thread stats
        if thread_stats and thread_stats.get('max_threads', 0) > 0:
            active_threads = thread_stats.get('active_threads', 0)
            max_threads = thread_stats.get('max_threads', 0)
            footer_table.add_row(
                "ScreenScraper:", Text(f"{active_threads} active / {max_threads} max threads", style="cyan"),
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
