"""
Rate limit override system for advanced scenarios

Allows manual rate limit configuration while providing safety warnings.
"""

import logging
from typing import Optional, Dict, Any, NamedTuple

logger = logging.getLogger(__name__)


class RateLimits(NamedTuple):
    """Rate limit configuration"""
    max_threads: int
    requests_per_second: float
    daily_quota: int


class RateLimitOverride:
    """
    Manual rate limit overrides for advanced scenarios
    
    Use cases:
    - Developer/premium accounts with higher limits
    - Testing with restricted quotas
    - Custom throttling for shared networks
    
    WARNING: Exceeding ScreenScraper limits may result in temporary bans
    
    Configuration example:
        scraping:
          rate_limit_override_enabled: false
          rate_limit_override:
            max_threads: 4
            requests_per_second: 2.0
            daily_quota: 10000
    
    Example:
        override = RateLimitOverride(config)
        
        # Get effective limits (API + overrides)
        limits = override.get_effective_limits(api_provided_limits)
        
        # Use limits for rate limiting
        rate_limiter.configure(
            max_threads=limits.max_threads,
            requests_per_second=limits.requests_per_second
        )
    """
    
    # Default conservative limits (used as fallback)
    DEFAULT_MAX_THREADS = 1
    DEFAULT_REQUESTS_PER_SECOND = 1.0
    DEFAULT_DAILY_QUOTA = 10000
    
    # Typical API limits (for warning purposes)
    TYPICAL_MAX_THREADS = 4
    TYPICAL_REQUESTS_PER_SECOND = 2.0
    TYPICAL_DAILY_QUOTA = 20000
    
    def __init__(self, config: dict):
        """
        Initialize rate limit override
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.override_enabled = config.get('scraping', {}).get(
            'rate_limit_override_enabled', False
        )
        self.custom_limits = config.get('scraping', {}).get(
            'rate_limit_override', {}
        )
        
        # Validate on initialization
        if self.override_enabled:
            self.validate_overrides()
    
    def get_effective_limits(self, api_provided_limits: Optional[Dict[str, Any]]) -> RateLimits:
        """
        Merge API-provided limits with user overrides
        
        Priority:
        1. User overrides (if enabled and valid)
        2. API-provided limits (if available)
        3. Default conservative limits
        
        Args:
            api_provided_limits: dict with API response fields:
                - maxthreads: int
                - maxrequestsseconds: float
                - maxrequestsperday: int
        
        Returns:
            RateLimits with effective configuration
        
        Example:
            # API provides: maxthreads=4, maxrequestsseconds=2.0
            # Override: max_threads=2 (conservative)
            # Result: max_threads=2, requests_per_second=2.0
        """
        # Start with defaults
        max_threads = self.DEFAULT_MAX_THREADS
        requests_per_second = self.DEFAULT_REQUESTS_PER_SECOND
        daily_quota = self.DEFAULT_DAILY_QUOTA
        
        # Apply API-provided limits if available
        if api_provided_limits:
            if 'maxthreads' in api_provided_limits:
                max_threads = int(api_provided_limits['maxthreads'])
                logger.debug(f"Using API max_threads: {max_threads}")
            
            if 'maxrequestsseconds' in api_provided_limits:
                requests_per_second = float(api_provided_limits['maxrequestsseconds'])
                logger.debug(f"Using API requests_per_second: {requests_per_second}")
            
            if 'maxrequestsperday' in api_provided_limits:
                daily_quota = int(api_provided_limits['maxrequestsperday'])
                logger.debug(f"Using API daily_quota: {daily_quota}")
        
        # Apply user overrides if enabled
        if self.override_enabled:
            if 'max_threads' in self.custom_limits:
                override_threads = int(self.custom_limits['max_threads'])
                logger.info(
                    f"Overriding max_threads: {max_threads} -> {override_threads}"
                )
                max_threads = override_threads
            
            if 'requests_per_second' in self.custom_limits:
                override_rps = float(self.custom_limits['requests_per_second'])
                logger.info(
                    f"Overriding requests_per_second: {requests_per_second} -> {override_rps}"
                )
                requests_per_second = override_rps
            
            if 'daily_quota' in self.custom_limits:
                override_quota = int(self.custom_limits['daily_quota'])
                logger.info(
                    f"Overriding daily_quota: {daily_quota} -> {override_quota}"
                )
                daily_quota = override_quota
        
        return RateLimits(
            max_threads=max_threads,
            requests_per_second=requests_per_second,
            daily_quota=daily_quota
        )
    
    def validate_overrides(self) -> None:
        """
        Validate override configuration
        Warn if overrides exceed typical API limits
        """
        if not self.override_enabled:
            return
        
        warnings = []
        
        # Check max_threads
        if 'max_threads' in self.custom_limits:
            max_threads = int(self.custom_limits['max_threads'])
            
            if max_threads < 1:
                warnings.append(
                    f"max_threads={max_threads} is invalid. Must be at least 1."
                )
            elif max_threads > self.TYPICAL_MAX_THREADS:
                warnings.append(
                    f"max_threads={max_threads} exceeds typical limit of "
                    f"{self.TYPICAL_MAX_THREADS}. This may result in API bans."
                )
        
        # Check requests_per_second
        if 'requests_per_second' in self.custom_limits:
            rps = float(self.custom_limits['requests_per_second'])
            
            if rps <= 0:
                warnings.append(
                    f"requests_per_second={rps} is invalid. Must be greater than 0."
                )
            elif rps > self.TYPICAL_REQUESTS_PER_SECOND:
                warnings.append(
                    f"requests_per_second={rps} exceeds typical limit of "
                    f"{self.TYPICAL_REQUESTS_PER_SECOND}. This may result in API bans."
                )
        
        # Check daily_quota
        if 'daily_quota' in self.custom_limits:
            quota = int(self.custom_limits['daily_quota'])
            
            if quota < 1:
                warnings.append(
                    f"daily_quota={quota} is invalid. Must be at least 1."
                )
            elif quota > self.TYPICAL_DAILY_QUOTA:
                warnings.append(
                    f"daily_quota={quota} exceeds typical limit of "
                    f"{self.TYPICAL_DAILY_QUOTA}. Verify your account has this quota."
                )
        
        # Log warnings
        if warnings:
            logger.warning("Rate limit override validation warnings:")
            for warning in warnings:
                logger.warning(f"  - {warning}")
            
            logger.warning(
                "Using aggressive overrides may result in temporary API bans. "
                "Proceed with caution."
            )
    
    def is_enabled(self) -> bool:
        """
        Check if rate limit override is enabled
        
        Returns:
            True if overrides are enabled
        """
        return self.override_enabled
    
    def get_override_summary(self) -> str:
        """
        Get human-readable summary of overrides
        
        Returns:
            Summary string
        """
        if not self.override_enabled:
            return "Rate limit overrides: DISABLED"
        
        lines = ["Rate limit overrides: ENABLED"]
        
        if 'max_threads' in self.custom_limits:
            lines.append(f"  - max_threads: {self.custom_limits['max_threads']}")
        
        if 'requests_per_second' in self.custom_limits:
            lines.append(
                f"  - requests_per_second: {self.custom_limits['requests_per_second']}"
            )
        
        if 'daily_quota' in self.custom_limits:
            lines.append(f"  - daily_quota: {self.custom_limits['daily_quota']}")
        
        return "\n".join(lines)
