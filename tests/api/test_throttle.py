"""
Comprehensive test suite for ThrottleManager

Tests sliding window rate limiting, exponential backoff, per-endpoint tracking,
and concurrent access patterns.
"""

import pytest
import time
import threading
from concurrent.futures import ThreadPoolExecutor
from curateur.api.throttle import ThrottleManager, RateLimit


class TestSlidingWindow:
    """Test sliding window rate limiting."""
    
    def test_sliding_window_expiration(self):
        """Test that old calls expire from sliding window."""
        # 10 calls per 2 seconds
        throttle = ThrottleManager(RateLimit(calls=10, window_seconds=2))
        endpoint = 'test.php'
        
        # Make 10 calls (should be instant)
        for _ in range(10):
            wait_time = throttle.wait_if_needed(endpoint)
            assert wait_time == 0.0
        
        # 11th call should block
        wait_time = throttle.wait_if_needed(endpoint)
        assert wait_time > 0
        
        # After window/2, some calls should have expired
        time.sleep(1.1)
        
        # Make another 10 calls - first few should be instant
        instant_calls = 0
        for _ in range(5):
            wait_time = throttle.wait_if_needed(endpoint)
            if wait_time == 0.0:
                instant_calls += 1
        
        # At least some calls should have been instant due to expiration
        assert instant_calls > 0
    
    def test_rate_limit_enforcement(self):
        """Test that rate limit is enforced correctly."""
        # 5 calls per second
        throttle = ThrottleManager(RateLimit(calls=5, window_seconds=1))
        endpoint = 'test.php'
        
        start_time = time.time()
        
        # Make 5 calls
        for _ in range(5):
            throttle.wait_if_needed(endpoint)
        
        elapsed = time.time() - start_time
        assert elapsed < 0.1  # Should be nearly instant
        
        # 6th call should block for ~1 second
        wait_time = throttle.wait_if_needed(endpoint)
        assert wait_time >= 0.9


class TestPerEndpointIsolation:
    """Test that endpoints are tracked independently."""
    
    def test_endpoints_isolated(self):
        """Test that maxing out one endpoint doesn't affect another."""
        throttle = ThrottleManager(RateLimit(calls=5, window_seconds=1))
        
        # Max out endpoint A
        for _ in range(5):
            throttle.wait_if_needed('endpointA.php')
        
        # Endpoint A should block
        wait_time_a = throttle.wait_if_needed('endpointA.php')
        assert wait_time_a > 0
        
        # Endpoint B should still be available
        wait_time_b = throttle.wait_if_needed('endpointB.php')
        assert wait_time_b == 0.0
    
    def test_per_endpoint_call_history(self):
        """Test that each endpoint maintains its own call history."""
        throttle = ThrottleManager(RateLimit(calls=10, window_seconds=1))
        
        # Make calls to different endpoints
        for _ in range(3):
            throttle.wait_if_needed('endpoint1.php')
        
        for _ in range(5):
            throttle.wait_if_needed('endpoint2.php')
        
        for _ in range(7):
            throttle.wait_if_needed('endpoint3.php')
        
        # Check stats for each endpoint
        stats1 = throttle.get_stats('endpoint1.php')
        stats2 = throttle.get_stats('endpoint2.php')
        stats3 = throttle.get_stats('endpoint3.php')
        
        assert stats1['recent_calls'] == 3
        assert stats2['recent_calls'] == 5
        assert stats3['recent_calls'] == 7


class Test429Handling:
    """Test 429 rate limit response handling."""
    
    def test_429_sets_backoff(self):
        """Test that handle_rate_limit sets backoff correctly."""
        throttle = ThrottleManager(RateLimit(calls=10, window_seconds=1))
        endpoint = 'test.php'
        
        # Trigger 429 with 30 second backoff
        throttle.handle_rate_limit(endpoint, retry_after=30)
        
        # Next call should wait for backoff
        start_time = time.time()
        wait_time = throttle.wait_if_needed(endpoint)
        
        assert wait_time >= 29.9  # Account for timing precision
    
    def test_429_clears_call_history(self):
        """Test that 429 clears recent call history."""
        throttle = ThrottleManager(RateLimit(calls=10, window_seconds=1), adaptive=True)
        endpoint = 'test.php'
        
        # Make some calls
        for _ in range(5):
            throttle.wait_if_needed(endpoint)
        
        stats = throttle.get_stats(endpoint)
        assert stats['recent_calls'] == 5
        
        # Trigger 429
        throttle.handle_rate_limit(endpoint, retry_after=1)
        
        # Call history should be cleared
        stats = throttle.get_stats(endpoint)
        assert stats['recent_calls'] == 0


