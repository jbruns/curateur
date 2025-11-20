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
        # Rate limit: 120 calls per minute
        throttle = ThrottleManager(
            default_limit=RateLimit(calls=120, window_seconds=60)
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
        self.consecutive_429s = {}  # endpoint -> count for exponential backoff
        self.backoff_multiplier = {}  # endpoint -> current multiplier
        self.global_lock = threading.Lock()
    
    def _get_endpoint_lock(self, endpoint: str) -> threading.Lock:
        """Get or create lock for endpoint"""
        with self.global_lock:
            if endpoint not in self.locks:
                self.locks[endpoint] = threading.Lock()
                self.call_history[endpoint] = deque()
                self.consecutive_429s[endpoint] = 0
                self.backoff_multiplier[endpoint] = 1
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
                    # Sleep in small chunks to keep UI responsive
                    remaining = wait_time
                    while remaining > 0:
                        chunk = min(remaining, 0.1)  # 100ms chunks
                        time.sleep(chunk)
                        remaining -= chunk
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
                    # Sleep in small chunks to keep UI responsive
                    remaining = wait_time
                    while remaining > 0:
                        chunk = min(remaining, 0.1)  # 100ms chunks
                        time.sleep(chunk)
                        remaining -= chunk
                    
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
        
        Implements adaptive backoff with exponential multiplier if enabled.
        Consecutive 429s increase backoff: 1x -> 2x -> 4x -> 8x (capped at 8x)
        
        Args:
            endpoint: API endpoint that returned 429
            retry_after: Retry-After header value in seconds (optional)
        """
        lock = self._get_endpoint_lock(endpoint)
        
        with lock:
            if retry_after is None:
                # Default backoff: 60 seconds
                retry_after = 60
            
            # Track consecutive 429s and calculate exponential backoff multiplier
            self.consecutive_429s[endpoint] += 1
            
            # Calculate multiplier: 1x, 2x, 4x, 8x (capped at 8x)
            multiplier = min(2 ** (self.consecutive_429s[endpoint] - 1), 8)
            self.backoff_multiplier[endpoint] = multiplier
            
            # Apply multiplier to retry_after
            actual_backoff = retry_after * multiplier
            backoff_until = time.time() + actual_backoff
            self.backoff_until[endpoint] = backoff_until
            
            logger.warning(
                f"Rate limit hit for {endpoint}: "
                f"backing off for {actual_backoff}s "
                f"(base={retry_after}s, multiplier={multiplier}x, consecutive_429s={self.consecutive_429s[endpoint]})"
            )
            
            # Clear recent call history to be conservative
            if self.adaptive:
                self.call_history[endpoint].clear()
                logger.info(f"Cleared call history for {endpoint}")
    
    def reset_backoff_multiplier(self, endpoint: str) -> None:
        """
        Reset backoff multiplier after successful request
        
        Args:
            endpoint: API endpoint with successful request
        """
        lock = self._get_endpoint_lock(endpoint)
        
        with lock:
            if self.consecutive_429s[endpoint] > 0:
                logger.info(
                    f"Resetting backoff multiplier for {endpoint} "
                    f"(was {self.backoff_multiplier[endpoint]}x after "
                    f"{self.consecutive_429s[endpoint]} consecutive 429s)"
                )
                self.consecutive_429s[endpoint] = 0
                self.backoff_multiplier[endpoint] = 1
    
    def get_stats(self, endpoint: str) -> dict:
        """
        Get throttle statistics for endpoint
        
        Args:
            endpoint: API endpoint name
        
        Returns:
            dict with recent_calls, backoff_remaining, backoff_multiplier, consecutive_429s
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
                'in_backoff': backoff_remaining > 0,
                'backoff_multiplier': self.backoff_multiplier.get(endpoint, 1),
                'consecutive_429s': self.consecutive_429s.get(endpoint, 0)
            }
    
    def reset(self, endpoint: Optional[str] = None) -> None:
        """
        Reset throttle state including backoff multipliers
        
        Args:
            endpoint: Specific endpoint to reset (None = all)
        """
        if endpoint:
            lock = self._get_endpoint_lock(endpoint)
            with lock:
                self.call_history[endpoint].clear()
                if endpoint in self.backoff_until:
                    del self.backoff_until[endpoint]
                self.consecutive_429s[endpoint] = 0
                self.backoff_multiplier[endpoint] = 1
                logger.info(f"Reset throttle for {endpoint}")
        else:
            with self.global_lock:
                for ep in list(self.call_history.keys()):
                    self.call_history[ep].clear()
                self.backoff_until.clear()
                self.consecutive_429s.clear()
                self.backoff_multiplier.clear()
                logger.info("Reset all throttles")
