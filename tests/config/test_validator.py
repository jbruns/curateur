"""
Tests for config.validator module.
"""
import pytest
from pathlib import Path
from curateur.config.validator import (
    validate_config, ValidationError,
    _validate_screenscraper, _validate_paths, _validate_scraping,
    _validate_api, _validate_logging, _validate_runtime, _validate_search
)


@pytest.mark.unit
class TestValidateConfig:
    """Test main validation entry point."""
    
    def test_validate_complete_valid_config(self, valid_config, tmp_path):
        """Test validation passes for complete valid configuration."""
        # Create es_systems file that config references
        es_systems = tmp_path / "systems.xml"
        es_systems.write_text("<?xml version='1.0'?><systemList></systemList>")
        valid_config['paths']['es_systems'] = str(es_systems)
        
        # Should not raise
        validate_config(valid_config)
    
    def test_validate_minimal_config(self, minimal_config, tmp_path):
        """Test validation passes for minimal required configuration."""
        # Create es_systems file
        es_systems = tmp_path / "systems.xml"
        es_systems.write_text("<?xml version='1.0'?><systemList></systemList>")
        minimal_config['paths']['es_systems'] = str(es_systems)
        
        # Should not raise
        validate_config(minimal_config)
    
    def test_validate_accumulates_multiple_errors(self, tmp_path):
        """Test that all validation errors are collected and reported."""
        config = {
            'screenscraper': {},  # Missing credentials
            'paths': {},  # Missing all paths
            'scraping': {
                'media_types': [],  # Empty
                'preferred_language': 'english'  # Not 2 letters
            },
            'logging': {
                'level': 'TRACE',  # Invalid level
                'console': 'yes'  # Not boolean
            }
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validate_config(config)
        
        error_msg = str(exc_info.value)
        assert 'user_id is required' in error_msg
        assert 'user_password is required' in error_msg
        assert 'paths.roms is required' in error_msg
        assert 'preferred_language must be a 2-letter code' in error_msg
        assert 'logging.level must be one of' in error_msg
        assert 'logging.console must be a boolean' in error_msg
    
    def test_validate_error_message_formatting(self):
        """Test that error messages are formatted correctly."""
        config = {
            'screenscraper': {},
            'paths': {}
        }
        
        with pytest.raises(ValidationError) as exc_info:
            validate_config(config)
        
        error_msg = str(exc_info.value)
        assert 'Configuration validation failed:' in error_msg
        assert '\n  - ' in error_msg  # Bullet points


@pytest.mark.unit
class TestScreenscraperValidation:
    """Test ScreenScraper credentials validation."""
    
    def test_valid_screenscraper_section(self):
        """Test validation passes with all required fields."""
        section = {
            'user_id': 'test_user',
            'user_password': 'test_pass',
            'devid': 'dev_id',
            'devpassword': 'dev_pass',
            'softname': 'software'
        }
        
        errors = _validate_screenscraper(section)
        
        assert len(errors) == 0
    
    def test_missing_user_id(self):
        """Test error when user_id is missing."""
        section = {
            'user_password': 'pass',
            'devid': 'dev',
            'devpassword': 'dev_pass',
            'softname': 'soft'
        }
        
        errors = _validate_screenscraper(section)
        
        assert any('user_id is required' in err for err in errors)
    
    def test_missing_user_password(self):
        """Test error when user_password is missing."""
        section = {
            'user_id': 'user',
            'devid': 'dev',
            'devpassword': 'dev_pass',
            'softname': 'soft'
        }
        
        errors = _validate_screenscraper(section)
        
        assert any('user_password is required' in err for err in errors)
    
    def test_missing_devid(self):
        """Test error when devid is missing (internal error)."""
        section = {
            'user_id': 'user',
            'user_password': 'pass',
            'devpassword': 'dev_pass',
            'softname': 'soft'
        }
        
        errors = _validate_screenscraper(section)
        
        assert any('devid missing' in err for err in errors)
    
    def test_missing_devpassword(self):
        """Test error when devpassword is missing."""
        section = {
            'user_id': 'user',
            'user_password': 'pass',
            'devid': 'dev',
            'softname': 'soft'
        }
        
        errors = _validate_screenscraper(section)
        
        assert any('devpassword missing' in err for err in errors)
    
    def test_missing_softname(self):
        """Test error when softname is missing."""
        section = {
            'user_id': 'user',
            'user_password': 'pass',
            'devid': 'dev',
            'devpassword': 'dev_pass'
        }
        
        errors = _validate_screenscraper(section)
        
        assert any('softname missing' in err for err in errors)
    
    def test_empty_user_id(self):
        """Test that empty user_id is treated as missing."""
        section = {
            'user_id': '',
            'user_password': 'pass',
            'devid': 'dev',
            'devpassword': 'dev_pass',
            'softname': 'soft'
        }
        
        errors = _validate_screenscraper(section)
        
        assert any('user_id is required' in err for err in errors)
    
    def test_all_credentials_missing(self):
        """Test multiple errors when all credentials missing."""
        section = {}
        
        errors = _validate_screenscraper(section)
        
        assert len(errors) == 5  # All 5 required fields


@pytest.mark.unit
class TestPathsValidation:
    """Test paths section validation."""
    
    def test_valid_paths_section(self, tmp_path):
        """Test validation passes with all required paths."""
        es_systems = tmp_path / "systems.xml"
        es_systems.write_text("<?xml version='1.0'?><systemList></systemList>")
        
        section = {
            'roms': './roms',
            'media': './media',
            'gamelists': './gamelists',
            'es_systems': str(es_systems)
        }
        
        errors = _validate_paths(section)
        
        assert len(errors) == 0
    
    def test_missing_roms_path(self):
        """Test error when roms path is missing."""
        section = {
            'media': './media',
            'gamelists': './gamelists',
            'es_systems': './systems.xml'
        }
        
        errors = _validate_paths(section)
        
        assert any('paths.roms is required' in err for err in errors)
    
    def test_missing_media_path(self):
        """Test error when media path is missing."""
        section = {
            'roms': './roms',
            'gamelists': './gamelists',
            'es_systems': './systems.xml'
        }
        
        errors = _validate_paths(section)
        
        assert any('paths.media is required' in err for err in errors)
    
    def test_missing_gamelists_path(self):
        """Test error when gamelists path is missing."""
        section = {
            'roms': './roms',
            'media': './media',
            'es_systems': './systems.xml'
        }
        
        errors = _validate_paths(section)
        
        assert any('paths.gamelists is required' in err for err in errors)
    
    def test_missing_es_systems_path(self):
        """Test error when es_systems path is missing."""
        section = {
            'roms': './roms',
            'media': './media',
            'gamelists': './gamelists'
        }
        
        errors = _validate_paths(section)
        
        assert any('paths.es_systems is required' in err for err in errors)
    
    def test_es_systems_file_not_found(self):
        """Test error when es_systems file doesn't exist."""
        section = {
            'roms': './roms',
            'media': './media',
            'gamelists': './gamelists',
            'es_systems': '/nonexistent/systems.xml'
        }
        
        errors = _validate_paths(section)
        
        assert any('file not found' in err for err in errors)
    
    def test_es_systems_is_directory(self, tmp_path):
        """Test error when es_systems points to directory."""
        es_dir = tmp_path / "systems"
        es_dir.mkdir()
        
        section = {
            'roms': './roms',
            'media': './media',
            'gamelists': './gamelists',
            'es_systems': str(es_dir)
        }
        
        errors = _validate_paths(section)
        
        assert any('must be a file' in err for err in errors)
    
    def test_empty_path_values(self):
        """Test error when path values are empty strings."""
        section = {
            'roms': '',
            'media': '',
            'gamelists': '',
            'es_systems': ''
        }
        
        errors = _validate_paths(section)
        
        assert len(errors) == 4  # All paths required


@pytest.mark.unit
class TestScrapingValidation:
    """Test scraping options validation."""
    
    def test_valid_scraping_section(self):
        """Test validation passes with valid scraping options."""
        section = {
            'systems': ['nes', 'snes'],
            'media_types': ['covers', 'screenshots'],
            'preferred_regions': ['us', 'eu'],
            'preferred_language': 'en',
            'crc_size_limit': 1073741824,
            'image_min_dimension': 50,
            'name_verification': 'normal'
        }
        
        errors = _validate_scraping(section)
        
        assert len(errors) == 0
    
    def test_systems_not_a_list(self):
        """Test error when systems is not a list."""
        section = {
            'systems': 'nes',
            'media_types': ['covers']
        }
        
        errors = _validate_scraping(section)
        
        assert any('systems must be a list' in err for err in errors)
    
    def test_media_types_not_a_list(self):
        """Test error when media_types is not a list."""
        section = {
            'systems': [],
            'media_types': 'covers'
        }
        
        errors = _validate_scraping(section)
        
        assert any('media_types must be a list' in err for err in errors)
    
    def test_media_types_empty_is_valid(self):
        """Test that empty media_types list is valid (metadata only, no media download)."""
        section = {
            'systems': [],
            'media_types': []
        }
        
        errors = _validate_scraping(section)
        
        # Empty media_types should be valid - means no media download
        media_type_errors = [err for err in errors if 'media_types' in err]
        assert len(media_type_errors) == 0
    
    def test_invalid_media_type(self):
        """Test error when media_types contains invalid type."""
        section = {
            'systems': [],
            'media_types': ['covers', 'invalid_type', 'screenshots']
        }
        
        errors = _validate_scraping(section)
        
        assert any('Invalid media type: invalid_type' in err for err in errors)
    
    def test_multiple_invalid_media_types(self):
        """Test multiple errors for multiple invalid media types."""
        section = {
            'systems': [],
            'media_types': ['bad1', 'covers', 'bad2', 'screenshots', 'bad3']
        }
        
        errors = _validate_scraping(section)
        
        # Should have 3 errors for the 3 invalid types
        invalid_errors = [e for e in errors if 'Invalid media type' in e]
        assert len(invalid_errors) == 3
    
    def test_valid_media_types(self):
        """Test all valid media types are accepted."""
        valid_types = ['covers', 'screenshots', 'titlescreens', 'marquees',
                       '3dboxes', 'backcovers', 'fanart', 'manuals',
                       'miximages', 'physicalmedia', 'videos']
        section = {
            'systems': [],
            'media_types': valid_types
        }
        
        errors = _validate_scraping(section)
        
        assert len(errors) == 0
    
    def test_preferred_regions_not_a_list(self):
        """Test error when preferred_regions is not a list."""
        section = {
            'systems': [],
            'media_types': ['covers'],
            'preferred_regions': 'us'
        }
        
        errors = _validate_scraping(section)
        
        assert any('preferred_regions must be a list' in err for err in errors)
    
    def test_preferred_language_not_two_letters(self):
        """Test error when language code is not 2 characters."""
        section = {
            'systems': [],
            'media_types': ['covers'],
            'preferred_language': 'english'
        }
        
        errors = _validate_scraping(section)
        
        assert any('preferred_language must be a 2-letter code' in err for err in errors)
    
    def test_preferred_language_not_string(self):
        """Test error when language is not a string."""
        section = {
            'systems': [],
            'media_types': ['covers'],
            'preferred_language': 123
        }
        
        errors = _validate_scraping(section)
        
        assert any('preferred_language must be a 2-letter code' in err for err in errors)
    
    def test_crc_size_limit_negative(self):
        """Test error when crc_size_limit is negative."""
        section = {
            'systems': [],
            'media_types': ['covers'],
            'crc_size_limit': -100
        }
        
        errors = _validate_scraping(section)
        
        assert any('crc_size_limit must be a non-negative integer' in err for err in errors)
    
    def test_crc_size_limit_not_integer(self):
        """Test error when crc_size_limit is not an integer."""
        section = {
            'systems': [],
            'media_types': ['covers'],
            'crc_size_limit': 10.5
        }
        
        errors = _validate_scraping(section)
        
        assert any('crc_size_limit must be a non-negative integer' in err for err in errors)
    
    def test_crc_size_limit_zero_is_valid(self):
        """Test that crc_size_limit of 0 is valid (disabled)."""
        section = {
            'systems': [],
            'media_types': ['covers'],
            'crc_size_limit': 0
        }
        
        errors = _validate_scraping(section)
        
        # No errors for crc_size_limit
        assert not any('crc_size_limit' in err for err in errors)
    
    def test_image_min_dimension_zero(self):
        """Test error when image_min_dimension is zero."""
        section = {
            'systems': [],
            'media_types': ['covers'],
            'image_min_dimension': 0
        }
        
        errors = _validate_scraping(section)
        
        assert any('image_min_dimension must be a positive integer' in err for err in errors)
    
    def test_image_min_dimension_negative(self):
        """Test error when image_min_dimension is negative."""
        section = {
            'systems': [],
            'media_types': ['covers'],
            'image_min_dimension': -10
        }
        
        errors = _validate_scraping(section)
        
        assert any('image_min_dimension must be a positive integer' in err for err in errors)
    
    def test_image_min_dimension_not_integer(self):
        """Test error when image_min_dimension is not an integer."""
        section = {
            'systems': [],
            'media_types': ['covers'],
            'image_min_dimension': 50.5
        }
        
        errors = _validate_scraping(section)
        
        assert any('image_min_dimension must be a positive integer' in err for err in errors)
    
    def test_name_verification_invalid_mode(self):
        """Test error when name_verification has invalid mode."""
        section = {
            'systems': [],
            'media_types': ['covers'],
            'name_verification': 'medium'
        }
        
        errors = _validate_scraping(section)
        
        assert any('name_verification must be one of' in err for err in errors)
    
    def test_name_verification_valid_modes(self):
        """Test all valid name_verification modes."""
        valid_modes = ['strict', 'normal', 'lenient', 'disabled']
        
        for mode in valid_modes:
            section = {
                'systems': [],
                'media_types': ['covers'],
                'name_verification': mode
            }
            
            errors = _validate_scraping(section)
            
            assert not any('name_verification' in err for err in errors), \
                f"Mode '{mode}' should be valid"


@pytest.mark.unit
class TestAPIValidation:
    """Test API options validation."""
    
    def test_valid_api_section(self):
        """Test validation passes with valid API options."""
        section = {
            'request_timeout': 30,
            'max_retries': 3,
            'retry_backoff_seconds': 5
        }
        
        errors = _validate_api(section)
        
        assert len(errors) == 0
    
    def test_request_timeout_negative(self):
        """Test error when timeout is negative."""
        section = {'request_timeout': -5}
        
        errors = _validate_api(section)
        
        assert any('request_timeout must be a positive number' in err for err in errors)
    
    def test_request_timeout_zero(self):
        """Test error when timeout is zero."""
        section = {'request_timeout': 0}
        
        errors = _validate_api(section)
        
        assert any('request_timeout must be a positive number' in err for err in errors)
    
    def test_request_timeout_float_valid(self):
        """Test that float timeout values are accepted."""
        section = {'request_timeout': 30.5}
        
        errors = _validate_api(section)
        
        assert not any('request_timeout' in err for err in errors)
    
    def test_request_timeout_not_numeric(self):
        """Test error when timeout is not numeric."""
        section = {'request_timeout': '30'}
        
        errors = _validate_api(section)
        
        assert any('request_timeout must be a positive number' in err for err in errors)
    
    def test_max_retries_negative(self):
        """Test error when retries is negative."""
        section = {'max_retries': -1}
        
        errors = _validate_api(section)
        
        assert any('max_retries must be a non-negative integer' in err for err in errors)
    
    def test_max_retries_zero_is_valid(self):
        """Test that zero retries is valid (disabled)."""
        section = {'max_retries': 0}
        
        errors = _validate_api(section)
        
        assert not any('max_retries' in err for err in errors)
    
    def test_max_retries_not_integer(self):
        """Test error when retries is not an integer."""
        section = {'max_retries': 3.5}
        
        errors = _validate_api(section)
        
        assert any('max_retries must be a non-negative integer' in err for err in errors)
    
    def test_retry_backoff_negative(self):
        """Test error when backoff is negative."""
        section = {'retry_backoff_seconds': -5}
        
        errors = _validate_api(section)
        
        assert any('retry_backoff_seconds must be non-negative' in err for err in errors)
    
    def test_retry_backoff_zero_is_valid(self):
        """Test that zero backoff is valid."""
        section = {'retry_backoff_seconds': 0}
        
        errors = _validate_api(section)
        
        assert not any('retry_backoff_seconds' in err for err in errors)
    
    def test_retry_backoff_float_valid(self):
        """Test that float backoff values are accepted."""
        section = {'retry_backoff_seconds': 2.5}
        
        errors = _validate_api(section)
        
        assert not any('retry_backoff_seconds' in err for err in errors)


@pytest.mark.unit
class TestLoggingValidation:
    """Test logging options validation."""
    
    def test_valid_logging_section(self):
        """Test validation passes with valid logging options."""
        section = {
            'level': 'INFO',
            'console': True
        }
        
        errors = _validate_logging(section)
        
        assert len(errors) == 0
    
    def test_log_level_invalid(self):
        """Test error when log level is invalid."""
        section = {'level': 'TRACE'}
        
        errors = _validate_logging(section)
        
        assert any('logging.level must be one of' in err for err in errors)
    
    def test_log_level_valid_options(self):
        """Test all valid log levels."""
        valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR']
        
        for level in valid_levels:
            section = {'level': level, 'console': True}
            
            errors = _validate_logging(section)
            
            assert not any('logging.level' in err for err in errors), \
                f"Level '{level}' should be valid"
    
    def test_log_level_case_sensitive(self):
        """Test that log level is case-sensitive."""
        section = {'level': 'info'}  # lowercase
        
        errors = _validate_logging(section)
        
        assert any('logging.level must be one of' in err for err in errors)
    
    def test_console_not_boolean(self):
        """Test error when console is not a boolean."""
        section = {'level': 'INFO', 'console': 'yes'}
        
        errors = _validate_logging(section)
        
        assert any('logging.console must be a boolean' in err for err in errors)
    
    def test_console_integer_not_valid(self):
        """Test that integer values for console are invalid."""
        section = {'level': 'INFO', 'console': 1}
        
        errors = _validate_logging(section)
        
        assert any('logging.console must be a boolean' in err for err in errors)


@pytest.mark.unit
class TestRuntimeValidation:
    """Test runtime options validation."""
    
    def test_valid_runtime_section(self):
        """Test validation passes with valid runtime options."""
        section = {
            'dry_run': False,
            'threads': 4
        }
        
        errors = _validate_runtime(section)
        
        assert len(errors) == 0
    
    def test_dry_run_not_boolean(self):
        """Test error when dry_run is not a boolean."""
        section = {'dry_run': 'false'}
        
        errors = _validate_runtime(section)
        
        assert any('runtime.dry_run must be a boolean' in err for err in errors)
    
    def test_threads_zero(self):
        """Test error when threads is zero."""
        section = {'threads': 0}
        
        errors = _validate_runtime(section)
        
        assert any('runtime.threads must be a positive integer' in err for err in errors)
    
    def test_threads_negative(self):
        """Test error when threads is negative."""
        section = {'threads': -2}
        
        errors = _validate_runtime(section)
        
        assert any('runtime.threads must be a positive integer' in err for err in errors)
    
    def test_threads_not_integer(self):
        """Test error when threads is not an integer."""
        section = {'threads': 4.5}
        
        errors = _validate_runtime(section)
        
        assert any('runtime.threads must be a positive integer' in err for err in errors)
    
    def test_threads_one_is_valid(self):
        """Test that single thread is valid."""
        section = {'threads': 1}
        
        errors = _validate_runtime(section)
        
        assert not any('threads' in err for err in errors)


@pytest.mark.unit
class TestSearchValidation:
    """Test search options validation."""
    
    def test_valid_search_section(self):
        """Test validation passes with valid search options."""
        section = {
            'enable_search_fallback': True,
            'confidence_threshold': 0.7,
            'max_results': 5,
            'interactive_search': False
        }
        
        errors = _validate_search(section)
        
        assert len(errors) == 0
    
    def test_enable_search_fallback_not_boolean(self):
        """Test error when enable_search_fallback is not a boolean."""
        section = {'enable_search_fallback': 'true'}
        
        errors = _validate_search(section)
        
        assert any('enable_search_fallback must be a boolean' in err for err in errors)
    
    def test_confidence_threshold_below_zero(self):
        """Test error when threshold is below 0.0."""
        section = {'confidence_threshold': -0.1}
        
        errors = _validate_search(section)
        
        assert any('confidence_threshold must be between 0.0 and 1.0' in err for err in errors)
    
    def test_confidence_threshold_above_one(self):
        """Test error when threshold is above 1.0."""
        section = {'confidence_threshold': 1.5}
        
        errors = _validate_search(section)
        
        assert any('confidence_threshold must be between 0.0 and 1.0' in err for err in errors)
    
    def test_confidence_threshold_boundary_values(self):
        """Test that 0.0 and 1.0 are valid boundary values."""
        for threshold in [0.0, 1.0]:
            section = {'confidence_threshold': threshold}
            
            errors = _validate_search(section)
            
            assert not any('confidence_threshold' in err for err in errors), \
                f"Threshold {threshold} should be valid"
    
    def test_confidence_threshold_not_numeric(self):
        """Test error when threshold is not numeric."""
        section = {'confidence_threshold': '0.7'}
        
        errors = _validate_search(section)
        
        assert any('confidence_threshold must be between 0.0 and 1.0' in err for err in errors)
    
    def test_max_results_below_one(self):
        """Test error when max_results is below 1."""
        section = {'max_results': 0}
        
        errors = _validate_search(section)
        
        assert any('max_results must be between 1 and 10' in err for err in errors)
    
    def test_max_results_above_ten(self):
        """Test error when max_results is above 10."""
        section = {'max_results': 15}
        
        errors = _validate_search(section)
        
        assert any('max_results must be between 1 and 10' in err for err in errors)
    
    def test_max_results_boundary_values(self):
        """Test that 1 and 10 are valid boundary values."""
        for max_res in [1, 10]:
            section = {'max_results': max_res}
            
            errors = _validate_search(section)
            
            assert not any('max_results' in err for err in errors), \
                f"max_results {max_res} should be valid"
    
    def test_max_results_not_integer(self):
        """Test error when max_results is not an integer."""
        section = {'max_results': 5.5}
        
        errors = _validate_search(section)
        
        assert any('max_results must be between 1 and 10' in err for err in errors)
    
    def test_interactive_search_not_boolean(self):
        """Test error when interactive_search is not a boolean."""
        section = {'interactive_search': 1}
        
        errors = _validate_search(section)
        
        assert any('interactive_search must be a boolean' in err for err in errors)