class TestExponentialBackoff:
    """Test exponential backoff on consecutive 429s."""
    
    def test_backoff_multiplier_increases(self):
        """Test that consecutive 429s increase backoff: 1x, 2x, 4x, 8x."""
        throttle = ThrottleManager(RateLimit(calls=10, window_seconds=1))
        endpoint = 'test.php'
        
        # First 429
        throttle.handle_rate_limit(endpoint, retry_after=10)
        stats = throttle.get_stats(endpoint)
        assert stats['backoff_multiplier'] == 1
        assert stats['consecutive_429s'] == 1
        
        # Wait for backoff to clear
        time.sleep(0.1)
        throttle.backoff_until[endpoint] = time.time() - 1
        
        # Second 429
        throttle.handle_rate_limit(endpoint, retry_after=10)
        stats = throttle.get_stats(endpoint)
        assert stats['backoff_multiplier'] == 2
        assert stats['consecutive_429s'] == 2
        
        # Wait for backoff to clear
        throttle.backoff_until[endpoint] = time.time() - 1
        
        # Third 429
        throttle.handle_rate_limit(endpoint, retry_after=10)
        stats = throttle.get_stats(endpoint)
        assert stats['backoff_multiplier'] == 4
        assert stats['consecutive_429s'] == 3
        
        # Wait for backoff to clear
        throttle.backoff_until[endpoint] = time.time() - 1
        
        # Fourth 429 - should cap at 8x
        throttle.handle_rate_limit(endpoint, retry_after=10)
        stats = throttle.get_stats(endpoint)
        assert stats['backoff_multiplier'] == 8
        assert stats['consecutive_429s'] == 4
        
        # Fifth 429 - should stay at 8x (capped)
        throttle.backoff_until[endpoint] = time.time() - 1
        throttle.handle_rate_limit(endpoint, retry_after=10)
        stats = throttle.get_stats(endpoint)
        assert stats['backoff_multiplier'] == 8
        assert stats['consecutive_429s'] == 5
    
    def test_backoff_multiplier_reset_on_success(self):
        """Test that successful request resets backoff multiplier."""
        throttle = ThrottleManager(RateLimit(calls=10, window_seconds=1))
        endpoint = 'test.php'
        
        # Trigger 429 twice
        throttle.handle_rate_limit(endpoint, retry_after=1)
        time.sleep(0.1)
        throttle.backoff_until[endpoint] = time.time() - 1
        throttle.handle_rate_limit(endpoint, retry_after=1)
        
        stats = throttle.get_stats(endpoint)
        assert stats['backoff_multiplier'] == 2
        assert stats['consecutive_429s'] == 2
        
        # Successful request should reset
        throttle.reset_backoff_multiplier(endpoint)
        
        stats = throttle.get_stats(endpoint)
        assert stats['backoff_multiplier'] == 1
        assert stats['consecutive_429s'] == 0
    
    def test_retry_after_applies_multiplier(self):
        """Test that retry_after duration is multiplied correctly."""
        throttle = ThrottleManager(RateLimit(calls=10, window_seconds=1))
        endpoint = 'test.php'
        
        # First 429: 10s * 1x = 10s
        throttle.handle_rate_limit(endpoint, retry_after=10)
        stats = throttle.get_stats(endpoint)
        assert 9.9 <= stats['backoff_remaining'] <= 10.1
        
        # Clear backoff
        throttle.backoff_until[endpoint] = time.time() - 1
        
        # Second 429: 10s * 2x = 20s
        throttle.handle_rate_limit(endpoint, retry_after=10)
        stats = throttle.get_stats(endpoint)
        assert 19.9 <= stats['backoff_remaining'] <= 20.1


class TestConcurrentAccess:
    """Test thread safety."""
    
    def test_concurrent_same_endpoint(self):
        """Test thread-safe access to same endpoint."""
        throttle = ThrottleManager(RateLimit(calls=100, window_seconds=1))
        endpoint = 'test.php'
        call_count = [0]
        lock = threading.Lock()
        
        def make_calls(count):
            for _ in range(count):
                throttle.wait_if_needed(endpoint)
                with lock:
                    call_count[0] += 1
        
        # 20 threads making 10 calls each = 200 calls
        with ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(make_calls, 10) for _ in range(20)]
            for future in futures:
                future.result()
        
        assert call_count[0] == 200
        
        # Should have blocked some calls due to rate limit
        stats = throttle.get_stats(endpoint)
        # Recent calls should be <= limit
        assert stats['recent_calls'] <= 100
    
    def test_concurrent_different_endpoints(self):
        """Test that different endpoints don't interfere."""
        throttle = ThrottleManager(RateLimit(calls=50, window_seconds=1))
        results = {'endpoint1': 0, 'endpoint2': 0, 'endpoint3': 0}
        lock = threading.Lock()
        
        def make_calls(endpoint, count):
            for _ in range(count):
                throttle.wait_if_needed(endpoint)
                with lock:
                    results[endpoint] += 1
        
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = []
            futures.append(executor.submit(make_calls, 'endpoint1', 30))
            futures.append(executor.submit(make_calls, 'endpoint1', 30))
            futures.append(executor.submit(make_calls, 'endpoint2', 30))
            futures.append(executor.submit(make_calls, 'endpoint2', 30))
            futures.append(executor.submit(make_calls, 'endpoint3', 30))
            futures.append(executor.submit(make_calls, 'endpoint3', 30))
            
            for future in futures:
                future.result()
        
        # Each endpoint should have received all its calls
        assert results['endpoint1'] == 60
        assert results['endpoint2'] == 60
        assert results['endpoint3'] == 60


