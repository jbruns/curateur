import pytest

from curateur.api.response_parser import (
    ResponseError,
    validate_response,
    parse_game_info,
    parse_search_results,
    extract_error_message,
    decode_html_entities,
)


@pytest.mark.unit
def test_validate_response_happy_path():
    xml = b"<Data><jeu id='123'><noms><nom region='us'>Example</nom></noms></jeu></Data>"
    root = validate_response(xml)
    assert root.tag == "Data"


@pytest.mark.unit
@pytest.mark.parametrize(
    "payload,expected",
    [
        (b"", "Empty response body"),
        (b"<NotData></NotData>", "Invalid root element"),
        (b"<Data><bad></Data>", "Malformed XML"),
    ],
)
def test_validate_response_rejects_bad_payloads(payload, expected):
    with pytest.raises(ResponseError) as exc:
        validate_response(payload)
    assert expected in str(exc.value)


@pytest.mark.unit
def test_parse_game_info_extracts_core_fields():
    xml = b"""
    <Data>
      <jeu id="42">
        <noms>
          <nom region="us">The Legend of Parsing</nom>
          <nom region="eu">Le Parsing</nom>
        </noms>
        <systeme>nes</systeme>
        <synopsis>
          <synopsis langue="en">A heroic tale &amp; test.</synopsis>
        </synopsis>
        <dates><date region="us">1989</date></dates>
        <genres>
          <genre id="1" principale="1" langue="en">Adventure</genre>
        </genres>
        <developpeur>Parser Works</developpeur>
        <editeur>Verifier Co</editeur>
        <joueurs>1-2</joueurs>
        <note>15</note>
        <medias>
          <media type="screenshot" format="png" region="us">http://example/s.png</media>
        </medias>
      </jeu>
    </Data>
    """
    root = validate_response(xml)
    game = parse_game_info(root)

    assert game["id"] == "42"
    assert game["name"] == "The Legend of Parsing"
    assert game["names"]["eu"] == "Le Parsing"
    assert game["system"] == "nes"
    assert game["descriptions"]["en"] == "A heroic tale & test."
    assert game["release_dates"]["us"] == "1989"
    assert game["genres"] == ["Adventure"]
    assert game["developer"] == "Parser Works"
    assert game["publisher"] == "Verifier Co"
    assert game["players"] == "1-2"
    assert game["rating"] == 15.0
    media = game["media"]["screenshot"][0]
    assert media["url"].startswith("http://example")
    assert media["region"] == "us"


@pytest.mark.unit
def test_parse_game_info_requires_jeu_element():
    root = validate_response(b"<Data></Data>")
    with pytest.raises(ResponseError):
        parse_game_info(root)


@pytest.mark.unit
def test_parse_search_results_returns_multiple_entries():
    xml = b"""
    <Data>
      <jeux>
        <jeu id="1"><noms><nom region="us">Alpha</nom></noms></jeu>
        <jeu id="2"><noms><nom region="us">Beta</nom></noms></jeu>
      </jeux>
    </Data>
    """
    root = validate_response(xml)
    results = parse_search_results(root)
    assert [r["id"] for r in results] == ["1", "2"]
    assert results[0]["name"] == "Alpha"


@pytest.mark.unit
def test_extract_error_message_decodes_entities():
    root = validate_response(b"<Data><erreur>Bad &amp; wrong</erreur></Data>")
    assert extract_error_message(root) == "Bad & wrong"


@pytest.mark.unit
def test_decode_html_entities_round_trip():
    assert decode_html_entities("Foo &amp; Bar") == "Foo & Bar"


@pytest.mark.unit
def test_parse_genres_with_multiple_languages():
    """Test genre parsing with real ScreenScraper API structure (multiple languages per genre)."""
    xml = b"""
    <Data>
      <jeu id="14001">
        <noms><nom region="us">Test Game</nom></noms>
        <genres>
          <genre id="27" nomcourt="0500" principale="1" parentid="0" langue="en">Strategy</genre>
          <genre id="27" nomcourt="0500" principale="1" parentid="0" langue="fr">Strategie</genre>
          <genre id="40" nomcourt="0400" principale="1" parentid="0" langue="en">Simulation</genre>
          <genre id="40" nomcourt="0400" principale="1" parentid="0" langue="fr">Simulation</genre>
        </genres>
      </jeu>
    </Data>
    """
    root = validate_response(xml)
    game = parse_game_info(root, 'en')

    # Should extract only English genres and de-duplicate by ID
    assert game["genres"] == ["Strategy", "Simulation"]


