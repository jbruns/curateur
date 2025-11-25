"""
Prioritized work queue for ROM processing

Provides priority-based processing with retry handling using asyncio.
"""

import asyncio
import logging
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
    Manages prioritized work queue for ROM processing using asyncio.Queue
    
    Features:
    - Priority-based processing
    - Retry handling with exponential backoff
    - Dynamic reordering
    - Progress tracking
    - System completion tracking for clean task shutdown
    
    Example:
        manager = WorkQueueManager(max_retries=3)
        
        # Add work items (synchronous)
        for rom in roms:
            manager.add_work(rom, 'full_scrape', Priority.NORMAL)
        
        # Process queue (async)
        while not manager.is_system_complete():
            item = await manager.get_work_async()
            if item:
                success = await process_rom(item)
                if not success:
                    manager.retry_failed(item, 'API timeout')
        
        # Mark system complete before moving to next
        manager.mark_system_complete()
        
        # Get statistics
        stats = manager.get_stats()
    """
    
    def __init__(self, max_retries: int = 3):
        """
        Initialize work queue manager
        
        Args:
            max_retries: Maximum retry attempts per item
        """
        self.queue = asyncio.PriorityQueue()
        self.max_retries = max_retries
        self.processed_count = 0
        self.failed = []
        self._lock = asyncio.Lock()
        self._item_counter = 0  # For stable sorting when priorities equal
        self._system_complete = False  # Flag to signal tasks that system is done
    
    def add_work(
        self,
        rom_info: dict,
        action: str,
        priority: Priority = Priority.NORMAL
    ) -> None:
        """
        Add work item to queue (synchronous for scanner compatibility)
        
        Args:
            rom_info: ROM information dict
            action: Action type ('full_scrape', 'media_only', 'update')
            priority: Work priority level
        """
        item = WorkItem(rom_info, action, priority, retry_count=0)
        
        # Use counter for stable sort (FIFO within same priority)
        # Note: We can't use async lock here since this is sync method
        # asyncio.PriorityQueue is thread-safe for put_nowait()
        self._item_counter += 1
        sort_key = (priority.value, self._item_counter)
        
        self.queue.put_nowait((sort_key, item))
        # Temporarily disabled to reduce log noise
        # logger.debug(
        #     f"Added work: {rom_info.get('filename', 'unknown')} "
        #     f"(action={action}, priority={priority.name})"
        # )
    
    async def get_work_async(self) -> Optional[WorkItem]:
        """
        Get next ROM from queue (blocking if empty).
        
        Pipeline tasks should use this method to continuously pull work.
        
        Returns:
            ROMInfo or None if system complete and queue empty
        """
        # If system marked complete and queue empty, return None to signal task exit
        if self._system_complete and self.queue.empty():
            return None
        
        try:
            # Wait for work item (blocks until available)
            _, item = await self.queue.get()
            return item
        except asyncio.CancelledError:
            # Graceful cancellation
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
            
            self._item_counter += 1
            sort_key = (Priority.HIGH.value, self._item_counter)
            
            self.queue.put_nowait((sort_key, work_item))
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
    
    async def mark_processed(self, work_item: WorkItem) -> None:
        """
        Mark work item as successfully processed
        
        Args:
            work_item: Completed work item
        """
        async with self._lock:
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
    
    def mark_system_complete(self) -> None:
        """
        Mark current system as complete
        
        Signals to tasks that no more work will be added for this system.
        Tasks will exit after draining the queue.
        """
        self._system_complete = True
        logger.debug("System marked as complete - pipeline tasks will exit after queue drains")
    
    def is_system_complete(self) -> bool:
        """
        Check if system is marked complete
        
        Returns:
            True if system is complete
        """
        return self._system_complete
    
    async def drain(self, timeout: float = 300.0) -> None:
        """
        Wait for queue to be empty (async)
        
        Use this to wait for all work to be consumed before moving to next system.
        
        Args:
            timeout: Maximum time to wait in seconds (default 5 minutes)
        """
        import time
        start_time = time.time()
        while not self.queue.empty():
            if time.time() - start_time > timeout:
                # Only log warning for substantial timeouts (> 5 seconds)
                # Short timeouts are used for periodic polling and shouldn't warn
                if timeout > 5.0:
                    logger.warning(f"Queue drain timed out after {timeout}s with {self.queue.qsize()} items remaining")
                break
            await asyncio.sleep(0.1)
        else:
            logger.debug("Queue drained - all work consumed")
    
    def reset_for_new_system(self) -> None:
        """
        Reset queue state for a new system
        
        Call this before populating queue with a new system's ROMs.
        """
        self._system_complete = False
        self.processed_count = 0
        self.failed = []
        # Note: queue should already be empty from drain(), but clear just in case
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        logger.debug("Queue reset for new system")
    
    def get_stats(self) -> dict:
        """
        Get queue statistics
        
        Returns:
            dict with pending, processed, failed counts
        """
        return {
            'pending': self.queue.qsize(),
            'processed': self.processed_count,
            'failed': len(self.failed),
            'max_retries': self.max_retries,
            'system_complete': self._system_complete
        }
    
    def get_failed_items(self) -> list:
        """
        Get list of failed work items
        
        Returns:
            List of failed item dicts
        """
        return self.failed.copy()
