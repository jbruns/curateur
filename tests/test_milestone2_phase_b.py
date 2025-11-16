"""
Milestone 2 Phase B Integration Tests

Tests for Update Mode, Hash Comparison, Metadata Merging, and Change Detection.
"""

import pytest
from pathlib import Path
import tempfile
import shutil
from typing import Dict, List

from curateur.workflow.hash_comparator import HashComparator, HashComparison
from curateur.gamelist.metadata_merger import MetadataMerger, MergeResult
from curateur.workflow.update_coordinator import UpdateCoordinator, UpdateDecision
from curateur.workflow.change_detector import ChangeDetector, ChangeReport


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_dir():
    """Create temporary directory for tests"""
    temp = tempfile.mkdtemp()
    yield Path(temp)
    shutil.rmtree(temp)


@pytest.fixture
def sample_config():
    """Sample configuration"""
    return {
        'scraping': {
            'update_policy': 'changed_only',
            'update_metadata': True,
            'update_media': True,
            'media_types': ['screenshot', 'titlescreen', 'marquee'],
            'merge_strategy': 'preserve_user_edits',
            'log_changes': True,
            'log_unchanged_fields': False,
        }
    }


@pytest.fixture
def mock_hash_calculator():
    """Mock hash calculator for testing"""
    class MockHashCalculator:
        def __init__(self):
            self.hashes = {}
        
        def calculate_md5(self, file_path):
            return self.hashes.get(str(file_path), 'default_hash')
        
        def calculate_crc(self, file_path):
            return self.hashes.get(str(file_path), 'default_crc')
        
        def set_hash(self, file_path, hash_value):
            self.hashes[str(file_path)] = hash_value
    
    return MockHashCalculator()


@pytest.fixture
def existing_metadata():
    """Sample existing gamelist metadata"""
    return {
        'path': './game1.rom',
        'name': 'Game 1',
        'desc': 'Original description',
        'rating': '0.8',
        'developer': 'Dev Studio',
        'hash': 'abc123',
        'favorite': 'true',
        'playcount': '5',
    }


@pytest.fixture
def api_response_metadata():
    """Sample API response metadata"""
    return {
        'path': './game1.rom',
        'name': 'Game 1 Updated',
        'desc': 'Updated description from API',
        'rating': '0.9',
        'developer': 'Dev Studio Inc',
        'publisher': 'New Publisher',
        'hash': 'xyz789',
    }


# ============================================================================
# HashComparator Tests
# ============================================================================

