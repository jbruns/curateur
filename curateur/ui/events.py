"""Event types for UI updates.

This module defines all event types that flow from the scraping engine to the UI.
Events are immutable dataclasses that carry state updates from the workflow
orchestrator to the Textual UI.
"""

from dataclasses import dataclass
from typing import Optional, Literal
from datetime import datetime


@dataclass(frozen=True)
class SystemStartedEvent:
    """Emitted when a system scraping begins.

    Attributes:
        system_name: Short system name (e.g., 'nes')
        system_fullname: Full system name (e.g., 'Nintendo Entertainment System')
        total_roms: Total number of ROMs to process in this system
        current_index: Index of this system (0-based)
        total_systems: Total number of systems being scraped
    """
    system_name: str
    system_fullname: str
    total_roms: int
    current_index: int
    total_systems: int


@dataclass(frozen=True)
class ROMProgressEvent:
    """Emitted for ROM-level progress updates.

    Attributes:
        rom_name: ROM filename
        system: System short name
        status: Current processing status
        detail: Optional detail message (e.g., error description)
        progress: Optional progress percentage (0.0-1.0)
    """
    rom_name: str
    system: str
    status: Literal['scanning', 'hashing', 'querying', 'downloading', 'complete', 'failed', 'skipped']
    detail: Optional[str] = None
    progress: Optional[float] = None


@dataclass(frozen=True)
class HashingProgressEvent:
    """Emitted during batch ROM hashing.

    Attributes:
        completed: Number of ROMs hashed so far
        total: Total number of ROMs to hash
        in_progress: Whether hashing is currently active
        skipped: Number of ROMs skipped (e.g., too large)
    """
    completed: int
    total: int
    in_progress: bool
    skipped: int = 0


@dataclass(frozen=True)
class APIActivityEvent:
    """Emitted for API request activity tracking.

    Attributes:
        metadata_in_flight: Number of active metadata queries
        metadata_total: Total metadata queries completed
        search_in_flight: Number of active search queries
        search_total: Total search queries completed
    """
    metadata_in_flight: int
    metadata_total: int
    search_in_flight: int
    search_total: int


@dataclass(frozen=True)
class MediaDownloadEvent:
    """Emitted for media download progress.

    Attributes:
        media_type: Type of media (e.g., 'box-2D', 'screenshot')
        rom_name: ROM filename being processed
        status: Download status
        progress: Optional download progress (0.0-1.0)
    """
    media_type: str
    rom_name: str
    status: Literal['downloading', 'complete', 'failed']
    progress: Optional[float] = None


@dataclass(frozen=True)
class LogEntryEvent:
    """Emitted for log messages.

    Attributes:
        level: Logging level (logging.DEBUG, INFO, WARNING, ERROR, CRITICAL)
        message: Formatted log message
        timestamp: When the log was generated
    """
    level: int
    message: str
    timestamp: datetime


@dataclass(frozen=True)
class PerformanceUpdateEvent:
    """Emitted periodically with performance metrics.

    Attributes:
        api_quota_used: API requests used today
        api_quota_limit: Daily API request limit
        threads_in_use: Currently active worker threads
        threads_limit: Maximum allowed threads
        throughput_history: Recent throughput samples (ROMs/hour)
        api_rate_history: Recent API rate samples (calls/minute)
        cache_hit_rate: Optional cache hit rate percentage (0.0-1.0)
    """
    api_quota_used: int
    api_quota_limit: int
    threads_in_use: int
    threads_limit: int
    throughput_history: list[int]
    api_rate_history: list[int]
    cache_hit_rate: Optional[float] = None


@dataclass(frozen=True)
class GameCompletedEvent:
    """Event emitted when a game is successfully scraped and added to gamelist."""
    game_id: str
    title: str
    year: Optional[str] = None
    genre: Optional[str] = None
    developer: Optional[str] = None
    publisher: Optional[str] = None
    players: Optional[str] = None
    rating: Optional[float] = None
    description: Optional[str] = None


