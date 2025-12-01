"""
Tests for automatic sortname generation feature.

Tests that sortname is correctly generated for games with articles (A, An, The)
and that the feature can be enabled/disabled via configuration.
"""

import pytest
from curateur.gamelist.game_entry import GameEntry


@pytest.mark.unit
class TestSortnameGeneration:
    """Test the sortname generation logic"""

    def test_generate_sortname_with_the(self):
        """Test sortname generation for names starting with 'The'"""
        sortname = GameEntry._generate_sortname("The Legend of Zelda")
        assert sortname == "Legend of Zelda, The"

    def test_generate_sortname_with_a(self):
        """Test sortname generation for names starting with 'A'"""
        sortname = GameEntry._generate_sortname("A Link to the Past")
        assert sortname == "Link to the Past, A"

    def test_generate_sortname_with_an(self):
        """Test sortname generation for names starting with 'An'"""
        sortname = GameEntry._generate_sortname("An American Tail")
        assert sortname == "American Tail, An"

    def test_generate_sortname_without_article(self):
        """Test that sortname is None for names without articles"""
        sortname = GameEntry._generate_sortname("Super Mario Bros")
        assert sortname is None

    def test_generate_sortname_with_article_only(self):
        """Test that sortname is None if name is only an article"""
        assert GameEntry._generate_sortname("The") is None
        assert GameEntry._generate_sortname("A") is None
        assert GameEntry._generate_sortname("An") is None

    def test_generate_sortname_empty_string(self):
        """Test that sortname is None for empty string"""
        sortname = GameEntry._generate_sortname("")
        assert sortname is None

    def test_generate_sortname_none(self):
        """Test that sortname is None for None input"""
        sortname = GameEntry._generate_sortname(None)
        assert sortname is None

    def test_generate_sortname_preserves_case(self):
        """Test that sortname preserves the case of the original name"""
        sortname = GameEntry._generate_sortname("The LAST of Us")
        assert sortname == "LAST of Us, The"

    def test_generate_sortname_with_special_characters(self):
        """Test sortname with special characters"""
        sortname = GameEntry._generate_sortname("The Legend of Zelda: Breath of the Wild")
        assert sortname == "Legend of Zelda: Breath of the Wild, The"


@pytest.mark.unit
class TestSortnameIntegration:
    """Test sortname integration with GameEntry.from_api_response"""

    def test_sortname_enabled_with_article(self):
        """Test that sortname is generated when enabled and name has article"""
        game_info = {
            'id': '1',
            'names': {'us': 'The Legend of Zelda'},
            'rating': 18.0
        }

        entry = GameEntry.from_api_response(
            game_info,
            './zelda.rom',
            auto_sortname_enabled=True
        )

        assert entry.name == "The Legend of Zelda"
        assert entry.sortname == "Legend of Zelda, The"

    def test_sortname_enabled_without_article(self):
        """Test that sortname is None when enabled but name has no article"""
        game_info = {
            'id': '1',
            'names': {'us': 'Super Mario Bros'},
            'rating': 18.0
        }

        entry = GameEntry.from_api_response(
            game_info,
            './mario.rom',
            auto_sortname_enabled=True
        )

        assert entry.name == "Super Mario Bros"
        assert entry.sortname is None

    def test_sortname_disabled_with_article(self):
        """Test that sortname is None when disabled even if name has article"""
        game_info = {
            'id': '1',
            'names': {'us': 'The Legend of Zelda'},
            'rating': 18.0
        }

        entry = GameEntry.from_api_response(
            game_info,
            './zelda.rom',
            auto_sortname_enabled=False
        )

        assert entry.name == "The Legend of Zelda"
        assert entry.sortname is None

    def test_sortname_default_disabled(self):
        """Test that sortname is disabled by default"""
        game_info = {
            'id': '1',
            'names': {'us': 'The Legend of Zelda'},
            'rating': 18.0
        }

        entry = GameEntry.from_api_response(
            game_info,
            './zelda.rom'
        )

        assert entry.name == "The Legend of Zelda"
        assert entry.sortname is None

    def test_sortname_with_multiple_articles(self):
        """Test sortname with 'A' in the middle of the name"""
        game_info = {
            'id': '1',
            'names': {'us': 'A Boy and His Blob'},
            'rating': 15.0
        }

        entry = GameEntry.from_api_response(
            game_info,
            './blob.rom',
            auto_sortname_enabled=True
        )

        # Should only move the first article
        assert entry.name == "A Boy and His Blob"
        assert entry.sortname == "Boy and His Blob, A"
