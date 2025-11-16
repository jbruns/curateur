"""
Integration tests for config module workflows.
"""
import pytest
import yaml
from pathlib import Path
from curateur.config.loader import load_config, ConfigError
from curateur.config.validator import validate_config, ValidationError
from curateur.config.es_systems import parse_es_systems, get_systems_by_name, ESSystemsError


@pytest.mark.integration
class TestConfigWorkflows:
    """Test end-to-end configuration workflows."""
    
    def test_load_validate_parse_complete_workflow(self, fixture_path, mock_dev_credentials):
        """Test complete workflow: load → validate → parse systems."""
        # Load configuration
        config_file = fixture_path / 'valid' / 'complete.yaml'
        config = load_config(str(config_file))
        
        # Create temporary es_systems file for validation
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.xml', delete=False) as f:
            f.write("""<?xml version="1.0"?>
<systemList>
  <system>
    <name>nes</name>
    <fullname>Nintendo Entertainment System</fullname>
    <path>./roms/nes</path>
    <extension>.nes .NES</extension>
    <platform>nes</platform>
  </system>
  <system>
    <name>snes</name>
    <fullname>Super Nintendo</fullname>
    <path>./roms/snes</path>
    <extension>.smc .SFC</extension>
    <platform>snes</platform>
  </system>
</systemList>
""")
            temp_es_systems = f.name
        
        try:
            config['paths']['es_systems'] = temp_es_systems
            
            # Validate configuration
            validate_config(config)
            
            # Parse ES systems
            systems = parse_es_systems(Path(config['paths']['es_systems']))
            
            # Filter by configured systems
            requested_systems = config.get('scraping', {}).get('systems', [])
            if requested_systems:
                filtered_systems = get_systems_by_name(systems, requested_systems)
            else:
                filtered_systems = systems
            
            # Verify complete workflow
            assert len(systems) == 2
            assert len(filtered_systems) == 2
            assert config['screenscraper']['devid'] == 'test_dev_id'
        finally:
            Path(temp_es_systems).unlink()
    
    def test_load_validate_minimal_config_workflow(self, fixture_path, mock_dev_credentials, tmp_path):
        """Test workflow with minimal configuration."""
        # Create es_systems file
        es_systems = tmp_path / "systems.xml"
        es_systems.write_text("""<?xml version="1.0"?>
<systemList>
  <system>
    <name>nes</name>
    <fullname>NES</fullname>
    <path>./roms/nes</path>
    <extension>.nes</extension>
    <platform>nes</platform>
  </system>
</systemList>
""")
        
        # Load minimal config
        config_file = fixture_path / 'valid' / 'minimal.yaml'
        config = load_config(str(config_file))
        config['paths']['es_systems'] = str(es_systems)
        
        # Validate
        validate_config(config)
        
        # Parse systems
        systems = parse_es_systems(Path(config['paths']['es_systems']))
        
        assert len(systems) == 1
        assert systems[0].name == 'nes'
    
    def test_config_error_propagation(self, tmp_path, mock_dev_credentials):
        """Test that ConfigError is raised for invalid files."""
        nonexistent_file = tmp_path / "nonexistent.yaml"
        
        with pytest.raises(ConfigError) as exc_info:
            load_config(str(nonexistent_file))
        
        assert 'Configuration file not found' in str(exc_info.value)
    
    def test_validation_error_propagation(self, tmp_path, mock_dev_credentials):
        """Test that ValidationError is raised for invalid config."""
        config_data = {
            'screenscraper': {
                'user_id': 'test',
                'user_password': 'test',
                'devid': 'dev',
                'devpassword': 'devpass',
                'softname': 'soft'
            },
            'paths': {
                'roms': './roms',
                'media': './media',
                'gamelists': './gamelists',
                'es_systems': '/nonexistent/file.xml'
            }
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validate_config(config_data)
        
        assert 'file not found' in str(exc_info.value)
    
    def test_es_systems_error_propagation(self, tmp_path):
        """Test that ESSystemsError is raised for invalid XML."""
        es_systems = tmp_path / "bad_systems.xml"
        es_systems.write_text("not valid xml")
        
        with pytest.raises(ESSystemsError) as exc_info:
            parse_es_systems(es_systems)
        
        assert 'Invalid XML' in str(exc_info.value)
    
    def test_workflow_with_system_filtering(self, tmp_path, mock_dev_credentials):
        """Test workflow with system name filtering."""
        # Create config with specific systems requested
        config_data = {
            'screenscraper': {
                'user_id': 'test',
                'user_password': 'test'
            },
            'paths': {
                'roms': './roms',
                'media': './media',
                'gamelists': './gamelists',
                'es_systems': str(tmp_path / 'systems.xml')
            },
            'scraping': {
                'systems': ['nes', 'snes'],  # Request specific systems
                'media_types': ['covers']
            }
        }
        
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))
        
        # Create es_systems with 3 systems
        es_systems = tmp_path / "systems.xml"
        es_systems.write_text("""<?xml version="1.0"?>
<systemList>
  <system>
    <name>nes</name>
    <fullname>NES</fullname>
    <path>./roms/nes</path>
    <extension>.nes</extension>
    <platform>nes</platform>
  </system>
  <system>
    <name>snes</name>
    <fullname>SNES</fullname>
    <path>./roms/snes</path>
    <extension>.smc</extension>
    <platform>snes</platform>
  </system>
  <system>
    <name>psx</name>
    <fullname>PlayStation</fullname>
    <path>./roms/psx</path>
    <extension>.cue</extension>
    <platform>psx</platform>
  </system>
</systemList>
""")
        
        # Execute workflow
        config = load_config(str(config_file))
        validate_config(config)
        all_systems = parse_es_systems(Path(config['paths']['es_systems']))
        filtered_systems = get_systems_by_name(all_systems, config['scraping']['systems'])
        
        # Verify filtering
        assert len(all_systems) == 3
        assert len(filtered_systems) == 2
        assert filtered_systems[0].name == 'nes'
        assert filtered_systems[1].name == 'snes'
    
    def test_workflow_with_invalid_system_filter(self, tmp_path, mock_dev_credentials):
        """Test error when requested system doesn't exist."""
        # Create config
        config_data = {
            'screenscraper': {
                'user_id': 'test',
                'user_password': 'test'
            },
            'paths': {
                'roms': './roms',
                'media': './media',
                'gamelists': './gamelists',
                'es_systems': str(tmp_path / 'systems.xml')
            },
            'scraping': {
                'systems': ['nes', 'nonexistent'],  # Invalid system
                'media_types': ['covers']
            }
        }
        
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))
        
        # Create es_systems with only nes
        es_systems = tmp_path / "systems.xml"
        es_systems.write_text("""<?xml version="1.0"?>
<systemList>
  <system>
    <name>nes</name>
    <fullname>NES</fullname>
    <path>./roms/nes</path>
    <extension>.nes</extension>
    <platform>nes</platform>
  </system>
</systemList>
""")
        
        # Execute workflow until filtering fails
        config = load_config(str(config_file))
        validate_config(config)
        all_systems = parse_es_systems(Path(config['paths']['es_systems']))
        
        with pytest.raises(ValueError) as exc_info:
            get_systems_by_name(all_systems, config['scraping']['systems'])
        
        assert 'nonexistent' in str(exc_info.value)
    
    def test_workflow_credentials_injected_before_validation(self, tmp_path, mock_dev_credentials):
        """Test that credentials are injected during load, before validation."""
        config_data = {
            'screenscraper': {
                'user_id': 'test',
                'user_password': 'test'
                # No dev credentials - loader should inject them
            },
            'paths': {
                'roms': './roms',
                'media': './media',
                'gamelists': './gamelists',
                'es_systems': str(tmp_path / 'systems.xml')
            },
            'scraping': {
                'media_types': ['covers']  # Required field
            }
        }
        
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))
        
        # Create minimal es_systems
        es_systems = tmp_path / "systems.xml"
        es_systems.write_text("""<?xml version="1.0"?>
<systemList>
  <system>
    <name>nes</name>
    <fullname>NES</fullname>
    <path>./roms/nes</path>
    <extension>.nes</extension>
    <platform>nes</platform>
  </system>
</systemList>
""")
        
        # Load config (should inject credentials)
        config = load_config(str(config_file))
        
        # Validation should pass (credentials were injected)
        validate_config(config)
        
        assert config['screenscraper']['devid'] == 'test_dev_id'
        assert config['screenscraper']['devpassword'] == 'test_dev_password'
        assert config['screenscraper']['softname'] == 'test_software'
    
    def test_workflow_with_defaults(self, tmp_path, mock_dev_credentials):
        """Test workflow uses defaults for optional config values."""
        config_data = {
            'screenscraper': {
                'user_id': 'test',
                'user_password': 'test'
            },
            'paths': {
                'roms': './roms',
                'media': './media',
                'gamelists': './gamelists',
                'es_systems': str(tmp_path / 'systems.xml')
            },
            'scraping': {
                'media_types': ['covers']  # Minimal required field
            }
            # Other scraping fields, api, logging sections omitted - should use defaults
        }
        
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(config_data))
        
        # Create es_systems
        es_systems = tmp_path / "systems.xml"
        es_systems.write_text("""<?xml version="1.0"?>
<systemList>
  <system>
    <name>nes</name>
    <fullname>NES</fullname>
    <path>./roms/nes</path>
    <extension>.nes</extension>
    <platform>nes</platform>
  </system>
</systemList>
""")
        
        # Load and validate
        config = load_config(str(config_file))
        validate_config(config)
        
        # Parse systems (should work even with defaults)
        systems = parse_es_systems(Path(config['paths']['es_systems']))
        
        assert len(systems) == 1
    
    def test_error_messages_are_helpful(self, tmp_path, mock_dev_credentials):
        """Test that error messages guide users to solutions."""
        # Test ConfigError message
        with pytest.raises(ConfigError) as exc_info:
            load_config(str(tmp_path / "nonexistent.yaml"))
        
        error_msg = str(exc_info.value)
        assert 'config.yaml.example' in error_msg
        
        # Test ValidationError message
        config_data = {
            'screenscraper': {},  # Missing credentials
            'paths': {}  # Missing paths
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validate_config(config_data)
        
        error_msg = str(exc_info.value)
        assert 'user_id is required' in error_msg
        assert 'paths.roms is required' in error_msg
        
        # Test ESSystemsError message
        bad_xml = tmp_path / "bad.xml"
        bad_xml.write_text("<wrongRoot></wrongRoot>")
        
        with pytest.raises(ESSystemsError) as exc_info:
            parse_es_systems(bad_xml)
        
        error_msg = str(exc_info.value)
        assert 'systemList' in error_msg
