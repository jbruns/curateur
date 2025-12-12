"""
Adaptive throttling for API rate limiting

Implements sliding window rate limiting with adaptive backoff.
"""

import asyncio
import logging
import random
import time
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
        await throttle.wait_if_needed('jeuInfos.php')

        # Make API call
        response = await api.call()

        # Handle 429 response
        if response.status_code == 429:
            retry_after = response.headers.get('Retry-After', 60)
            throttle.handle_rate_limit('jeuInfos.php', retry_after)
    """

    def __init__(
        self,
        default_limit: RateLimit,
        adaptive: bool = True,
        max_concurrent: Optional[int] = None
    ):
        """
        Initialize throttle manager

        Args:
            default_limit: Default rate limit for endpoints
            adaptive: Enable adaptive backoff on rate limit errors
            max_concurrent: Maximum concurrent API requests (default: None, will be set from API limits)
        """
        self.default_limit = default_limit
        self.adaptive = adaptive
        self.locks = {}
        self.call_history = {}  # endpoint -> deque of timestamps
        self.backoff_until = {}  # endpoint -> timestamp
        self.consecutive_429s = {}  # endpoint -> count for exponential backoff
        self.backoff_multiplier = {}  # endpoint -> current multiplier
        self.global_lock = asyncio.Lock()

        # Concurrency limiting (will be updated from API limits)
        self.max_concurrent = max_concurrent or 3  # Default fallback
        self.concurrency_semaphore = asyncio.Semaphore(self.max_concurrent)

        # Separate semaphore for media downloads (higher limit for throughput)
        self.max_media_downloads = 20  # Allow more concurrent media downloads
        self.media_download_semaphore = asyncio.Semaphore(self.max_media_downloads)

        logger.debug(
            "Throttle manager initialized with max %s concurrent API requests, %s concurrent media downloads",
            self.max_concurrent,
            self.max_media_downloads
        )

        # Quota tracking from ScreenScraper API
        self.requeststoday = 0
        self.maxrequestsperday = 0
        self.requestskotoday = 0
        self.maxrequestskoperday = 0

        # Session-wide threshold warning flags
        self._quota_threshold_warned = False
        self._bad_quota_threshold_warned = False
        self._quota_lock = asyncio.Lock()

        # UI callback for throttle status
        self.ui_callback = None

    async def _get_endpoint_lock(self, endpoint: str) -> asyncio.Lock:
        """Get or create lock for endpoint"""
        async with self.global_lock:
            if endpoint not in self.locks:
                self.locks[endpoint] = asyncio.Lock()
                self.call_history[endpoint] = deque()
                self.consecutive_429s[endpoint] = 0
                self.backoff_multiplier[endpoint] = 1
            return self.locks[endpoint]

    def update_concurrency_limit(self, max_concurrent: int) -> None:
        """
        Update maximum concurrent request limit.

        Creates a new semaphore with the updated limit. This should be called
        after getting API limits from the user info endpoint.

        Args:
            max_concurrent: New maximum concurrent requests
        """
        if max_concurrent != self.max_concurrent:
            old_limit = self.max_concurrent
            self.max_concurrent = max_concurrent
            self.concurrency_semaphore = asyncio.Semaphore(max_concurrent)

            # Scale media downloads proportionally (but cap at reasonable limit)
            # Use 5x API limit, capped at 30
            old_media_limit = self.max_media_downloads
            self.max_media_downloads = min(max_concurrent * 5, 30)
            self.media_download_semaphore = asyncio.Semaphore(self.max_media_downloads)

            logger.info(
                f"Updated throttle concurrency limits: API {old_limit} -> {max_concurrent}, "
                f"Media {old_media_limit} -> {self.max_media_downloads}"
            )

    async def wait_if_needed(self, endpoint: str) -> float:
        """
        Wait if rate limit would be exceeded

        Args:
            endpoint: API endpoint name

        Returns:
            Seconds waited (0 if no wait needed)
        """
        lock = await self._get_endpoint_lock(endpoint)

        async with lock:
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

                    # Notify UI: Throttling active
                    if self.ui_callback:
                        self.ui_callback(True)

                    # Async sleep - UI stays responsive
                    await asyncio.sleep(wait_time)

                    # Notify UI: Throttling ended
                    if self.ui_callback:
                        self.ui_callback(False)

                    return wait_time
                else:
                    # Backoff period ended
                    del self.backoff_until[endpoint]
                    logger.info(f"Rate limit backoff ended for {endpoint}")

                    # Notify UI: Throttling ended
                    if self.ui_callback:
                        self.ui_callback(False)

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

                    # Notify UI: Throttling active
                    if self.ui_callback:
                        self.ui_callback(True)

                    # Async sleep - UI stays responsive
                    await asyncio.sleep(wait_time)

                    # Notify UI: Throttling ended
                    if self.ui_callback:
                        self.ui_callback(False)

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

        Implements adaptive backoff with progressive multiplier if enabled.
        Consecutive 429s increase backoff: 1x → 1.5x → 2x → 3x (capped at 3x)
        Includes ±10% random jitter to prevent thundering herd on recovery.

        Note: This is synchronous as it only updates internal state.
        Use await wait_if_needed() to actually wait for the backoff period.

        Args:
            endpoint: API endpoint that returned 429
            retry_after: Retry-After header value in seconds (optional)
        """
        # Since we need to support synchronous calls from exception handlers,
        # we'll use a synchronous method here. The actual waiting is done in wait_if_needed()
        if endpoint not in self.locks:
            # Initialize endpoint if needed (synchronous version)
            self.locks[endpoint] = asyncio.Lock()
            self.call_history[endpoint] = deque()
            self.consecutive_429s[endpoint] = 0
            self.backoff_multiplier[endpoint] = 1

        if retry_after is None:
            # Default backoff: 60 seconds
            retry_after = 60

        # Track consecutive 429s and calculate progressive backoff multiplier
        self.consecutive_429s[endpoint] += 1

        # Calculate multiplier: 1x → 1.5x → 2x → 3x (capped at 3x)
        # More conservative than exponential to avoid excessive backoff
        multipliers = [1.0, 1.5, 2.0, 3.0]
        multiplier_index = min(self.consecutive_429s[endpoint] - 1, len(multipliers) - 1)
        base_multiplier = multipliers[multiplier_index]

        # Add ±10% random jitter to prevent thundering herd when multiple concurrent requests recover
        jitter = random.uniform(0.9, 1.1)
        multiplier = base_multiplier * jitter

        self.backoff_multiplier[endpoint] = multiplier

        # Apply multiplier to retry_after
        actual_backoff = retry_after * multiplier
        backoff_until = time.time() + actual_backoff
        self.backoff_until[endpoint] = backoff_until

        logger.warning(
            f"Rate limit hit for {endpoint}: "
            f"backing off for {actual_backoff:.1f}s "
            f"(base={retry_after}s, multiplier={base_multiplier:.1f}x+jitter={jitter:.2f}, "
            f"consecutive_429s={self.consecutive_429s[endpoint]})"
        )

        # Clear recent call history to be conservative
        if self.adaptive:
            self.call_history[endpoint].clear()
            logger.info(f"Cleared call history for {endpoint}")

    def reset_backoff_multiplier(self, endpoint: str) -> None:
        """
        Reset backoff multiplier after successful request

        Note: Synchronous method for use in non-async contexts

        Args:
            endpoint: API endpoint with successful request
        """
        if endpoint in self.consecutive_429s and self.consecutive_429s[endpoint] > 0:
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

        Note: Synchronous method for use in non-async contexts

        Args:
            endpoint: API endpoint name

        Returns:
            dict with recent_calls, backoff_remaining, backoff_multiplier, consecutive_429s
        """
        if endpoint not in self.call_history:
            return {
                'endpoint': endpoint,
                'recent_calls': 0,
                'limit': self.default_limit.calls,
                'window_seconds': self.default_limit.window_seconds,
                'backoff_remaining': 0.0,
                'in_backoff': False,
                'backoff_multiplier': 1,
                'consecutive_429s': 0
            }

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

        Note: Synchronous method for use in non-async contexts

        Args:
            endpoint: Specific endpoint to reset (None = all)
        """
        if endpoint:
            if endpoint in self.call_history:
                self.call_history[endpoint].clear()
            if endpoint in self.backoff_until:
                del self.backoff_until[endpoint]
            if endpoint in self.consecutive_429s:
                self.consecutive_429s[endpoint] = 0
            if endpoint in self.backoff_multiplier:
                self.backoff_multiplier[endpoint] = 1
            logger.info(f"Reset throttle for {endpoint}")
        else:
            for ep in list(self.call_history.keys()):
                self.call_history[ep].clear()
            self.backoff_until.clear()
            self.consecutive_429s.clear()
            self.backoff_multiplier.clear()
            logger.info("Reset all throttles")

    async def update_quota(self, user_limits: dict) -> None:
        """
        Update quota information from API response

        Thread-safe update of quota fields from ScreenScraper user info.

        Args:
            user_limits: Dictionary with user quota fields from API response
        """
        async with self._quota_lock:
            if 'requeststoday' in user_limits:
                self.requeststoday = int(user_limits['requeststoday'])
            if 'maxrequestsperday' in user_limits:
                self.maxrequestsperday = int(user_limits['maxrequestsperday'])
            if 'requestskotoday' in user_limits:
                self.requestskotoday = int(user_limits['requestskotoday'])
            if 'maxrequestskoperday' in user_limits:
                self.maxrequestskoperday = int(user_limits['maxrequestskoperday'])

    async def check_quota_threshold(self, threshold: float) -> None:
        """
        Check if quota threshold is exceeded and log warning once per session

        Calculates percentage usage for both regular and bad request quotas,
        logging a WARNING once per session when threshold is crossed for each type.

        Args:
            threshold: Warning threshold as float 0.0-1.0 (e.g., 0.95 = 95%)
        """
        async with self._quota_lock:
            # Check regular request quota
            if self.maxrequestsperday > 0 and not self._quota_threshold_warned:
                usage_pct = self.requeststoday / self.maxrequestsperday
                if usage_pct >= threshold:
                    logger.warning(
                        f"API quota threshold exceeded: {self.requeststoday}/{self.maxrequestsperday} "
                        f"requests today ({usage_pct:.1%} >= {threshold:.1%})"
                    )
                    self._quota_threshold_warned = True

            # Check bad request quota
            if self.maxrequestskoperday > 0 and not self._bad_quota_threshold_warned:
                bad_usage_pct = self.requestskotoday / self.maxrequestskoperday
                if bad_usage_pct >= threshold:
                    logger.warning(
                        f"API bad request quota threshold exceeded: {self.requestskotoday}/{self.maxrequestskoperday} "
                        f"bad requests today ({bad_usage_pct:.1%} >= {threshold:.1%})"
                    )
                    self._bad_quota_threshold_warned = True

    def get_quota_stats(self) -> dict:
        """
        Get current quota statistics

        Returns flat dict with all quota fields for UI display.
        Synchronous method for use in non-async contexts.

        Returns:
            Dictionary with requeststoday, maxrequestsperday,
            requestskotoday, maxrequestskoperday
        """
        return {
            'requeststoday': self.requeststoday,
            'maxrequestsperday': self.maxrequestsperday,
            'requestskotoday': self.requestskotoday,
            'maxrequestskoperday': self.maxrequestskoperday
        }
