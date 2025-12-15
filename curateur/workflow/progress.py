"""
Progress tracking for scraping operations.

Provides simple console output for tracking scraping progress.
"""

import time
from typing import List, Optional
from dataclasses import dataclass, field


@dataclass
class ROMProgress:
    """Progress tracking for a single ROM."""
    name: str
    status: str  # 'pending', 'scraping', 'success', 'failed', 'skipped'
    detail: str = ""
    start_time: Optional[float] = None
    end_time: Optional[float] = None


@dataclass
class SystemProgress:
    """Progress tracking for a system."""
    name: str
    total_roms: int
    processed: int = 0
    succeeded: int = 0
    failed: int = 0
    skipped: int = 0
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    roms: List[ROMProgress] = field(default_factory=list)


class ProgressTracker:
    """
    Tracks scraping progress with simple console output.
    
    Features:
    - System-level progress
    - ROM-level status tracking
    - Success/failure statistics
    - Simple console logging (no rich UI for MVP)
    """
    
    def __init__(self):
        """Initialize progress tracker."""
        self.current_system: Optional[SystemProgress] = None
        self.systems: List[SystemProgress] = []
        self.start_time = time.time()
    
    def start_system(self, system_name: str, total_roms: int) -> None:
        """
        Start tracking a new system.
        
        Args:
            system_name: Name of the system
            total_roms: Total number of ROMs to process
        """
        self.current_system = SystemProgress(
            name=system_name,
            total_roms=total_roms,
            start_time=time.time()
        )
        
        print(f"\n{'='*60}")
        print(f"Scraping {system_name}")
        print(f"Total ROMs: {total_roms}")
        print(f"{'='*60}\n")
    
    def log_rom(
        self,
        rom_name: str,
        status: str,
        detail: str = ""
    ) -> None:
        """
        Log ROM processing status.
        
        Args:
            rom_name: Name of the ROM
            status: Status ('success', 'failed', 'skipped')
            detail: Additional detail message
        """
        if not self.current_system:
            return
        
        self.current_system.processed += 1
        
        if status == 'success':
            self.current_system.succeeded += 1
            symbol = "✓"
        elif status == 'failed':
            self.current_system.failed += 1
            symbol = "✗"
        elif status == 'skipped':
            self.current_system.skipped += 1
            symbol = "○"
        else:
            symbol = "?"
        
        # Progress indicator
        progress = f"[{self.current_system.processed}/{self.current_system.total_roms}]"
        
        # Build message
        message = f"  {symbol} {progress} {rom_name}"
        if detail:
            message += f" - {detail}"
        
        print(message)
        
        # Store in history
        self.current_system.roms.append(ROMProgress(
            name=rom_name,
            status=status,
            detail=detail
        ))
    
    def finish_system(
        self, succeeded: Optional[int] = None, failed: Optional[int] = None,
        skipped: Optional[int] = None
    ) -> None:
        """Finish tracking current system and print summary.
        
        Args:
            succeeded: Override succeeded count (for Textual UI mode)
            failed: Override failed count (for Textual UI mode)
            skipped: Override skipped count (for Textual UI mode)
        """
        if not self.current_system:
            return
        
        # Use provided stats if available (for Textual UI mode where log_rom isn't called)
        if succeeded is not None:
            self.current_system.succeeded = succeeded
        if failed is not None:
            self.current_system.failed = failed
        if skipped is not None:
            self.current_system.skipped = skipped
        
        self.current_system.end_time = time.time()
        
        # Calculate elapsed time
        elapsed = self.current_system.end_time - self.current_system.start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        
        print(f"\n{'-'*60}")
        print(f"System Complete: {self.current_system.name}")
        print(f"  Total:     {self.current_system.total_roms}")
        print(f"  Succeeded: {self.current_system.succeeded}")
        print(f"  Failed:    {self.current_system.failed}")
        print(f"  Skipped:   {self.current_system.skipped}")
        print(f"  Time:      {minutes}m {seconds}s")
        print(f"{'-'*60}\n")
        
        self.systems.append(self.current_system)
        self.current_system = None
    
    def print_final_summary(self) -> None:
        """Print final summary of all systems processed."""
        if not self.systems:
            print("No systems processed.")
            return
        
        total_roms = sum(s.total_roms for s in self.systems)
        total_succeeded = sum(s.succeeded for s in self.systems)
        total_failed = sum(s.failed for s in self.systems)
        total_skipped = sum(s.skipped for s in self.systems)
        
        elapsed = time.time() - self.start_time
        minutes = int(elapsed // 60)
        seconds = int(elapsed % 60)
        
        print(f"\n{'='*60}")
        print("Final Summary")
        print(f"{'='*60}")
        print(f"Systems processed: {len(self.systems)}")
        print(f"Total ROMs:        {total_roms}")
        print(f"  Succeeded:       {total_succeeded}")
        print(f"  Failed:          {total_failed}")
        print(f"  Skipped:         {total_skipped}")
        print(f"Total time:        {minutes}m {seconds}s")
        print(f"{'='*60}\n")
        
        # Show per-system breakdown
        if len(self.systems) > 1:
            print("Per-system results:")
            for system in self.systems:
                success_rate = (system.succeeded / system.total_roms * 100) if system.total_roms > 0 else 0
                print(f"  {system.name}: {system.succeeded}/{system.total_roms} ({success_rate:.1f}%)")
            print()


class ErrorLogger:
    """
    Simple error logger for tracking failures.
    
    Stores errors for summary reporting.
    """
    
    def __init__(self):
        """Initialize error logger."""
        self.errors: List[tuple] = []
    
    def log_error(self, filename: str, message: str) -> None:
        """
        Log an error.
        
        Args:
            filename: Name of the ROM file
            message: Error message
        """
        self.errors.append((filename, message))
    
    def write_summary(self, output_path: str = "errors.log") -> None:
        """
        Write error summary to file.
        
        Args:
            output_path: Path to error log file
        """
        if not self.errors:
            return
        
        with open(output_path, 'w') as f:
            f.write(f"Scraping Errors ({len(self.errors)} total)\n")
            f.write("="*60 + "\n\n")
            
            for filename, message in self.errors:
                f.write(f"File: {filename}\n")
                f.write(f"Error: {message}\n")
                f.write("-"*60 + "\n")
        
        print(f"Error log written to: {output_path}")
    
    def has_errors(self) -> bool:
        """Check if any errors were logged."""
        return len(self.errors) > 0
    
    def get_error_count(self) -> int:
        """Get total number of errors."""
        return len(self.errors)
