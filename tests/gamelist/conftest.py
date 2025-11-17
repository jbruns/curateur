"""Shared fixtures for gamelist module tests."""
import pytest
from pathlib import Path
from curateur.gamelist import GameEntry, GamelistMetadata


@pytest.fixture
def fixture_path():
    """Return path to gamelist fixtures directory."""
    return Path(__file__).parent.parent / 'fixtures' / 'gamelist'


@pytest.fixture
def sample_game_entry():
    """Sample GameEntry for testing."""
    return GameEntry(
        path="./TestGame.nes",
        name="Test Game",
        screenscraper_id="12345",
        desc="Test description with some details.",
        rating=0.85,
        releasedate="19900101T000000",
        developer="Test Developer",
        publisher="Test Publisher",
        genre="Action",
        players="1-2"
    )


@pytest.fixture
def sample_game_entry_with_media():
    """Sample GameEntry with media paths for internal tracking (not written to XML)."""
    return GameEntry(
        path="./TestGame.nes",
        name="Test Game",
        screenscraper_id="12345",
        desc="Test description",
        rating=0.85,
        releasedate="19900101T000000",
        developer="Test Developer",
        publisher="Test Publisher",
        genre="Action",
        players="1-2",
        image="~/downloaded_media/nes/covers/TestGame.png",
        thumbnail="~/downloaded_media/nes/screenshots/TestGame.png",
        video="~/downloaded_media/nes/videos/TestGame.mp4"
    )


@pytest.fixture
def sample_game_entry_with_user_fields():
    """Sample GameEntry with user-editable fields for testing."""
    return GameEntry(
        path="./TestGame.nes",
        name="Test Game",
        screenscraper_id="12345",
        desc="Test description",
        rating=0.85,
        favorite=True,
        playcount=42,
        lastplayed="20251115T143000",
        hidden=False,
        extra_fields={'kidgame': 'true'}
    )


@pytest.fixture
def sample_metadata():
    """Sample GamelistMetadata."""
    return GamelistMetadata(
        system="Nintendo Entertainment System",
        software="curateur",
        database="ScreenScraper.fr",
        web="http://www.screenscraper.fr"
    )


@pytest.fixture
def api_game_info():
    """Sample API game info dict (as returned by API client)."""
    return {
        'id': '12345',
        'names': {'us': 'Test Game', 'wor': 'World Test Game'},
        'descriptions': {'en': 'Test description with some details.'},
        'release_dates': {'us': '1990-01-01'},
        'developer': 'Test Developer',
        'publisher': 'Test Publisher',
        'genres': ['Action'],
        'players': '1-2',
        'rating': 4.25  # ScreenScraper uses 0-5 scale
    }


@pytest.fixture
def api_game_info_minimal():
    """Minimal API game info dict with only required fields."""
    return {
        'id': '99999',
        'names': {'us': 'Minimal Game'},
        'descriptions': {},
        'release_dates': {},
        'developer': None,
        'publisher': None,
        'genres': [],
        'players': None,
        'rating': None
    }


@pytest.fixture
def api_game_info_with_html_entities():
    """API game info with HTML entities that need decoding."""
    return {
        'id': '55555',
        'names': {'us': 'Mario &amp; Luigi: Partners &quot;Forever&quot;'},
        'descriptions': {'en': 'A game with &lt;special&gt; characters &amp; symbols.'},
        'release_dates': {'us': '2000-01-01'},
        'developer': 'Company &amp; Co.',
        'publisher': 'Test &apos;Publisher&apos;',
        'genres': ['RPG'],
        'players': '1-2',
        'rating': 4.5
    }


@pytest.fixture
def temp_gamelist_dir(tmp_path):
    """Create temporary gamelist directory structure for testing."""
    rom_dir = tmp_path / "roms" / "nes"
    media_dir = tmp_path / "downloaded_media" / "nes"
    gamelist_dir = tmp_path / "gamelists" / "nes"
    
    rom_dir.mkdir(parents=True)
    media_dir.mkdir(parents=True)
    gamelist_dir.mkdir(parents=True)
    
    # Create media subdirectories
    (media_dir / "covers").mkdir()
    (media_dir / "screenshots").mkdir()
    (media_dir / "videos").mkdir()
    
    return {
        'rom_dir': rom_dir,
        'media_dir': media_dir,
        'gamelist_dir': gamelist_dir,
        'root': tmp_path
    }


@pytest.fixture
def temp_rom_files(temp_gamelist_dir):
    """Create temporary ROM files for testing."""
    rom_dir = temp_gamelist_dir['rom_dir']
    
    # Create some test ROM files
    roms = [
        rom_dir / "Super Mario Bros.nes",
        rom_dir / "The Legend of Zelda.nes",
        rom_dir / "Metroid.nes"
    ]
    
    for rom in roms:
        rom.write_bytes(b"FAKE_ROM_DATA")
    
    return roms


@pytest.fixture
def temp_media_files(temp_gamelist_dir):
    """Create temporary media files for testing."""
    media_dir = temp_gamelist_dir['media_dir']
    
    # Create some test media files
    media_files = {
        'covers': [
            media_dir / "covers" / "Super Mario Bros.png",
            media_dir / "covers" / "The Legend of Zelda.png"
        ],
        'screenshots': [
            media_dir / "screenshots" / "Super Mario Bros.png",
            media_dir / "screenshots" / "The Legend of Zelda.png"
        ],
        'videos': [
            media_dir / "videos" / "Super Mario Bros.mp4"
        ]
    }
    
    for file_list in media_files.values():
        for media_file in file_list:
            media_file.write_bytes(b"FAKE_MEDIA_DATA")
    
    return media_files