class TestHashComparator:
    """Test Hash Comparator functionality"""
    
    def test_hash_match_unchanged(self, mock_hash_calculator, temp_dir):
        """Test unchanged ROM with matching hash"""
        comparator = HashComparator(mock_hash_calculator)
        
        rom_path = temp_dir / "game1.rom"
        rom_path.touch()
        
        stored_hash = 'abc123'
        mock_hash_calculator.set_hash(rom_path, 'abc123')
        
        result = comparator.compare_rom_hash(rom_path, stored_hash, 'md5')
        
        assert result.has_changed is False
        assert result.stored_hash == 'abc123'
        assert result.current_hash == 'abc123'
        assert result.hash_type == 'md5'
    
    def test_hash_mismatch_changed(self, mock_hash_calculator, temp_dir):
        """Test changed ROM with mismatched hash"""
        comparator = HashComparator(mock_hash_calculator)
        
        rom_path = temp_dir / "game2.rom"
        rom_path.touch()
        
        stored_hash = 'abc123'
        mock_hash_calculator.set_hash(rom_path, 'xyz789')
        
        result = comparator.compare_rom_hash(rom_path, stored_hash, 'md5')
        
        assert result.has_changed is True
        assert result.stored_hash == 'abc123'
        assert result.current_hash == 'xyz789'
        assert result.hash_type == 'md5'
    
    def test_no_stored_hash_assumes_changed(self, mock_hash_calculator, temp_dir):
        """Test ROM with no stored hash is marked as changed"""
        comparator = HashComparator(mock_hash_calculator)
        
        rom_path = temp_dir / "game3.rom"
        rom_path.touch()
        
        result = comparator.compare_rom_hash(rom_path, None, 'md5')
        
        assert result.has_changed is True
        assert result.stored_hash is None
        assert result.hash_type == 'none'
    
    def test_batch_comparison(self, mock_hash_calculator, temp_dir):
        """Test batch hash comparison"""
        comparator = HashComparator(mock_hash_calculator)
        
        # Create test ROMs
        rom1 = temp_dir / "game1.rom"
        rom2 = temp_dir / "game2.rom"
        rom3 = temp_dir / "game3.rom"
        
        for rom in [rom1, rom2, rom3]:
            rom.touch()
        
        # Set hashes
        mock_hash_calculator.set_hash(rom1, 'hash1')
        mock_hash_calculator.set_hash(rom2, 'hash2_new')
        mock_hash_calculator.set_hash(rom3, 'hash3')
        
        stored_hashes = {
            'game1': 'hash1',  # Match
            'game2': 'hash2_old',  # Mismatch
            'game3': 'hash3',  # Match
        }
        
        results = comparator.compare_batch([rom1, rom2, rom3], stored_hashes, 'md5')
        
        assert len(results) == 3
        assert results['game1'].has_changed is False
        assert results['game2'].has_changed is True
        assert results['game3'].has_changed is False
    
    def test_should_rescrape_policy(self, mock_hash_calculator):
        """Test rescrape decision based on policy"""
        comparator = HashComparator(mock_hash_calculator)
        
        changed = HashComparison('game', True, 'old', 'new', 'md5')
        unchanged = HashComparison('game', False, 'same', 'same', 'md5')
        
        # Always policy
        assert comparator.should_rescrape(changed, 'always') is True
        assert comparator.should_rescrape(unchanged, 'always') is True
        
        # Changed only policy
        assert comparator.should_rescrape(changed, 'changed_only') is True
        assert comparator.should_rescrape(unchanged, 'changed_only') is False
        
        # Never policy
        assert comparator.should_rescrape(changed, 'never') is False
        assert comparator.should_rescrape(unchanged, 'never') is False


# ============================================================================
# MetadataMerger Tests
# ============================================================================

class TestMetadataMerger:
    """Test Metadata Merger functionality"""
    
    def test_preserve_user_editable_fields(self, sample_config,
                                          existing_metadata, api_response_metadata):
        """Test user-editable fields are preserved"""
        merger = MetadataMerger(sample_config)
        
        result = merger.merge_metadata(existing_metadata, api_response_metadata)
        
        # User fields preserved
        assert result.merged_data['favorite'] == 'true'
        assert result.merged_data['playcount'] == '5'
        assert 'favorite' in result.preserved_fields
        assert 'playcount' in result.preserved_fields
    
    def test_update_scraper_managed_fields(self, sample_config,
                                          existing_metadata, api_response_metadata):
        """Test scraper-managed fields are updated"""
        merger = MetadataMerger(sample_config)
        
        result = merger.merge_metadata(existing_metadata, api_response_metadata)
        
        # Scraper fields updated
        assert result.merged_data['name'] == 'Game 1 Updated'
        assert result.merged_data['desc'] == 'Updated description from API'
        assert result.merged_data['rating'] == '0.9'
        assert result.merged_data['developer'] == 'Dev Studio Inc'
        assert 'name' in result.updated_fields
        assert 'desc' in result.updated_fields
    
    def test_preserve_path_field(self, sample_config,
                                existing_metadata, api_response_metadata):
        """Test path field is always preserved"""
        merger = MetadataMerger(sample_config)
        
        # Try to change path in API response
        api_response_metadata['path'] = './different_path.rom'
        
        result = merger.merge_metadata(existing_metadata, api_response_metadata)
        
        # Path should remain unchanged
        assert result.merged_data['path'] == './game1.rom'
        assert 'path' in result.preserved_fields
    
    def test_add_new_fields_from_api(self, sample_config,
                                    existing_metadata, api_response_metadata):
        """Test new fields from API are added"""
        merger = MetadataMerger(sample_config)
        
        result = merger.merge_metadata(existing_metadata, api_response_metadata)
        
        # New field from API
        assert result.merged_data['publisher'] == 'New Publisher'
        assert 'publisher' in result.updated_fields
    
    def test_conflict_detection(self, sample_config,
                               existing_metadata, api_response_metadata):
        """Test conflict detection for changed scraper fields"""
        merger = MetadataMerger(sample_config)
        
        result = merger.merge_metadata(existing_metadata, api_response_metadata)
        
        # Conflicts: scraper fields that differ
        assert 'name' in result.conflicts
        assert 'desc' in result.conflicts
        assert 'rating' in result.conflicts
    
    def test_batch_merge(self, sample_config):
        """Test batch metadata merging"""
        merger = MetadataMerger(sample_config)
        
        existing = {
            'game1': {'name': 'Game 1', 'favorite': 'true'},
            'game2': {'name': 'Game 2', 'playcount': '3'},
        }
        
        api_data = {
            'game1': {'name': 'Game 1 Updated', 'desc': 'New description'},
            'game2': {'name': 'Game 2 Updated', 'rating': '0.8'},
        }
        
        results = merger.merge_batch(existing, api_data)
        
        assert len(results) == 2
        assert results['game1'].merged_data['favorite'] == 'true'
        assert results['game1'].merged_data['name'] == 'Game 1 Updated'
        assert results['game2'].merged_data['playcount'] == '3'
        assert results['game2'].merged_data['name'] == 'Game 2 Updated'
    
    def test_field_category_detection(self, sample_config):
        """Test field category detection"""
        merger = MetadataMerger(sample_config)
        
        assert merger.get_field_category('favorite') == 'user_editable'
        assert merger.get_field_category('name') == 'scraper_managed'
        assert merger.get_field_category('id') == 'protected'
        assert merger.get_field_category('custom_field') == 'custom'


