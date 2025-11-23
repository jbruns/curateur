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
    requests_per_minute: int
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
        runtime:
          rate_limit_override_enabled: false
          rate_limit_override:
            max_threads: 4
            requests_per_minute: 120
            daily_quota: 10000
    
    Example:
        override = RateLimitOverride(config)
        
        # Get effective limits (API + overrides)
        limits = override.get_effective_limits(api_provided_limits)
        
        # Use limits for rate limiting
        rate_limiter.configure(
            max_threads=limits.max_threads,
            requests_per_minute=limits.requests_per_minute
        )
    """
    
    # Default conservative limits (used as fallback)
    DEFAULT_MAX_THREADS = 1
    DEFAULT_REQUESTS_PER_MINUTE = 60
    DEFAULT_DAILY_QUOTA = 10000
    
    # Typical API limits (for warning purposes)
    TYPICAL_MAX_THREADS = 4
    TYPICAL_REQUESTS_PER_MINUTE = 120
    TYPICAL_DAILY_QUOTA = 20000
    
    def __init__(self, config: dict):
        """
        Initialize rate limit override
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.override_enabled = config.get('runtime', {}).get(
            'rate_limit_override_enabled', False
        )
        self.custom_limits = config.get('runtime', {}).get(
            'rate_limit_override', {}
        )
        
        # Validate on initialization
        if self.override_enabled:
            self.validate_overrides()
    
    def get_effective_limits(self, api_provided_limits: Optional[Dict[str, Any]]) -> RateLimits:
        """
        Merge API-provided limits with user overrides
        
        Rules:
        1. API limits are authoritative upper bounds
        2. User overrides can only reduce limits, not exceed API limits
        3. If user tries to exceed API limit: log warning and cap at API limit
        4. If user sets lower limit than API: log warning and honor user's choice
        
        Args:
            api_provided_limits: dict with API response fields:
                - maxthreads: int
                - maxrequestspermin: int
                - maxrequestsperday: int
        
        Returns:
            RateLimits with effective configuration
        
        Example:
            # API provides: maxthreads=4, maxrequestspermin=120
            # Override: max_threads=2 (conservative) - accepted
            # Override: max_threads=8 (too high) - capped at 4 with warning
        """
        # Start with defaults
        max_threads = self.DEFAULT_MAX_THREADS
        requests_per_minute = self.DEFAULT_REQUESTS_PER_MINUTE
        daily_quota = self.DEFAULT_DAILY_QUOTA
        
        # Track API limits for override validation
        api_max_threads = None
        api_max_rpm = None
        api_max_daily = None
        
        # Apply API-provided limits if available
        if api_provided_limits:
            if 'maxthreads' in api_provided_limits:
                api_max_threads = int(api_provided_limits['maxthreads'])
                max_threads = api_max_threads
                logger.debug(f"API max_threads: {max_threads}")
            
            if 'maxrequestspermin' in api_provided_limits:
                api_max_rpm = int(api_provided_limits['maxrequestspermin'])
                requests_per_minute = api_max_rpm
                logger.debug(f"API requests_per_minute: {requests_per_minute}")
            
            if 'maxrequestsperday' in api_provided_limits:
                api_max_daily = int(api_provided_limits['maxrequestsperday'])
                daily_quota = api_max_daily
                logger.debug(f"API daily_quota: {daily_quota}")
        
        # Apply user overrides if enabled (with API limit enforcement)
        if self.override_enabled:
            if 'max_threads' in self.custom_limits:
                override_threads = int(self.custom_limits['max_threads'])
                
                if api_max_threads is not None:
                    if override_threads > api_max_threads:
                        logger.warning(
                            f"Override max_threads={override_threads} exceeds API limit={api_max_threads}. "
                            f"Capping at API limit to comply with ScreenScraper terms."
                        )
                        max_threads = api_max_threads
                    elif override_threads < api_max_threads:
                        logger.warning(
                            f"Override max_threads={override_threads} is lower than API limit={api_max_threads}. "
                            f"Using conservative user setting."
                        )
                        max_threads = override_threads
                    else:
                        max_threads = override_threads
                else:
                    logger.info(f"Using override max_threads: {override_threads} (no API limit available)")
                    max_threads = override_threads
            
            if 'requests_per_minute' in self.custom_limits:
                override_rpm = int(self.custom_limits['requests_per_minute'])
                
                if api_max_rpm is not None:
                    if override_rpm > api_max_rpm:
                        logger.warning(
                            f"Override requests_per_minute={override_rpm} exceeds API limit={api_max_rpm}. "
                            f"Capping at API limit to comply with ScreenScraper terms."
                        )
                        requests_per_minute = api_max_rpm
                    elif override_rpm < api_max_rpm:
                        logger.warning(
                            f"Override requests_per_minute={override_rpm} is lower than API limit={api_max_rpm}. "
                            f"Using conservative user setting."
                        )
                        requests_per_minute = override_rpm
                    else:
                        requests_per_minute = override_rpm
                else:
                    logger.info(f"Using override requests_per_minute: {override_rpm} (no API limit available)")
                    requests_per_minute = override_rpm
            
            if 'daily_quota' in self.custom_limits:
                override_quota = int(self.custom_limits['daily_quota'])
                
                if api_max_daily is not None:
                    if override_quota > api_max_daily:
                        logger.warning(
                            f"Override daily_quota={override_quota} exceeds API limit={api_max_daily}. "
                            f"Capping at API limit to comply with ScreenScraper terms."
                        )
                        daily_quota = api_max_daily
                    elif override_quota < api_max_daily:
                        logger.warning(
                            f"Override daily_quota={override_quota} is lower than API limit={api_max_daily}. "
                            f"Using conservative user setting."
                        )
                        daily_quota = override_quota
                    else:
                        daily_quota = override_quota
                else:
                    logger.info(f"Using override daily_quota: {override_quota} (no API limit available)")
                    daily_quota = override_quota
        
        return RateLimits(
            max_threads=max_threads,
            requests_per_minute=requests_per_minute,
            daily_quota=daily_quota
        )
    
    def validate_overrides(self) -> None:
        """
        Validate override configuration
        Warn about configuration issues
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
        
        # Check requests_per_minute
        if 'requests_per_minute' in self.custom_limits:
            rpm = int(self.custom_limits['requests_per_minute'])
            
            if rpm <= 0:
                warnings.append(
                    f"requests_per_minute={rpm} is invalid. Must be greater than 0."
                )
            elif rpm > self.TYPICAL_REQUESTS_PER_MINUTE:
                warnings.append(
                    f"requests_per_minute={rpm} exceeds typical limit of "
                    f"{self.TYPICAL_REQUESTS_PER_MINUTE}. May be capped by API."
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
        
        if 'requests_per_minute' in self.custom_limits:
            lines.append(
                f"  - requests_per_minute: {self.custom_limits['requests_per_minute']}"
            )
        
        if 'daily_quota' in self.custom_limits:
            lines.append(f"  - daily_quota: {self.custom_limits['daily_quota']}")
        
        return "\n".join(lines)