@dataclass(frozen=True)
class SystemCompletedEvent:
    """Emitted when a system scraping completes.

    Attributes:
        system_name: Short system name
        total_roms: Total ROMs processed
        successful: Number of successful matches
        failed: Number of failures
        skipped: Number of ROMs skipped
        elapsed_time: Optional processing time in seconds
    """
    system_name: str
    total_roms: int
    successful: int
    failed: int
    skipped: int
    elapsed_time: Optional[float] = None


@dataclass(frozen=True)
class ActiveRequestEvent:
    """Emitted for tracking active API requests.

    Attributes:
        request_id: Unique request identifier
        rom_name: ROM being queried
        stage: Request stage ('API Fetch', 'Search', 'Media DL')
        status: Request status ('Active', 'Retrying', 'Complete', 'Failed')
        duration: Request duration in seconds
        retry_count: Number of retry attempts
        last_failure: Last failure reason (if any)
    """
    request_id: str
    rom_name: str
    stage: Literal['API Fetch', 'Search', 'Media DL', 'Hashing']
    status: Literal['Active', 'Retrying', 'Complete', 'Failed']
    duration: float
    retry_count: int = 0
    last_failure: Optional[str] = None


@dataclass(frozen=True)
class SearchRequestEvent:
    """Emitted when interactive search is needed.

    Attributes:
        request_id: Unique identifier for this search request
        rom_name: ROM filename requiring manual match
        rom_path: Full path to ROM file
        system: System name
        search_results: List of scored candidates from search
            Each candidate is dict with: {"game_data": {...}, "confidence": 0.XX}
    """
    request_id: str
    rom_name: str
    rom_path: str
    system: str
    search_results: list[dict]


@dataclass(frozen=True)
class SearchResponseEvent:
    """Emitted when user responds to search prompt.

    Attributes:
        request_id: ID matching the SearchRequestEvent
        action: User's choice ('selected', 'skip', 'cancel')
        selected_game: Game data if action='selected', None otherwise
    """
    request_id: str
    action: Literal['selected', 'skip', 'cancel']
    selected_game: Optional[dict] = None


@dataclass(frozen=True)
class CacheMetricsEvent:
    """Emitted for cache metrics tracking.

    Attributes:
        existing: Cache entries loaded at startup
        added: New cache entries added this session
        hits: Total cache hits
        misses: Total cache misses
        hit_rate: Cache hit rate percentage (0.0-100.0)
    """
    existing: int
    added: int
    hits: int
    misses: int
    hit_rate: float


@dataclass(frozen=True)
class GamelistUpdateEvent:
    """Emitted for gamelist update tracking.

    Attributes:
        system: System short name
        existing: Existing entries in gamelist at start
        added: New entries added this session
        updated: Existing entries updated this session
    """
    system: str
    existing: int
    added: int
    updated: int


@dataclass(frozen=True)
class AuthenticationEvent:
    """Emitted for authentication status updates.

    Attributes:
        status: Authentication status
        username: Logged in username (None if authenticating/failed)
    """
    status: Literal['authenticating', 'authenticated', 'failed']
    username: Optional[str] = None


@dataclass(frozen=True)
class SearchActivityEvent:
    """Emitted for search fallback and unmatched ROM tracking.

    Attributes:
        fallback_count: Number of times search fallback was used
        unmatched_count: Number of ROMs that could not be matched
    """
    fallback_count: int
    unmatched_count: int


@dataclass(frozen=True)
class MediaStatsEvent:
    """Emitted for media download statistics.

    Attributes:
        by_type: Per-media-type breakdown {'box-2D': {'successful': N, 'failed': M}, ...}
        total_validated: Total media files validated (already existed)
        total_skipped: Total media downloads skipped
        total_failed: Total media downloads failed
    """
    by_type: dict
    total_validated: int
    total_skipped: int
    total_failed: int


@dataclass(frozen=True)
class ProcessingSummaryEvent:
    """Emitted with categorized processing results (mirrors summary log format).

    Provides real-time view of results breakdown matching what will be written
    to the summary log file.

    Attributes:
        successful: List of successful ROM filenames
        skipped: List of tuples (filename, skip_reason)
        failed: List of tuples (filename, error_message)
    """
    successful: list[str]
    skipped: list[tuple[str, str]]
    failed: list[tuple[str, str]]
