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
          <genre><noms><nom langue="en">Adventure</nom></noms></genre>
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
