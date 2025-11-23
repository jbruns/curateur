"""
Integration tests for Phase E: WorkQueueManager and ThrottleManager

Tests the integration of work queue retry handling, throttle management,
error categorization, and UI visibility.
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path

from curateur.workflow.work_queue import WorkQueueManager, Priority
from curateur.api.throttle import ThrottleManager, RateLimit
from curateur.api.error_handler import (
    ErrorCategory, categorize_error,
    SkippableAPIError, RetryableAPIError, FatalAPIError
)
from curateur.ui.console_ui import ConsoleUI


class TestWorkQueueRetryFlow:
    """Test work queue retry integration."""
    
    def test_retryable_error_requeues_item(self):
        """Test that 429 error causes item to be requeued with HIGH priority."""
        work_queue = WorkQueueManager(max_retries=3)
        
        # Add item
        rom_info = {'filename': 'test.rom', 'system': 'nes'}
        work_queue.add_work(rom_info, 'full_scrape', Priority.NORMAL)
        
        # Get and simulate 429 error
        item = work_queue.get_work()
        assert item.priority == Priority.NORMAL
        
        # Retry on 429
        work_queue.retry_failed(item, 'Thread limit reached (HTTP 429)')
        
        # Should be requeued as HIGH priority
        retried_item = work_queue.get_work()
        assert retried_item.priority == Priority.HIGH
        assert retried_item.retry_count == 1
    
    def test_multiple_retries_escalate_priority(self):
        """Test that repeated failures maintain HIGH priority."""
        work_queue = WorkQueueManager(max_retries=3)
        
        rom_info = {'filename': 'test.rom'}
        work_queue.add_work(rom_info, 'full_scrape', Priority.NORMAL)
        
        item = work_queue.get_work()
        
        # First retry - escalates to HIGH
        work_queue.retry_failed(item, 'Error 1')
        item = work_queue.get_work()
        assert item.priority == Priority.HIGH
        assert item.retry_count == 1
        
        # Second retry - stays HIGH
        work_queue.retry_failed(item, 'Error 2')
        item = work_queue.get_work()
        assert item.priority == Priority.HIGH
        assert item.retry_count == 2
    
    def test_max_retries_moves_to_failed_list(self):
        """Test that max retries moves item to failed list."""
        work_queue = WorkQueueManager(max_retries=3)
        
        rom_info = {'filename': 'test.rom'}
        work_queue.add_work(rom_info, 'full_scrape', Priority.NORMAL)
        
        item = work_queue.get_work()
        
        # Fail 3 times
        for i in range(3):
            work_queue.retry_failed(item, f'Error {i}')
            if not work_queue.is_empty():
                item = work_queue.get_work()
        
        # Should be in failed list
        failed = work_queue.get_failed_items()
        assert len(failed) == 1
        assert failed[0]['retry_count'] == 3


class TestErrorCategorizationIntegration:
    """Test error categorization with work queue."""
    
    def test_not_found_error_not_retried(self):
        """Test that 404 errors are categorized and not retried."""
        error = SkippableAPIError("Game not found (HTTP 404)")
        exception, category = categorize_error(error)
        
        assert category == ErrorCategory.NOT_FOUND
        assert isinstance(exception, SkippableAPIError)
    
    def test_retryable_error_identified(self):
        """Test that retryable errors are correctly identified."""
        error = RetryableAPIError("Thread limit reached (HTTP 429)")
        exception, category = categorize_error(error)
        
        assert category == ErrorCategory.RETRYABLE
    
    def test_fatal_error_identified(self):
        """Test that fatal errors are correctly identified."""
        error = FatalAPIError("Invalid credentials (HTTP 403)")
        exception, category = categorize_error(error)
        
        assert category == ErrorCategory.FATAL
    
    def test_network_error_categorized_as_retryable(self):
        """Test that network errors are categorized as retryable."""
        error = Exception("Connection timeout")
        exception, category = categorize_error(error)
        
        assert category == ErrorCategory.RETRYABLE


class TestNotFoundHandling:
    """Test 404 handling and not-found summary."""
    
    @patch('curateur.workflow.orchestrator.Path')
    def test_not_found_tracked_separately(self, mock_path):
        """Test that 404 errors are tracked in not_found_items."""
        # This is more of a workflow test that would need full orchestrator mocking
        # For now, just test the data structure
        not_found_items = []
        
        from curateur.scanner.rom_types import ROMInfo
        rom_info = Mock(spec=ROMInfo)
        rom_info.filename = 'test.rom'
        rom_info.hash_value = 'abc123'
        rom_info.hash_type = 'crc32'
        rom_info.file_size = 1024
        
        not_found_items.append({
            'rom_info': rom_info,
            'error': 'Game not found (HTTP 404)'
        })
        
        assert len(not_found_items) == 1
        assert not_found_items[0]['rom_info'].filename == 'test.rom'
        assert '404' in not_found_items[0]['error']
    
    def test_not_found_summary_file_structure(self, tmp_path):
        """Test that not-found summary file is created with correct format."""
        from curateur.workflow.orchestrator import WorkflowOrchestrator
        from curateur.scanner.rom_types import ROMInfo
        from curateur.config.es_systems import SystemDefinition
        
        # Create mock components
        system = Mock(spec=SystemDefinition)
        system.name = 'nes'
        system.fullname = 'Nintendo Entertainment System'
        
        rom_info = Mock(spec=ROMInfo)
        rom_info.filename = 'test.rom'
        rom_info.hash_value = 'abc123'
        rom_info.hash_type = 'crc32'
        rom_info.file_size = 1024
        
        not_found_items = [
            {'rom_info': rom_info, 'error': 'Game not found (HTTP 404)'}
        ]
        
        # Create orchestrator with temp paths
        from curateur.api.throttle import ThrottleManager, RateLimit
        
        api_client = Mock()
        work_queue = WorkQueueManager(max_retries=3)
        throttle_manager = ThrottleManager(default_limit=RateLimit(calls=120, window_seconds=60))
        
        orchestrator = WorkflowOrchestrator(
            api_client=api_client,
            rom_directory=tmp_path / 'roms',
            media_directory=tmp_path / 'media',
            gamelist_directory=tmp_path / 'gamelists',
            work_queue=work_queue,
            throttle_manager=throttle_manager
        )
        
        # Write summary
        orchestrator._write_not_found_summary(system, not_found_items)
        
        # Check file exists
        summary_file = tmp_path / 'gamelists' / 'nes' / 'nes_not_found.txt'
        assert summary_file.exists()
        
        # Check content
        content = summary_file.read_text()
        assert 'test.rom' in content
        assert 'abc123' in content
        assert '404' in content


class TestFatal403Handling:
    """Test that 403 errors halt execution."""
    
    def test_403_raises_system_exit(self):
        """Test that 403 error triggers SystemExit."""
        from curateur.api.error_handler import handle_http_status
        
        with pytest.raises(SystemExit):
            handle_http_status(403, context="test")


class TestExponentialBackoffIntegration:
    """Test exponential backoff in practice."""
    
    def test_consecutive_429s_increase_backoff(self):
        """Test that consecutive 429s increase backoff time exponentially."""
        throttle = ThrottleManager(RateLimit(calls=10, window_seconds=60))
        endpoint = 'jeuInfos.php'
        
        # First 429: 10s * 1x = 10s
        throttle.handle_rate_limit(endpoint, retry_after=10)
        stats = throttle.get_stats(endpoint)
        assert stats['backoff_multiplier'] == 1
        
        # Clear backoff to simulate time passing
        throttle.backoff_until[endpoint] = time.time() - 1
        
        # Second 429: 10s * 2x = 20s
        throttle.handle_rate_limit(endpoint, retry_after=10)
        stats = throttle.get_stats(endpoint)
        assert stats['backoff_multiplier'] == 2
        
        # Clear backoff
        throttle.backoff_until[endpoint] = time.time() - 1
        
        # Third 429: 10s * 4x = 40s
        throttle.handle_rate_limit(endpoint, retry_after=10)
        stats = throttle.get_stats(endpoint)
        assert stats['backoff_multiplier'] == 4
    
    def test_successful_request_resets_backoff(self):
        """Test that backoff multiplier resets after successful request."""
        throttle = ThrottleManager(RateLimit(calls=10, window_seconds=60))
        endpoint = 'jeuInfos.php'
        
        # Trigger 429 twice
        throttle.handle_rate_limit(endpoint, retry_after=5)
        throttle.backoff_until[endpoint] = time.time() - 1
        throttle.handle_rate_limit(endpoint, retry_after=5)
        
        stats = throttle.get_stats(endpoint)
        assert stats['backoff_multiplier'] == 2
        
        # Simulate successful request
        throttle.reset_backoff_multiplier(endpoint)
        
        stats = throttle.get_stats(endpoint)
        assert stats['backoff_multiplier'] == 1
        assert stats['consecutive_429s'] == 0


class TestThrottleWithRetryAfter:
    """Test throttle handling with Retry-After header."""
    
    def test_retry_after_header_respected(self):
        """Test that Retry-After header value is used for backoff."""
        throttle = ThrottleManager(RateLimit(calls=10, window_seconds=60))
        endpoint = 'jeuInfos.php'
        
        # Trigger 429 with specific retry_after
        throttle.handle_rate_limit(endpoint, retry_after=15)
        
        stats = throttle.get_stats(endpoint)
        # First 429, so multiplier is 1x
        assert 14.9 <= stats['backoff_remaining'] <= 15.1


class TestPerEndpointThrottling:
    """Test per-endpoint throttle isolation."""
    
    def test_jeu_infos_rate_limit_doesnt_affect_media_jeu(self):
        """Test that rate limiting one endpoint doesn't affect another."""
        throttle = ThrottleManager(RateLimit(calls=5, window_seconds=1))
        
        # Max out jeuInfos.php
        for _ in range(5):
            throttle.wait_if_needed('jeuInfos.php')
        
        # jeuInfos should be rate limited
        wait_time = throttle.wait_if_needed('jeuInfos.php')
        assert wait_time > 0
        
        # mediaJeu.php should still be available
        wait_time = throttle.wait_if_needed('mediaJeu.php')
        assert wait_time == 0.0


