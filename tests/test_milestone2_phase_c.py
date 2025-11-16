"""
Tests for Milestone 2 Phase C: Resilience & UX

Tests checkpoint management, console UI, prompts, and rate limit overrides.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from io import StringIO

from curateur.workflow.checkpoint import CheckpointManager, CheckpointData, prompt_resume_from_checkpoint
from curateur.ui.prompts import PromptSystem
from curateur.api.rate_override import RateLimitOverride, RateLimits


# ============================================================================
# CheckpointManager Tests
# ============================================================================

class TestCheckpointManager:
    """Test checkpoint save/load/resume functionality"""
    
    def test_init_checkpoint_data(self, tmp_path):
        """Test checkpoint initialization"""
        config = {'scraping': {'checkpoint_interval': 100}}
        manager = CheckpointManager(str(tmp_path), 'nes', config)
        
        assert manager.system_name == 'nes'
        assert manager.interval == 100
        assert manager.processed_count == 0
        assert manager.data['system'] == 'nes'
        assert manager.data['processed_roms'] == []
        assert manager.data['failed_roms'] == []
        assert manager.data['stats']['total_roms'] == 0
    
    def test_checkpoint_disabled_when_interval_zero(self, tmp_path):
        """Test checkpointing is disabled when interval is 0"""
        config = {'scraping': {'checkpoint_interval': 0}}
        manager = CheckpointManager(str(tmp_path), 'nes', config)
        
        manager.add_processed_rom('game1.nes', 'full_scrape', True)
        manager.save_checkpoint()  # Should not create file
        
        assert not manager.checkpoint_file.exists()
    
    def test_save_checkpoint_at_interval(self, tmp_path):
        """Test checkpoint saves at configured interval"""
        config = {'scraping': {'checkpoint_interval': 10}}
        manager = CheckpointManager(str(tmp_path), 'nes', config)
        manager.set_total_roms(100)
        
        # Process 9 ROMs - should not save
        for i in range(9):
            manager.add_processed_rom(f'game{i}.nes', 'full_scrape', True)
            manager.save_checkpoint()
        
        assert not manager.checkpoint_file.exists()
        
        # Process 10th ROM - should save
        manager.add_processed_rom('game10.nes', 'full_scrape', True)
        manager.save_checkpoint()
        
        assert manager.checkpoint_file.exists()
        
        # Verify checkpoint content
        with open(manager.checkpoint_file) as f:
            data = json.load(f)
        
        assert data['system'] == 'nes'
        assert data['stats']['processed'] == 10
        assert len(data['processed_roms']) == 10
    
    def test_save_checkpoint_forced(self, tmp_path):
        """Test forced checkpoint save regardless of interval"""
        config = {'scraping': {'checkpoint_interval': 100}}
        manager = CheckpointManager(str(tmp_path), 'nes', config)
        
        manager.add_processed_rom('game1.nes', 'full_scrape', True)
        manager.save_checkpoint(force=True)  # Force save before interval
        
        assert manager.checkpoint_file.exists()
    
    def test_load_checkpoint(self, tmp_path):
        """Test loading existing checkpoint"""
        config = {'scraping': {'checkpoint_interval': 10}}
        
        # Create checkpoint
        manager1 = CheckpointManager(str(tmp_path), 'nes', config)
        manager1.set_total_roms(100)
        manager1.add_processed_rom('game1.nes', 'full_scrape', True)
        manager1.add_processed_rom('game2.nes', 'full_scrape', True)
        manager1.add_processed_rom('game3.nes', 'full_scrape', False, 'API error')
        manager1.save_checkpoint(force=True)
        
        # Load checkpoint in new manager
        manager2 = CheckpointManager(str(tmp_path), 'nes', config)
        checkpoint = manager2.load_checkpoint()
        
        assert checkpoint is not None
        assert checkpoint.system == 'nes'
        assert len(checkpoint.processed_roms) == 3
        assert checkpoint.stats['processed'] == 3
        assert checkpoint.stats['successful'] == 2
        assert checkpoint.stats['failed'] == 1
        assert len(checkpoint.failed_roms) == 1
        assert checkpoint.failed_roms[0]['filename'] == 'game3.nes'
    
    def test_load_checkpoint_missing_file(self, tmp_path):
        """Test loading when no checkpoint exists"""
        config = {'scraping': {'checkpoint_interval': 10}}
        manager = CheckpointManager(str(tmp_path), 'nes', config)
        
        checkpoint = manager.load_checkpoint()
        assert checkpoint is None
    
    def test_load_checkpoint_system_mismatch(self, tmp_path):
        """Test loading checkpoint for wrong system"""
        config = {'scraping': {'checkpoint_interval': 10}}
        
        # Create checkpoint for 'nes'
        manager1 = CheckpointManager(str(tmp_path), 'nes', config)
        manager1.add_processed_rom('game1.nes', 'full_scrape', True)
        manager1.save_checkpoint(force=True)
        
        # Try to load for 'snes'
        manager2 = CheckpointManager(str(tmp_path), 'snes', config)
        checkpoint = manager2.load_checkpoint()
        
        assert checkpoint is None  # Should reject mismatched system
    
    def test_is_processed(self, tmp_path):
        """Test checking if ROM was processed"""
        config = {'scraping': {'checkpoint_interval': 10}}
        manager = CheckpointManager(str(tmp_path), 'nes', config)
        
        assert not manager.is_processed('game1.nes')
        
        manager.add_processed_rom('game1.nes', 'full_scrape', True)
        assert manager.is_processed('game1.nes')
        assert not manager.is_processed('game2.nes')
    
    def test_add_processed_rom_success(self, tmp_path):
        """Test recording successful ROM processing"""
        config = {'scraping': {'checkpoint_interval': 10}}
        manager = CheckpointManager(str(tmp_path), 'nes', config)
        
        manager.add_processed_rom('game1.nes', 'full_scrape', True)
        
        assert manager.processed_count == 1
        assert manager.data['stats']['processed'] == 1
        assert manager.data['stats']['successful'] == 1
        assert manager.data['stats']['failed'] == 0
        assert 'game1.nes' in manager.data['processed_roms']
    
    def test_add_processed_rom_failure(self, tmp_path):
        """Test recording failed ROM processing"""
        config = {'scraping': {'checkpoint_interval': 10}}
        manager = CheckpointManager(str(tmp_path), 'nes', config)
        
        manager.add_processed_rom('game1.nes', 'full_scrape', False, 'Network timeout')
        
        assert manager.data['stats']['failed'] == 1
        assert len(manager.data['failed_roms']) == 1
        assert manager.data['failed_roms'][0]['filename'] == 'game1.nes'
        assert manager.data['failed_roms'][0]['reason'] == 'Network timeout'
    
    def test_add_processed_rom_action_counts(self, tmp_path):
        """Test action-specific counting (skip, media_only)"""
        config = {'scraping': {'checkpoint_interval': 10}}
        manager = CheckpointManager(str(tmp_path), 'nes', config)
        
        manager.add_processed_rom('game1.nes', 'skip', True)
        manager.add_processed_rom('game2.nes', 'media_only', True)
        manager.add_processed_rom('game3.nes', 'full_scrape', True)
        
        assert manager.data['stats']['skipped'] == 1
        assert manager.data['stats']['media_only'] == 1
        assert manager.data['stats']['successful'] == 3
    
    def test_update_api_quota(self, tmp_path):
        """Test API quota tracking"""
        config = {'scraping': {'checkpoint_interval': 10}}
        manager = CheckpointManager(str(tmp_path), 'nes', config)
        
        quota_info = {
            'maxrequestsseconds': 2.0,
            'maxrequestsperday': 10000,
            'requeststoday': 1234
        }
        
        manager.update_api_quota(quota_info)
        
        assert manager.data['api_quota']['max_requests_per_second'] == 2.0
        assert manager.data['api_quota']['max_requests_per_day'] == 10000
        assert manager.data['api_quota']['requests_today'] == 1234
        assert 'last_updated' in manager.data['api_quota']
    
    def test_remove_checkpoint(self, tmp_path):
        """Test checkpoint removal after completion"""
        config = {'scraping': {'checkpoint_interval': 10}}
        manager = CheckpointManager(str(tmp_path), 'nes', config)
        
        manager.add_processed_rom('game1.nes', 'full_scrape', True)
        manager.save_checkpoint(force=True)
        assert manager.checkpoint_file.exists()
        
        manager.remove_checkpoint()
        assert not manager.checkpoint_file.exists()
    
    def test_atomic_write(self, tmp_path):
        """Test checkpoint uses atomic write (temp + rename)"""
        config = {'scraping': {'checkpoint_interval': 1}}
        manager = CheckpointManager(str(tmp_path), 'nes', config)
        
        manager.add_processed_rom('game1.nes', 'full_scrape', True)
        manager.save_checkpoint()
        
        # Verify no temp file left behind
        temp_file = manager.checkpoint_file.with_suffix('.tmp')
        assert not temp_file.exists()
        assert manager.checkpoint_file.exists()


class TestPromptResumeFromCheckpoint:
    """Test checkpoint resume prompt"""
    
    @patch('builtins.input', return_value='y')
    def test_prompt_resume_yes(self, mock_input):
        """Test user confirms resume"""
        checkpoint = CheckpointData(
            system='nes',
            timestamp='2025-11-15T10:00:00',
            processed_roms=['game1.nes', 'game2.nes'],
            failed_roms=[],
            api_quota={'requests_today': 100},
            stats={'total_roms': 100, 'processed': 2, 'successful': 2, 'failed': 0, 'skipped': 0, 'media_only': 0}
        )
        
        result = prompt_resume_from_checkpoint(checkpoint)
        assert result is True
    
    @patch('builtins.input', return_value='n')
    def test_prompt_resume_no(self, mock_input):
        """Test user declines resume"""
        checkpoint = CheckpointData(
            system='nes',
            timestamp='2025-11-15T10:00:00',
            processed_roms=[],
            failed_roms=[],
            api_quota={},
            stats={'total_roms': 0, 'processed': 0, 'successful': 0, 'failed': 0, 'skipped': 0, 'media_only': 0}
        )
        
        result = prompt_resume_from_checkpoint(checkpoint)
        assert result is False


# ============================================================================
# PromptSystem Tests
# ============================================================================

class TestPromptSystem:
    """Test interactive prompt system"""
    
    @patch('builtins.input', return_value='y')
    def test_confirm_yes(self, mock_input):
        """Test confirmation with yes response"""
        prompts = PromptSystem()
        result = prompts.confirm("Continue?")
        assert result is True
    
    @patch('builtins.input', return_value='n')
    def test_confirm_no(self, mock_input):
        """Test confirmation with no response"""
        prompts = PromptSystem()
        result = prompts.confirm("Continue?")
        assert result is False
    
    @patch('builtins.input', return_value='')
    def test_confirm_default_yes(self, mock_input):
        """Test confirmation using default yes"""
        prompts = PromptSystem()
        result = prompts.confirm("Continue?", default='y')
        assert result is True
    
    @patch('builtins.input', return_value='')
    def test_confirm_default_no(self, mock_input):
        """Test confirmation using default no"""
        prompts = PromptSystem()
        result = prompts.confirm("Continue?", default='n')
        assert result is False
    
    @patch('builtins.input', side_effect=['invalid', 'y'])
    def test_confirm_invalid_then_valid(self, mock_input):
        """Test confirmation handles invalid input then accepts valid"""
        prompts = PromptSystem()
        result = prompts.confirm("Continue?")
        assert result is True
        assert mock_input.call_count == 2
    
    @patch('builtins.input', return_value='2')
    def test_choose_by_number(self, mock_input):
        """Test multiple choice selection"""
        prompts = PromptSystem()
        choices = ['low', 'medium', 'high']
        result = prompts.choose("Select quality:", choices)
        assert result == 'medium'
    
    @patch('builtins.input', return_value='')
    def test_choose_default(self, mock_input):
        """Test multiple choice with default"""
        prompts = PromptSystem()
        choices = ['skip', 'retry', 'abort']
        result = prompts.choose("What to do?", choices, default=1)
        assert result == 'retry'
    
    @patch('builtins.input', side_effect=['0', '4', '2'])
    def test_choose_invalid_then_valid(self, mock_input):
        """Test choice handles out-of-range then accepts valid"""
        prompts = PromptSystem()
        choices = ['one', 'two', 'three']
        result = prompts.choose("Pick one:", choices)
        assert result == 'two'
        assert mock_input.call_count == 3
    
    @patch('builtins.input', return_value='test_value')
    def test_input_text(self, mock_input):
        """Test text input"""
        prompts = PromptSystem()
        result = prompts.input_text("Enter name:")
        assert result == 'test_value'
    
    @patch('builtins.input', return_value='')
    def test_input_text_default(self, mock_input):
        """Test text input with default"""
        prompts = PromptSystem()
        result = prompts.input_text("Enter name:", default='default_name')
        assert result == 'default_name'
    
    @patch('builtins.input', side_effect=['invalid123', 'valid'])
    def test_input_text_validator(self, mock_input):
        """Test text input with validator"""
        prompts = PromptSystem()
        result = prompts.input_text(
            "Enter name:",
            validator=lambda x: x.isalpha()  # Only letters
        )
        assert result == 'valid'
        assert mock_input.call_count == 2
    
    @patch('builtins.input', return_value='42')
    def test_input_int(self, mock_input):
        """Test integer input"""
        prompts = PromptSystem()
        result = prompts.input_int("Enter count:")
        assert result == 42
    
    @patch('builtins.input', return_value='')
    def test_input_int_default(self, mock_input):
        """Test integer input with default"""
        prompts = PromptSystem()
        result = prompts.input_int("Enter count:", default=10)
        assert result == 10
    
    @patch('builtins.input', side_effect=['0', '101', '50'])
    def test_input_int_range_validation(self, mock_input):
        """Test integer input with range validation"""
        prompts = PromptSystem()
        result = prompts.input_int("Enter count:", min_value=1, max_value=100)
        assert result == 50
        assert mock_input.call_count == 3


# ============================================================================
# RateLimitOverride Tests
# ============================================================================

class TestRateLimitOverride:
    """Test rate limit override system"""
    
    def test_override_disabled_by_default(self):
        """Test overrides are disabled by default"""
        config = {'scraping': {}}
        override = RateLimitOverride(config)
        
        assert not override.is_enabled()
    
    def test_get_effective_limits_defaults_only(self):
        """Test effective limits with no API or overrides"""
        config = {'scraping': {}}
        override = RateLimitOverride(config)

        limits = override.get_effective_limits(None)

        assert limits.max_threads == RateLimitOverride.DEFAULT_MAX_THREADS
        assert limits.requests_per_minute == RateLimitOverride.DEFAULT_REQUESTS_PER_MINUTE
        assert limits.daily_quota == RateLimitOverride.DEFAULT_DAILY_QUOTA

    def test_get_effective_limits_api_provided(self):
        """Test effective limits with API-provided values"""
        config = {'scraping': {}}
        override = RateLimitOverride(config)

        api_limits = {
            'maxthreads': 4,
            'maxrequestspermin': 120,
            'maxrequestsperday': 20000
        }

        limits = override.get_effective_limits(api_limits)

        assert limits.max_threads == 4
        assert limits.requests_per_minute == 120
        assert limits.daily_quota == 20000

    def test_get_effective_limits_overrides_enabled(self):
        """Test overrides respect API limits (cannot exceed)"""
        config = {
            'scraping': {
                'rate_limit_override_enabled': True,
                'rate_limit_override': {
                    'max_threads': 2,
                    'requests_per_minute': 60,
                    'daily_quota': 5000
                }
            }
        }
        override = RateLimitOverride(config)

        api_limits = {
            'maxthreads': 4,
            'maxrequestspermin': 120,
            'maxrequestsperday': 20000
        }

        limits = override.get_effective_limits(api_limits)

        # Overrides below API limits are honored
        assert limits.max_threads == 2
        assert limits.requests_per_minute == 60
        assert limits.daily_quota == 5000

    def test_get_effective_limits_partial_overrides(self):
        """Test partial overrides (only some fields overridden)"""
        config = {
            'scraping': {
                'rate_limit_override_enabled': True,
                'rate_limit_override': {
                    'max_threads': 2  # Only override threads
                }
            }
        }
        override = RateLimitOverride(config)

        api_limits = {
            'maxthreads': 4,
            'maxrequestspermin': 120,
            'maxrequestsperday': 20000
        }

        limits = override.get_effective_limits(api_limits)

        # Thread override applied, others from API
        assert limits.max_threads == 2
        assert limits.requests_per_minute == 120
        assert limits.daily_quota == 20000

    def test_validate_overrides_within_limits(self):
        """Test validation passes for reasonable overrides"""
        config = {
            'scraping': {
                'rate_limit_override_enabled': True,
                'rate_limit_override': {
                    'max_threads': 2,
                    'requests_per_minute': 90,
                    'daily_quota': 15000
                }
            }
        }
        
        # Should not raise, just log info
        override = RateLimitOverride(config)
        override.validate_overrides()  # No exception expected
    
    def test_validate_overrides_exceeds_typical(self, caplog):
        """Test validation warns when exceeding typical limits"""
        config = {
            'scraping': {
                'rate_limit_override_enabled': True,
                'rate_limit_override': {
                    'max_threads': 10,  # Exceeds typical of 4
                    'requests_per_minute': 300,  # Exceeds typical of 120
                    'daily_quota': 50000  # Exceeds typical of 20000
                }
            }
        }

        with caplog.at_level('WARNING'):
            override = RateLimitOverride(config)

        # Should have warnings in log
        assert 'max_threads=10 exceeds typical limit' in caplog.text
        assert 'requests_per_minute=300 exceeds typical limit' in caplog.text
        assert 'daily_quota=50000 exceeds typical limit' in caplog.text

    def test_validate_overrides_invalid_values(self, caplog):
        """Test validation warns for invalid values"""
        config = {
            'scraping': {
                'rate_limit_override_enabled': True,
                'rate_limit_override': {
                    'max_threads': 0,  # Invalid
                    'requests_per_minute': -1,  # Invalid
                    'daily_quota': 0  # Invalid
                }
            }
        }

        with caplog.at_level('WARNING'):
            override = RateLimitOverride(config)

        assert 'max_threads=0 is invalid' in caplog.text
        assert 'requests_per_minute=-1 is invalid' in caplog.text
        assert 'daily_quota=0 is invalid' in caplog.text

    def test_get_override_summary_disabled(self):
        """Test summary when overrides disabled"""
        config = {'scraping': {}}
        override = RateLimitOverride(config)
        
        summary = override.get_override_summary()
        assert "DISABLED" in summary
    
    def test_get_override_summary_enabled(self):
        """Test summary when overrides enabled"""
        config = {
            'scraping': {
                'rate_limit_override_enabled': True,
                'rate_limit_override': {
                    'max_threads': 2,
                    'requests_per_minute': 60
                }
            }
        }
        override = RateLimitOverride(config)

        summary = override.get_override_summary()
        assert "ENABLED" in summary
        assert "max_threads: 2" in summary
        assert "requests_per_minute: 60" in summary

    def test_get_effective_limits_caps_excessive_overrides(self, caplog):
        """Test that overrides exceeding API limits are capped with warning"""
        config = {
            'scraping': {
                'rate_limit_override_enabled': True,
                'rate_limit_override': {
                    'max_threads': 10,  # Exceeds API limit of 4
                    'requests_per_minute': 240,  # Exceeds API limit of 120
                    'daily_quota': 50000  # Exceeds API limit of 20000
                }
            }
        }
        override = RateLimitOverride(config)

        api_limits = {
            'maxthreads': 4,
            'maxrequestspermin': 120,
            'maxrequestsperday': 20000
        }

        with caplog.at_level('WARNING'):
            limits = override.get_effective_limits(api_limits)

        # Should cap at API limits
        assert limits.max_threads == 4
        assert limits.requests_per_minute == 120
        assert limits.daily_quota == 20000

        # Should have warnings about capping
        assert 'max_threads=10 exceeds API limit=4' in caplog.text
        assert 'requests_per_minute=240 exceeds API limit=120' in caplog.text
        assert 'daily_quota=50000 exceeds API limit=20000' in caplog.text

# ============================================================================
# Integration Tests
# ============================================================================

class TestPhaseCIntegration:
    """Integration tests for Phase C components"""
    
    def test_checkpoint_workflow(self, tmp_path):
        """Test complete checkpoint workflow: create, save, resume"""
        config = {'scraping': {'checkpoint_interval': 5}}
        
        # Step 1: Create checkpoint during processing
        manager1 = CheckpointManager(str(tmp_path), 'nes', config)
        manager1.set_total_roms(20)
        
        for i in range(10):
            success = i != 7  # Simulate one failure
            reason = 'API error' if not success else None
            manager1.add_processed_rom(f'game{i}.nes', 'full_scrape', success, reason)
            manager1.save_checkpoint()
        
        # Update quota
        manager1.update_api_quota({
            'maxrequestsperday': 10000,
            'requeststoday': 150
        })
        manager1.save_checkpoint(force=True)
        
        # Step 2: Load and resume
        manager2 = CheckpointManager(str(tmp_path), 'nes', config)
        checkpoint = manager2.load_checkpoint()
        
        assert checkpoint is not None
        assert len(checkpoint.processed_roms) == 10
        assert checkpoint.stats['successful'] == 9
        assert checkpoint.stats['failed'] == 1
        
        # Continue processing
        for i in range(10, 20):
            if not manager2.is_processed(f'game{i}.nes'):
                manager2.add_processed_rom(f'game{i}.nes', 'full_scrape', True)
                manager2.save_checkpoint()
        
        # Step 3: Complete and cleanup
        final_stats = manager2.get_stats()
        assert final_stats['processed'] == 20
        
        manager2.remove_checkpoint()
        assert not manager2.checkpoint_file.exists()
    
    def test_rate_override_with_quota_monitoring(self):
        """Test rate override integration with quota tracking"""
        config = {
            'scraping': {
                'rate_limit_override_enabled': True,
                'rate_limit_override': {
                    'max_threads': 2,
                    'daily_quota': 5000
                }
            }
        }
        
        override = RateLimitOverride(config)
        
        # Simulate API response with higher limits
        api_limits = {
            'maxthreads': 4,
            'maxrequestspermin': 120,
            'maxrequestsperday': 10000,
            'requeststoday': 4800  # Near override limit
        }
        
        # Get effective limits (overrides should apply)
        limits = override.get_effective_limits(api_limits)
        
        assert limits.max_threads == 2  # Overridden (conservative)
        assert limits.requests_per_minute == 120  # From API (no override)
        assert limits.daily_quota == 5000  # Overridden (conservative)
        
        # Check if we're near quota
        requests_remaining = limits.daily_quota - api_limits['requeststoday']
        assert requests_remaining == 200  # 5000 - 4800