class TestReset:
    """Test reset functionality."""
    
    def test_reset_single_endpoint(self):
        """Test resetting a specific endpoint."""
        throttle = ThrottleManager(RateLimit(calls=10, window_seconds=1))
        
        # Make calls to two endpoints
        for _ in range(5):
            throttle.wait_if_needed('endpoint1.php')
            throttle.wait_if_needed('endpoint2.php')
        
        # Trigger 429 on endpoint1
        throttle.handle_rate_limit('endpoint1.php', retry_after=30)
        
        # Reset endpoint1
        throttle.reset('endpoint1.php')
        
        # Endpoint1 should be clear
        stats1 = throttle.get_stats('endpoint1.php')
        assert stats1['recent_calls'] == 0
        assert stats1['backoff_remaining'] == 0
        assert stats1['consecutive_429s'] == 0
        assert stats1['backoff_multiplier'] == 1
        
        # Endpoint2 should be unchanged
        stats2 = throttle.get_stats('endpoint2.php')
        assert stats2['recent_calls'] == 5
    
    def test_reset_all_endpoints(self):
        """Test resetting all endpoints."""
        throttle = ThrottleManager(RateLimit(calls=10, window_seconds=1))
        
        # Make calls and trigger 429s on multiple endpoints
        for endpoint in ['ep1.php', 'ep2.php', 'ep3.php']:
            for _ in range(5):
                throttle.wait_if_needed(endpoint)
            throttle.handle_rate_limit(endpoint, retry_after=30)
        
        # Reset all
        throttle.reset()
        
        # All should be cleared
        for endpoint in ['ep1.php', 'ep2.php', 'ep3.php']:
            stats = throttle.get_stats(endpoint)
            assert stats['recent_calls'] == 0
            assert stats['backoff_remaining'] == 0
            assert stats['consecutive_429s'] == 0


class TestGetStats:
    """Test statistics reporting."""
    
    def test_get_stats_includes_all_fields(self):
        """Test that get_stats returns all required fields."""
        throttle = ThrottleManager(RateLimit(calls=10, window_seconds=60))
        endpoint = 'test.php'
        
        throttle.wait_if_needed(endpoint)
        stats = throttle.get_stats(endpoint)
        
        # Check all required fields exist
        assert 'endpoint' in stats
        assert 'recent_calls' in stats
        assert 'limit' in stats
        assert 'window_seconds' in stats
        assert 'backoff_remaining' in stats
        assert 'in_backoff' in stats
        assert 'backoff_multiplier' in stats
        assert 'consecutive_429s' in stats
        
        # Check values
        assert stats['endpoint'] == endpoint
        assert stats['recent_calls'] == 1
        assert stats['limit'] == 10
        assert stats['window_seconds'] == 60
        assert stats['backoff_multiplier'] == 1
        assert stats['consecutive_429s'] == 0
    
    def test_get_stats_reflects_backoff_state(self):
        """Test that stats correctly reflect backoff state."""
        throttle = ThrottleManager(RateLimit(calls=10, window_seconds=1))
        endpoint = 'test.php'
        
        # Before backoff
        stats = throttle.get_stats(endpoint)
        assert not stats['in_backoff']
        assert stats['backoff_remaining'] == 0
        
        # Trigger 429 with 5 second backoff
        throttle.handle_rate_limit(endpoint, retry_after=5)
        
        # During backoff
        stats = throttle.get_stats(endpoint)
        assert stats['in_backoff']
        assert 4.9 <= stats['backoff_remaining'] <= 5.1
        
        # After backoff expires
        time.sleep(5.1)
        throttle.wait_if_needed(endpoint)  # This will clear expired backoff
        
        stats = throttle.get_stats(endpoint)
        assert not stats['in_backoff']
        assert stats['backoff_remaining'] == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