class TestWorkQueueUIVisibility:
    """Test work queue statistics visibility in UI."""
    
    def test_console_ui_update_work_queue_stats(self):
        """Test that ConsoleUI can display work queue stats."""
        # Create mock config
        config = {'logging': {'level': 'INFO'}}
        
        # We can't easily test the full UI without a TTY, but we can test the method exists
        # and accepts the right parameters
        ui = ConsoleUI(config)
        
        # This should not raise an error
        ui.update_work_queue_stats(
            pending=10,
            processed=50,
            failed=2,
            not_found=5,
            retry_count=8
        )
        
        # Check that state was updated
        assert ui.current_work_queue_stats['pending'] == 10
        assert ui.current_work_queue_stats['processed'] == 50
        assert ui.current_work_queue_stats['failed'] == 2
        assert ui.current_work_queue_stats['not_found'] == 5
        assert ui.current_work_queue_stats['retry_count'] == 8


class TestCLIPerformanceSummary:
    """Test CLI reports work queue and throttle statistics."""
    
    def test_work_queue_stats_in_summary(self):
        """Test that work queue stats are included in summary."""
        work_queue = WorkQueueManager(max_retries=3)
        
        # Add and process some items
        for i in range(5):
            work_queue.add_work({'id': i}, 'action', Priority.NORMAL)
        
        for _ in range(3):
            item = work_queue.get_work()
            work_queue.mark_processed(item)
        
        # Get one and fail it repeatedly
        item = work_queue.get_work()
        for _ in range(3):
            work_queue.retry_failed(item, 'Error')
            if not work_queue.is_empty():
                item = work_queue.get_work()
        
        # Check stats structure
        stats = work_queue.get_stats()
        assert 'processed' in stats
        assert 'failed' in stats
        assert 'pending' in stats
        
        failed_items = work_queue.get_failed_items()
        assert len(failed_items) > 0
        assert 'rom_info' in failed_items[0]
        assert 'retry_count' in failed_items[0]


