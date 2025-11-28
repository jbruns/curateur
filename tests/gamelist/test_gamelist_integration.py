"""
Integration tests for gamelist generation with all config combinations.

Tests the complete flow: config -> generator -> merger -> XML output
Verifies all merge strategies, auto-favorite, and user field preservation.
"""
import pytest
from pathlib import Path
from lxml import etree

from curateur.gamelist.generator import GamelistGenerator


def _create_existing_gamelist(path: Path, entries: list):
    """Helper to create an existing gamelist.xml for testing"""
    root = etree.Element("gameList")
    provider = etree.SubElement(root, "provider")
    etree.SubElement(provider, "System").text = "Test"
    etree.SubElement(provider, "software").text = "test"

    for entry in entries:
        game = etree.SubElement(root, "game")
        for key, value in entry.items():
            if key == "id":
                game.set("id", value)
            else:
                elem = etree.SubElement(game, key)
                elem.text = str(value)

    tree = etree.ElementTree(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(str(path), encoding='utf-8', xml_declaration=True, pretty_print=True)


def _parse_gamelist(path: Path) -> dict:
    """Helper to parse gamelist.xml and extract game entries"""
    tree = etree.parse(str(path))
    root = tree.getroot()

    games = {}
    for game in root.findall("game"):
        path_elem = game.find("path")
        if path_elem is None or path_elem.text is None:
            continue

        game_data = {"path": path_elem.text}
        for child in game:
            if child.tag != "path" and child.text:
                game_data[child.tag] = child.text

        # Store attributes
        if game.get("id"):
            game_data["id"] = game.get("id")

        games[game_data["path"]] = game_data

    return games


@pytest.mark.integration
class TestNewGamelistGeneration:
    """Test generating brand new gamelists (no existing gamelist.xml)"""

    def test_refresh_metadata_with_auto_favorite_enabled(self, tmp_path):
        """New gamelist with refresh_metadata should apply auto-favorite"""
        rom_dir = tmp_path / "roms"
        media_dir = tmp_path / "media"
        gamelist_dir = tmp_path / "gamelist"
        rom_dir.mkdir()
        media_dir.mkdir()
        gamelist_dir.mkdir()

        generator = GamelistGenerator(
            system_name="nes",
            full_system_name="Nintendo",
            rom_directory=rom_dir,
            media_directory=media_dir,
            gamelist_directory=gamelist_dir,
            merge_strategy="refresh_metadata",
            auto_favorite_enabled=True,
            auto_favorite_threshold=0.9,
        )

        scraped_games = [
            {
                "rom_path": rom_dir / "HighRated.nes",
                "game_info": {
                    "id": "1",
                    "names": {"us": "High Rated"},
                    "rating": 18.0,  # 0.9 on ES-DE scale
                },
                "media_paths": {},
            },
            {
                "rom_path": rom_dir / "LowRated.nes",
                "game_info": {
                    "id": "2",
                    "names": {"us": "Low Rated"},
                    "rating": 10.0,  # 0.5 on ES-DE scale
                },
                "media_paths": {},
            },
        ]

        generator.generate_gamelist(scraped_games, validate=False)

        games = _parse_gamelist(generator.gamelist_path)

        # High rated should be favorited
        assert "./HighRated.nes" in games
        assert games["./HighRated.nes"].get("favorite") == "true"
        assert games["./HighRated.nes"]["rating"] == "0.9"

        # Low rated should NOT be favorited
        assert "./LowRated.nes" in games
        assert "favorite" not in games["./LowRated.nes"]
        assert games["./LowRated.nes"]["rating"] == "0.5"

    def test_preserve_user_edits_blocks_auto_favorite(self, tmp_path):
        """New gamelist with preserve_user_edits should NOT apply auto-favorite"""
        rom_dir = tmp_path / "roms"
        media_dir = tmp_path / "media"
        gamelist_dir = tmp_path / "gamelist"
        rom_dir.mkdir()
        media_dir.mkdir()
        gamelist_dir.mkdir()

        generator = GamelistGenerator(
            system_name="nes",
            full_system_name="Nintendo",
            rom_directory=rom_dir,
            media_directory=media_dir,
            gamelist_directory=gamelist_dir,
            merge_strategy="preserve_user_edits",
            auto_favorite_enabled=True,
            auto_favorite_threshold=0.9,
        )

        scraped_games = [
            {
                "rom_path": rom_dir / "HighRated.nes",
                "game_info": {
                    "id": "1",
                    "names": {"us": "High Rated"},
                    "rating": 19.0,  # 0.95 - well above threshold
                },
                "media_paths": {},
            },
        ]

        generator.generate_gamelist(scraped_games, validate=False)

        games = _parse_gamelist(generator.gamelist_path)

        # Should NOT be favorited despite high rating (preserve_user_edits blocks it)
        assert "./HighRated.nes" in games
        assert "favorite" not in games["./HighRated.nes"]
        assert games["./HighRated.nes"]["rating"] == "0.95"

    def test_reset_all_allows_auto_favorite(self, tmp_path):
        """New gamelist with reset_all should apply auto-favorite"""
        rom_dir = tmp_path / "roms"
        media_dir = tmp_path / "media"
        gamelist_dir = tmp_path / "gamelist"
        rom_dir.mkdir()
        media_dir.mkdir()
        gamelist_dir.mkdir()

        generator = GamelistGenerator(
            system_name="nes",
            full_system_name="Nintendo",
            rom_directory=rom_dir,
            media_directory=media_dir,
            gamelist_directory=gamelist_dir,
            merge_strategy="reset_all",
            auto_favorite_enabled=True,
            auto_favorite_threshold=0.9,
        )

        scraped_games = [
            {
                "rom_path": rom_dir / "HighRated.nes",
                "game_info": {
                    "id": "1",
                    "names": {"us": "High Rated"},
                    "rating": 19.0,
                },
                "media_paths": {},
            },
        ]

        generator.generate_gamelist(scraped_games, validate=False)

        games = _parse_gamelist(generator.gamelist_path)

        # Should be favorited
        assert games["./HighRated.nes"].get("favorite") == "true"

    def test_auto_favorite_disabled(self, tmp_path):
        """New gamelist with auto_favorite disabled should never favorite"""
        rom_dir = tmp_path / "roms"
        media_dir = tmp_path / "media"
        gamelist_dir = tmp_path / "gamelist"
        rom_dir.mkdir()
        media_dir.mkdir()
        gamelist_dir.mkdir()

        generator = GamelistGenerator(
            system_name="nes",
            full_system_name="Nintendo",
            rom_directory=rom_dir,
            media_directory=media_dir,
            gamelist_directory=gamelist_dir,
            merge_strategy="refresh_metadata",
            auto_favorite_enabled=False,  # Disabled
            auto_favorite_threshold=0.9,
        )

        scraped_games = [
            {
                "rom_path": rom_dir / "HighRated.nes",
                "game_info": {
                    "id": "1",
                    "names": {"us": "High Rated"},
                    "rating": 20.0,  # Perfect rating
                },
                "media_paths": {},
            },
        ]

        generator.generate_gamelist(scraped_games, validate=False)

        games = _parse_gamelist(generator.gamelist_path)

        # Should NOT be favorited (feature disabled)
        assert "favorite" not in games["./HighRated.nes"]


@pytest.mark.integration
class TestExistingGamelistUpdates:
    """Test updating existing gamelists"""

    def test_preserve_user_edits_keeps_all_fields(self, tmp_path):
        """preserve_user_edits should keep ALL existing fields unchanged"""
        rom_dir = tmp_path / "roms"
        media_dir = tmp_path / "media"
        gamelist_dir = tmp_path / "gamelist"
        rom_dir.mkdir()
        media_dir.mkdir()
        gamelist_dir.mkdir()

        # Create existing gamelist with user edits
        _create_existing_gamelist(
            gamelist_dir / "gamelist.xml",
            [
                {
                    "path": "./Game.nes",
                    "name": "User Custom Name",
                    "desc": "User custom description",
                    "rating": "0.5",
                    "favorite": "true",
                    "playcount": "10",
                    "lastplayed": "20230101T000000",
                }
            ]
        )

        generator = GamelistGenerator(
            system_name="nes",
            full_system_name="Nintendo",
            rom_directory=rom_dir,
            media_directory=media_dir,
            gamelist_directory=gamelist_dir,
            merge_strategy="preserve_user_edits",
            auto_favorite_enabled=True,
            auto_favorite_threshold=0.9,
        )

        scraped_games = [
            {
                "rom_path": rom_dir / "Game.nes",
                "game_info": {
                    "id": "1",
                    "names": {"us": "New API Name"},
                    "descriptions": {"en": "New API description"},
                    "rating": 19.0,  # High rating from API
                    "developer": "Dev Co",
                },
                "media_paths": {},
            },
        ]

        generator.generate_gamelist(scraped_games, validate=False, merge_existing=True)

        games = _parse_gamelist(generator.gamelist_path)
        game = games["./Game.nes"]

        # ALL fields should be preserved from existing (no updates)
        assert game["name"] == "User Custom Name"
        assert game["desc"] == "User custom description"
        assert game["rating"] == "0.5"
        assert game["favorite"] == "true"
        assert game["playcount"] == "10"
        assert game["lastplayed"] == "20230101T000000"
        # New scraped field should NOT be added
        assert "developer" not in game

    def test_refresh_metadata_updates_scraped_preserves_user(self, tmp_path):
        """refresh_metadata should update scraped fields, preserve user fields, apply auto-favorite"""
        rom_dir = tmp_path / "roms"
        media_dir = tmp_path / "media"
        gamelist_dir = tmp_path / "gamelist"
        rom_dir.mkdir()
        media_dir.mkdir()
        gamelist_dir.mkdir()

        # Create existing gamelist
        _create_existing_gamelist(
            gamelist_dir / "gamelist.xml",
            [
                {
                    "path": "./Game.nes",
                    "name": "Old Name",
                    "desc": "Old description",
                    "rating": "0.5",
                    "developer": "Old Dev",
                    "favorite": "false",  # User explicitly unfavorited
                    "playcount": "10",
                    "lastplayed": "20230101T000000",
                }
            ]
        )

        generator = GamelistGenerator(
            system_name="nes",
            full_system_name="Nintendo",
            rom_directory=rom_dir,
            media_directory=media_dir,
            gamelist_directory=gamelist_dir,
            merge_strategy="refresh_metadata",
            auto_favorite_enabled=True,
            auto_favorite_threshold=0.9,
        )

        scraped_games = [
            {
                "rom_path": rom_dir / "Game.nes",
                "game_info": {
                    "id": "1",
                    "names": {"us": "New Name"},
                    "descriptions": {"en": "New description"},
                    "rating": 19.0,  # High rating
                    "developer": "New Dev",
                },
                "media_paths": {},
            },
        ]

        generator.generate_gamelist(scraped_games, validate=False, merge_existing=True)

        games = _parse_gamelist(generator.gamelist_path)
        game = games["./Game.nes"]

        # Scraped fields should be updated
        assert game["name"] == "New Name"
        assert game["desc"] == "New description"
        assert game["rating"] == "0.95"
        assert game["developer"] == "New Dev"

        # User fields should be preserved
        assert game["playcount"] == "10"
        assert game["lastplayed"] == "20230101T000000"

        # Auto-favorite should apply (rating above threshold, user had it as false)
        assert game["favorite"] == "true"

    def test_refresh_metadata_respects_user_favorite_true(self, tmp_path):
        """refresh_metadata should preserve user's favorite=true even for low-rated games"""
        rom_dir = tmp_path / "roms"
        media_dir = tmp_path / "media"
        gamelist_dir = tmp_path / "gamelist"
        rom_dir.mkdir()
        media_dir.mkdir()
        gamelist_dir.mkdir()

        # Create existing gamelist - user favorited a low-rated game
        _create_existing_gamelist(
            gamelist_dir / "gamelist.xml",
            [
                {
                    "path": "./Game.nes",
                    "name": "Favorite Game",
                    "rating": "0.3",
                    "favorite": "true",  # User manually favorited despite low rating
                }
            ]
        )

        generator = GamelistGenerator(
            system_name="nes",
            full_system_name="Nintendo",
            rom_directory=rom_dir,
            media_directory=media_dir,
            gamelist_directory=gamelist_dir,
            merge_strategy="refresh_metadata",
            auto_favorite_enabled=True,
            auto_favorite_threshold=0.9,
        )

        scraped_games = [
            {
                "rom_path": rom_dir / "Game.nes",
                "game_info": {
                    "id": "1",
                    "names": {"us": "Favorite Game"},
                    "rating": 6.0,  # Still low (0.3)
                },
                "media_paths": {},
            },
        ]

        generator.generate_gamelist(scraped_games, validate=False, merge_existing=True)

        games = _parse_gamelist(generator.gamelist_path)
        game = games["./Game.nes"]

        # Should preserve user's favorite=true
        assert game["favorite"] == "true"
        assert game["rating"] == "0.3"

    def test_reset_all_applies_auto_favorite_to_existing(self, tmp_path):
        """reset_all should apply auto-favorite even to existing entries"""
        rom_dir = tmp_path / "roms"
        media_dir = tmp_path / "media"
        gamelist_dir = tmp_path / "gamelist"
        rom_dir.mkdir()
        media_dir.mkdir()
        gamelist_dir.mkdir()

        # Create existing gamelist
        _create_existing_gamelist(
            gamelist_dir / "gamelist.xml",
            [
                {
                    "path": "./Game.nes",
                    "name": "Old Name",
                    "rating": "0.5",
                    "playcount": "10",  # User data
                }
            ]
        )

        generator = GamelistGenerator(
            system_name="nes",
            full_system_name="Nintendo",
            rom_directory=rom_dir,
            media_directory=media_dir,
            gamelist_directory=gamelist_dir,
            merge_strategy="reset_all",
            auto_favorite_enabled=True,
            auto_favorite_threshold=0.9,
        )

        scraped_games = [
            {
                "rom_path": rom_dir / "Game.nes",
                "game_info": {
                    "id": "1",
                    "names": {"us": "New Name"},
                    "rating": 19.0,
                },
                "media_paths": {},
            },
        ]

        generator.generate_gamelist(scraped_games, validate=False, merge_existing=True)

        games = _parse_gamelist(generator.gamelist_path)
        game = games["./Game.nes"]

        # Should apply auto-favorite
        assert game["favorite"] == "true"
        assert game["rating"] == "0.95"


@pytest.mark.integration
class TestAutoFavoriteThresholds:
    """Test auto-favorite threshold boundary conditions"""

    def test_rating_exactly_at_threshold(self, tmp_path):
        """Rating exactly at threshold should be favorited"""
        rom_dir = tmp_path / "roms"
        media_dir = tmp_path / "media"
        gamelist_dir = tmp_path / "gamelist"
        rom_dir.mkdir()
        media_dir.mkdir()
        gamelist_dir.mkdir()

        generator = GamelistGenerator(
            system_name="nes",
            full_system_name="Nintendo",
            rom_directory=rom_dir,
            media_directory=media_dir,
            gamelist_directory=gamelist_dir,
            merge_strategy="refresh_metadata",
            auto_favorite_enabled=True,
            auto_favorite_threshold=0.9,
        )

        scraped_games = [
            {
                "rom_path": rom_dir / "Game.nes",
                "game_info": {
                    "id": "1",
                    "names": {"us": "Game"},
                    "rating": 18.0,  # Exactly 0.9
                },
                "media_paths": {},
            },
        ]

        generator.generate_gamelist(scraped_games, validate=False)

        games = _parse_gamelist(generator.gamelist_path)

        # Exactly at threshold should be favorited (>= check)
        assert games["./Game.nes"]["favorite"] == "true"

    def test_rating_just_below_threshold(self, tmp_path):
        """Rating just below threshold should NOT be favorited"""
        rom_dir = tmp_path / "roms"
        media_dir = tmp_path / "media"
        gamelist_dir = tmp_path / "gamelist"
        rom_dir.mkdir()
        media_dir.mkdir()
        gamelist_dir.mkdir()

        generator = GamelistGenerator(
            system_name="nes",
            full_system_name="Nintendo",
            rom_directory=rom_dir,
            media_directory=media_dir,
            gamelist_directory=gamelist_dir,
            merge_strategy="refresh_metadata",
            auto_favorite_enabled=True,
            auto_favorite_threshold=0.9,
        )

        scraped_games = [
            {
                "rom_path": rom_dir / "Game.nes",
                "game_info": {
                    "id": "1",
                    "names": {"us": "Game"},
                    "rating": 17.9,  # 0.895, just below 0.9
                },
                "media_paths": {},
            },
        ]

        generator.generate_gamelist(scraped_games, validate=False)

        games = _parse_gamelist(generator.gamelist_path)

        # Just below threshold should NOT be favorited
        assert "favorite" not in games["./Game.nes"]

    def test_custom_threshold(self, tmp_path):
        """Custom threshold should work correctly"""
        rom_dir = tmp_path / "roms"
        media_dir = tmp_path / "media"
        gamelist_dir = tmp_path / "gamelist"
        rom_dir.mkdir()
        media_dir.mkdir()
        gamelist_dir.mkdir()

        generator = GamelistGenerator(
            system_name="nes",
            full_system_name="Nintendo",
            rom_directory=rom_dir,
            media_directory=media_dir,
            gamelist_directory=gamelist_dir,
            merge_strategy="refresh_metadata",
            auto_favorite_enabled=True,
            auto_favorite_threshold=0.75,  # Custom threshold
        )

        scraped_games = [
            {
                "rom_path": rom_dir / "High.nes",
                "game_info": {
                    "id": "1",
                    "names": {"us": "High"},
                    "rating": 16.0,  # 0.8, above 0.75
                },
                "media_paths": {},
            },
            {
                "rom_path": rom_dir / "Low.nes",
                "game_info": {
                    "id": "2",
                    "names": {"us": "Low"},
                    "rating": 14.0,  # 0.7, below 0.75
                },
                "media_paths": {},
            },
        ]

        generator.generate_gamelist(scraped_games, validate=False)

        games = _parse_gamelist(generator.gamelist_path)

        # 0.8 should be favorited (>= 0.75)
        assert games["./High.nes"]["favorite"] == "true"
        # 0.7 should NOT be favorited (< 0.75)
        assert "favorite" not in games["./Low.nes"]


@pytest.mark.integration
class TestMixedScenarios:
    """Test complex real-world scenarios"""

    def test_mixed_new_and_updated_entries(self, tmp_path):
        """Test mix of new entries and updates to existing entries"""
        rom_dir = tmp_path / "roms"
        media_dir = tmp_path / "media"
        gamelist_dir = tmp_path / "gamelist"
        rom_dir.mkdir()
        media_dir.mkdir()
        gamelist_dir.mkdir()

        # Create existing gamelist with 2 games
        _create_existing_gamelist(
            gamelist_dir / "gamelist.xml",
            [
                {
                    "path": "./Existing1.nes",
                    "name": "Existing Game 1",
                    "rating": "0.5",
                    "playcount": "5",
                },
                {
                    "path": "./Existing2.nes",
                    "name": "Existing Game 2",
                    "rating": "0.8",
                    "favorite": "true",
                },
            ]
        )

        generator = GamelistGenerator(
            system_name="nes",
            full_system_name="Nintendo",
            rom_directory=rom_dir,
            media_directory=media_dir,
            gamelist_directory=gamelist_dir,
            merge_strategy="refresh_metadata",
            auto_favorite_enabled=True,
            auto_favorite_threshold=0.9,
        )

        scraped_games = [
            # Update existing with high rating
            {
                "rom_path": rom_dir / "Existing1.nes",
                "game_info": {
                    "id": "1",
                    "names": {"us": "Updated Existing 1"},
                    "rating": 19.0,  # Upgraded to high rating
                },
                "media_paths": {},
            },
            # Update existing (already favorited, rating stays low)
            {
                "rom_path": rom_dir / "Existing2.nes",
                "game_info": {
                    "id": "2",
                    "names": {"us": "Updated Existing 2"},
                    "rating": 15.0,  # Still below threshold
                },
                "media_paths": {},
            },
            # New entry with high rating
            {
                "rom_path": rom_dir / "New1.nes",
                "game_info": {
                    "id": "3",
                    "names": {"us": "New High Rated"},
                    "rating": 18.5,
                },
                "media_paths": {},
            },
            # New entry with low rating
            {
                "rom_path": rom_dir / "New2.nes",
                "game_info": {
                    "id": "4",
                    "names": {"us": "New Low Rated"},
                    "rating": 10.0,
                },
                "media_paths": {},
            },
        ]

        generator.generate_gamelist(scraped_games, validate=False, merge_existing=True)

        games = _parse_gamelist(generator.gamelist_path)

        # Existing1: upgraded rating, should be auto-favorited
        assert games["./Existing1.nes"]["name"] == "Updated Existing 1"
        assert games["./Existing1.nes"]["rating"] == "0.95"
        assert games["./Existing1.nes"]["favorite"] == "true"  # Auto-favorited
        assert games["./Existing1.nes"]["playcount"] == "5"  # Preserved

        # Existing2: user's favorite preserved despite low rating
        assert games["./Existing2.nes"]["name"] == "Updated Existing 2"
        assert games["./Existing2.nes"]["rating"] == "0.75"
        assert games["./Existing2.nes"]["favorite"] == "true"  # Preserved

        # New1: high rating, should be auto-favorited
        assert games["./New1.nes"]["name"] == "New High Rated"
        assert games["./New1.nes"]["rating"] == "0.925"
        assert games["./New1.nes"]["favorite"] == "true"

        # New2: low rating, should NOT be favorited
        assert games["./New2.nes"]["name"] == "New Low Rated"
        assert games["./New2.nes"]["rating"] == "0.5"
        assert "favorite" not in games["./New2.nes"]

        # All 4 games should be present
        assert len(games) == 4
