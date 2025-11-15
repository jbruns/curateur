"""Configuration loading and parsing."""

import yaml
from pathlib import Path
from typing import Dict, Any, Optional


class ConfigError(Exception):
    """Configuration-related errors."""
    pass


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load and parse configuration file.
    
    Args:
        config_path: Path to config.yaml file. If None, searches current directory.
        
    Returns:
        Parsed configuration dictionary
        
    Raises:
        ConfigError: If config file cannot be loaded or parsed
    """
    # Determine config file path
    if config_path is None:
        config_path = Path.cwd() / "config.yaml"
    else:
        config_path = Path(config_path)
    
    if not config_path.exists():
        raise ConfigError(
            f"Configuration file not found: {config_path}\n"
            f"Copy config.yaml.example to config.yaml and configure it."
        )
    
    # Load YAML
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ConfigError(f"Invalid YAML in config file: {e}")
    except Exception as e:
        raise ConfigError(f"Failed to read config file: {e}")
    
    if not isinstance(config, dict):
        raise ConfigError("Configuration file must contain a YAML dictionary")
    
    # Merge with developer credentials
    from curateur.api.credentials import get_dev_credentials
    
    try:
        dev_creds = get_dev_credentials()
    except ValueError as e:
        raise ConfigError(f"Developer credentials not initialized: {e}")
    
    # Ensure screenscraper section exists
    if 'screenscraper' not in config:
        config['screenscraper'] = {}
    
    # Add developer credentials (these override any user-provided values)
    config['screenscraper']['devid'] = dev_creds['devid']
    config['screenscraper']['devpassword'] = dev_creds['devpassword']
    config['screenscraper']['softname'] = dev_creds['softname']
    
    return config


def get_config_value(config: Dict[str, Any], path: str, default: Any = None) -> Any:
    """
    Get a nested configuration value using dot notation.
    
    Args:
        config: Configuration dictionary
        path: Dot-separated path (e.g., 'scraping.media_types')
        default: Default value if path not found
        
    Returns:
        Configuration value or default
        
    Example:
        >>> get_config_value(config, 'scraping.media_types')
        ['covers', 'screenshots']
    """
    keys = path.split('.')
    value = config
    
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    
    return value