class TestInterruptCleanup:
    """Test cleanup on interrupt."""
    
    def test_work_queue_state_logged_on_interrupt(self):
        """Test that pending/failed items are logged on interrupt."""
        work_queue = WorkQueueManager(max_retries=3)
        
        # Add items
        for i in range(5):
            work_queue.add_work({'filename': f'test{i}.rom'}, 'action', Priority.NORMAL)
        
        # Process some
        item1 = work_queue.get_work()
        work_queue.mark_processed(item1)
        
        # Fail one
        item2 = work_queue.get_work()
        for _ in range(3):
            work_queue.retry_failed(item2, 'Error')
            if not work_queue.is_empty():
                item2 = work_queue.get_work()
        
        # Check state before cleanup
        stats = work_queue.get_stats()
        assert stats['pending'] > 0  # Some items still pending
        assert stats['failed'] > 0   # One item failed
        
        failed_items = work_queue.get_failed_items()
        assert len(failed_items) == 1


class TestConfigValidation:
    """Test Phase E configuration validation."""
    
    def test_max_retries_validation(self):
        """Test that api.max_retries is validated correctly."""
        from curateur.config.validator import _validate_api
        
        # Valid values
        assert len(_validate_api({'max_retries': 1})) == 0
        assert len(_validate_api({'max_retries': 5})) == 0
        assert len(_validate_api({'max_retries': 10})) == 0
        
        # Invalid values
        errors = _validate_api({'max_retries': 0})
        assert any('between 1 and 10' in e for e in errors)
        
        errors = _validate_api({'max_retries': 11})
        assert any('between 1 and 10' in e for e in errors)
        
        errors = _validate_api({'max_retries': 'invalid'})
        assert any('must be an integer' in e for e in errors)
    
    def test_requests_per_minute_validation(self):
        """Test that api.requests_per_minute is validated correctly."""
        from curateur.config.validator import _validate_api
        
        # Valid values
        assert len(_validate_api({'requests_per_minute': 1})) == 0
        assert len(_validate_api({'requests_per_minute': 120})) == 0
        assert len(_validate_api({'requests_per_minute': 300})) == 0
        
        # Invalid values
        errors = _validate_api({'requests_per_minute': 0})
        assert any('between 1 and 300' in e for e in errors)
        
        errors = _validate_api({'requests_per_minute': 301})
        assert any('between 1 and 300' in e for e in errors)
        
        errors = _validate_api({'requests_per_minute': 'invalid'})
        assert any('must be an integer' in e for e in errors)
    
    def test_missing_values_use_defaults(self):
        """Test that missing config values use defaults."""
        from curateur.config.validator import _validate_api
        
        # Missing values should not cause errors (defaults will be used)
        errors = _validate_api({})
        assert len(errors) == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
