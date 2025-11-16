"""
Adaptive throttling for API rate limiting

Implements sliding window rate limiting with adaptive backoff.
"""

import logging
import time
import threading
from collections import deque
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RateLimit:
    """Rate limit configuration"""
    calls: int          # Maximum calls per window
    window_seconds: int # Time window in seconds
    

class ThrottleManager:
    """
    Adaptive rate limiting with sliding window
    
    Features:
    - Sliding window rate limiting
    - Per-endpoint tracking
    - Adaptive backoff on 429 responses
    - Automatic recovery
    
    Example:
        throttle = ThrottleManager(
            default_limit=RateLimit(calls=5, window_seconds=1)
        )
        
        # Wait if needed before API call
        throttle.wait_if_needed('jeuInfos.php')
        
        # Make API call
        response = api.call()
        
        # Handle 429 response
        if response.status_code == 429:
            retry_after = response.headers.get('Retry-After', 60)
            throttle.handle_rate_limit('jeuInfos.php', retry_after)
    """
    
    def __init__(
        self,
        default_limit: RateLimit,
        adaptive: bool = True
    ):
        """
        Initialize throttle manager
        
        Args:
            default_limit: Default rate limit for endpoints
            adaptive: Enable adaptive backoff on rate limit errors
        """
        self.default_limit = default_limit
        self.adaptive = adaptive
        self.locks = {}
        self.call_history = {}  # endpoint -> deque of timestamps
        self.backoff_until = {}  # endpoint -> timestamp
        self.global_lock = threading.Lock()
    
    def _get_endpoint_lock(self, endpoint: str) -> threading.Lock:
        """Get or create lock for endpoint"""
        with self.global_lock:
            if endpoint not in self.locks:
                self.locks[endpoint] = threading.Lock()
                self.call_history[endpoint] = deque()
            return self.locks[endpoint]
    
    def wait_if_needed(self, endpoint: str) -> float:
        """
        Wait if rate limit would be exceeded
        
        Args:
            endpoint: API endpoint name
        
        Returns:
            Seconds waited (0 if no wait needed)
        """
        lock = self._get_endpoint_lock(endpoint)
        
        with lock:
            # Check if in backoff period
            if endpoint in self.backoff_until:
                backoff_until = self.backoff_until[endpoint]
                now = time.time()
                if now < backoff_until:
                    wait_time = backoff_until - now
                    logger.warning(
                        f"Rate limit backoff for {endpoint}: "
                        f"waiting {wait_time:.1f}s"
                    )
                    time.sleep(wait_time)
                    return wait_time
                else:
                    # Backoff period ended
                    del self.backoff_until[endpoint]
                    logger.info(f"Rate limit backoff ended for {endpoint}")
            
            # Clean old calls outside window
            history = self.call_history[endpoint]
            now = time.time()
            window_start = now - self.default_limit.window_seconds
            
            while history and history[0] < window_start:
                history.popleft()
            
            # Check if limit would be exceeded
            if len(history) >= self.default_limit.calls:
                # Must wait until oldest call expires
                oldest_call = history[0]
                wait_until = oldest_call + self.default_limit.window_seconds
                wait_time = wait_until - now
                
                if wait_time > 0:
                    logger.debug(
                        f"Rate limit throttle for {endpoint}: "
                        f"waiting {wait_time:.1f}s"
                    )
                    time.sleep(wait_time)
                    
                    # Clean expired call
                    history.popleft()
                    
                    return wait_time
            
            # Record this call
            history.append(time.time())
            return 0.0
    
    def handle_rate_limit(
        self,
        endpoint: str,
        retry_after: Optional[int] = None
    ) -> None:
        """
        Handle 429 rate limit response
        
        Implements adaptive backoff if enabled.
        
        Args:
            endpoint: API endpoint that returned 429
            retry_after: Retry-After header value in seconds (optional)
        """
        lock = self._get_endpoint_lock(endpoint)
        
        with lock:
            if retry_after is None:
                # Default backoff: 60 seconds
                retry_after = 60
            
            backoff_until = time.time() + retry_after
            self.backoff_until[endpoint] = backoff_until
            
            logger.warning(
                f"Rate limit hit for {endpoint}: "
                f"backing off for {retry_after}s"
            )
            
            # Clear recent call history to be conservative
            if self.adaptive:
                self.call_history[endpoint].clear()
                logger.info(f"Cleared call history for {endpoint}")
    
    def get_stats(self, endpoint: str) -> dict:
        """
        Get throttle statistics for endpoint
        
        Args:
            endpoint: API endpoint name
        
        Returns:
            dict with recent_calls, backoff_remaining
        """
        lock = self._get_endpoint_lock(endpoint)
        
        with lock:
            history = self.call_history[endpoint]
            now = time.time()
            window_start = now - self.default_limit.window_seconds
            
            # Count recent calls
            recent_calls = sum(1 for t in history if t >= window_start)
            
            # Check backoff
            backoff_remaining = 0.0
            if endpoint in self.backoff_until:
                backoff_remaining = max(0, self.backoff_until[endpoint] - now)
            
            return {
                'endpoint': endpoint,
                'recent_calls': recent_calls,
                'limit': self.default_limit.calls,
                'window_seconds': self.default_limit.window_seconds,
                'backoff_remaining': backoff_remaining,
                'in_backoff': backoff_remaining > 0
            }
    
    def reset(self, endpoint: Optional[str] = None) -> None:
        """
        Reset throttle state
        
        Args:
            endpoint: Specific endpoint to reset (None = all)
        """
        if endpoint:
            lock = self._get_endpoint_lock(endpoint)
            with lock:
                self.call_history[endpoint].clear()
                if endpoint in self.backoff_until:
                    del self.backoff_until[endpoint]
                logger.info(f"Reset throttle for {endpoint}")
        else:
            with self.global_lock:
                for ep in list(self.call_history.keys()):
                    self.call_history[ep].clear()
                self.backoff_until.clear()
                logger.info("Reset all throttles")
