"""
Tests for config.loader module.
"""
import pytest
import yaml
from pathlib import Path
from curateur.config.loader import load_config, get_config_value, ConfigError


@pytest.mark.unit
class TestConfigLoading:
    """Test configuration file loading."""
    
    def test_load_valid_config_from_file(self, tmp_path, valid_config, mock_dev_credentials):
        """Test loading a valid configuration file."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(valid_config))
        
        config = load_config(str(config_file))
        
        assert isinstance(config, dict)
        assert 'screenscraper' in config
        assert 'paths' in config
        assert config['screenscraper']['user_id'] == 'test_user'
    
    def test_load_minimal_config(self, tmp_path, minimal_config, mock_dev_credentials):
        """Test loading minimal required configuration."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(minimal_config))
        
        config = load_config(str(config_file))
        
        assert config['screenscraper']['user_id'] == 'minimal_user'
        assert config['paths']['roms'] == './roms'
    
    def test_load_config_from_fixture(self, fixture_path, mock_dev_credentials):
        """Test loading from fixture file."""
        config_file = fixture_path / 'valid' / 'complete.yaml'
        
        config = load_config(str(config_file))
        
        assert isinstance(config, dict)
        assert 'screenscraper' in config
        assert 'scraping' in config
    
    def test_load_config_file_not_found(self, mock_dev_credentials):
        """Test error when config file doesn't exist."""
        with pytest.raises(ConfigError) as exc_info:
            load_config('/nonexistent/path/config.yaml')
        
        assert 'Configuration file not found' in str(exc_info.value)
        assert 'config.yaml.example' in str(exc_info.value)
    
    def test_load_config_directory_instead_of_file(self, tmp_path, mock_dev_credentials):
        """Test error when path is a directory."""
        config_dir = tmp_path / "config.yaml"
        config_dir.mkdir()
        
        with pytest.raises(ConfigError) as exc_info:
            load_config(str(config_dir))
        
        assert 'Failed to read config file' in str(exc_info.value)
    
    def test_load_config_none_path_uses_cwd(self, tmp_path, valid_config, mock_dev_credentials, monkeypatch):
        """Test that None path uses current working directory."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(valid_config))
        
        monkeypatch.chdir(tmp_path)
        config = load_config(None)
        
        assert isinstance(config, dict)
        assert 'screenscraper' in config
    
    def test_load_config_invalid_yaml_syntax(self, tmp_path, mock_dev_credentials):
        """Test error with invalid YAML syntax."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("invalid: yaml: syntax:\n  - broken")
        
        with pytest.raises(ConfigError) as exc_info:
            load_config(str(config_file))
        
        assert 'Invalid YAML' in str(exc_info.value)
    
    def test_load_config_from_fixture_invalid_yaml(self, fixture_path, mock_dev_credentials):
        """Test loading invalid YAML fixture."""
        config_file = fixture_path / 'invalid' / 'invalid_yaml.txt'
        
        with pytest.raises(ConfigError) as exc_info:
            load_config(str(config_file))
        
        assert 'Invalid YAML' in str(exc_info.value)
    
    def test_load_config_not_a_dict_list(self, tmp_path, mock_dev_credentials):
        """Test error when YAML root is a list."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(['item1', 'item2']))
        
        with pytest.raises(ConfigError) as exc_info:
            load_config(str(config_file))
        
        assert 'must contain a YAML dictionary' in str(exc_info.value)
    
    def test_load_config_not_a_dict_string(self, tmp_path, mock_dev_credentials):
        """Test error when YAML root is a string."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("just a string")
        
        with pytest.raises(ConfigError) as exc_info:
            load_config(str(config_file))
        
        assert 'must contain a YAML dictionary' in str(exc_info.value)
    
    def test_load_config_from_fixture_not_a_dict(self, fixture_path, mock_dev_credentials):
        """Test loading not-a-dict fixture."""
        config_file = fixture_path / 'invalid' / 'not_a_dict.yaml'
        
        with pytest.raises(ConfigError) as exc_info:
            load_config(str(config_file))
        
        assert 'must contain a YAML dictionary' in str(exc_info.value)
    
    def test_load_config_empty_file(self, tmp_path, mock_dev_credentials):
        """Test loading empty config file."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text("")
        
        with pytest.raises(ConfigError) as exc_info:
            load_config(str(config_file))
        
        assert 'must contain a YAML dictionary' in str(exc_info.value)
    
    def test_load_config_utf8_encoding(self, tmp_path, mock_dev_credentials):
        """Test loading config with UTF-8 characters."""
        config_file = tmp_path / "config.yaml"
        config_data = {
            'screenscraper': {
                'user_id': 'test_用户',
                'user_password': 'пароль'
            },
            'paths': {
                'roms': './röms',
                'media': './media',
                'gamelists': './gamelists',
                'es_systems': './systems.xml'
            }
        }
        config_file.write_text(yaml.dump(config_data, allow_unicode=True), encoding='utf-8')
        
        config = load_config(str(config_file))
        
        assert config['screenscraper']['user_id'] == 'test_用户'
        assert config['screenscraper']['user_password'] == 'пароль'
        assert config['paths']['roms'] == './röms'


@pytest.mark.unit
class TestCredentialInjection:
    """Test developer credential merging."""
    
    def test_credentials_injected_into_config(self, tmp_path, valid_config, mock_dev_credentials):
        """Test that developer credentials are added to config."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(valid_config))
        
        config = load_config(str(config_file))
        
        assert 'devid' in config['screenscraper']
        assert 'devpassword' in config['screenscraper']
        assert 'softname' in config['screenscraper']
        assert config['screenscraper']['devid'] == 'test_dev_id'
        assert config['screenscraper']['devpassword'] == 'test_dev_password'
        assert config['screenscraper']['softname'] == 'test_software'
    
    def test_credentials_override_user_values(self, tmp_path, mock_dev_credentials):
        """Test that dev credentials override any user-provided dev values."""
        config_data = {
            'screenscraper': {
                'user_id': 'user',
                'user_password': 'pass',
                'devid': 'user_devid',  # Should be overridden
                'devpassword': 'user_devpass',  # Should be overridden
                'softname': 'user_soft'  # Should be overridden
            },
            'paths': {
                'roms': './roms',
                'media': './media',
                'gamelists': './gamelists',
                'es_systems': './systems.xml'
            }
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))
        
        config = load_config(str(config_file))
        
        # Dev credentials should override user values
        assert config['screenscraper']['devid'] == 'test_dev_id'
        assert config['screenscraper']['devpassword'] == 'test_dev_password'
        assert config['screenscraper']['softname'] == 'test_software'
        # User credentials unchanged
        assert config['screenscraper']['user_id'] == 'user'
        assert config['screenscraper']['user_password'] == 'pass'
    
    def test_credentials_missing_raises_error(self, tmp_path, valid_config, mocker):
        """Test error when developer credentials not initialized."""
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(valid_config))
        
        # Mock get_dev_credentials to raise ValueError
        mocker.patch(
            'curateur.api.credentials.get_dev_credentials',
            side_effect=ValueError('Credentials not set up')
        )
        
        with pytest.raises(ConfigError) as exc_info:
            load_config(str(config_file))
        
        assert 'Developer credentials not initialized' in str(exc_info.value)
    
    def test_credentials_added_when_screenscraper_section_missing(self, tmp_path, mock_dev_credentials):
        """Test credentials added even when screenscraper section doesn't exist."""
        config_data = {
            'paths': {
                'roms': './roms',
                'media': './media',
                'gamelists': './gamelists',
                'es_systems': './systems.xml'
            }
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))
        
        config = load_config(str(config_file))
        
        assert 'screenscraper' in config
        assert config['screenscraper']['devid'] == 'test_dev_id'
        assert config['screenscraper']['devpassword'] == 'test_dev_password'
        assert config['screenscraper']['softname'] == 'test_software'
    
    def test_credentials_preserves_other_screenscraper_fields(self, tmp_path, mock_dev_credentials):
        """Test that credential injection preserves other fields."""
        config_data = {
            'screenscraper': {
                'user_id': 'user',
                'user_password': 'pass',
                'custom_field': 'custom_value'
            },
            'paths': {
                'roms': './roms',
                'media': './media',
                'gamelists': './gamelists',
                'es_systems': './systems.xml'
            }
        }
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))
        
        config = load_config(str(config_file))
        
        assert config['screenscraper']['user_id'] == 'user'
        assert config['screenscraper']['user_password'] == 'pass'
        assert config['screenscraper']['custom_field'] == 'custom_value'
        assert config['screenscraper']['devid'] == 'test_dev_id'


