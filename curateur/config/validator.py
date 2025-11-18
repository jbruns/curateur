"""Configuration validation."""

from pathlib import Path
from typing import Dict, Any, List


class ValidationError(Exception):
    """Configuration validation errors."""
    pass


def validate_config(config: Dict[str, Any]) -> None:
    """
    Validate configuration structure and values.
    
    Args:
        config: Configuration dictionary from loader
        
    Raises:
        ValidationError: If configuration is invalid
    """
    errors = []
    
    # Validate screenscraper section
    errors.extend(_validate_screenscraper(config.get('screenscraper', {})))
    
    # Validate paths section
    errors.extend(_validate_paths(config.get('paths', {})))
    
    # Validate scraping section
    errors.extend(_validate_scraping(config.get('scraping', {})))
    
    # Validate api section
    errors.extend(_validate_api(config.get('api', {})))
    
    # Validate logging section
    errors.extend(_validate_logging(config.get('logging', {})))
    
    # Validate runtime section
    errors.extend(_validate_runtime(config.get('runtime', {})))
    
    # Validate search section
    errors.extend(_validate_search(config.get('search', {})))
    
    if errors:
        raise ValidationError(
            "Configuration validation failed:\n  - " + "\n  - ".join(errors)
        )


def _validate_screenscraper(section: Dict[str, Any]) -> List[str]:
    """Validate screenscraper credentials section."""
    errors = []
    
    # Check required user credentials
    if not section.get('user_id'):
        errors.append("screenscraper.user_id is required")
    if not section.get('user_password'):
        errors.append("screenscraper.user_password is required")
    
    # Developer credentials should be present (added by loader)
    if not section.get('devid'):
        errors.append("screenscraper.devid missing (internal error)")
    if not section.get('devpassword'):
        errors.append("screenscraper.devpassword missing (internal error)")
    if not section.get('softname'):
        errors.append("screenscraper.softname missing (internal error)")
    
    return errors


def _validate_paths(section: Dict[str, Any]) -> List[str]:
    """Validate paths section."""
    errors = []
    
    # Check required paths
    required_paths = ['roms', 'media', 'gamelists', 'es_systems']
    for path_key in required_paths:
        if not section.get(path_key):
            errors.append(f"paths.{path_key} is required")
        else:
            path = Path(section[path_key]).expanduser()
            
            # Check es_systems.xml exists
            if path_key == 'es_systems':
                if not path.exists():
                    errors.append(f"paths.es_systems file not found: {path}")
                elif not path.is_file():
                    errors.append(f"paths.es_systems must be a file: {path}")
    
    return errors


def _validate_scraping(section: Dict[str, Any]) -> List[str]:
    """Validate scraping options section."""
    errors = []
    
    # Validate systems list
    systems = section.get('systems', [])
    if not isinstance(systems, list):
        errors.append("scraping.systems must be a list")
    
    # Validate media_types
    media_types = section.get('media_types', [])
    if not isinstance(media_types, list):
        errors.append("scraping.media_types must be a list")
    else:
        # Empty list is valid - means no media download, only gamelist updates
        valid_types = {'covers', 'screenshots', 'titlescreens', 'marquees', 
                       '3dboxes', 'backcovers', 'fanart', 'manuals', 
                       'miximages', 'physicalmedia', 'videos'}
        for media_type in media_types:
            if media_type not in valid_types:
                errors.append(f"Invalid media type: {media_type}")
    
    # Validate regions
    regions = section.get('preferred_regions', [])
    if not isinstance(regions, list):
        errors.append("scraping.preferred_regions must be a list")
    
    # Validate language
    language = section.get('preferred_language', 'en')
    if not isinstance(language, str) or len(language) != 2:
        errors.append("scraping.preferred_language must be a 2-letter code")
    
    # Validate numeric values
    if 'crc_size_limit' in section:
        limit = section['crc_size_limit']
        if not isinstance(limit, int) or limit < 0:
            errors.append("scraping.crc_size_limit must be a non-negative integer")
    
    if 'image_min_dimension' in section:
        dim = section['image_min_dimension']
        if not isinstance(dim, int) or dim < 1:
            errors.append("scraping.image_min_dimension must be a positive integer")
    
    # Validate verification mode
    if 'name_verification' in section:
        mode = section['name_verification']
        valid_modes = ['strict', 'normal', 'lenient', 'disabled']
        if mode not in valid_modes:
            errors.append(
                f"scraping.name_verification must be one of: {', '.join(valid_modes)}"
            )
    
    return errors


