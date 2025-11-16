"""
Milestone 2 Phase D: Performance & Parallelism - Acceptance Tests

Tests all Phase D deliverables:
1. ThreadPoolManager - Parallel execution
2. ConnectionPoolManager - Connection pooling
3. WorkQueueManager - Priority queue
4. ThrottleManager - Rate limiting
5. PerformanceMonitor - Metrics tracking
"""

import pytest
import time
import threading
from concurrent.futures import Future
from unittest.mock import Mock, patch, MagicMock
import requests

from curateur.workflow.thread_pool import ThreadPoolManager
from curateur.api.connection_pool import ConnectionPoolManager
from curateur.workflow.work_queue import WorkQueueManager, Priority, WorkItem
from curateur.api.throttle import ThrottleManager, RateLimit
from curateur.workflow.performance import PerformanceMonitor, PerformanceMetrics


# ============================================================================
# ThreadPoolManager Tests
# ============================================================================

class TestThreadPoolManager:
    """Tests for ThreadPoolManager"""
    
    def test_initialize_pools_creates_separate_pools(self):
        """Should create separate API and download pools"""
        config = {}
        manager = ThreadPoolManager(config)
        
        api_limits = {'maxthreads': 8, 'maxdownloadthreads': 8}
        manager.initialize_pools(api_limits)
        
        assert manager.api_pool is not None
        assert manager.download_pool is not None
        assert manager.max_threads == 8
    
    def test_initialize_pools_handles_low_thread_count(self):
        """Should gracefully handle low thread counts"""
        config = {}
        manager = ThreadPoolManager(config)
        
        api_limits = {'maxthreads': 1, 'maxdownloadthreads': 1}
        manager.initialize_pools(api_limits)
        
        assert manager.max_threads == 1
        assert manager.api_pool is not None
        assert manager.download_pool is not None
    
    def test_submit_api_batch_processes_in_parallel(self):
        """Should process API batch in parallel"""
        config = {}
        manager = ThreadPoolManager(config)
        api_limits = {'maxthreads': 4, 'maxdownloadthreads': 4}
        manager.initialize_pools(api_limits)
        
        def mock_api_func(rom):
            time.sleep(0.1)
            return {'filename': rom['filename'], 'metadata': {'title': 'Test'}}
        
        roms = [{'filename': f'rom{i}.nes'} for i in range(3)]
        
        results = list(manager.submit_api_batch(mock_api_func, roms))
        
        assert len(results) == 3
        assert all(isinstance(r, tuple) for r in results)
        assert all(r[1].get('metadata') for r in results)
        
        manager.shutdown()
    
    def test_submit_api_batch_handles_errors(self):
        """Should catch and return errors per item"""
        config = {}
        manager = ThreadPoolManager(config)
        api_limits = {'maxthreads': 4, 'maxdownloadthreads': 4}
        manager.initialize_pools(api_limits)
        
        def failing_func(rom):
            if 'fail' in rom['filename']:
                raise ValueError("API error")
            return {'filename': rom['filename'], 'success': True}
        
        roms = [
            {'filename': 'rom1.nes'},
            {'filename': 'fail.nes'},
            {'filename': 'rom2.nes'}
        ]
        
        results = list(manager.submit_api_batch(failing_func, roms))
        
        assert len(results) == 3
        
        # Check error result
        error_result = next(r for r in results if r[0]['filename'] == 'fail.nes')
        assert 'error' in error_result[1]
    
    def test_submit_download_batch_processes_downloads(self):
        """Should process download batch"""
        config = {}
        manager = ThreadPoolManager(config)
        api_limits = {'maxthreads': 4, 'maxdownloadthreads': 4}
        manager.initialize_pools(api_limits)
        
        def mock_download_func(media):
            return {'url': media['url'], 'path': f"/tmp/{media['type']}.png"}
        
        media_list = [
            {'url': 'http://example.com/box.png', 'type': 'box-2D'},
            {'url': 'http://example.com/screen.png', 'type': 'screenshot'}
        ]
        
        results = list(manager.submit_download_batch(mock_download_func, media_list))
        
        assert len(results) == 2
        assert all(r[1].get('path') for r in results)
        
        manager.shutdown()
    
    def test_shutdown_waits_for_completion(self):
        """Should wait for all tasks to complete on shutdown"""
        config = {}
        manager = ThreadPoolManager(config)
        api_limits = {'maxthreads': 4, 'maxdownloadthreads': 4}
        manager.initialize_pools(api_limits)
        
        completed = []
        
        def slow_func(rom):
            time.sleep(0.2)
            completed.append(rom['filename'])
            return {'filename': rom['filename']}
        
        roms = [{'filename': f'rom{i}.nes'} for i in range(2)]
        
        # Submit and consume results
        results = list(manager.submit_api_batch(slow_func, roms))
        
        # All should have completed
        assert len(completed) == 2
        assert len(results) == 2
        
        manager.shutdown(wait=True)