@pytest.mark.unit
def test_parse_genres_without_english():
    """Test genre parsing falls back to other languages when English not available."""
    xml = b"""
    <Data>
      <jeu id="123">
        <noms><nom region="us">Test Game</nom></noms>
        <genres>
          <genre id="27" principale="1" langue="fr">Strategie</genre>
          <genre id="40" principale="1" langue="de">Simulation</genre>
        </genres>
      </jeu>
    </Data>
    """
    root = validate_response(xml)
    game = parse_game_info(root)

    # Should fall back to first available language for each genre ID
    assert game["genres"] == ["Strategie", "Simulation"]


@pytest.mark.unit
def test_parse_genres_empty():
    """Test genre parsing with empty genres element."""
    xml = b"""
    <Data>
      <jeu id="123">
        <noms><nom region="us">Test Game</nom></noms>
        <genres></genres>
      </jeu>
    </Data>
    """
    root = validate_response(xml)
    game = parse_game_info(root)

    # Should not have genres key when no genres present
    assert "genres" not in game


@pytest.mark.unit
def test_parse_genres_filters_by_principale():
    """Test genre parsing only includes principale='1' genres."""
    xml = b"""
    <Data>
      <jeu id="123">
        <noms><nom region="us">Test Game</nom></noms>
        <genres>
          <genre id="27" principale="1" langue="en">Action</genre>
          <genre id="40" principale="0" langue="en">Sub-Genre</genre>
          <genre id="50" langue="en">No-Attribute</genre>
        </genres>
      </jeu>
    </Data>
    """
    root = validate_response(xml)
    game = parse_game_info(root)

    # Should only include principale="1" genres
    assert game["genres"] == ["Action"]


@pytest.mark.unit
def test_parse_genres_respects_preferred_language():
    """Test genre parsing uses preferred language when specified."""
    xml = """
    <Data>
      <jeu id="123">
        <noms><nom region="us">Test Game</nom></noms>
        <genres>
          <genre id="27" principale="1" langue="en">Strategy</genre>
          <genre id="27" principale="1" langue="fr">Stratégie</genre>
          <genre id="27" principale="1" langue="de">Strategie</genre>
        </genres>
      </jeu>
    </Data>
    """.encode('utf-8')
    root = validate_response(xml)

    # Test with French
    game_fr = parse_game_info(root, 'fr')
    assert game_fr["genres"] == ["Stratégie"]

    # Test with German
    game_de = parse_game_info(root, 'de')
    assert game_de["genres"] == ["Strategie"]

    # Test with English (default)
    game_en = parse_game_info(root, 'en')
    assert game_en["genres"] == ["Strategy"]


@pytest.mark.unit
def test_parse_genres_comprehensive_coverage():
    """Test all genre parsing scenarios with real-world structures."""

    # Case 1: Single principal genre (like Sonic.xml)
    xml_single = b"""
    <Data>
      <jeu id="1">
        <noms><nom region="us">Platform Game</nom></noms>
        <genres>
          <genre id="7" principale="1" parentid="0" langue="en">Platform</genre>
          <genre id="7" principale="1" parentid="0" langue="fr">Plateforme</genre>
        </genres>
      </jeu>
    </Data>
    """
    root = validate_response(xml_single)
    game = parse_game_info(root, 'en')
    assert game["genres"] == ["Platform"]

    # Case 2: Principal with sub-genre (like AirZonk.xml)
    xml_with_sub = b"""
    <Data>
      <jeu id="2">
        <noms><nom region="us">Shooter Game</nom></noms>
        <genres>
          <genre id="79" principale="1" parentid="0" langue="en">Shoot'em Up</genre>
          <genre id="2870" principale="0" parentid="79" langue="en">Shoot'em Up / Horizontal</genre>
        </genres>
      </jeu>
    </Data>
    """
    root = validate_response(xml_with_sub)
    game = parse_game_info(root, 'en')
    # Should only include principale="1", not the sub-genre
    assert game["genres"] == ["Shoot'em Up"]

    # Case 3: Multiple principal genres (like TicTacToe.xml)
    xml_multiple = b"""
    <Data>
      <jeu id="3">
        <noms><nom region="us">Multi-Genre Game</nom></noms>
        <genres>
          <genre id="27" principale="1" parentid="0" langue="en">Strategy</genre>
          <genre id="40" principale="1" parentid="0" langue="en">Simulation</genre>
        </genres>
      </jeu>
    </Data>
    """
    root = validate_response(xml_multiple)
    game = parse_game_info(root, 'en')
    assert game["genres"] == ["Strategy", "Simulation"]
