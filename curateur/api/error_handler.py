"""Unified error handling for ScreenScraper API interactions."""

from typing import Optional, Dict, Any, Tuple, Callable, Awaitable, Union
from enum import Enum
import asyncio
import time
import logging
import sys

logger = logging.getLogger(__name__)


class ErrorCategory(Enum):
    """Categorize errors for selective retry logic."""
    RETRYABLE = "retryable"        # 429, 5xx, network - should retry
    NOT_FOUND = "not_found"        # 404 - track separately, don't retry
    NON_RETRYABLE = "non_retryable"  # 400 - don't retry
    FATAL = "fatal"                # 403, auth - halt execution


class APIError(Exception):
    """Base exception for API errors."""
    pass


class FatalAPIError(APIError):
    """Fatal API error requiring immediate stop."""
    pass


class RetryableAPIError(APIError):
    """Retryable API error (rate limits, transient failures)."""
    pass


class SkippableAPIError(APIError):
    """Non-fatal error, skip item and continue."""
    pass


# HTTP status code mapping
HTTP_STATUS_MESSAGES = {
    200: "Success",
    400: "Malformed request",
    401: "API closed for non-members (server overload)",
    403: "Invalid credentials",
    404: "Game not found",
    423: "API fully closed",
    426: "Software blacklisted",
    429: "Thread limit reached",
    430: "Daily quota exceeded",
    431: "Too many not-found requests",
}


def get_error_message(status_code: int) -> str:
    """
    Get user-friendly error message for HTTP status code.
    
    Args:
        status_code: HTTP status code
        
    Returns:
        Error message string
    """
    return HTTP_STATUS_MESSAGES.get(
        status_code, 
        f"Unknown error (HTTP {status_code})"
    )


def handle_http_status(
    status_code: int,
    context: str = "",
    throttle_manager: Optional[Any] = None,
    endpoint: Optional[str] = None,
    retry_after: Optional[int] = None
) -> None:
    """
    Handle HTTP status code and raise appropriate exception.
    
    Args:
        status_code: HTTP status code from API
        context: Additional context for error message
        throttle_manager: Optional ThrottleManager for 429 handling
        endpoint: Optional endpoint name for throttle tracking
        retry_after: Optional Retry-After header value
        
    Raises:
        FatalAPIError: For fatal errors (403, 423, 426, 430)
        RetryableAPIError: For retryable errors (401, 429)
        SkippableAPIError: For skippable errors (400, 404, 431)
    """
    msg = get_error_message(status_code)
    if context:
        msg = f"{msg} ({context})"
    
    # Handle 429 with throttle manager if provided
    if status_code == 429 and throttle_manager and endpoint:
        throttle_manager.handle_rate_limit(endpoint, retry_after)
    
    # Fatal errors - stop execution
    if status_code == 403:
        # Authentication failure - critical halt
        logger.critical("Authentication failure - halting execution")
        sys.exit(1)
    elif status_code in [423, 426, 430]:
        raise FatalAPIError(msg)
    
    # Retryable errors - wait and retry
    elif status_code in [401, 429]:
        raise RetryableAPIError(msg)
    
    # Skippable errors - skip ROM and continue
    elif status_code in [400, 404, 431]:
        raise SkippableAPIError(msg)
    
    # Unexpected error
    elif status_code != 200:
        raise APIError(msg)


def categorize_error(exception: Exception) -> Tuple[Exception, ErrorCategory]:
    """
    Categorize an error for selective retry logic.
    
    Args:
        exception: Exception to categorize
        
    Returns:
        Tuple of (exception, ErrorCategory)
    """
    # Fatal errors - halt execution
    if isinstance(exception, FatalAPIError):
        return (exception, ErrorCategory.FATAL)
    
    # Check for 404 (not found) - track separately
    error_str = str(exception).lower()
    if isinstance(exception, SkippableAPIError) and ('not found' in error_str or '404' in error_str):
        return (exception, ErrorCategory.NOT_FOUND)
    
    # Non-retryable skippable errors (e.g., 400 malformed request)
    if isinstance(exception, SkippableAPIError):
        return (exception, ErrorCategory.NON_RETRYABLE)
    
    # Retryable errors (429, 5xx, network issues)
    if isinstance(exception, RetryableAPIError):
        return (exception, ErrorCategory.RETRYABLE)
    
    # Check for network-related exceptions
    retryable_keywords = ['timeout', 'connection', 'network', 'temporary', 'unavailable', '5']
    if any(keyword in error_str for keyword in retryable_keywords):
        return (exception, ErrorCategory.RETRYABLE)
    
    # Default to non-retryable
    return (exception, ErrorCategory.NON_RETRYABLE)


async def retry_with_backoff(
    func: Union[Callable, Callable[[], Awaitable]],
    max_attempts: int = 3,
    initial_delay: float = 5.0,
    backoff_factor: float = 2.0,
    context: str = ""
):
    """
    Retry a function with exponential backoff using selective retry logic.
    
    Supports both sync and async functions. For async functions, uses asyncio.sleep()
    for better responsiveness.
    
    Args:
        func: Function to retry (sync or async)
        max_attempts: Maximum number of attempts
        initial_delay: Initial delay in seconds
        backoff_factor: Multiplier for each retry
        context: Context string for error messages
        
    Returns:
        Function result if successful
        
    Raises:
        Last exception if all retries fail or if error is FATAL/NOT_FOUND/NON_RETRYABLE
    """
    delay = initial_delay
    last_exception = None
    is_async = asyncio.iscoroutinefunction(func)
    
    for attempt in range(1, max_attempts + 1):
        try:
            if is_async:
                return await func()
            else:
                return func()
        except Exception as e:
            # Categorize the error
            exception, category = categorize_error(e)
            last_exception = exception
            
            # Fatal errors - propagate immediately
            if category == ErrorCategory.FATAL:
                raise exception
            
            # Not found errors - don't retry, propagate immediately
            if category == ErrorCategory.NOT_FOUND:
                raise exception
            
            # Non-retryable errors - don't retry, propagate immediately
            if category == ErrorCategory.NON_RETRYABLE:
                raise exception
            
            # Retryable errors - retry with backoff
            if category == ErrorCategory.RETRYABLE:
                if attempt < max_attempts:
                    print(f"  ⚠ {context}: {exception}")
                    print(f"  ⏳ Retrying in {delay:.1f}s (attempt {attempt}/{max_attempts})...")
                    # Use async sleep if we're in async context for better UI responsiveness
                    if is_async:
                        await asyncio.sleep(delay)
                    else:
                        # Sleep in small chunks to keep UI responsive for sync calls
                        remaining = delay
                        while remaining > 0:
                            chunk = min(remaining, 0.1)  # 100ms chunks
                            time.sleep(chunk)
                            remaining -= chunk
                    delay *= backoff_factor
                else:
                    print(f"  ✗ {context}: Failed after {max_attempts} attempts")
    
    # All retries exhausted
    if last_exception:
        raise last_exception
    else:
        raise APIError(f"Failed after {max_attempts} attempts")


def is_retryable_error(error: Exception) -> bool:
    """
    Check if an error should be retried.
    
    Args:
        error: Exception to check
        
    Returns:
        True if error is retryable
    """
    if isinstance(error, RetryableAPIError):
        return True
    
    # Check for network-related errors
    error_str = str(error).lower()
    retryable_keywords = [
        'timeout', 'connection', 'network', 
        'temporary', 'unavailable'
    ]
    
    return any(keyword in error_str for keyword in retryable_keywords)
