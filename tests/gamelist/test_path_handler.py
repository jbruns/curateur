"""Tests for path_handler module."""
import pytest
from pathlib import Path
from curateur.gamelist.path_handler import PathHandler


@pytest.mark.unit
class TestPathHandlerInitialization:
    """Test PathHandler initialization."""
    
    def test_init_with_paths(self, temp_gamelist_dir):
        """Test initialization with directory paths."""
        handler = PathHandler(
            rom_directory=temp_gamelist_dir['rom_dir'],
            media_directory=temp_gamelist_dir['media_dir'],
            gamelist_directory=temp_gamelist_dir['gamelist_dir']
        )
        
        assert handler.rom_directory == temp_gamelist_dir['rom_dir']
        assert handler.media_directory == temp_gamelist_dir['media_dir']
        assert handler.gamelist_directory == temp_gamelist_dir['gamelist_dir']


@pytest.mark.unit
class TestRomPathConversion:
    """Test ROM path conversion methods."""
    
    def test_to_relative_rom_path_basic(self, temp_gamelist_dir):
        """Test converting absolute ROM path to relative."""
        handler = PathHandler(
            rom_directory=temp_gamelist_dir['rom_dir'],
            media_directory=temp_gamelist_dir['media_dir'],
            gamelist_directory=temp_gamelist_dir['gamelist_dir']
        )
        
        rom_path = temp_gamelist_dir['rom_dir'] / "Game.nes"
        relative = handler.to_relative_rom_path(rom_path)
        
        assert relative == "./Game.nes"
    
    def test_to_relative_rom_path_with_spaces(self, temp_gamelist_dir):
        """Test converting ROM path with spaces in filename."""
        handler = PathHandler(
            rom_directory=temp_gamelist_dir['rom_dir'],
            media_directory=temp_gamelist_dir['media_dir'],
            gamelist_directory=temp_gamelist_dir['gamelist_dir']
        )
        
        rom_path = temp_gamelist_dir['rom_dir'] / "Super Mario Bros.nes"
        relative = handler.to_relative_rom_path(rom_path)
        
        assert relative == "./Super Mario Bros.nes"
    
    def test_to_relative_rom_path_subdirectory(self, temp_gamelist_dir):
        """Test converting ROM path in subdirectory."""
        handler = PathHandler(
            rom_directory=temp_gamelist_dir['rom_dir'],
            media_directory=temp_gamelist_dir['media_dir'],
            gamelist_directory=temp_gamelist_dir['gamelist_dir']
        )
        
        subdir = temp_gamelist_dir['rom_dir'] / "Disc Games"
        subdir.mkdir()
        rom_path = subdir / "Game.cue"
        relative = handler.to_relative_rom_path(rom_path)
        
        assert relative == "./Disc Games/Game.cue"
    
    def test_to_relative_rom_path_string_input(self, temp_gamelist_dir):
        """Test converting ROM path given as string."""
        handler = PathHandler(
            rom_directory=temp_gamelist_dir['rom_dir'],
            media_directory=temp_gamelist_dir['media_dir'],
            gamelist_directory=temp_gamelist_dir['gamelist_dir']
        )
        
        rom_path = str(temp_gamelist_dir['rom_dir'] / "Game.nes")
        relative = handler.to_relative_rom_path(rom_path)
        
        assert relative == "./Game.nes"
    
    def test_to_absolute_rom_path_basic(self, temp_gamelist_dir):
        """Test converting relative ROM path to absolute."""
        handler = PathHandler(
            rom_directory=temp_gamelist_dir['rom_dir'],
            media_directory=temp_gamelist_dir['media_dir'],
            gamelist_directory=temp_gamelist_dir['gamelist_dir']
        )
        
        relative = "./Game.nes"
        absolute = handler.to_absolute_rom_path(relative)
        
        assert absolute == temp_gamelist_dir['rom_dir'] / "Game.nes"
    
    def test_to_absolute_rom_path_subdirectory(self, temp_gamelist_dir):
        """Test converting relative ROM path with subdirectory."""
        handler = PathHandler(
            rom_directory=temp_gamelist_dir['rom_dir'],
            media_directory=temp_gamelist_dir['media_dir'],
            gamelist_directory=temp_gamelist_dir['gamelist_dir']
        )
        
        relative = "./Disc Games/Game.cue"
        absolute = handler.to_absolute_rom_path(relative)
        
        assert absolute == temp_gamelist_dir['rom_dir'] / "Disc Games" / "Game.cue"


@pytest.mark.unit
class TestMediaPathConversion:
    """Test media path conversion methods."""
    
    def test_to_relative_media_path_basic(self, temp_gamelist_dir):
        """Test converting absolute media path to relative."""
        handler = PathHandler(
            rom_directory=temp_gamelist_dir['rom_dir'],
            media_directory=temp_gamelist_dir['media_dir'],
            gamelist_directory=temp_gamelist_dir['gamelist_dir']
        )
        
        media_path = temp_gamelist_dir['media_dir'] / "covers" / "Game.png"
        relative = handler.to_relative_media_path(media_path)
        
        # Should be relative to gamelist directory
        assert "covers/Game.png" in relative or "covers\\Game.png" in relative
    
    def test_to_relative_media_path_with_tilde(self, temp_gamelist_dir):
        """Test media path uses tilde notation."""
        handler = PathHandler(
            rom_directory=temp_gamelist_dir['rom_dir'],
            media_directory=temp_gamelist_dir['media_dir'],
            gamelist_directory=temp_gamelist_dir['gamelist_dir']
        )
        
        media_path = temp_gamelist_dir['media_dir'] / "covers" / "Game.png"
        relative = handler.to_relative_media_path(media_path)
        
        # ES-DE uses ~/ prefix for media paths
        assert relative.startswith("~/")
    
    def test_to_relative_media_path_screenshot(self, temp_gamelist_dir):
        """Test converting screenshot media path."""
        handler = PathHandler(
            rom_directory=temp_gamelist_dir['rom_dir'],
            media_directory=temp_gamelist_dir['media_dir'],
            gamelist_directory=temp_gamelist_dir['gamelist_dir']
        )
        
        media_path = temp_gamelist_dir['media_dir'] / "screenshots" / "Game.png"
        relative = handler.to_relative_media_path(media_path)
        
        assert "screenshots/Game.png" in relative or "screenshots\\Game.png" in relative
    
    def test_to_absolute_media_path_basic(self, temp_gamelist_dir):
        """Test converting relative media path to absolute."""
        handler = PathHandler(
            rom_directory=temp_gamelist_dir['rom_dir'],
            media_directory=temp_gamelist_dir['media_dir'],
            gamelist_directory=temp_gamelist_dir['gamelist_dir']
        )
        
        relative = "~/downloaded_media/nes/covers/Game.png"
        absolute = handler.to_absolute_media_path(relative)
        
        assert absolute.name == "Game.png"
        assert "covers" in str(absolute)


