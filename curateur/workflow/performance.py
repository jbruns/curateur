"""
Performance monitoring and metrics tracking

Tracks scraping performance and calculates ETA.
"""

import logging
import time
import psutil
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """Performance metrics snapshot"""
    # Timing
    elapsed_seconds: float = 0.0
    estimated_total_seconds: float = 0.0
    
    # Throughput
    roms_per_second: float = 0.0
    api_calls_per_second: float = 0.0
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
    
    def record_rom_processed(self) -> None:
        """Record a ROM as processed"""
        self.roms_processed += 1
    
    def record_api_call(self) -> None:
        """Record an API call"""
        self.api_calls += 1
    
    def record_download(self) -> None:
        """Record a media download"""
        self.downloads += 1
    
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
        
        # Calculate completion
        percent = (
            (self.roms_processed / self.total_roms * 100)
            if self.total_roms > 0
            else 0.0
        )
        
        # Calculate ETA
        remaining_roms = self.total_roms - self.roms_processed
        eta = (
            remaining_roms / roms_per_sec
            if roms_per_sec > 0 and remaining_roms > 0
            else 0.0
        )
        
        # Get resource usage
        memory_mb = self.process.memory_info().rss / 1024 / 1024
        cpu_percent = self.process.cpu_percent(interval=0.1)
        
        return PerformanceMetrics(
            elapsed_seconds=elapsed,
            estimated_total_seconds=elapsed + eta,
            roms_per_second=roms_per_sec,
            api_calls_per_second=api_per_sec,
            downloads_per_second=downloads_per_sec,
            roms_processed=self.roms_processed,
            roms_total=self.total_roms,
            api_calls=self.api_calls,
            downloads=self.downloads,
            memory_mb=memory_mb,
            cpu_percent=cpu_percent,
            percent_complete=percent,
            eta_seconds=eta
        )
    
    def log_metrics(self) -> None:
        """Log current metrics at INFO level"""
        metrics = self.get_metrics()
        
        logger.info(
            f"Performance: {metrics.roms_processed}/{metrics.roms_total} ROMs "
            f"({metrics.percent_complete:.1f}%) | "
            f"{metrics.roms_per_second:.2f} ROMs/s | "
            f"ETA: {metrics.eta_seconds / 60:.1f} min"
        )
        
        logger.debug(
            f"Resources: {metrics.memory_mb:.1f} MB memory, "
            f"{metrics.cpu_percent:.1f}% CPU | "
            f"API: {metrics.api_calls} calls ({metrics.api_calls_per_second:.2f}/s) | "
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