@pytest.mark.unit
class TestGetConfigValue:
    """Test nested value retrieval."""
    
    def test_get_simple_path(self, valid_config):
        """Test retrieving a top-level value."""
        value = get_config_value(valid_config, 'paths')
        
        assert isinstance(value, dict)
        assert 'roms' in value
    
    def test_get_nested_path(self, valid_config):
        """Test retrieving nested values with dot notation."""
        value = get_config_value(valid_config, 'scraping.media_types')
        
        assert isinstance(value, list)
        assert 'covers' in value
        assert 'screenshots' in value
    
    def test_get_deep_nested_path(self, valid_config):
        """Test retrieving deeply nested values."""
        value = get_config_value(valid_config, 'scraping.rate_limit_override.max_threads')
        
        assert value == 1
    
    def test_get_missing_path_returns_default(self, valid_config):
        """Test that missing path returns default value."""
        value = get_config_value(valid_config, 'nonexistent.path', default='default_value')
        
        assert value == 'default_value'
    
    def test_get_missing_path_returns_none_by_default(self, valid_config):
        """Test that missing path returns None when no default specified."""
        value = get_config_value(valid_config, 'nonexistent.path')
        
        assert value is None
    
    def test_get_partial_path_exists(self, valid_config):
        """Test when partial path exists but full path doesn't."""
        value = get_config_value(valid_config, 'scraping.nonexistent.field', default='fallback')
        
        assert value == 'fallback'
    
    def test_get_path_with_empty_string_key(self, valid_config):
        """Test path with empty key segment."""
        value = get_config_value(valid_config, 'scraping..media_types', default='fallback')
        
        assert value == 'fallback'
    
    def test_get_single_key_path(self, valid_config):
        """Test path with no dots (single key)."""
        value = get_config_value(valid_config, 'logging')
        
        assert isinstance(value, dict)
        assert value['level'] == 'INFO'
    
    def test_get_path_returns_none_value(self):
        """Test retrieving a path that exists but has None value."""
        config = {
            'section': {
                'field': None
            }
        }
        
        value = get_config_value(config, 'section.field', default='default')
        
        assert value is None  # Actual None value, not default
    
    def test_get_path_returns_false_value(self):
        """Test retrieving a path with False value (not treated as missing)."""
        config = {
            'section': {
                'enabled': False
            }
        }
        
        value = get_config_value(config, 'section.enabled', default=True)
        
        assert value is False  # Actual False value, not default
    
    def test_get_path_returns_zero_value(self):
        """Test retrieving a path with 0 value (not treated as missing)."""
        config = {
            'section': {
                'count': 0
            }
        }
        
        value = get_config_value(config, 'section.count', default=10)
        
        assert value == 0  # Actual 0 value, not default
    
    def test_get_path_returns_empty_string(self):
        """Test retrieving a path with empty string (not treated as missing)."""
        config = {
            'section': {
                'text': ''
            }
        }
        
        value = get_config_value(config, 'section.text', default='default')
        
        assert value == ''  # Actual empty string, not default
    
    def test_get_path_non_dict_intermediate(self):
        """Test when intermediate value is not a dict."""
        config = {
            'section': 'string_value'
        }
        
        value = get_config_value(config, 'section.field', default='fallback')
        
        assert value == 'fallback'
    
    def test_get_path_list_intermediate(self):
        """Test when intermediate value is a list."""
        config = {
            'section': ['item1', 'item2']
        }
        
        value = get_config_value(config, 'section.field', default='fallback')
        
        assert value == 'fallback'
    
    def test_get_path_with_trailing_dot(self, valid_config):
        """Test path with trailing dot."""
        value = get_config_value(valid_config, 'scraping.', default='fallback')
        
        # Empty key at end will fail to match
        assert value == 'fallback'
    
    def test_get_path_empty_string(self, valid_config):
        """Test empty path string."""
        value = get_config_value(valid_config, '', default='fallback')
        
        assert value == 'fallback'
