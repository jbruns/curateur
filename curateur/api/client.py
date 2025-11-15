"""ScreenScraper API client implementation."""

import requests
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
from curateur.api.rate_limiter import RateLimiter
from curateur.api.response_parser import (
    validate_response,
    parse_game_info,
    parse_user_info,
    extract_error_message,
    ResponseError
)
from curateur.api.name_verifier import verify_name_match, format_verification_result


class ScreenScraperClient:
    """
    Client for ScreenScraper API.
    
    Handles authentication, rate limiting, and API requests.
    """
    
    BASE_URL = "https://api.screenscraper.fr/api2"
    
    def __init__(self, config: Dict[str, Any]):
        """
        Initialize API client.
        
        Args:
            config: Configuration dictionary with screenscraper credentials
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
        
        # Rate limiter (will be updated from first API response)
        self.rate_limiter = RateLimiter()
        
        # Track if we've extracted rate limits from API
        self._rate_limits_initialized = False
    
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
        
        try:
            response = requests.get(
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
        
        # Handle HTTP status
        handle_http_status(response.status_code, context=romnom)
        
        # Validate and parse response
        try:
            root = validate_response(response.content, expected_format='xml')
        except ResponseError as e:
            raise SkippableAPIError(f"Invalid response: {e}")
        
        # Check for API error message
        error_msg = extract_error_message(root)
        if error_msg:
            raise SkippableAPIError(f"API error: {error_msg}")
        
        # Update rate limits from first response
        if not self._rate_limits_initialized:
            user_info = parse_user_info(root)
            if user_info:
                self.rate_limiter.update_from_api(user_info)
                self._rate_limits_initialized = True
        
        # Parse game info
        try:
            game_data = parse_game_info(root)
        except ResponseError as e:
            raise SkippableAPIError(str(e))
        
        return game_data
    
    def get_rate_limits(self) -> Dict[str, Any]:
        """
        Get current rate limit information.
        
        Returns:
            Dictionary with rate limit info
        """
        return self.rate_limiter.get_limits()
