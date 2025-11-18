"""ScreenScraper API client implementation."""

import logging
import requests
import time
from enum import Enum
from typing import Dict, Any, Optional
from urllib.parse import urlencode

from curateur.scanner.rom_types import ROMInfo
from curateur.api.system_map import get_systemeid
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
    
    def __init__(self, config: Dict[str, Any], throttle_manager: ThrottleManager, session: Optional[requests.Session] = None):
        """
        Initialize API client.
        
        Args:
            config: Configuration dictionary with screenscraper credentials
            throttle_manager: ThrottleManager instance for rate limiting
            session: Optional requests.Session for connection pooling
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
        
        # HTTP session (use provided or create new)
        self.session = session if session else requests.Session()
        
        # Throttle manager for rate limiting
        self.throttle_manager = throttle_manager
        
        # Track if we've extracted rate limits from API
        self._rate_limits_initialized = False
    
    def _build_redacted_url(self, url: str, params: Dict[str, Any]) -> str:
        """Build URL with credentials redacted for logging."""
        redacted_params = params.copy()
        redacted_params['devpassword'] = 'redacted'
        redacted_params['sspassword'] = 'redacted'
        query_string = urlencode(redacted_params)
        return f"{url}?{query_string}"
    
    def query_game(self, rom_info: ROMInfo) -> Optional[Dict[str, Any]]:
        """
        Query ScreenScraper for game information.
        
        Args:
            rom_info: ROM information from scanner
            
        Returns:
            Game data dictionary or None if not found
            
        Raises:
            FatalAPIError: For fatal errors requiring stop
            SkippableAPIError: For skippable errors (game not found, etc.)
        """
        # Get system ID
        try:
            systemeid = get_systemeid(rom_info.system)
        except KeyError as e:
            raise SkippableAPIError(f"Platform not mapped: {e}")
        
        # Build API request
        def make_request():
            return self._query_jeu_infos(
                systemeid=systemeid,
                romnom=rom_info.query_filename,
                romtaille=rom_info.file_size,
                crc=rom_info.crc32
            )
        
        # Execute with retry
        context = f"{rom_info.filename} ({rom_info.system.upper()})"
        
        try:
            game_data = retry_with_backoff(
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
                # Log verification failure
                print(format_verification_result(
                    rom_info.filename,
                    game_data['name'],
                    is_match,
                    similarity,
                    reason
                ))
                raise SkippableAPIError("Name verification failed")
        
        return game_data
    
    def _query_jeu_infos(
        self,
        systemeid: int,
        romnom: str,
        romtaille: int,
        crc: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Query jeuInfos.php endpoint.
        
        Args:
            systemeid: ScreenScraper system ID
            romnom: ROM filename
            romtaille: File size in bytes
            crc: CRC32 hash (optional)
            
        Returns:
            Parsed game data
            
        Raises:
            Various API errors
        """
        # Wait for rate limit
        self.rate_limiter.wait_if_needed()
        
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
            logger.debug(f"API Request: {redacted_url}")
        
        start_time = time.time()
        try:
            response = self.session.get(
                url,
                params=params,
                timeout=self.request_timeout
            )
        except requests.exceptions.Timeout:
            raise Exception("Request timeout")
        except requests.exceptions.ConnectionError:
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
        
        # Validate and parse response
        try:
            root = validate_response(response.content, expected_format='xml')
        except ResponseError as e:
            raise SkippableAPIError(f"Invalid response: {e}")
        
        # Check for API error message
        error_msg = extract_error_message(root)
        if error_msg:
            raise SkippableAPIError(f"API error: {error_msg}")
        
        # Update rate limits from first response (already handled by throttle_manager initialization)
        if not self._rate_limits_initialized:
            self._rate_limits_initialized = True
        
        # Parse game info
        try:
            game_data = parse_game_info(root)
        except ResponseError as e:
            raise SkippableAPIError(str(e))
        
        return game_data
    
    def search_game(
        self,
        rom_info: ROMInfo,
        max_results: int = 5
    ) -> list[Dict[str, Any]]:
        """
        Search for game by name using jeuRecherche.php endpoint.
        
        This is a fallback when hash-based lookup fails. Returns multiple
        candidates that should be scored for confidence.
        
        Args:
            rom_info: ROM information from scanner
            max_results: Maximum number of results to return
            
        Returns:
            List of game data dictionaries (may be empty)
            
        Raises:
            FatalAPIError: For fatal errors requiring stop
            SkippableAPIError: For skippable errors
        """
        # Get system ID
        try:
            systemeid = get_systemeid(rom_info.system)
        except KeyError as e:
            raise SkippableAPIError(f"Platform not mapped: {e}")
        
        # Build API request
        def make_request():
            return self._query_jeu_recherche(
                systemeid=systemeid,
                recherche=rom_info.query_filename,
                max_results=max_results
            )
        
        # Execute with retry
        context = f"Search: {rom_info.query_filename} ({rom_info.system.upper()})"
        
        try:
            results = retry_with_backoff(
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
    
    def _query_jeu_recherche(
        self,
        systemeid: int,
        recherche: str,
        max_results: int = 5
    ) -> list[Dict[str, Any]]:
        """
        Query jeuRecherche.php endpoint for text search.
        
        Args:
            systemeid: ScreenScraper system ID
            recherche: Search query (typically filename without extension)
            max_results: Maximum results to return
            
        Returns:
            List of parsed game data dictionaries
            
        Raises:
            Various API errors
        """
        # Wait for rate limit
        self.throttle_manager.wait_if_needed(APIEndpoint.JEU_RECHERCHE.value)
        
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
        
        start_time = time.time()
        try:
            response = self.session.get(
                url,
                params=params,
                timeout=self.request_timeout
            )
        except requests.exceptions.Timeout:
            raise Exception("Request timeout")
        except requests.exceptions.ConnectionError:
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
        
        # Validate and parse response
        try:
            root = validate_response(response.content, expected_format='xml')
        except ResponseError as e:
            raise SkippableAPIError(f"Invalid response: {e}")
        
        # Check for API error message
        error_msg = extract_error_message(root)
        if error_msg:
            raise SkippableAPIError(f"API error: {error_msg}")
        
        # Update rate limits from first response (already handled by throttle_manager initialization)
        if not self._rate_limits_initialized:
            self._rate_limits_initialized = True
        
        # Parse search results
        try:
            results = parse_search_results(root)
        except ResponseError as e:
            raise SkippableAPIError(str(e))
        
        return results
    
    def get_rate_limits(self) -> Dict[str, Any]:
        """
        Get current rate limit information.
        
        Returns:
            Dictionary with rate limit info from throttle manager
        """
        # Return stats for all endpoints
        return {
            endpoint.value: self.throttle_manager.get_stats(endpoint.value)
            for endpoint in APIEndpoint
        }
