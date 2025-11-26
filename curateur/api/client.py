"""ScreenScraper API client implementation."""

import asyncio
import logging
import httpx
import time
from enum import Enum
from typing import Dict, Any, Optional
from urllib.parse import urlencode

from curateur.scanner.rom_types import ROMInfo
from curateur.api.system_map import get_systemeid
from curateur.api.cache import MetadataCache
from curateur.api.error_handler import (
    handle_http_status,
    retry_with_backoff,
    FatalAPIError,
    SkippableAPIError
)
from curateur.api.throttle import ThrottleManager
from curateur.api.response_parser import (
    validate_response,
    parse_game_info,
    parse_search_results,
    parse_user_info,
    extract_error_message,
    ResponseError
)
from curateur.api.name_verifier import verify_name_match, format_verification_result

logger = logging.getLogger(__name__)


class APIEndpoint(Enum):
    """ScreenScraper API endpoints."""
    JEU_INFOS = 'jeuInfos.php'
    JEU_RECHERCHE = 'jeuRecherche.php'
    MEDIA_JEU = 'mediaJeu.php'


class ScreenScraperClient:
    """
    Client for ScreenScraper API.

    Handles authentication, rate limiting, and API requests.
    """

    BASE_URL = "https://api.screenscraper.fr/api2"

    def __init__(
        self,
        config: Dict[str, Any],
        throttle_manager: ThrottleManager,
        client: Optional[httpx.AsyncClient] = None,
        cache: Optional[MetadataCache] = None,
        connection_pool_manager: Optional[Any] = None
    ):
        """
        Initialize API client.

        Args:
            config: Configuration dictionary with screenscraper credentials
            throttle_manager: ThrottleManager instance for rate limiting
            client: Optional httpx.AsyncClient for connection pooling
            cache: Optional MetadataCache for response caching
            connection_pool_manager: Optional ConnectionPoolManager for health tracking
        """
        # Authentication
        self.devid = config['screenscraper']['devid']
        self.devpassword = config['screenscraper']['devpassword']
        self.softname = config['screenscraper']['softname']
        self.ssid = config['screenscraper']['user_id']
        self.sspassword = config['screenscraper']['user_password']

        # Configuration
        self.request_timeout = config.get('api', {}).get('request_timeout', 30)
        self.max_retries = config.get('api', {}).get('max_retries', 3)
        self.retry_backoff = config.get('api', {}).get('retry_backoff_seconds', 5)
        self.name_verification = config.get('scraping', {}).get('name_verification', 'normal')
        self._quota_warning_threshold = config.get('api', {}).get('quota_warning_threshold', 0.95)
        self._timeout = httpx.Timeout(
            connect=5.0,
            read=self.request_timeout,
            write=5.0,
            pool=5.0
        )

        # Scrape mode for cache behavior
        self.scrape_mode = config.get('scraping', {}).get('scrape_mode', 'changed')

        # HTTP client (use provided or None - caller must provide)
        self.client = client

        # Throttle manager for rate limiting
        self.throttle_manager = throttle_manager

        # Metadata cache (optional)
        self.cache = cache
        
        # Connection pool manager for health tracking (optional)
        self.connection_pool_manager = connection_pool_manager

        # Track if we've extracted rate limits from API
        self._rate_limits_initialized = False

        # Store user limits from API (maxthreads, etc.) with async-safe access
        self._user_limits: Optional[Dict[str, Any]] = None
        self._user_limits_lock = asyncio.Lock()

    def _build_redacted_url(self, url: str, params: Dict[str, Any]) -> str:
        """Build URL with credentials redacted for logging."""
        redacted_params = params.copy()
        redacted_params['devpassword'] = 'redacted'
        redacted_params['sspassword'] = 'redacted'
        query_string = urlencode(redacted_params)
        return f"{url}?{query_string}"

    async def query_game(
        self,
        rom_info: ROMInfo,
        shutdown_event: Optional[asyncio.Event] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Query ScreenScraper for game information.

        Args:
            rom_info: ROM information from scanner
            shutdown_event: Optional event to check for cancellation

        Returns:
            Game data dictionary or None if not found

        Raises:
            FatalAPIError: For fatal errors requiring stop
            SkippableAPIError: For skippable errors (game not found, etc.)
            asyncio.CancelledError: If shutdown is requested
        """
        # Check for shutdown before starting
        if shutdown_event and shutdown_event.is_set():
            raise asyncio.CancelledError("Shutdown requested")

        # Get system ID
        try:
            systemeid = get_systemeid(rom_info.system)
        except KeyError as e:
            raise SkippableAPIError(f"Platform not mapped: {e}")

        # Build API request
        async def make_request():
            return await self._query_jeu_infos(
                systemeid=systemeid,
                romnom=rom_info.query_filename,
                romtaille=rom_info.file_size,
                crc=rom_info.hash_value,
                shutdown_event=shutdown_event
            )

        # Execute with retry
        context = f"{rom_info.filename} ({rom_info.system.upper()})"

        try:
            game_data = await retry_with_backoff(
                make_request,
                max_attempts=self.max_retries,
                initial_delay=self.retry_backoff,
                backoff_factor=2.0,
                context=context
            )
        except (FatalAPIError, SkippableAPIError):
            raise
        except Exception as e:
            # Convert other errors to skippable
            raise SkippableAPIError(f"API error: {e}")

        # Verify game name matches ROM
        if game_data and 'name' in game_data:
            is_match, similarity, reason = verify_name_match(
                rom_info.filename,
                game_data['name'],
                threshold_mode=self.name_verification
            )

            if not is_match:
                # Log verification failure with formatted details
                print(format_verification_result(
                    rom_info.filename,
                    game_data['name'],
                    is_match,
                    similarity,
                    reason
                ))
                # Include API name in error message for logging
                raise SkippableAPIError(f"Name verification failed (API returned: '{game_data['name']}')")

        return game_data

    async def get_user_info(self) -> Dict[str, Any]:
        """
        Authenticate and get user information from ssuserInfos.php.

        This should be called before any processing to:
        1. Validate credentials and user access level
        2. Get maxthreads for thread pool sizing
        3. Get quota info for tracking and display

        Returns:
            User limits dict with maxthreads, maxrequestspermin, requeststoday, etc.

        Raises:
            SystemExit: If authentication fails or user level insufficient
        """
        # Wait for rate limit (though this is typically the first call)
        await self.throttle_manager.wait_if_needed('ssuserInfos.php')

        # Build parameters
        params = {
            'devid': self.devid,
            'devpassword': self.devpassword,
            'softname': self.softname,
            'ssid': self.ssid,
            'sspassword': self.sspassword,
            'output': 'xml'
        }

        # Make request
        url = f"{self.BASE_URL}/ssuserInfos.php"

        # Log request with redacted credentials
        if logger.isEnabledFor(logging.DEBUG):
            redacted_url = self._build_redacted_url(url, params)
            logger.debug(f"API Request (authentication): {redacted_url}")

        try:
            response = await self.client.get(
                url,
                params=params,
                timeout=self._timeout
            )
        except httpx.TimeoutException:
            logger.error("Authentication failed: Request timeout - network error, retry possible")
            if self.connection_pool_manager:
                if self.connection_pool_manager.record_timeout():
                    logger.warning("Connection pool health degraded, consider restarting")
            raise SystemExit(1)
        except httpx.ConnectError:
            logger.error("Authentication failed: Connection error - network error, retry possible")
            raise SystemExit(1)
        except Exception as e:
            logger.error(f"Authentication failed: Network error - {e}")
            raise SystemExit(1)

        # Check HTTP status
        if response.status_code == 401 or response.status_code == 403:
            logger.error("Authentication failed: Invalid credentials - check config.yaml user_id and user_password")
            raise SystemExit(1)
        elif response.status_code != 200:
            logger.error(f"Authentication failed: HTTP {response.status_code}")
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Response body: {response.text}")
            raise SystemExit(1)

        # Validate and parse response
        try:
            root = validate_response(response.content, expected_format='xml')
        except ResponseError as e:
            logger.error(f"Authentication failed: Invalid XML response - {e}")
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Response body: {response.text}")
            raise SystemExit(1)

        # Extract user info
        user_info = parse_user_info(root)
        if not user_info:
            logger.error("Authentication failed: No user info in response")
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"Response body: {response.text}")
            raise SystemExit(1)

        # Validate user level (niveau == 1 required for API access)
        niveau = user_info.get('niveau')
        if niveau != 1:
            logger.error(f"Authentication failed: User level {niveau} insufficient (niveau=1 required)")
            raise SystemExit(1)

        # Store user limits
        async with self._user_limits_lock:
            self._user_limits = user_info
            self._rate_limits_initialized = True

        # Log success with username
        username = user_info.get('id', 'unknown')
        logger.info(f"Authenticated as ScreenScraper user: {username}")
        logger.info(f"API limits: maxthreads={user_info.get('maxthreads')}, "
                   f"maxrequestsperday={user_info.get('maxrequestsperday')}, "
                   f"maxrequestspermin={user_info.get('maxrequestspermin')}")

        return user_info

    async def _query_jeu_infos(
        self,
        systemeid: int,
        romnom: str,
        romtaille: int,
        crc: Optional[str] = None,
        shutdown_event: Optional[asyncio.Event] = None
    ) -> Dict[str, Any]:
        """
        Query jeuInfos.php endpoint.

        Args:
            systemeid: ScreenScraper system ID
            romnom: ROM filename
            romtaille: File size in bytes
            crc: CRC32 hash (optional)
            shutdown_event: Optional event to check for cancellation

        Returns:
            Parsed game data

        Raises:
            Various API errors
            asyncio.CancelledError: If shutdown is requested
        """
                # Check cache first (unless scrape_mode is 'force')
        use_cache = self.cache and self.scrape_mode != 'force'
        if use_cache and crc:
            cached_entry = self.cache.get(crc, rom_size=romtaille)
            if cached_entry is not None:
                logger.debug(f"Cache hit for {romnom} (hash={crc})")
                return cached_entry.get('response')

        # Wait for rate limit
        await self.throttle_manager.wait_if_needed(APIEndpoint.JEU_INFOS.value)

        # Build parameters
        params = {
            'devid': self.devid,
            'devpassword': self.devpassword,
            'softname': self.softname,
            'ssid': self.ssid,
            'sspassword': self.sspassword,
            'output': 'xml',
            'systemeid': systemeid,
            'romnom': romnom,
            'romtaille': romtaille,
            'romtype': 'rom',
        }

        if crc:
            params['crc'] = crc

        # Make request
        url = f"{self.BASE_URL}/jeuInfos.php"

        # Log request URL with redacted credentials
        if logger.isEnabledFor(logging.DEBUG):
            redacted_url = self._build_redacted_url(url, params)
            logger.debug(f"API Request (search): {redacted_url}")

        # Check shutdown before making request
        if shutdown_event and shutdown_event.is_set():
            raise asyncio.CancelledError("Shutdown requested")

        # Acquire concurrency semaphore to limit concurrent API requests
        async with self.throttle_manager.concurrency_semaphore:
            start_time = time.time()
            try:
                # Create the HTTP request task that can be cancelled
                request_task = asyncio.create_task(
                    self.client.get(
                        url,
                        params=params,
                        timeout=self._timeout
                    )
                )

                # Wait for either completion or shutdown
                if shutdown_event:
                    # Race between request completion and shutdown
                    done, pending = await asyncio.wait(
                        [request_task],
                        return_when=asyncio.FIRST_COMPLETED,
                        timeout=0.1  # Check shutdown every 100ms
                    )

                    # Check for shutdown while waiting
                    while not done and not shutdown_event.is_set():
                        done, pending = await asyncio.wait(
                            [request_task],
                            return_when=asyncio.FIRST_COMPLETED,
                            timeout=0.1
                        )

                    if shutdown_event.is_set() and not done:
                        # Shutdown requested, cancel the request
                        request_task.cancel()
                        try:
                            await request_task
                        except asyncio.CancelledError:
                            # Expected when cancelling task during shutdown
                            pass
                        raise asyncio.CancelledError("Shutdown requested during API search")

                    response = await request_task
                else:
                    # No shutdown event, just wait for response
                    response = await request_task

            except asyncio.CancelledError:
                            # Expected when cancelling task during shutdown
                raise
            except httpx.TimeoutException:
                if self.connection_pool_manager:
                    if self.connection_pool_manager.record_timeout():
                        logger.warning("Multiple consecutive timeouts detected - resetting connection pool")
                        await self.connection_pool_manager.reset_client()
                        self.client = await self.connection_pool_manager.get_client()
                raise Exception("Request timeout")
            except httpx.ConnectError:
                if self.connection_pool_manager:
                    if self.connection_pool_manager.record_timeout():
                        logger.warning("Multiple consecutive connection errors - resetting connection pool")
                        await self.connection_pool_manager.reset_client()
                        self.client = await self.connection_pool_manager.get_client()
                raise Exception("Connection error")
            except Exception as e:
                raise Exception(f"Network error: {e}")

            elapsed_time = time.time() - start_time

            # Log response
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"API Response: {response.status_code} in {elapsed_time:.2f}s")

            # Handle HTTP status (pass throttle_manager for 429 handling)
            handle_http_status(
                response.status_code,
                context=romnom,
                throttle_manager=self.throttle_manager,
                endpoint=APIEndpoint.JEU_INFOS.value,
                retry_after=response.headers.get('Retry-After')
            )

            # Reset backoff on successful request
            if response.status_code == 200:
                self.throttle_manager.reset_backoff_multiplier(APIEndpoint.JEU_INFOS.value)
                # Record successful request for connection health tracking
                if self.connection_pool_manager:
                    self.connection_pool_manager.record_success()

            # Validate and parse response
            try:
                root = validate_response(response.content, expected_format='xml')
            except ResponseError as e:
                raise SkippableAPIError(f"Invalid response: {e}")

            # Check for API error message
            error_msg = extract_error_message(root)
            if error_msg:
                raise SkippableAPIError(f"API error: {error_msg}")

            # Extract and store user limits from response (async-safe with monotonic updates)
            new_user_info = parse_user_info(root)
            if new_user_info:
                async with self._user_limits_lock:
                    # First time initialization
                    if self._user_limits is None:
                        self._user_limits = new_user_info
                        self._rate_limits_initialized = True
                        logger.info(f"API user limits detected: {self._user_limits}")
                    # Monotonic update: only update if requeststoday increased (handle out-of-order responses)
                    elif 'requeststoday' in new_user_info:
                        new_requests = new_user_info.get('requeststoday', 0)
                        old_requests = self._user_limits.get('requeststoday', 0)
                        if new_requests > old_requests:
                            self._user_limits = new_user_info
                            logger.debug(f"API quota updated: {old_requests} -> {new_requests} requests today")

                # Update throttle manager quota tracking
                await self.throttle_manager.update_quota(new_user_info)

                # Check quota thresholds and log warnings if exceeded
                await self.throttle_manager.check_quota_threshold(self._quota_warning_threshold)

            # Parse game info
            try:
                game_data = parse_game_info(root)
            except ResponseError as e:
                raise SkippableAPIError(str(e))

            # Store in cache if enabled and we have a hash
            if use_cache and crc and game_data:
                self.cache.put(crc, game_data, rom_size=romtaille)
                logger.debug(f"Cached response for {romnom} (hash={crc}, size={romtaille})")

            return game_data

    async def search_game(
        self,
        rom_info: ROMInfo,
        shutdown_event: Optional[asyncio.Event] = None,
        max_results: int = 5
    ) -> list[Dict[str, Any]]:
        """
        Search for game by name using jeuRecherche.php endpoint.

        This is a fallback when hash-based lookup fails. Returns multiple
        candidates that should be scored for confidence.

        Args:
            rom_info: ROM information from scanner
            shutdown_event: Optional event to check for cancellation
            max_results: Maximum number of results to return

        Returns:
            List of game data dictionaries (may be empty)

        Raises:
            FatalAPIError: For fatal errors requiring stop
            SkippableAPIError: For skippable errors
            asyncio.CancelledError: If shutdown is requested
        """
        # Check for shutdown before starting
        if shutdown_event and shutdown_event.is_set():
            raise asyncio.CancelledError("Shutdown requested")

        # Get system ID
        try:
            systemeid = get_systemeid(rom_info.system)
        except KeyError as e:
            raise SkippableAPIError(f"Platform not mapped: {e}")

        # Build API request
        async def make_request():
            return await self._query_jeu_recherche(
                systemeid=systemeid,
                recherche=rom_info.query_filename,
                max_results=max_results,
                shutdown_event=shutdown_event
            )

        # Execute with retry
        context = f"Search: {rom_info.query_filename} ({rom_info.system.upper()})"

        try:
            results = await retry_with_backoff(
                make_request,
                max_attempts=self.max_retries,
                initial_delay=self.retry_backoff,
                backoff_factor=2.0,
                context=context
            )
            return results
        except (FatalAPIError, SkippableAPIError):
            raise
        except Exception as e:
            # Convert other errors to skippable
            raise SkippableAPIError(f"Search API error: {e}")

    async def _query_jeu_recherche(
        self,
        systemeid: int,
        recherche: str,
        max_results: int = 5,
        shutdown_event: Optional[asyncio.Event] = None
    ) -> list[Dict[str, Any]]:
        """
        Query jeuRecherche.php endpoint for text search.

        Args:
            systemeid: ScreenScraper system ID
            recherche: Search query (typically filename without extension)
            max_results: Maximum results to return
            shutdown_event: Optional event to check for cancellation

        Returns:
            List of parsed game data dictionaries

        Raises:
            Various API errors
            asyncio.CancelledError: If shutdown is requested
        """
        # Wait for rate limit
        await self.throttle_manager.wait_if_needed(APIEndpoint.JEU_RECHERCHE.value)

        # Build parameters
        params = {
            'devid': self.devid,
            'devpassword': self.devpassword,
            'softname': self.softname,
            'ssid': self.ssid,
            'sspassword': self.sspassword,
            'output': 'xml',
            'systemeid': systemeid,
            'recherche': recherche,
            'max': max_results,
        }

        # Make request
        url = f"{self.BASE_URL}/jeuRecherche.php"

        # Log request URL with redacted credentials
        if logger.isEnabledFor(logging.DEBUG):
            redacted_url = self._build_redacted_url(url, params)
            logger.debug(f"API Request: {redacted_url}")

        # Check shutdown before making request
        if shutdown_event and shutdown_event.is_set():
            raise asyncio.CancelledError("Shutdown requested")

        # Acquire concurrency semaphore to limit concurrent API requests
        async with self.throttle_manager.concurrency_semaphore:
            start_time = time.time()
            try:
                # Create the HTTP request task that can be cancelled
                request_task = asyncio.create_task(
                    self.client.get(
                        url,
                        params=params,
                        timeout=self._timeout
                    )
                )

                # Wait for either completion or shutdown
                if shutdown_event:
                    # Race between request completion and shutdown
                    done, pending = await asyncio.wait(
                        [request_task],
                        return_when=asyncio.FIRST_COMPLETED,
                        timeout=0.1  # Check shutdown every 100ms
                    )

                    # Check for shutdown while waiting
                    while not done and not shutdown_event.is_set():
                        done, pending = await asyncio.wait(
                            [request_task],
                            return_when=asyncio.FIRST_COMPLETED,
                            timeout=0.1
                        )

                    if shutdown_event.is_set() and not done:
                        # Shutdown requested, cancel the request
                        request_task.cancel()
                        try:
                            await request_task
                        except asyncio.CancelledError:
                            # Expected when cancelling task during shutdown
                            pass
                        raise asyncio.CancelledError("Shutdown requested during API search")

                    response = await request_task
                else:
                    # No shutdown event, just wait for response
                    response = await request_task

            except asyncio.CancelledError:
                            # Expected when cancelling task during shutdown
                raise
            except httpx.TimeoutException:
                if self.connection_pool_manager:
                    if self.connection_pool_manager.record_timeout():
                        logger.warning("Multiple consecutive timeouts detected - resetting connection pool")
                        await self.connection_pool_manager.reset_client()
                        self.client = await self.connection_pool_manager.get_client()
                raise Exception("Request timeout")
            except httpx.ConnectError:
                if self.connection_pool_manager:
                    if self.connection_pool_manager.record_timeout():
                        logger.warning("Multiple consecutive connection errors - resetting connection pool")
                        await self.connection_pool_manager.reset_client()
                        self.client = await self.connection_pool_manager.get_client()
                raise Exception("Connection error")
            except Exception as e:
                raise Exception(f"Network error: {e}")

            elapsed_time = time.time() - start_time

            # Log response
            if logger.isEnabledFor(logging.DEBUG):
                logger.debug(f"API Response: {response.status_code} in {elapsed_time:.2f}s")

            # Handle HTTP status (pass throttle_manager for 429 handling)
            handle_http_status(
                response.status_code,
                context=f"search:{recherche}",
                throttle_manager=self.throttle_manager,
                endpoint=APIEndpoint.JEU_RECHERCHE.value,
                retry_after=response.headers.get('Retry-After')
            )

            # Reset backoff on successful request
            if response.status_code == 200:
                self.throttle_manager.reset_backoff_multiplier(APIEndpoint.JEU_RECHERCHE.value)
                # Record successful request for connection health tracking
                if self.connection_pool_manager:
                    self.connection_pool_manager.record_success()

            # Validate and parse response
            try:
                root = validate_response(response.content, expected_format='xml')
            except ResponseError as e:
                raise SkippableAPIError(f"Invalid response: {e}")

            # Check for API error message
            error_msg = extract_error_message(root)
            if error_msg:
                raise SkippableAPIError(f"API error: {error_msg}")

            # Extract and store user limits from response (async-safe with monotonic updates)
            new_user_info = parse_user_info(root)
            if new_user_info:
                async with self._user_limits_lock:
                    # First time initialization
                    if self._user_limits is None:
                        self._user_limits = new_user_info
                        self._rate_limits_initialized = True
                        logger.info(f"API user limits detected: {self._user_limits}")
                    # Monotonic update: only update if requeststoday increased (handle out-of-order responses)
                    elif 'requeststoday' in new_user_info:
                        new_requests = new_user_info.get('requeststoday', 0)
                        old_requests = self._user_limits.get('requeststoday', 0)
                        if new_requests > old_requests:
                            self._user_limits = new_user_info
                            logger.debug(f"API quota updated: {old_requests} -> {new_requests} requests today")

            # Parse search results
            try:
                results = parse_search_results(root)
            except ResponseError as e:
                raise SkippableAPIError(str(e))

            return results

    def get_user_limits(self) -> Optional[Dict[str, Any]]:
        """
        Get API-provided user limits (maxthreads, maxrequestspermin, etc.).

        This information is available after get_user_info() or first API call.

        Returns:
            Dictionary with user limits from API, or None if not yet initialized
            Expected keys: maxthreads, maxrequestspermin, maxrequestsperday, requeststoday,
                          requestskotoday, maxrequestskoperday
        """
        return self._user_limits
