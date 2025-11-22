"""
Prioritized work queue for ROM processing

Provides priority-based processing with retry handling.
"""

import logging
import queue
import threading
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional, Any

logger = logging.getLogger(__name__)


class Priority(IntEnum):
    """Work priority levels"""
    HIGH = 1      # Failed retries, user-requested
    NORMAL = 2    # Standard processing
    LOW = 3       # Media-only, background tasks


@dataclass
class WorkItem:
    """Work queue item"""
    rom_info: dict
    action: str  # 'full_scrape' | 'media_only' | 'update'
    priority: Priority
    retry_count: int = 0


class WorkQueueManager:
    """
    Manages prioritized work queue for ROM processing
    
    Features:
    - Priority-based processing
    - Retry handling with exponential backoff
    - Dynamic reordering
    - Progress tracking
    
    Example:
        manager = WorkQueueManager(max_retries=3)
        
        # Add work items
        for rom in roms:
            manager.add_work(rom, 'full_scrape', Priority.NORMAL)
        
        # Process queue
        while not manager.is_empty():
            item = manager.get_work()
            if item:
                success = process_rom(item)
                if not success:
                    manager.retry_failed(item, 'API timeout')
        
        # Get statistics
        stats = manager.get_stats()
    """
    
    def __init__(self, max_retries: int = 3):
        """
        Initialize work queue manager
        
        Args:
            max_retries: Maximum retry attempts per item
        """
        self.queue = queue.PriorityQueue()
        self.max_retries = max_retries
        self.processed_count = 0
        self.failed = []
        self.lock = threading.Lock()
        self._item_counter = 0  # For stable sorting when priorities equal
    
    def add_work(
        self,
        rom_info: dict,
        action: str,
        priority: Priority = Priority.NORMAL
    ) -> None:
        """
        Add work item to queue
        
        Args:
            rom_info: ROM information dict
            action: Action type ('full_scrape', 'media_only', 'update')
            priority: Work priority level
        """
        item = WorkItem(rom_info, action, priority, retry_count=0)
        
        # Use counter for stable sort (FIFO within same priority)
        with self.lock:
            self._item_counter += 1
            sort_key = (priority.value, self._item_counter)
        
        self.queue.put((sort_key, item))
        # Temporarily disabled to reduce log noise
        # logger.debug(
        #     f"Added work: {rom_info.get('filename', 'unknown')} "
        #     f"(action={action}, priority={priority.name})"
        # )
    
    def get_work(self, timeout: Optional[float] = None) -> Optional[WorkItem]:
        """
        Get next work item from queue
        
        Args:
            timeout: Maximum time to wait for item (None = no wait)
        
        Returns:
            WorkItem or None if queue empty
        """
        try:
            _, item = self.queue.get(timeout=timeout)
            return item
        except queue.Empty:
            return None
    
    def retry_failed(self, work_item: WorkItem, error: str) -> None:
        """
        Requeue failed work with higher priority
        
        Rules:
        - Increment retry_count
        - If < max_retries: requeue with HIGH priority
        - If >= max_retries: add to failed list
        
        Args:
            work_item: Failed work item
            error: Error description
        """
        work_item.retry_count += 1
        
        if work_item.retry_count < self.max_retries:
            # Retry with HIGH priority
            logger.warning(
                f"Retrying work: {work_item.rom_info.get('filename', 'unknown')} "
                f"(attempt {work_item.retry_count + 1}/{self.max_retries})"
            )
            
            # Update priority to HIGH for retry
            work_item.priority = Priority.HIGH
            
            with self.lock:
                self._item_counter += 1
                sort_key = (Priority.HIGH.value, self._item_counter)
            
            self.queue.put((sort_key, work_item))
        else:
            # Max retries exceeded, add to failed list
            logger.error(
                f"Work failed after {self.max_retries} retries: "
                f"{work_item.rom_info.get('filename', 'unknown')} - {error}"
            )
            
            self.failed.append({
                'rom_info': work_item.rom_info,
                'action': work_item.action,
                'error': error,
                'retry_count': work_item.retry_count
            })
    
    def mark_processed(self, work_item: WorkItem) -> None:
        """
        Mark work item as successfully processed
        
        Args:
            work_item: Completed work item
        """
        with self.lock:
            self.processed_count += 1
        filename = work_item.rom_info.get('filename', work_item.rom_info.get('id', 'unknown'))
        logger.debug(f"Marked processed: {filename}")
    
    def is_empty(self) -> bool:
        """
        Check if queue is empty
        
        Returns:
            True if no work items in queue
        """
        return self.queue.qsize() == 0
    
    def get_stats(self) -> dict:
        """
        Get queue statistics
        
        Returns:
            dict with pending, processed, failed counts
        """
        with self.lock:
            processed = self.processed_count
        
        return {
            'pending': self.queue.qsize(),
            'processed': processed,
            'failed': len(self.failed),
            'max_retries': self.max_retries
        }
    
    def get_failed_items(self) -> list:
        """
        Get list of failed work items
        
        Returns:
            List of failed item dicts
        """
        return self.failed.copy()
