"""Configuration validation."""

import logging
from pathlib import Path
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


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

    # Validate media section
    errors.extend(_validate_media(config.get('media', {})))

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
    elif any(not isinstance(s, str) for s in systems):
        errors.append("scraping.systems entries must be strings")

    # Validate regions
    regions = section.get('preferred_regions', [])
    if not isinstance(regions, list):
        errors.append("scraping.preferred_regions must be a list")

    # Validate language
    language = section.get('preferred_language', 'en')
    if not isinstance(language, str) or len(language) != 2:
        errors.append("scraping.preferred_language must be a 2-letter code")

    # Validate numeric values
    if 'gamelist_integrity_threshold' in section:
        threshold = section['gamelist_integrity_threshold']
        if not isinstance(threshold, (int, float)):
            errors.append("scraping.gamelist_integrity_threshold must be a number")
        elif threshold < 0.0 or threshold > 1.0:
            errors.append("scraping.gamelist_integrity_threshold must be between 0.0 and 1.0")

    # Validate scrape_mode
    if 'scrape_mode' in section:
        mode = section['scrape_mode']
        valid_modes = ['new_only', 'changed', 'force', 'skip']
        if mode not in valid_modes:
            errors.append(
                f"scraping.scrape_mode must be one of: {', '.join(valid_modes)}"
            )

    # Validate merge_strategy
    if 'merge_strategy' in section:
        strategy = section['merge_strategy']
        valid_strategies = ['preserve_user_edits', 'refresh_metadata', 'reset_all']
        if strategy not in valid_strategies:
            errors.append(
                f"scraping.merge_strategy must be one of: {', '.join(valid_strategies)}"
            )

    # Validate auto_favorite settings
    if 'auto_favorite_enabled' in section:
        if not isinstance(section['auto_favorite_enabled'], bool):
            errors.append("scraping.auto_favorite_enabled must be a boolean")

    if 'auto_favorite_threshold' in section:
        threshold = section['auto_favorite_threshold']
        if not isinstance(threshold, (int, float)):
            errors.append("scraping.auto_favorite_threshold must be a number")
        elif threshold < 0.0 or threshold > 1.0:
            errors.append("scraping.auto_favorite_threshold must be between 0.0 and 1.0")

    # Validate name_verification
    if 'name_verification' in section:
        verification = section['name_verification']
        valid_modes = ['strict', 'normal', 'lenient', 'disabled']
        if verification not in valid_modes:
            errors.append(
                f"scraping.name_verification must be one of: {', '.join(valid_modes)}"
            )

    return errors


def _validate_media(section: Dict[str, Any]) -> List[str]:
    """Validate media options section."""
    errors = []

    # Validate media_types
    media_types = section.get('media_types', [])
    if not isinstance(media_types, list):
        errors.append("media.media_types must be a list")
    else:
        # Empty list is valid - means no media download, only gamelist updates
        valid_types = {'covers', 'screenshots', 'titlescreens', 'marquees',
                       '3dboxes', 'backcovers', 'fanart', 'manuals',
                       'miximages', 'physicalmedia', 'videos'}
        for media_type in media_types:
            if media_type not in valid_types:
                errors.append(f"Invalid media type: {media_type}")

    # Validate image_min_dimension
    if 'image_min_dimension' in section:
        dim = section['image_min_dimension']
        if not isinstance(dim, int) or dim < 1:
            errors.append("media.image_min_dimension must be a positive integer")

    # Validate validation_mode
    if 'validation_mode' in section:
        mode = section['validation_mode']
        valid_modes = ['disabled', 'normal', 'strict']
        if mode not in valid_modes:
            errors.append(
                f"media.validation_mode must be one of: {', '.join(valid_modes)}"
            )

    # Validate clean_mismatched_media
    if 'clean_mismatched_media' in section:
        if not isinstance(section['clean_mismatched_media'], bool):
            errors.append("media.clean_mismatched_media must be a boolean")

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

    # Quota warning threshold
    if 'quota_warning_threshold' in section:
        threshold = section['quota_warning_threshold']
        if not isinstance(threshold, (int, float)):
            errors.append("api.quota_warning_threshold must be a number")
        elif not (0.0 <= threshold <= 1.0):
            errors.append("api.quota_warning_threshold must be between 0.0 and 1.0")

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

    # Validate optional log file
    if 'file' in section and section['file'] is not None:
        if not isinstance(section['file'], str):
            errors.append("logging.file must be a string path or null")

    return errors


def _validate_runtime(section: Dict[str, Any]) -> List[str]:
    """Validate runtime options section."""
    errors = []

    # Validate dry_run flag
    dry_run = section.get('dry_run', False)
    if not isinstance(dry_run, bool):
        errors.append("runtime.dry_run must be a boolean")

    # Hash algorithm
    hash_algorithm = section.get('hash_algorithm', 'crc32')
    valid_hashes = ['crc32', 'md5', 'sha1']
    if hash_algorithm not in valid_hashes:
        errors.append(f"runtime.hash_algorithm must be one of: {', '.join(valid_hashes)}")

    # CRC size limit
    if 'crc_size_limit' in section:
        size_limit = section['crc_size_limit']
        if not isinstance(size_limit, int) or size_limit < 0:
            errors.append("runtime.crc_size_limit must be a non-negative integer")

    # Rate limit override toggle
    if 'rate_limit_override_enabled' in section:
        if not isinstance(section['rate_limit_override_enabled'], bool):
            errors.append("runtime.rate_limit_override_enabled must be a boolean")

    # Rate limit override values
    if 'rate_limit_override' in section:
        override = section['rate_limit_override']
        if not isinstance(override, dict):
            errors.append("runtime.rate_limit_override must be a mapping")
        else:
            max_workers = override.get('max_workers')
            if max_workers is not None:
                if not isinstance(max_workers, int) or not (1 <= max_workers <= 10):
                    errors.append("runtime.rate_limit_override.max_workers must be between 1 and 10")

            rpm = override.get('requests_per_minute')
            if rpm is not None:
                if not isinstance(rpm, int) or not (1 <= rpm <= 300):
                    errors.append("runtime.rate_limit_override.requests_per_minute must be between 1 and 300")

            daily_quota = override.get('daily_quota')
            if daily_quota is not None:
                if not isinstance(daily_quota, int) or daily_quota < 1:
                    errors.append("runtime.rate_limit_override.daily_quota must be a positive integer")

    # Validate enable_cache flag
    if 'enable_cache' in section:
        enable_cache = section['enable_cache']
        if not isinstance(enable_cache, bool):
            errors.append("runtime.enable_cache must be a boolean")

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