# ============================================================================
# ConnectionPoolManager Tests
# ============================================================================

class TestConnectionPoolManager:
    """Tests for ConnectionPoolManager"""
    
    def test_create_session_configures_retry(self):
        """Should configure session with retry strategy"""
        config = {'api': {'request_timeout': 30}}
        manager = ConnectionPoolManager(config)
        session = manager.create_session(max_connections=10)
        
        adapter = session.get_adapter('http://')
        assert adapter.max_retries.total == 3
        assert 429 in adapter.max_retries.status_forcelist
        assert 503 in adapter.max_retries.status_forcelist
    
    def test_create_session_configures_connection_pool(self):
        """Should configure connection pooling"""
        config = {'api': {'request_timeout': 30}}
        manager = ConnectionPoolManager(config)
        session = manager.create_session(max_connections=5)
        
        adapter = session.get_adapter('http://')
        # Check pool configuration
        assert adapter._pool_connections == 5
        assert adapter._pool_maxsize == 10  # 2x connections
    
    def test_get_session_returns_current_session(self):
        """Should return current session"""
        config = {'api': {'request_timeout': 30}}
        manager = ConnectionPoolManager(config)
        session1 = manager.get_session()
        session2 = manager.get_session()
        
        assert session1 is session2
    
    def test_get_session_thread_safe(self):
        """Should be thread-safe for concurrent access"""
        config = {'api': {'request_timeout': 30}}
        manager = ConnectionPoolManager(config)
        manager.create_session()
        
        sessions = []
        
        def get_session():
            sessions.append(manager.get_session())
        
        threads = [threading.Thread(target=get_session) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        # All should get same session
        assert len(set(id(s) for s in sessions)) == 1
    
    def test_close_session_releases_connections(self):
        """Should close and release session"""
        config = {'api': {'request_timeout': 30}}
        manager = ConnectionPoolManager(config)
        manager.create_session()
        
        manager.close_session()
        
        assert manager.session is None


# ============================================================================
# WorkQueueManager Tests
# ============================================================================

class TestWorkQueueManager:
    """Tests for WorkQueueManager"""
    
    def test_add_work_queues_item(self):
        """Should add work item to queue"""
        manager = WorkQueueManager(max_retries=3)
        
        rom = {'filename': 'test.nes', 'path': '/roms/test.nes'}
        manager.add_work(rom, 'full_scrape', Priority.NORMAL)
        
        assert not manager.is_empty()
    
    def test_get_work_returns_highest_priority(self):
        """Should return highest priority item first"""
        manager = WorkQueueManager(max_retries=3)
        
        # Add in reverse priority order
        manager.add_work({'filename': 'low.nes'}, 'full_scrape', Priority.LOW)
        manager.add_work({'filename': 'high.nes'}, 'full_scrape', Priority.HIGH)
        manager.add_work({'filename': 'normal.nes'}, 'full_scrape', Priority.NORMAL)
        
        item1 = manager.get_work()
        assert item1.priority == Priority.HIGH
        assert item1.rom_info['filename'] == 'high.nes'
        
        item2 = manager.get_work()
        assert item2.priority == Priority.NORMAL
        
        item3 = manager.get_work()
        assert item3.priority == Priority.LOW
    
    def test_get_work_returns_none_when_empty(self):
        """Should return None when queue is empty"""
        manager = WorkQueueManager(max_retries=3)
        
        item = manager.get_work(timeout=0.1)
        
        assert item is None
    
    def test_retry_failed_requeues_with_high_priority(self):
        """Should requeue failed item with HIGH priority"""
        manager = WorkQueueManager(max_retries=3)
        
        rom = {'filename': 'test.nes'}
        work_item = WorkItem(rom, 'full_scrape', Priority.NORMAL, retry_count=0)
        
        manager.retry_failed(work_item, 'API timeout')
        
        # Should be requeued with HIGH priority
        requeued = manager.get_work()
        assert requeued.priority == Priority.HIGH
        assert requeued.retry_count == 1
    
    def test_retry_failed_moves_to_failed_list_after_max_retries(self):
        """Should move to failed list after max retries"""
        manager = WorkQueueManager(max_retries=2)
        
        rom = {'filename': 'test.nes'}
        work_item = WorkItem(rom, 'full_scrape', Priority.NORMAL, retry_count=0)
        
        # First retry
        manager.retry_failed(work_item, 'Error 1')
        assert len(manager.failed) == 0
        
        # Get and retry again
        work_item = manager.get_work()
        manager.retry_failed(work_item, 'Error 2')
        
        # Should be in failed list now
        assert len(manager.failed) == 1
        assert manager.failed[0]['rom_info']['filename'] == 'test.nes'
    
    def test_mark_processed_tracks_completed_items(self):
        """Should track processed items"""
        manager = WorkQueueManager(max_retries=3)
        
        rom = {'filename': 'test.nes'}
        work_item = WorkItem(rom, 'full_scrape', Priority.NORMAL)
        
        manager.mark_processed(work_item)
        
        assert 'test.nes' in manager.processed
    
    def test_get_stats_returns_counts(self):
        """Should return queue statistics"""
        manager = WorkQueueManager(max_retries=3)
        
        # Add some work
        for i in range(3):
            manager.add_work({'filename': f'rom{i}.nes'}, 'full_scrape')
        
        # Process one
        item = manager.get_work()
        manager.mark_processed(item)
        
        # Fail one
        item2 = manager.get_work()
        item2.retry_count = 2  # Will exceed max_retries
        manager.retry_failed(item2, 'Error')
        
        stats = manager.get_stats()
        
        assert stats['pending'] == 1
        assert stats['processed'] == 1
        assert stats['failed'] == 1


# ============================================================================
# ThrottleManager Tests
# ============================================================================

class TestThrottleManager:
    """Tests for ThrottleManager"""
    
    def test_wait_if_needed_allows_calls_within_limit(self):
        """Should allow calls within rate limit"""
        limit = RateLimit(calls=5, window_seconds=1)
        throttle = ThrottleManager(default_limit=limit)
        
        # Should allow first 5 calls immediately
        for _ in range(5):
            wait_time = throttle.wait_if_needed('test_endpoint')
            assert wait_time == 0.0
    
    def test_wait_if_needed_throttles_when_limit_exceeded(self):
        """Should throttle when rate limit exceeded"""
        limit = RateLimit(calls=2, window_seconds=1)
        throttle = ThrottleManager(default_limit=limit)
        
        # First 2 calls immediate
        throttle.wait_if_needed('test_endpoint')
        throttle.wait_if_needed('test_endpoint')
        
        # Third call should wait
        start = time.time()
        wait_time = throttle.wait_if_needed('test_endpoint')
        elapsed = time.time() - start
        
        assert wait_time > 0
        assert elapsed >= wait_time
    
    def test_handle_rate_limit_sets_backoff(self):
        """Should set backoff period on 429 response"""
        limit = RateLimit(calls=5, window_seconds=1)
        throttle = ThrottleManager(default_limit=limit)
        
        throttle.handle_rate_limit('test_endpoint', retry_after=2)
        
        # Next call should wait for backoff
        start = time.time()
        throttle.wait_if_needed('test_endpoint')
        elapsed = time.time() - start
        
        assert elapsed >= 2.0
    
    def test_handle_rate_limit_clears_history_when_adaptive(self):
        """Should clear call history on rate limit when adaptive"""
        limit = RateLimit(calls=5, window_seconds=1)
        throttle = ThrottleManager(default_limit=limit, adaptive=True)
        
        # Make some calls
        for _ in range(3):
            throttle.wait_if_needed('test_endpoint')
        
        # Handle rate limit
        throttle.handle_rate_limit('test_endpoint', retry_after=1)
        
        # After backoff, history should be clear
        time.sleep(1.1)
        stats = throttle.get_stats('test_endpoint')
        assert stats['recent_calls'] == 0
    
    def test_get_stats_returns_throttle_info(self):
        """Should return throttle statistics"""
        limit = RateLimit(calls=5, window_seconds=1)
        throttle = ThrottleManager(default_limit=limit)
        
        # Make some calls
        throttle.wait_if_needed('test_endpoint')
        throttle.wait_if_needed('test_endpoint')
        
        stats = throttle.get_stats('test_endpoint')
        
        assert stats['endpoint'] == 'test_endpoint'
        assert stats['recent_calls'] == 2
        assert stats['limit'] == 5
        assert stats['in_backoff'] is False
    
    def test_reset_clears_endpoint_state(self):
        """Should clear endpoint state on reset"""
        limit = RateLimit(calls=5, window_seconds=1)
        throttle = ThrottleManager(default_limit=limit)
        
        # Make some calls and set backoff
        throttle.wait_if_needed('test_endpoint')
        throttle.handle_rate_limit('test_endpoint', retry_after=60)
        
        # Reset
        throttle.reset('test_endpoint')
        
        stats = throttle.get_stats('test_endpoint')
        assert stats['recent_calls'] == 0
        assert stats['backoff_remaining'] == 0.0


# ============================================================================
# PerformanceMonitor Tests
# ============================================================================

class TestPerformanceMonitor:
    """Tests for PerformanceMonitor"""
    
    def test_record_rom_processed_increments_counter(self):
        """Should increment ROM counter"""
        monitor = PerformanceMonitor(total_roms=10)
        
        monitor.record_rom_processed()
        monitor.record_rom_processed()
        
        metrics = monitor.get_metrics()
        assert metrics.roms_processed == 2
    
    def test_record_api_call_increments_counter(self):
        """Should increment API call counter"""
        monitor = PerformanceMonitor(total_roms=10)
        
        monitor.record_api_call()
        monitor.record_api_call()
        monitor.record_api_call()
        
        metrics = monitor.get_metrics()
        assert metrics.api_calls == 3
    
    def test_record_download_increments_counter(self):
        """Should increment download counter"""
        monitor = PerformanceMonitor(total_roms=10)
        
        monitor.record_download()
        
        metrics = monitor.get_metrics()
        assert metrics.downloads == 1
    
    def test_get_metrics_calculates_rates(self):
        """Should calculate throughput rates"""
        monitor = PerformanceMonitor(total_roms=10)
        
        # Process some items
        for _ in range(5):
            monitor.record_rom_processed()
        
        time.sleep(0.5)
        
        metrics = monitor.get_metrics()
        
        assert metrics.roms_per_second > 0
        assert metrics.elapsed_seconds > 0
    
    def test_get_metrics_calculates_percent_complete(self):
        """Should calculate percent complete"""
        monitor = PerformanceMonitor(total_roms=10)
        
        for _ in range(3):
            monitor.record_rom_processed()
        
        metrics = monitor.get_metrics()
        
        assert metrics.percent_complete == 30.0
    
    def test_get_metrics_calculates_eta(self):
        """Should calculate ETA"""
        monitor = PerformanceMonitor(total_roms=10)
        
        # Process half
        for _ in range(5):
            monitor.record_rom_processed()
        
        time.sleep(0.5)
        
        metrics = monitor.get_metrics()
        
        # ETA should be roughly equal to elapsed (50% done)
        assert metrics.eta_seconds > 0
        assert 0.3 < metrics.eta_seconds < 1.0  # Should be ~0.5s
    
    def test_get_metrics_tracks_resource_usage(self):
        """Should track memory and CPU usage"""
        monitor = PerformanceMonitor(total_roms=10)
        
        metrics = monitor.get_metrics()
        
        assert metrics.memory_mb > 0
        assert metrics.cpu_percent >= 0
    
    def test_get_summary_returns_final_statistics(self):
        """Should return summary statistics"""
        monitor = PerformanceMonitor(total_roms=10)
        
        for _ in range(10):
            monitor.record_rom_processed()
        monitor.record_api_call()
        monitor.record_download()
        
        summary = monitor.get_summary()
        
        assert summary['total_roms'] == 10
        assert summary['roms_processed'] == 10
        assert summary['total_api_calls'] == 1
        assert summary['total_downloads'] == 1
        assert summary['elapsed_seconds'] > 0


# ============================================================================
# Integration Tests
# ============================================================================

class TestPhaseDIntegration:
    """Integration tests for Phase D components"""
    
    def test_thread_pool_with_connection_pool(self):
        """Should use connection pool for parallel downloads"""
        config = {'api': {'request_timeout': 30}}
        thread_manager = ThreadPoolManager(config)
        conn_manager = ConnectionPoolManager(config)
        
        # Initialize
        api_limits = {'maxthreads': 4, 'maxdownloadthreads': 4}
        thread_manager.initialize_pools(api_limits)
        session = conn_manager.create_session(max_connections=4)
        
        def download_with_session(media):
            # Would use session here
            return {'url': media['url'], 'success': True}
        
        media_list = [
            {'url': f'http://example.com/image{i}.png', 'type': 'screenshot'}
            for i in range(3)
        ]
        
        results = list(thread_manager.submit_download_batch(download_with_session, media_list))
        
        assert len(results) == 3
        assert all(r[1]['success'] for r in results)
        
        thread_manager.shutdown()
        conn_manager.close_session()
    
    def test_work_queue_with_throttle(self):
        """Should process work queue with throttling"""
        queue_manager = WorkQueueManager(max_retries=3)
        throttle = ThrottleManager(RateLimit(calls=2, window_seconds=1))
        
        # Add work
        for i in range(3):
            queue_manager.add_work(
                {'filename': f'rom{i}.nes'},
                'full_scrape',
                Priority.NORMAL
            )
        
        processed = []
        
        # Process with throttling
        while not queue_manager.is_empty():
            throttle.wait_if_needed('api_endpoint')
            
            item = queue_manager.get_work()
            if item:
                # Simulate processing
                processed.append(item.rom_info['filename'])
                queue_manager.mark_processed(item)
        
        assert len(processed) == 3
    
    def test_performance_monitor_with_thread_pool(self):
        """Should track performance during parallel processing"""
        monitor = PerformanceMonitor(total_roms=5)
        config = {}
        thread_manager = ThreadPoolManager(config)
        
        api_limits = {'maxthreads': 4, 'maxdownloadthreads': 4}
        thread_manager.initialize_pools(api_limits)
        
        def mock_scrape(rom):
            monitor.record_api_call()
            time.sleep(0.1)
            monitor.record_rom_processed()
            return {'filename': rom['filename'], 'success': True}
        
        roms = [{'filename': f'rom{i}.nes'} for i in range(5)]
        
        list(thread_manager.submit_api_batch(mock_scrape, roms))
        
        metrics = monitor.get_metrics()
        
        assert metrics.roms_processed == 5
        assert metrics.api_calls == 5
        assert metrics.percent_complete == 100.0
        
        thread_manager.shutdown()
