"""Unified error handling for ScreenScraper API interactions."""

from typing import Optional, Dict, Any
import time


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


def handle_http_status(status_code: int, context: str = "") -> None:
    """
    Handle HTTP status code and raise appropriate exception.
    
    Args:
        status_code: HTTP status code from API
        context: Additional context for error message
        
    Raises:
        FatalAPIError: For fatal errors (403, 423, 426, 430)
        RetryableAPIError: For retryable errors (401, 429)
        SkippableAPIError: For skippable errors (400, 404, 431)
    """
    msg = get_error_message(status_code)
    if context:
        msg = f"{msg} ({context})"
    
    # Fatal errors - stop execution
    if status_code in [403, 423, 426, 430]:
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


def retry_with_backoff(
    func,
    max_attempts: int = 3,
    initial_delay: float = 5.0,
    backoff_factor: float = 2.0,
    context: str = ""
):
    """
    Retry a function with exponential backoff.
    
    Args:
        func: Function to retry
        max_attempts: Maximum number of attempts
        initial_delay: Initial delay in seconds
        backoff_factor: Multiplier for each retry
        context: Context string for error messages
        
    Returns:
        Function result if successful
        
    Raises:
        Last exception if all retries fail
    """
    delay = initial_delay
    last_exception = None
    
    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except RetryableAPIError as e:
            last_exception = e
            if attempt < max_attempts:
                print(f"  ⚠ {context}: {e}")
                print(f"  ⏳ Retrying in {delay:.1f}s (attempt {attempt}/{max_attempts})...")
                time.sleep(delay)
                delay *= backoff_factor
            else:
                print(f"  ✗ {context}: Failed after {max_attempts} attempts")
        except (FatalAPIError, SkippableAPIError):
            # Don't retry fatal or skippable errors
            raise
        except Exception as e:
            # Network errors or other exceptions
            last_exception = e
            if attempt < max_attempts:
                print(f"  ⚠ {context}: Network error: {e}")
                print(f"  ⏳ Retrying in {delay:.1f}s (attempt {attempt}/{max_attempts})...")
                time.sleep(delay)
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
