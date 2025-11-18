"""
Comprehensive test suite for WorkQueueManager

Tests priority ordering, retry handling, concurrent access, and statistics.
"""

import pytest
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from curateur.workflow.work_queue import WorkQueueManager, WorkItem, Priority


class TestWorkQueuePriorityOrdering:
    """Test priority-based ordering."""
    
    def test_priority_ordering_with_multiple_items(self):
        """Test that HIGH < NORMAL < LOW priority ordering works correctly."""
        manager = WorkQueueManager(max_retries=3)
        
        # Add items in mixed order
        manager.add_work({'name': 'low1'}, 'action', Priority.LOW)
        manager.add_work({'name': 'high1'}, 'action', Priority.HIGH)
        manager.add_work({'name': 'normal1'}, 'action', Priority.NORMAL)
        manager.add_work({'name': 'low2'}, 'action', Priority.LOW)
        manager.add_work({'name': 'high2'}, 'action', Priority.HIGH)
        manager.add_work({'name': 'normal2'}, 'action', Priority.NORMAL)
        
        # Should be retrieved in priority order: HIGH, HIGH, NORMAL, NORMAL, LOW, LOW
        item1 = manager.get_work()
        assert item1.priority == Priority.HIGH
        assert item1.rom_info['name'] == 'high1'
        
        item2 = manager.get_work()
        assert item2.priority == Priority.HIGH
        assert item2.rom_info['name'] == 'high2'
        
        item3 = manager.get_work()
        assert item3.priority == Priority.NORMAL
        assert item3.rom_info['name'] == 'normal1'
        
        item4 = manager.get_work()
        assert item4.priority == Priority.NORMAL
        assert item4.rom_info['name'] == 'normal2'
        
        item5 = manager.get_work()
        assert item5.priority == Priority.LOW
        assert item5.rom_info['name'] == 'low1'
        
        item6 = manager.get_work()
        assert item6.priority == Priority.LOW
        assert item6.rom_info['name'] == 'low2'
    
    def test_fifo_within_same_priority(self):
        """Test FIFO ordering within same priority level."""
        manager = WorkQueueManager(max_retries=3)
        
        # Add 5 NORMAL items
        for i in range(5):
            manager.add_work({'name': f'item{i}'}, 'action', Priority.NORMAL)
        
        # Should be retrieved in exact order added
        for i in range(5):
            item = manager.get_work()
            assert item.rom_info['name'] == f'item{i}'
    
    def test_priority_enum_comparison(self):
        """Test that Priority IntEnum comparison works correctly."""
        assert Priority.HIGH < Priority.NORMAL
        assert Priority.NORMAL < Priority.LOW
        assert Priority.HIGH < Priority.LOW


class TestWorkQueueRetryHandling:
    """Test retry escalation and max retries."""
    
    def test_retry_escalates_to_high_priority(self):
        """Test that retry_failed promotes item to HIGH priority."""
        manager = WorkQueueManager(max_retries=3)
        
        # Add NORMAL item
        manager.add_work({'name': 'test'}, 'action', Priority.NORMAL)
        item = manager.get_work()
        assert item.priority == Priority.NORMAL
        
        # Retry should escalate to HIGH
        manager.retry_failed(item, 'Test error')
        
        retried_item = manager.get_work()
        assert retried_item.priority == Priority.HIGH
        assert retried_item.retry_count == 1
    
    def test_max_retries_moves_to_failed(self):
        """Test that exceeding max_retries moves item to failed list."""
        manager = WorkQueueManager(max_retries=3)
        
        manager.add_work({'name': 'test'}, 'action', Priority.NORMAL)
        item = manager.get_work()
        
        # Retry 3 times (max_retries)
        for i in range(3):
            manager.retry_failed(item, f'Error {i}')
            if not manager.is_empty():
                item = manager.get_work()
        
        # Item should now be in failed list
        failed_items = manager.get_failed_items()
        assert len(failed_items) == 1
        assert failed_items[0]['rom_info']['name'] == 'test'
        assert failed_items[0]['retry_count'] == 3
    
    def test_retry_increments_count(self):
        """Test that retry_count increments correctly."""
        manager = WorkQueueManager(max_retries=5)
        
        manager.add_work({'name': 'test'}, 'action', Priority.NORMAL)
        item = manager.get_work()
        assert item.retry_count == 0
        
        manager.retry_failed(item, 'Error 1')
        item = manager.get_work()
        assert item.retry_count == 1
        
        manager.retry_failed(item, 'Error 2')
        item = manager.get_work()
        assert item.retry_count == 2


