"""Tests for integrity_validator module."""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from curateur.gamelist.integrity_validator import IntegrityValidator, ValidationResult
from curateur.gamelist.game_entry import GameEntry


@pytest.mark.unit
class TestIntegrityValidator:
    """Test IntegrityValidator."""
    
    def test_init_with_default_threshold(self):
        """Test initialization with default threshold."""
        validator = IntegrityValidator()
        
        assert validator.threshold == 0.90  # Default threshold (90%)
    
    def test_init_with_custom_threshold(self):
        """Test initialization with custom threshold."""
        validator = IntegrityValidator(threshold=0.90)
        
        assert validator.threshold == 0.90
    
    def test_validate_perfect_match(self, temp_rom_files, temp_gamelist_dir):
        """Test validation with perfect ROM-to-gamelist match."""
        validator = IntegrityValidator(threshold=0.95)
        
        entries = [
            GameEntry(path="./Super Mario Bros.nes", name="Super Mario Bros."),
            GameEntry(path="./The Legend of Zelda.nes", name="The Legend of Zelda"),
            GameEntry(path="./Metroid.nes", name="Metroid")
        ]
        
        rom_files = temp_rom_files
        
        result = validator.validate(entries, rom_files)
        
        assert isinstance(result, ValidationResult)
        assert result.is_valid is True
        assert len(result.missing_roms) == 0
        assert len(result.orphaned_entries) == 0
        assert result.match_ratio == 1.0
    
    def test_validate_missing_roms(self, temp_rom_files, temp_gamelist_dir):
        """Test validation identifies missing ROMs."""
        validator = IntegrityValidator(threshold=0.95)
        
        entries = [
            GameEntry(path="./Super Mario Bros.nes", name="Super Mario Bros."),
            GameEntry(path="./Missing Game.nes", name="Missing Game"),
            GameEntry(path="./Another Missing.nes", name="Another Missing")
        ]
        
        rom_files = temp_rom_files  # Only has 3 specific ROMs
        
        result = validator.validate(entries, rom_files)
        
        assert result.is_valid is False
        assert len(result.missing_roms) == 2
        assert "./Missing Game.nes" in result.missing_roms
        assert "./Another Missing.nes" in result.missing_roms
    
    def test_validate_below_threshold(self, temp_rom_files, temp_gamelist_dir):
        """Test validation fails when below threshold."""
        validator = IntegrityValidator(threshold=0.95)
        
        # Only 1 out of 10 entries match (10% ratio)
        entries = [
            GameEntry(path="./Super Mario Bros.nes", name="Super Mario Bros."),
        ] + [
            GameEntry(path=f"./Missing{i}.nes", name=f"Missing {i}")
            for i in range(9)
        ]
        
        rom_files = temp_rom_files
        
        result = validator.validate(entries, rom_files)
        
        assert result.is_valid is False
        assert result.match_ratio < 0.95
    
    def test_calculate_match_ratio(self):
        """Test match ratio calculation."""
        validator = IntegrityValidator()
        
        # 7 out of 10 = 0.70
        ratio = validator._calculate_match_ratio(total=10, matches=7)
        assert ratio == 0.70
        
        # 10 out of 10 = 1.0
        ratio = validator._calculate_match_ratio(total=10, matches=10)
        assert ratio == 1.0
        
        # 0 out of 10 = 0.0
        ratio = validator._calculate_match_ratio(total=10, matches=0)
        assert ratio == 0.0
    
    def test_calculate_match_ratio_empty(self):
        """Test match ratio with empty list."""
        validator = IntegrityValidator()
        
        ratio = validator._calculate_match_ratio(total=0, matches=0)
        assert ratio == 1.0  # Empty is considered valid
    
    def test_identify_missing_roms(self, temp_gamelist_dir):
        """Test identifying missing ROM files."""
        validator = IntegrityValidator()
        
        rom_dir = temp_gamelist_dir['rom_dir']
        
        # Create only one ROM
        existing_rom = rom_dir / "Exists.nes"
        existing_rom.write_bytes(b"DATA")
        
        entries = [
            GameEntry(path="./Exists.nes", name="Exists"),
            GameEntry(path="./Missing.nes", name="Missing")
        ]
        
        missing = validator._identify_missing_roms(entries, rom_dir)
        
        assert len(missing) == 1
        assert missing[0] == "./Missing.nes"
    
    @patch('curateur.ui.prompts.confirm')
    def test_prompt_user_accepts_cleanup(self, mock_confirm):
        """Test user prompt accepts cleanup."""
        mock_confirm.return_value = True
        validator = IntegrityValidator()
        
        result = ValidationResult(
            is_valid=False,
            match_ratio=0.80,
            missing_roms=["./Missing.nes"],
            orphaned_entries=[GameEntry(path="./Missing.nes", name="Missing")]
        )
        
        should_cleanup = validator.prompt_user(result)
        
        assert should_cleanup is True
        mock_confirm.assert_called_once()
    
    @patch('curateur.ui.prompts.confirm')
    def test_prompt_user_declines_cleanup(self, mock_confirm):
        """Test user prompt declines cleanup."""
        mock_confirm.return_value = False
        validator = IntegrityValidator()
        
        result = ValidationResult(
            is_valid=False,
            match_ratio=0.80,
            missing_roms=["./Missing.nes"],
            orphaned_entries=[GameEntry(path="./Missing.nes", name="Missing")]
        )
        
        should_cleanup = validator.prompt_user(result)
        
        assert should_cleanup is False
    
    def test_cleanup_removes_entries(self, temp_gamelist_dir):
        """Test cleanup removes orphaned entries from gamelist."""
        validator = IntegrityValidator()
        
        all_entries = [
            GameEntry(path="./Keep.nes", name="Keep"),
            GameEntry(path="./Remove.nes", name="Remove")
        ]
        
        orphaned = [
            GameEntry(path="./Remove.nes", name="Remove")
        ]
        
        cleaned = validator._cleanup_entries(all_entries, orphaned)
        
        assert len(cleaned) == 1
        assert cleaned[0].path == "./Keep.nes"
    
    def test_cleanup_moves_media(self, temp_gamelist_dir, temp_media_files):
        """Test cleanup moves orphaned media to CLEANUP directory."""
        validator = IntegrityValidator()
        media_dir = temp_gamelist_dir['media_dir']
        
        # Create an orphaned media file
        orphaned_cover = media_dir / "covers" / "Orphaned.png"
        orphaned_cover.write_bytes(b"IMAGE_DATA")
        
        orphaned_entry = GameEntry(
            path="./Orphaned.nes",
            name="Orphaned",
            image=str(orphaned_cover)
        )
        
        validator._cleanup_media([orphaned_entry], media_dir)
        
        # Check if moved to CLEANUP directory
        cleanup_dir = media_dir / "CLEANUP"
        assert cleanup_dir.exists()


@pytest.mark.unit
class TestValidationResult:
    """Test ValidationResult dataclass."""
    
    def test_validation_result_creation(self):
        """Test creating ValidationResult."""
        result = ValidationResult(
            is_valid=True,
            match_ratio=1.0,
            missing_roms=[],
            orphaned_entries=[]
        )
        
        assert result.is_valid is True
        assert result.match_ratio == 1.0
        assert len(result.missing_roms) == 0
        assert len(result.orphaned_entries) == 0
    
    def test_validation_result_with_issues(self):
        """Test ValidationResult with validation issues."""
        missing = ["./Missing1.nes", "./Missing2.nes"]
        orphaned = [
            GameEntry(path="./Orphaned.nes", name="Orphaned")
        ]
        
        result = ValidationResult(
            is_valid=False,
            match_ratio=0.75,
            missing_roms=missing,
            orphaned_entries=orphaned
        )
        
        assert result.is_valid is False
        assert result.match_ratio == 0.75
        assert len(result.missing_roms) == 2
        assert len(result.orphaned_entries) == 1