# ============================================================================
# UpdateCoordinator Tests
# ============================================================================

class TestUpdateCoordinator:
    """Test Update Coordinator functionality"""
    
    def test_update_decision_hash_changed(self, sample_config, mock_hash_calculator, temp_dir):
        """Test update decision when hash changed"""
        comparator = HashComparator(mock_hash_calculator)
        merger = MetadataMerger(sample_config)
        coordinator = UpdateCoordinator(sample_config, comparator, merger)
        
        rom_path = temp_dir / "game1.rom"
        rom_path.touch()
        
        rom_info = {'basename': 'game1', 'path': str(rom_path)}
        existing_entry = {'hash': 'old_hash', 'name': 'Game 1'}
        
        mock_hash_calculator.set_hash(rom_path, 'new_hash')
        
        decision = coordinator.determine_update_action(rom_info, existing_entry, 'nes')
        
        assert decision.should_update_metadata is True
        assert decision.should_update_media is True
        assert decision.reason == 'hash_changed'
    
    def test_update_decision_hash_unchanged(self, sample_config, mock_hash_calculator, temp_dir):
        """Test update decision when hash unchanged"""
        comparator = HashComparator(mock_hash_calculator)
        merger = MetadataMerger(sample_config)
        coordinator = UpdateCoordinator(sample_config, comparator, merger)
        
        rom_path = temp_dir / "game2.rom"
        rom_path.touch()
        
        rom_info = {'basename': 'game2', 'path': str(rom_path)}
        existing_entry = {'hash': 'same_hash', 'name': 'Game 2'}
        
        mock_hash_calculator.set_hash(rom_path, 'same_hash')
        
        decision = coordinator.determine_update_action(rom_info, existing_entry, 'nes')
        
        assert decision.should_update_metadata is False
        assert decision.should_update_media is False
        assert decision.reason == 'hash_match'
    
    def test_update_policy_always(self, sample_config, mock_hash_calculator, temp_dir):
        """Test always update policy"""
        sample_config['scraping']['update_policy'] = 'always'
        
        comparator = HashComparator(mock_hash_calculator)
        merger = MetadataMerger(sample_config)
        coordinator = UpdateCoordinator(sample_config, comparator, merger)
        
        rom_path = temp_dir / "game3.rom"
        rom_path.touch()
        
        rom_info = {'basename': 'game3', 'path': str(rom_path)}
        existing_entry = {'hash': 'same_hash', 'name': 'Game 3'}
        
        mock_hash_calculator.set_hash(rom_path, 'same_hash')
        
        decision = coordinator.determine_update_action(rom_info, existing_entry, 'nes')
        
        # Should update even though hash matches
        assert decision.should_update_metadata is True
        assert decision.should_update_media is True
    
    def test_execute_update_metadata(self, sample_config, mock_hash_calculator):
        """Test metadata update execution"""
        comparator = HashComparator(mock_hash_calculator)
        merger = MetadataMerger(sample_config)
        coordinator = UpdateCoordinator(sample_config, comparator, merger)
        
        rom_info = {'basename': 'game1'}
        existing_entry = {'name': 'Old Name', 'favorite': 'true'}
        api_response = {'name': 'New Name', 'desc': 'New description'}
        
        decision = UpdateDecision(
            rom_basename='game1',
            should_update_metadata=True,
            should_update_media=False,
            media_types_to_update=[],
            reason='test'
        )
        
        result = coordinator.execute_update(rom_info, existing_entry, api_response, decision)
        
        assert result.metadata_updated is True
        assert len(result.media_updated) == 0
        assert len(result.errors) == 0
    
    def test_update_statistics(self, sample_config, mock_hash_calculator):
        """Test update statistics calculation"""
        comparator = HashComparator(mock_hash_calculator)
        merger = MetadataMerger(sample_config)
        coordinator = UpdateCoordinator(sample_config, comparator, merger)
        
        from curateur.workflow.update_coordinator import UpdateResult
        
        results = {
            'game1': UpdateResult('game1', True, {'screenshot': True}, []),
            'game2': UpdateResult('game2', False, {}, []),
            'game3': UpdateResult('game3', True, {'screenshot': True, 'titlescreen': False}, ['error']),
        }
        
        stats = coordinator.get_update_statistics(results)
        
        assert stats['total_roms'] == 3
        assert stats['metadata_updated'] == 2
        assert stats['media_updated'] == 2
        assert stats['errors'] == 1


