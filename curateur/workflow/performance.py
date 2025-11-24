"""
Performance monitoring and metrics tracking

Tracks scraping performance and calculates ETA.
"""

import logging
import time
import psutil
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, Deque

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics snapshot"""
    # Timing
    elapsed_seconds: float = 0.0
    estimated_total_seconds: float = 0.0
    
    # Throughput (display units)
    roms_per_hour: float = 0.0
    api_calls_per_minute: float = 0.0
    downloads_per_second: float = 0.0
    
    # Counts
    roms_processed: int = 0
    roms_total: int = 0
    api_calls: int = 0
    downloads: int = 0
    
    # Resources
    memory_mb: float = 0.0
    cpu_percent: float = 0.0
    
    # Derived
    percent_complete: float = 0.0
    eta_seconds: float = 0.0
    
    # Averages (new for UI)
    avg_api_time: float = 0.0  # Average API call duration in seconds
    avg_rom_time: float = 0.0  # Average total ROM processing time in seconds
    
    # Time-series for sparklines (10-second window at 0.25s refresh = 40 samples)
    throughput_history: list = field(default_factory=list)  # ROMs/hour history
    api_rate_history: list = field(default_factory=list)  # API calls/minute history
    

class PerformanceMonitor:
    """
    Tracks performance metrics and calculates ETA
    
    Features:
    - ROM processing rate tracking
    - API call and download counting
    - Memory and CPU monitoring
    - ETA calculation
    - Periodic snapshots
    
    Example:
        monitor = PerformanceMonitor(total_roms=100)
        
        # Record progress
        monitor.record_rom_processed()
        monitor.record_api_call()
        monitor.record_download()
        
        # Get current metrics
        metrics = monitor.get_metrics()
        print(f"Progress: {metrics.percent_complete:.1f}%")
        print(f"ETA: {metrics.eta_seconds / 60:.1f} minutes")
    """
    
    def __init__(self, total_roms: int):
        """
        Initialize performance monitor
        
        Args:
            total_roms: Total number of ROMs to process
        """
        self.total_roms = total_roms
        self.start_time = time.time()
        
        # Counters
        self.roms_processed = 0
        self.api_calls = 0
        self.downloads = 0
        
        # Process handle for resource monitoring
        self.process = psutil.Process()
        
        # Rolling averages with outlier exclusion
        self.api_times: Deque[float] = deque(maxlen=50)  # Last 50 API call durations
        self.rom_times: Deque[float] = deque(maxlen=50)  # Last 50 total ROM processing times
        
        # Time-series history for sparklines (40 samples = 10 seconds at 0.25s refresh)
        self.throughput_history: Deque[float] = deque(maxlen=40)
        self.api_rate_history: Deque[float] = deque(maxlen=40)
        
        # ETA caching to avoid jitter
        self.eta_cache: Optional[float] = None
        self.eta_last_calculated_at: int = 0  # ROM count when ETA was last calculated
        self.eta_recalc_interval: int = 10  # Recalculate ETA every N ROMs
    
    def record_rom_processed(self) -> None:
        """Record a ROM as processed"""
        self.roms_processed += 1
    
    def record_api_call(self, duration: Optional[float] = None) -> None:
        """
        Record an API call
        
        Args:
            duration: Optional API call duration in seconds for averaging
        """
        self.api_calls += 1
        if duration is not None and duration > 0:
            self.api_times.append(duration)
            logger.debug(f"Recorded API call duration: {duration:.3f}s ({len(self.api_times)} samples)")
    
    def record_rom_processing(self, duration: Optional[float] = None) -> None:
        """
        Record a complete ROM processing operation
        
        Args:
            duration: Optional total ROM processing time in seconds for averaging
        """
        self.roms_processed += 1
        if duration is not None and duration > 0:
            self.rom_times.append(duration)
            logger.debug(f"Recorded ROM processing duration: {duration:.3f}s ({len(self.rom_times)} samples)")
    
    def record_download(self) -> None:
        """Record a media download"""
        self.downloads += 1
    
    def _calculate_average_with_outlier_exclusion(self, values: Deque[float]) -> float:
        """
        Calculate average excluding top and bottom 10% outliers
        
        Args:
            values: Deque of timing values
            
        Returns:
            Average of middle 80%, or 0.0 if insufficient data
        """
        if len(values) < 5:  # Need at least 5 samples for meaningful outlier exclusion
            return sum(values) / len(values) if values else 0.0
        
        # Sort values to identify outliers
        sorted_values = sorted(values)
        
        # Calculate how many to exclude from each end (10%)
        exclude_count = max(1, len(sorted_values) // 10)
        
        # Take middle 80%
        middle_values = sorted_values[exclude_count:-exclude_count]
        
        return sum(middle_values) / len(middle_values) if middle_values else 0.0
    
    def get_metrics(self) -> PerformanceMetrics:
        """
        Get current performance metrics
        
        Returns:
            PerformanceMetrics snapshot
        """
        now = time.time()
        elapsed = now - self.start_time
        
        # Calculate rates (avoid division by zero)
        roms_per_sec = self.roms_processed / elapsed if elapsed > 0 else 0.0
        api_per_sec = self.api_calls / elapsed if elapsed > 0 else 0.0
        downloads_per_sec = self.downloads / elapsed if elapsed > 0 else 0.0
        
        # Convert to display units
        roms_per_hour = roms_per_sec * 3600  # ROMs per hour
        api_per_minute = api_per_sec * 60  # API calls per minute
        
        # Calculate completion
        percent = (
            (self.roms_processed / self.total_roms * 100)
            if self.total_roms > 0
            else 0.0
        )
        
        # Calculate rolling averages with outlier exclusion
        avg_api_time = self._calculate_average_with_outlier_exclusion(self.api_times)
        avg_rom_time = self._calculate_average_with_outlier_exclusion(self.rom_times)
        
        # Append current rates to history for sparkline visualization
        self.throughput_history.append(roms_per_hour)
        self.api_rate_history.append(api_per_minute)
        
        # Calculate ETA with caching to reduce jitter
        remaining_roms = self.total_roms - self.roms_processed
        
        # Recalculate ETA every N ROMs
        if (
            self.eta_cache is None
            or self.roms_processed - self.eta_last_calculated_at >= self.eta_recalc_interval
        ):
            if avg_rom_time > 0 and remaining_roms > 0:
                self.eta_cache = remaining_roms * avg_rom_time
            elif roms_per_sec > 0 and remaining_roms > 0:
                # Fallback to simple rate-based calculation if no timing samples
                self.eta_cache = remaining_roms / roms_per_sec
            else:
                self.eta_cache = 0.0
            
            self.eta_last_calculated_at = self.roms_processed
        
        eta = self.eta_cache if self.eta_cache is not None else 0.0
        
        # Get resource usage
        memory_mb = self.process.memory_info().rss / 1024 / 1024
        cpu_percent = self.process.cpu_percent(interval=0.1)
        
        return PerformanceMetrics(
            elapsed_seconds=elapsed,
            estimated_total_seconds=elapsed + eta,
            roms_per_hour=roms_per_hour,
            api_calls_per_minute=api_per_minute,
            downloads_per_second=downloads_per_sec,
            roms_processed=self.roms_processed,
            roms_total=self.total_roms,
            api_calls=self.api_calls,
            downloads=self.downloads,
            memory_mb=memory_mb,
            cpu_percent=cpu_percent,
            percent_complete=percent,
            eta_seconds=eta,
            avg_api_time=avg_api_time,
            avg_rom_time=avg_rom_time,
            throughput_history=list(self.throughput_history),
            api_rate_history=list(self.api_rate_history)
        )
    
    def log_metrics(self) -> None:
        """Log current metrics at INFO level"""
        metrics = self.get_metrics()
        
        logger.info(
            f"Performance: {metrics.roms_processed}/{metrics.roms_total} ROMs "
            f"({metrics.percent_complete:.1f}%) | "
            f"{metrics.roms_per_hour:.1f} ROMs/hr | "
            f"ETA: {metrics.eta_seconds / 60:.1f} min"
        )
        
        logger.debug(
            f"Resources: {metrics.memory_mb:.1f} MB memory, "
            f"{metrics.cpu_percent:.1f}% CPU | "
            f"API: {metrics.api_calls} calls ({metrics.api_calls_per_minute:.1f}/min) | "
            f"Downloads: {metrics.downloads} ({metrics.downloads_per_second:.2f}/s)"
        )
    
    def get_summary(self) -> dict:
        """
        Get summary for final report
        
        Returns:
            dict with key performance statistics
        """
        metrics = self.get_metrics()
        
        return {
            'total_roms': self.total_roms,
            'roms_processed': self.roms_processed,
            'elapsed_seconds': metrics.elapsed_seconds,
            'avg_roms_per_second': metrics.roms_per_second,
            'total_api_calls': self.api_calls,
            'total_downloads': self.downloads,
            'peak_memory_mb': metrics.memory_mb,
            'avg_cpu_percent': metrics.cpu_percent
        }