def _validate_api(section: Dict[str, Any]) -> List[str]:
    """Validate API options section."""
    errors = []
    
    # Validate timeout
    timeout = section.get('request_timeout', 30)
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        errors.append("api.request_timeout must be a positive number")
    
    # Phase E: Validate max_retries (required, range 1-10)
    if 'max_retries' in section:
        retries = section['max_retries']
        if not isinstance(retries, int):
            errors.append("api.max_retries must be an integer")
        elif retries < 1 or retries > 10:
            errors.append("api.max_retries must be between 1 and 10")
    # Use default if not specified (validation passes)
    
    # Phase E: Validate requests_per_minute (optional, range 1-300)
    if 'requests_per_minute' in section:
        rpm = section['requests_per_minute']
        if not isinstance(rpm, int):
            errors.append("api.requests_per_minute must be an integer")
        elif rpm < 1 or rpm > 300:
            errors.append("api.requests_per_minute must be between 1 and 300")
        # Note: requests_per_minute from API authentication response is authoritative
        # Config value is used as minimum constraint (min of API and config)
    
    # Validate backoff
    backoff = section.get('retry_backoff_seconds', 5)
    if not isinstance(backoff, (int, float)) or backoff < 0:
        errors.append("api.retry_backoff_seconds must be non-negative")
    
    return errors


def _validate_logging(section: Dict[str, Any]) -> List[str]:
    """Validate logging options section."""
    errors = []
    
    # Validate level
    level = section.get('level', 'INFO')
    valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR']
    if level not in valid_levels:
        errors.append(f"logging.level must be one of: {', '.join(valid_levels)}")
    
    # Validate console flag
    console = section.get('console', True)
    if not isinstance(console, bool):
        errors.append("logging.console must be a boolean")
    
    return errors


def _validate_runtime(section: Dict[str, Any]) -> List[str]:
    """Validate runtime options section."""
    errors = []
    
    # Validate dry_run flag
    dry_run = section.get('dry_run', False)
    if not isinstance(dry_run, bool):
        errors.append("runtime.dry_run must be a boolean")
    
    # Validate threads
    threads = section.get('threads', 1)
    if not isinstance(threads, int) or threads < 1:
        errors.append("runtime.threads must be a positive integer")
    
    return errors


def _validate_search(section: Dict[str, Any]) -> List[str]:
    """Validate search options section."""
    errors = []
    
    # Validate enable_search_fallback flag
    enable_search = section.get('enable_search_fallback', False)
    if not isinstance(enable_search, bool):
        errors.append("search.enable_search_fallback must be a boolean")
    
    # Validate confidence_threshold
    threshold = section.get('confidence_threshold', 0.7)
    if not isinstance(threshold, (int, float)) or not (0.0 <= threshold <= 1.0):
        errors.append("search.confidence_threshold must be between 0.0 and 1.0")
    
    # Validate max_results
    max_results = section.get('max_results', 5)
    if not isinstance(max_results, int) or not (1 <= max_results <= 10):
        errors.append("search.max_results must be between 1 and 10")
    
    # Validate interactive_search flag
    interactive = section.get('interactive_search', False)
    if not isinstance(interactive, bool):
        errors.append("search.interactive_search must be a boolean")
    
    return errors
