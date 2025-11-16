"""
Shared fixtures for config module tests.
"""
import pytest
import yaml
from pathlib import Path
from curateur.config.es_systems import SystemDefinition


@pytest.fixture
def valid_config():
    """Complete valid configuration."""
    return {
        'screenscraper': {
            'user_id': 'test_user',
            'user_password': 'test_password',
            # Dev credentials (normally injected by loader)
            'devid': 'test_dev_id',
            'devpassword': 'test_dev_password',
            'softname': 'test_software'
        },
        'paths': {
            'roms': './test_roms',
            'media': './test_media',
            'gamelists': './test_gamelists',
            'es_systems': './tests/fixtures/es_systems/systems.xml'
        },
        'scraping': {
            'systems': ['nes', 'snes'],
            'media_types': ['covers', 'screenshots'],
            'preferred_regions': ['us', 'eu'],
            'preferred_language': 'en',
            'crc_size_limit': 1073741824,
            'image_min_dimension': 50,
            'skip_scraped': False,
            'update_mode': False,
            'validate_gamelist': True,
            'gamelist_integrity_threshold': 0.95,
            'clean_mismatched_media': False,
            'media_only_mode': False,
            'update_policy': 'changed_only',
            'update_metadata': True,
            'update_media': True,
            'merge_strategy': 'preserve_user_edits',
            'log_changes': True,
            'log_unchanged_fields': False,
            'checkpoint_interval': 0,
            'name_verification': 'normal',
            'rate_limit_override_enabled': False,
            'rate_limit_override': {
                'max_threads': 1,
                'requests_per_minute': 60,
                'daily_quota': 10000
            }
        },
        'media': {
            'skip_existing_media': True
        },
        'api': {
            'request_timeout': 30,
            'max_retries': 3,
            'retry_backoff_seconds': 5
        },
        'logging': {
            'level': 'INFO',
            'console': True,
            'file': None
        },
        'runtime': {
            'dry_run': False
        },
        'search': {
            'enable_search_fallback': True,
            'confidence_threshold': 0.7,
            'max_results': 5,
            'interactive_search': False
        }
    }


@pytest.fixture
def minimal_config():
    """Minimal required configuration."""
    return {
        'screenscraper': {
            'user_id': 'minimal_user',
            'user_password': 'minimal_pass',
            # Dev credentials (normally injected by loader)
            'devid': 'test_dev_id',
            'devpassword': 'test_dev_password',
            'softname': 'test_software'
        },
        'paths': {
            'roms': './roms',
            'media': './media',
            'gamelists': './gamelists',
            'es_systems': './tests/fixtures/es_systems/systems.xml'
        },
        'scraping': {
            'media_types': ['covers']  # Minimal required media type
        }
    }


@pytest.fixture
def temp_config_file(tmp_path, valid_config):
    """Create temporary config file."""
    config_file = tmp_path / "config.yaml"
    config_file.write_text(yaml.dump(valid_config))
    return config_file


@pytest.fixture
def mock_dev_credentials(mocker):
    """Mock developer credentials."""
    return mocker.patch(
        'curateur.api.credentials.get_dev_credentials',
        return_value={
            'devid': 'test_dev_id',
            'devpassword': 'test_dev_password',
            'softname': 'test_software'
        }
    )


@pytest.fixture
def sample_es_systems_xml():
    """Sample ES systems XML string."""
    return """<?xml version="1.0"?>
<systemList>
  <system>
    <name>nes</name>
    <fullname>Nintendo Entertainment System</fullname>
    <path>%ROMPATH%/nes</path>
    <extension>.nes .zip</extension>
    <platform>nes</platform>
  </system>
  <system>
    <name>psx</name>
    <fullname>Sony PlayStation</fullname>
    <path>%ROMPATH%/psx</path>
    <extension>.cue .m3u</extension>
    <platform>psx</platform>
  </system>
</systemList>
"""


@pytest.fixture
def valid_system_definition():
    """Valid SystemDefinition instance."""
    return SystemDefinition(
        name="nes",
        fullname="Nintendo Entertainment System",
        path="%ROMPATH%/nes",
        extensions=[".nes", ".zip"],
        platform="nes"
    )


@pytest.fixture
def fixture_path():
    """Return path to config fixtures directory."""
    return Path(__file__).parent.parent / 'fixtures' / 'config'
