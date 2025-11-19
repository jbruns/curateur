"""
Rich console UI for curateur

Provides modern terminal interface with split panels, live updates, and progress bars.
"""

import logging
from typing import Optional, Dict, Any

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
        
        # Current state
        self.current_system = ""
        self.current_operation = {}
        self.current_stats = {}
        self.current_quota = {}
        self.current_work_queue_stats = {}
    
    def _create_layout(self) -> Layout:
        """Create split panel layout"""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="main", ratio=1),
            Layout(name="queue", size=3),
            Layout(name="footer", size=5)
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
        
        # Initialize main
        self.layout["main"].update(
            Panel(Text("Ready to begin processing", style="dim"), 
                  title="Current Operation", border_style="green")
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
                refresh_per_second=4,
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
    
    def update_main(self, operation_status: Dict[str, Any]) -> None:
        """
        Update main panel with current operation
        
        Args:
            operation_status: dict with:
                - rom_name: str
                - rom_num: int
                - total_roms: int
                - action: str ('scraping', 'downloading', 'skipping', etc.)
                - details: str (optional detail message)
        """
        self.current_operation = operation_status
        
        rom_name = operation_status.get('rom_name', 'Unknown')
        rom_num = operation_status.get('rom_num', 0)
        total_roms = operation_status.get('total_roms', 0)
        action = operation_status.get('action', 'processing')
        details = operation_status.get('details', '')
        
        # Create main content
        content = Table.grid(padding=(0, 2))
        content.add_column(style="bold", justify="right")
        content.add_column()
        
        # ROM info
        content.add_row("ROM:", Text(rom_name, style="yellow"))
        content.add_row("Progress:", f"{rom_num}/{total_roms}")
        content.add_row("Action:", Text(action.title(), style="green"))
        
        if details:
            content.add_row("Status:", Text(details, style="dim"))
        
        # Progress bar
        if total_roms > 0:
            percentage = rom_num / total_roms * 100
            bar_width = 40
            filled = int(bar_width * rom_num / total_roms)
            bar = "█" * filled + "░" * (bar_width - filled)
            content.add_row("", f"[{bar}] {percentage:.1f}%")
        
        self.layout["main"].update(
            Panel(content, title="Current Operation", border_style="green")
        )
    
    def update_footer(self, stats: Dict[str, int], api_quota: Dict[str, Any]) -> None:
        """
        Update footer panel with statistics and quota
        
        Args:
            stats: Statistics dict with counts (successful, failed, skipped, etc.)
            api_quota: API quota dict (requests_today, max_requests_per_day)
        """
        self.current_stats = stats
        self.current_quota = api_quota
        
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
        
        if max_requests > 0:
            quota_pct = (requests_today / max_requests) * 100
            quota_style = "red" if quota_pct > 90 else "yellow" if quota_pct > 75 else "green"
            quota_text = f"{requests_today}/{max_requests} ({quota_pct:.1f}%)"
        else:
            quota_style = "dim"
            quota_text = f"{requests_today}"
        
        footer_table.add_row(
            "API Quota:", Text(quota_text, style=quota_style),
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