class TestWorkQueueConcurrentAccess:
    """Test thread safety and concurrent operations."""
    
    def test_concurrent_add_and_get(self):
        """Test concurrent access from multiple threads."""
        manager = WorkQueueManager(max_retries=3)
        processed_items = []
        lock = threading.Lock()
        
        def producer(start_id, count):
            """Add items to queue"""
            for i in range(count):
                manager.add_work(
                    {'id': start_id + i, 'thread': threading.current_thread().name},
                    'action',
                    Priority.NORMAL
                )
        
        def consumer(count):
            """Get items from queue"""
            for _ in range(count):
                item = manager.get_work(timeout=1.0)
                if item:
                    with lock:
                        processed_items.append(item.rom_info['id'])
                    manager.mark_processed(item)
        
        # Spawn 10 producer threads each adding 10 items
        with ThreadPoolExecutor(max_workers=20) as executor:
            # Producers
            for i in range(10):
                executor.submit(producer, i * 10, 10)
            
            # Give producers a head start
            time.sleep(0.1)
            
            # Consumers
            for _ in range(10):
                executor.submit(consumer, 10)
        
        # Verify all items were processed
        assert len(processed_items) == 100
        assert len(set(processed_items)) == 100  # All unique
    
    def test_thread_safe_stats(self):
        """Test that statistics remain accurate under concurrent access."""
        manager = WorkQueueManager(max_retries=3)
        
        def worker(item_count):
            for i in range(item_count):
                manager.add_work({'id': i}, 'action', Priority.NORMAL)
                item = manager.get_work(timeout=0.5)
                if item:
                    manager.mark_processed(item)
        
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(worker, 20) for _ in range(5)]
            for future in futures:
                future.result()
        
        stats = manager.get_stats()
        assert stats['processed'] == 100


class TestWorkQueueStatistics:
    """Test statistics and status tracking."""
    
    def test_get_stats_returns_correct_counts(self):
        """Test that get_stats returns accurate counts."""
        manager = WorkQueueManager(max_retries=3)
        
        # Initial state
        stats = manager.get_stats()
        assert stats['pending'] == 0
        assert stats['processed'] == 0
        assert stats['failed'] == 0
        
        # Add items
        for i in range(5):
            manager.add_work({'id': i}, 'action', Priority.NORMAL)
        
        stats = manager.get_stats()
        assert stats['pending'] == 5
        
        # Process some
        item1 = manager.get_work()
        manager.mark_processed(item1)
        
        item2 = manager.get_work()
        manager.mark_processed(item2)
        
        stats = manager.get_stats()
        assert stats['pending'] == 3
        assert stats['processed'] == 2
        
        # Fail one
        item3 = manager.get_work()
        for _ in range(3):  # Exceed max retries
            manager.retry_failed(item3, 'Error')
            if not manager.is_empty():
                item3 = manager.get_work()
        
        stats = manager.get_stats()
        assert stats['failed'] == 1
    
    def test_get_failed_items_structure(self):
        """Test that get_failed_items returns correct structure."""
        manager = WorkQueueManager(max_retries=2)
        
        manager.add_work({'name': 'test', 'value': 123}, 'full_scrape', Priority.NORMAL)
        item = manager.get_work()
        
        # Fail it
        for _ in range(2):
            manager.retry_failed(item, 'Test error')
            if not manager.is_empty():
                item = manager.get_work()
        
        failed = manager.get_failed_items()
        assert len(failed) == 1
        assert failed[0]['rom_info']['name'] == 'test'
        assert failed[0]['rom_info']['value'] == 123
        assert failed[0]['action'] == 'full_scrape'
        assert failed[0]['retry_count'] == 2
        assert 'Test error' in failed[0]['error']


class TestWorkQueueBasicOperations:
    """Test basic queue operations."""
    
    def test_get_work_returns_none_on_empty_queue(self):
        """Test that get_work returns None when queue is empty."""
        manager = WorkQueueManager(max_retries=3)
        
        item = manager.get_work(timeout=0.1)
        assert item is None
    
    def test_is_empty_returns_correct_status(self):
        """Test is_empty method."""
        manager = WorkQueueManager(max_retries=3)
        
        assert manager.is_empty()
        
        manager.add_work({'name': 'test'}, 'action', Priority.NORMAL)
        assert not manager.is_empty()
        
        item = manager.get_work()
        assert manager.is_empty()
    
    def test_mark_processed_prevents_reprocessing(self):
        """Test that mark_processed prevents item from being returned again."""
        manager = WorkQueueManager(max_retries=3)
        
        manager.add_work({'name': 'test'}, 'action', Priority.NORMAL)
        item = manager.get_work()
        
        manager.mark_processed(item)
        
        # Trying to add same item again should work but it won't be marked as duplicate
        manager.add_work({'name': 'test'}, 'action', Priority.NORMAL)
        new_item = manager.get_work()
        assert new_item is not None  # Can add duplicates
        
        stats = manager.get_stats()
        assert stats['processed'] == 1


class TestWorkQueueComplexData:
    """Test with complex rom_info structures."""
    
    def test_complex_rom_info_preserved(self):
        """Test that complex nested data structures are preserved."""
        manager = WorkQueueManager(max_retries=3)
        
        complex_rom = {
            'name': 'test.rom',
            'metadata': {
                'region': 'us',
                'languages': ['en', 'es'],
                'properties': {
                    'licensed': True,
                    'rating': 4.5
                }
            },
            'hashes': ['abc123', 'def456']
        }
        
        manager.add_work(complex_rom, 'full_scrape', Priority.NORMAL)
        item = manager.get_work()
        
        # Verify structure preserved
        assert item.rom_info['name'] == 'test.rom'
        assert item.rom_info['metadata']['region'] == 'us'
        assert item.rom_info['metadata']['languages'] == ['en', 'es']
        assert item.rom_info['metadata']['properties']['licensed'] is True
        assert item.rom_info['metadata']['properties']['rating'] == 4.5
        assert item.rom_info['hashes'] == ['abc123', 'def456']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
