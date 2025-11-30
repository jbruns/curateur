"""ScreenScraper API response parsing and validation."""

import html
from typing import Dict, Any, Optional, List
from lxml import etree


class ResponseError(Exception):
    """Response parsing errors."""
    pass


def validate_response(
    response_content: bytes,
    expected_format: str = 'xml'
) -> etree.Element:
    """
    Validate and parse API response.

    Args:
        response_content: Raw response bytes
        expected_format: Expected format ('xml')

    Returns:
        Parsed XML root element

    Raises:
        ResponseError: If validation fails
    """
    if not response_content:
        raise ResponseError("Empty response body received")

    # Parse XML
    try:
        root = etree.fromstring(response_content)
    except etree.XMLSyntaxError as e:
        raise ResponseError(f"Malformed XML: {e}")
    except Exception as e:
        raise ResponseError(f"Failed to parse response: {e}")

    # Validate root element
    if root.tag != 'Data':
        raise ResponseError(f"Invalid root element: expected 'Data', got '{root.tag}'")

    return root


def _parse_jeu_element(jeu_elem: etree.Element, preferred_language: str = 'en') -> Dict[str, Any]:
    """
    Parse a <jeu> element into game metadata.

    Args:
        jeu_elem: <jeu> XML element
        preferred_language: Preferred language code (e.g., 'en', 'fr', 'de')

    Returns:
        Dictionary with game metadata
    """
    # Extract basic metadata
    game_data = {}

    # Game ID
    game_id = jeu_elem.get('id')
    if game_id:
        game_data['id'] = game_id

    # Names (multiple language support)
    noms = jeu_elem.find('noms')
    if noms is not None:
        names = {}
        for nom in noms.findall('nom'):
            region = nom.get('region', 'wor')
            text = nom.text
            if text:
                names[region] = decode_html_entities(text)
        game_data['names'] = names

    # Get primary name (prefer 'us', then 'wor', then first available)
    if 'names' in game_data:
        if 'us' in game_data['names']:
            game_data['name'] = game_data['names']['us']
        elif 'wor' in game_data['names']:
            game_data['name'] = game_data['names']['wor']
        elif game_data['names']:
            game_data['name'] = list(game_data['names'].values())[0]

    # System name
    systeme = jeu_elem.find('systeme')
    if systeme is not None and systeme.text:
        game_data['system'] = systeme.text

    # Descriptions
    synopsis = jeu_elem.find('synopsis')
    if synopsis is not None:
        descriptions = {}
        for desc in synopsis.findall('synopsis'):
            langue = desc.get('langue', 'en')
            text = desc.text
            if text:
                descriptions[langue] = decode_html_entities(text)
        if descriptions:
            game_data['descriptions'] = descriptions

    # Dates
    dates = jeu_elem.find('dates')
    if dates is not None:
        release_dates = {}
        for date in dates.findall('date'):
            region = date.get('region', 'wor')
            text = date.text
            if text:
                release_dates[region] = text
        if release_dates:
            game_data['release_dates'] = release_dates

    # Genres
    genres_elem = jeu_elem.find('genres')
    if genres_elem is not None:
        # Use a dict to track unique genres by ID (avoid duplicates)
        genre_dict = {}

        # Filter to primary genres only (principale="1")
        # Some games have sub-genres or tags; we only want main genres
        primary_genres = [g for g in genres_elem.findall('genre') if g.get('principale') == '1']

        # Try preferred language first
        for genre in primary_genres:
            if genre.get('langue') == preferred_language:
                genre_id = genre.get('id')
                if genre_id and genre.text and genre_id not in genre_dict:
                    genre_dict[genre_id] = decode_html_entities(genre.text)

        # Fall back to English if preferred language didn't yield results
        if not genre_dict and preferred_language != 'en':
            for genre in primary_genres:
                if genre.get('langue') == 'en':
                    genre_id = genre.get('id')
                    if genre_id and genre.text and genre_id not in genre_dict:
                        genre_dict[genre_id] = decode_html_entities(genre.text)

        # Fall back to any language for each unique genre ID if still empty
        if not genre_dict:
            for genre in primary_genres:
                genre_id = genre.get('id')
                if genre_id and genre.text and genre_id not in genre_dict:
                    genre_dict[genre_id] = decode_html_entities(genre.text)

        if genre_dict:
            # Return genres as a list (sorted by ID for consistency)
            game_data['genres'] = [genre_dict[gid] for gid in sorted(genre_dict.keys())]

    # Developer
    developpeur = jeu_elem.find('developpeur')
    if developpeur is not None and developpeur.text:
        game_data['developer'] = decode_html_entities(developpeur.text)

    # Publisher
    editeur = jeu_elem.find('editeur')
    if editeur is not None and editeur.text:
        game_data['publisher'] = decode_html_entities(editeur.text)

    # Players
    joueurs = jeu_elem.find('joueurs')
    if joueurs is not None and joueurs.text:
        game_data['players'] = joueurs.text

    # Rating
    note = jeu_elem.find('note')
    if note is not None and note.text:
        try:
            game_data['rating'] = float(note.text)
        except ValueError:
            # Invalid rating format - skip this field
            pass

    # Media URLs
    medias = jeu_elem.find('medias')
    if medias is not None:
        game_data['media'] = parse_media_urls(medias)

    return game_data


