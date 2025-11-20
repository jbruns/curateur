"""API rate limiting based on ScreenScraper-provided limits."""

import time
from typing import Optional, Dict


class RateLimiter:
    """
    Simple rate limiter using API-provided limits.
    
    For MVP, uses single-threaded operation with simple request spacing.
    """
    
    def __init__(
        self,
        max_requests_per_minute: Optional[int] = None,
        max_threads: int = 1
    ):
        """
        Initialize rate limiter.
        
        Args:
            max_requests_per_minute: Maximum requests per minute from API
            max_threads: Maximum concurrent threads (MVP always uses 1)
        """
        self.max_requests_per_minute = max_requests_per_minute
        self.max_threads = max_threads
        self.last_request_time = 0.0
        self.request_count = 0
        self.minute_start = time.time()
    
    def wait_if_needed(self) -> None:
        """Wait if rate limit would be exceeded."""
        if not self.max_requests_per_minute:
            return
        
        current_time = time.time()
        
        # Reset counter if a minute has passed
        if current_time - self.minute_start >= 60.0:
            self.request_count = 0
            self.minute_start = current_time
        
        # Check if we've hit the limit
        if self.request_count >= self.max_requests_per_minute:
            # Wait until the minute is up
            elapsed = current_time - self.minute_start
            wait_time = 60.0 - elapsed
            
            if wait_time > 0:
                print(f"  ⏳ Rate limit reached, waiting {wait_time:.1f}s...")
                # Sleep in small chunks to keep UI responsive
                remaining = wait_time
                while remaining > 0:
                    chunk = min(remaining, 0.1)  # 100ms chunks
                    time.sleep(chunk)
                    remaining -= chunk
                self.request_count = 0
                self.minute_start = time.time()
        
        # Simple spacing between requests
        min_delay = 60.0 / self.max_requests_per_minute if self.max_requests_per_minute else 0
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < min_delay:
            sleep_time = min_delay - time_since_last
            # Sleep in small chunks to keep UI responsive
            remaining = sleep_time
            while remaining > 0:
                chunk = min(remaining, 0.1)  # 100ms chunks
                time.sleep(chunk)
                remaining -= chunk
        
        self.last_request_time = time.time()
        self.request_count += 1
    
    def update_from_api(self, api_response: Dict) -> None:
        """
        Update rate limits from API response.
        
        Args:
            api_response: Parsed API response with ssuser data
        """
        # Extract rate limits from API response if present
        # Format: {'maxrequestspermin': 20, 'maxthreads': 1, ...}
        if 'maxrequestspermin' in api_response:
            self.max_requests_per_minute = int(api_response['maxrequestspermin'])
        
        if 'maxthreads' in api_response:
            self.max_threads = int(api_response['maxthreads'])
    
    def get_limits(self) -> Dict[str, Optional[int]]:
        """
        Get current rate limits.
        
        Returns:
            Dictionary with current limits
        """
        return {
            'max_requests_per_minute': self.max_requests_per_minute,
            'max_threads': self.max_threads,
            'current_requests': self.request_count
        }