# ============================================================================
# ChangeDetector Tests
# ============================================================================

class TestChangeDetector:
    """Test Change Detector functionality"""
    
    def test_detect_added_fields(self, sample_config):
        """Test detection of added fields"""
        detector = ChangeDetector(sample_config)
        
        old_metadata = {'name': 'Game 1'}
        new_metadata = {'name': 'Game 1', 'desc': 'New description', 'rating': '0.8'}
        
        report = detector.detect_changes(old_metadata, new_metadata, 'game1')
        
        assert report.added_count == 2
        assert report.modified_count == 0
        assert report.removed_count == 0
    
    def test_detect_modified_fields(self, sample_config):
        """Test detection of modified fields"""
        detector = ChangeDetector(sample_config)
        
        old_metadata = {'name': 'Game 1', 'rating': '0.7'}
        new_metadata = {'name': 'Game 1 Updated', 'rating': '0.9'}
        
        report = detector.detect_changes(old_metadata, new_metadata, 'game1')
        
        assert report.added_count == 0
        assert report.modified_count == 2
        assert report.removed_count == 0
    
    def test_detect_removed_fields(self, sample_config):
        """Test detection of removed fields"""
        detector = ChangeDetector(sample_config)
        
        old_metadata = {'name': 'Game 1', 'desc': 'Description', 'old_field': 'value'}
        new_metadata = {'name': 'Game 1'}
        
        report = detector.detect_changes(old_metadata, new_metadata, 'game1')
        
        assert report.added_count == 0
        assert report.modified_count == 0
        assert report.removed_count == 2
    
    def test_detect_unchanged_fields(self, sample_config):
        """Test detection of unchanged fields"""
        detector = ChangeDetector(sample_config)
        
        old_metadata = {'name': 'Game 1', 'rating': '0.8'}
        new_metadata = {'name': 'Game 1', 'rating': '0.8'}
        
        report = detector.detect_changes(old_metadata, new_metadata, 'game1')
        
        assert report.unchanged_count == 2
        assert report.added_count == 0
        assert report.modified_count == 0
    
    def test_batch_change_detection(self, sample_config):
        """Test batch change detection"""
        detector = ChangeDetector(sample_config)
        
        old_entries = {
            'game1': {'name': 'Game 1', 'rating': '0.7'},
            'game2': {'name': 'Game 2'},
        }
        
        new_entries = {
            'game1': {'name': 'Game 1 Updated', 'rating': '0.9'},
            'game2': {'name': 'Game 2', 'desc': 'New desc'},
        }
        
        reports = detector.detect_batch_changes(old_entries, new_entries)
        
        assert len(reports) == 2
        assert reports['game1'].modified_count == 2
        assert reports['game2'].added_count == 1
    
    def test_format_change_summary(self, sample_config):
        """Test change summary formatting"""
        detector = ChangeDetector(sample_config)
        
        old_metadata = {'name': 'Game 1'}
        new_metadata = {'name': 'Game 1 Updated', 'desc': 'New description'}
        
        report = detector.detect_changes(old_metadata, new_metadata, 'game1')
        summary = detector.format_change_summary(report, include_details=True)
        
        assert 'game1' in summary
        assert '1 added' in summary
        assert '1 modified' in summary
    
    def test_significant_changes_filter(self, sample_config):
        """Test filtering for significant changes"""
        detector = ChangeDetector(sample_config)
        
        old_metadata = {'name': 'Game 1', 'rating': '0.8', 'playcount': '5'}
        new_metadata = {'name': 'Game 1 Updated', 'rating': '0.9', 'playcount': '5'}
        
        report = detector.detect_changes(old_metadata, new_metadata, 'game1')
        
        # Only care about name changes
        significant = detector.filter_significant_changes(report, {'name'})
        
        assert len(significant) == 1
        assert significant[0].field_name == 'name'