def parse_game_info(root: etree.Element, preferred_language: str = 'en') -> Dict[str, Any]:
    """
    Parse game information from jeuInfos.php response.

    Args:
        root: Parsed XML root element
        preferred_language: Preferred language code (e.g., 'en', 'fr', 'de')

    Returns:
        Dictionary with game metadata

    Raises:
        ResponseError: If game not found or response invalid
    """
    # Check for <jeu> element
    jeu_elem = root.find('jeu')

    if jeu_elem is None:
        # Game not found
        raise ResponseError("Game not found in database (<jeu> element missing)")

    return _parse_jeu_element(jeu_elem, preferred_language)


def parse_search_results(root: etree.Element, preferred_language: str = 'en') -> list[Dict[str, Any]]:
    """
    Parse game list from jeuRecherche.php response.

    Args:
        root: Parsed XML root element with <jeux> container
        preferred_language: Preferred language code (e.g., 'en', 'fr', 'de')

    Returns:
        List of game metadata dictionaries
    """
    results = []

    # Find <jeux> container
    jeux = root.find('jeux')
    if jeux is None:
        return results

    # Parse each <jeu> element
    for jeu_elem in jeux.findall('jeu'):
        try:
            game_data = _parse_jeu_element(jeu_elem, preferred_language)
            results.append(game_data)
        except Exception:
            # Skip malformed entries
            continue

    return results


def parse_media_urls(medias_elem: etree.Element) -> Dict[str, List[Dict[str, Any]]]:
    """
    Parse media URLs from response.

    Args:
        medias_elem: <medias> XML element

    Returns:
        Dictionary mapping media type to list of media items
    """
    media_dict = {}

    for media in medias_elem.findall('media'):
        media_type = media.get('type')
        if not media_type:
            continue

        # Extract media info
        media_info = {
            'type': media_type,
            'url': media.text if media.text else None,
            'format': media.get('format'),
            'region': media.get('region'),
        }

        # Add to appropriate list
        if media_type not in media_dict:
            media_dict[media_type] = []

        media_dict[media_type].append(media_info)

    return media_dict


def parse_user_info(root: etree.Element) -> Dict[str, Any]:
    """
    Parse user information from API response header.

    Args:
        root: Parsed XML root element

    Returns:
        Dictionary with user info and rate limits
    """
    ssuser_elem = root.find('.//ssuser')

    if ssuser_elem is None:
        return {}

    user_info = {}

    # Extract rate limits and quota info
    for field in ['id', 'niveau', 'contribution', 'maxthreads',
                  'maxrequestspermin', 'requeststoday', 'maxrequestsperday',
                  'requestskotoday', 'maxrequestskoperday']:
        elem = ssuser_elem.find(field)
        if elem is not None and elem.text:
            try:
                user_info[field] = int(elem.text)
            except ValueError:
                user_info[field] = elem.text

    import logging
    logger = logging.getLogger(__name__)
    logger.debug(f"Parsed user_info from API response: {user_info}")

    return user_info


def decode_html_entities(text: str) -> str:
    """
    Decode HTML entities in API response text.

    ScreenScraper returns text with HTML entities that must be decoded.

    Args:
        text: Text with HTML entities

    Returns:
        Decoded text
    """
    if not text:
        return text

    return html.unescape(text)


def extract_error_message(root: etree.Element) -> Optional[str]:
    """
    Extract error message from API response.

    Args:
        root: Parsed XML root element

    Returns:
        Error message or None
    """
    error_elem = root.find('.//erreur')

    if error_elem is not None and error_elem.text:
        return decode_html_entities(error_elem.text)

    return None