@pytest.mark.unit
class TestPathNormalization:
    """Test path normalization utilities."""
    
    def test_normalize_path_forward_slashes(self, temp_gamelist_dir):
        """Test normalizing path to forward slashes."""
        handler = PathHandler(
            rom_directory=temp_gamelist_dir['rom_dir'],
            media_directory=temp_gamelist_dir['media_dir'],
            gamelist_directory=temp_gamelist_dir['gamelist_dir']
        )
        
        path_with_backslashes = "roms\\nes\\Game.nes"
        normalized = handler.normalize_path(path_with_backslashes)
        
        assert "\\" not in normalized
        assert "/" in normalized or normalized == "roms/nes/Game.nes"
    
    def test_normalize_path_mixed_separators(self, temp_gamelist_dir):
        """Test normalizing path with mixed separators."""
        handler = PathHandler(
            rom_directory=temp_gamelist_dir['rom_dir'],
            media_directory=temp_gamelist_dir['media_dir'],
            gamelist_directory=temp_gamelist_dir['gamelist_dir']
        )
        
        mixed_path = "roms/nes\\subdirectory\\Game.nes"
        normalized = handler.normalize_path(mixed_path)
        
        assert "\\" not in normalized


@pytest.mark.unit
class TestMediaBasename:
    """Test media basename extraction."""
    
    def test_get_media_basename_simple(self, temp_gamelist_dir):
        """Test getting basename for simple ROM file."""
        handler = PathHandler(
            rom_directory=temp_gamelist_dir['rom_dir'],
            media_directory=temp_gamelist_dir['media_dir'],
            gamelist_directory=temp_gamelist_dir['gamelist_dir']
        )
        
        rom_path = temp_gamelist_dir['rom_dir'] / "Game.nes"
        basename = handler.get_media_basename(rom_path)
        
        assert basename == "Game"
    
    def test_get_media_basename_with_spaces(self, temp_gamelist_dir):
        """Test getting basename for ROM with spaces."""
        handler = PathHandler(
            rom_directory=temp_gamelist_dir['rom_dir'],
            media_directory=temp_gamelist_dir['media_dir'],
            gamelist_directory=temp_gamelist_dir['gamelist_dir']
        )
        
        rom_path = temp_gamelist_dir['rom_dir'] / "Super Mario Bros.nes"
        basename = handler.get_media_basename(rom_path)
        
        assert basename == "Super Mario Bros"
    
    def test_get_media_basename_disc_subdirectory(self, temp_gamelist_dir):
        """Test getting basename for disc game in subdirectory."""
        handler = PathHandler(
            rom_directory=temp_gamelist_dir['rom_dir'],
            media_directory=temp_gamelist_dir['media_dir'],
            gamelist_directory=temp_gamelist_dir['gamelist_dir']
        )
        
        # Disc games are often in subdirectories named after the game
        disc_dir = temp_gamelist_dir['rom_dir'] / "Final Fantasy VII"
        disc_dir.mkdir()
        rom_path = disc_dir / "Final Fantasy VII.cue"
        basename = handler.get_media_basename(rom_path)
        
        # Should use parent directory name for disc games
        assert basename == "Final Fantasy VII"
    
    def test_get_media_basename_m3u_file(self, temp_gamelist_dir):
        """Test getting basename for multi-disc M3U file."""
        handler = PathHandler(
            rom_directory=temp_gamelist_dir['rom_dir'],
            media_directory=temp_gamelist_dir['media_dir'],
            gamelist_directory=temp_gamelist_dir['gamelist_dir']
        )
        
        rom_path = temp_gamelist_dir['rom_dir'] / "Metal Gear Solid.m3u"
        basename = handler.get_media_basename(rom_path)
        
        assert basename == "Metal Gear Solid"


@pytest.mark.unit
class TestPathCalculations:
    """Test path calculation methods."""
    
    def test_calculate_media_path_from_gamelist(self, temp_gamelist_dir):
        """Test calculating relative path from gamelist to media."""
        handler = PathHandler(
            rom_directory=temp_gamelist_dir['rom_dir'],
            media_directory=temp_gamelist_dir['media_dir'],
            gamelist_directory=temp_gamelist_dir['gamelist_dir']
        )
        
        media_path = temp_gamelist_dir['media_dir'] / "covers" / "Game.png"
        relative = handler.calculate_media_path_from_gamelist(media_path)
        
        # Should return path relative to gamelist directory
        assert isinstance(relative, (str, Path))
        assert "covers" in str(relative)
        assert "Game.png" in str(relative)