# ============================================================================
# Integration Tests
# ============================================================================

class TestPhaseBIntegration:
    """Integration tests combining multiple components"""
    
    def test_full_update_workflow(self, sample_config, mock_hash_calculator, temp_dir):
        """Test complete update workflow"""
        # Setup components
        comparator = HashComparator(mock_hash_calculator)
        merger = MetadataMerger(sample_config)
        coordinator = UpdateCoordinator(sample_config, comparator, merger)
        detector = ChangeDetector(sample_config)
        
        # Create ROM
        rom_path = temp_dir / "game1.rom"
        rom_path.touch()
        
        # Setup data
        rom_info = {'basename': 'game1', 'path': str(rom_path)}
        existing_entry = {
            'name': 'Old Name',
            'rating': '0.7',
            'hash': 'old_hash',
            'favorite': 'true',
        }
        api_response = {
            'name': 'New Name',
            'desc': 'New description',
            'rating': '0.9',
            'hash': 'new_hash',
        }
        
        # Simulate changed hash
        mock_hash_calculator.set_hash(rom_path, 'new_hash')
        
        # Determine update action
        decision = coordinator.determine_update_action(rom_info, existing_entry, 'nes')
        assert decision.should_update_metadata is True
        
        # Execute update
        result = coordinator.execute_update(rom_info, existing_entry, api_response, decision)
        assert result.metadata_updated is True
        
        # Get merged metadata from merger directly
        merge_result = merger.merge_metadata(existing_entry, api_response)
        
        # Detect changes
        change_report = detector.detect_changes(existing_entry, merge_result.merged_data, 'game1')
        
        # Verify workflow
        assert change_report.modified_count > 0
        assert merge_result.merged_data['favorite'] == 'true'  # User field preserved
        assert merge_result.merged_data['name'] == 'New Name'  # Scraper field updated
    
    def test_no_update_needed_workflow(self, sample_config, mock_hash_calculator, temp_dir):
        """Test workflow when no update needed"""
        comparator = HashComparator(mock_hash_calculator)
        merger = MetadataMerger(sample_config)
        coordinator = UpdateCoordinator(sample_config, comparator, merger)
        
        rom_path = temp_dir / "game2.rom"
        rom_path.touch()
        
        rom_info = {'basename': 'game2', 'path': str(rom_path)}
        existing_entry = {'name': 'Game 2', 'hash': 'unchanged_hash'}
        
        mock_hash_calculator.set_hash(rom_path, 'unchanged_hash')
        
        decision = coordinator.determine_update_action(rom_info, existing_entry, 'nes')
        
        assert decision.should_update_metadata is False
        assert decision.should_update_media is False
        assert decision.reason == 'hash_match'


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
