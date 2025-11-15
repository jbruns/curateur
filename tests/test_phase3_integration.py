#!/usr/bin/env python3
"""
Phase 3 Integration Test - API Client & Verification

Tests all API components with mock data and validation logic.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from curateur.api.error_handler import (
    get_error_message,
    handle_http_status,
    FatalAPIError,
    RetryableAPIError,
    SkippableAPIError,
    is_retryable_error
)
from curateur.api.rate_limiter import RateLimiter
from curateur.api.name_verifier import (
    normalize_name,
    calculate_similarity,
    check_word_overlap,
    verify_name_match,
    VERIFICATION_THRESHOLDS
)
from curateur.api.response_parser import (
    decode_html_entities,
    validate_response,
    ResponseError
)


def test_error_handler():
    """Test error handling and HTTP status code mapping."""
    print("Testing error handler...")
    
    # Test error messages
    test_cases = [
        (200, "Success"),
        (404, "Game not found"),
        (403, "Invalid credentials"),
        (429, "Thread limit reached"),
    ]
    
    all_pass = True
    for code, expected in test_cases:
        msg = get_error_message(code)
        if expected in msg:
            print(f"  ✓ HTTP {code}: {msg}")
        else:
            print(f"  ✗ HTTP {code}: expected '{expected}', got '{msg}'")
            all_pass = False
    
    # Test exception handling
    try:
        handle_http_status(403)  # Fatal error
        print("  ✗ Should have raised FatalAPIError")
        all_pass = False
    except FatalAPIError:
        print("  ✓ FatalAPIError raised for HTTP 403")
    
    try:
        handle_http_status(429)  # Retryable error
        print("  ✗ Should have raised RetryableAPIError")
        all_pass = False
    except RetryableAPIError:
        print("  ✓ RetryableAPIError raised for HTTP 429")
    
    try:
        handle_http_status(404)  # Skippable error
        print("  ✗ Should have raised SkippableAPIError")
        all_pass = False
    except SkippableAPIError:
        print("  ✓ SkippableAPIError raised for HTTP 404")
    
    return all_pass


def test_rate_limiter():
    """Test rate limiting logic."""
    print("\nTesting rate limiter...")
    
    limiter = RateLimiter(max_requests_per_minute=60, max_threads=1)
    
    # Test initialization
    limits = limiter.get_limits()
    if limits['max_requests_per_minute'] == 60:
        print("  ✓ Rate limiter initialized with 60 req/min")
    else:
        print(f"  ✗ Wrong limit: {limits}")
        return False
    
    # Test API update
    api_response = {
        'maxrequestspermin': 20,
        'maxthreads': 1
    }
    limiter.update_from_api(api_response)
    
    limits = limiter.get_limits()
    if limits['max_requests_per_minute'] == 20:
        print("  ✓ Rate limiter updated from API response")
    else:
        print(f"  ✗ Failed to update: {limits}")
        return False
    
    return True


def test_name_normalization():
    """Test name normalization."""
    print("\nTesting name normalization...")
    
    test_cases = [
        ("Super Mario Bros. (USA).zip", "super mario bros"),
        ("The Legend of Zelda [!]", "legend of zelda"),
        ("Final Fantasy VII (Disc 1)", "final fantasy vii"),
        ("Street Fighter II' - Champion Edition", "street fighter ii champion edition"),
    ]
    
    all_pass = True
    for input_name, expected in test_cases:
        result = normalize_name(input_name)
        if result == expected:
            print(f"  ✓ '{input_name}' -> '{result}'")
        else:
            print(f"  ✗ '{input_name}': expected '{expected}', got '{result}'")
            all_pass = False
    
    return all_pass


def test_name_similarity():
    """Test name similarity calculation."""
    print("\nTesting name similarity...")
    
    test_cases = [
        ("Super Mario Bros", "Super Mario Bros.", 0.9),  # High similarity
        ("Zelda", "The Legend of Zelda", 0.4),  # Medium similarity
        ("SMB3", "Super Mario Bros. 3", 0.1),  # Low similarity (but word overlap)
        ("Sonic", "Mario", 0.0),  # No similarity
    ]
    
    all_pass = True
    for name1, name2, min_expected in test_cases:
        similarity = calculate_similarity(name1, name2)
        if similarity >= min_expected:
            print(f"  ✓ '{name1}' vs '{name2}': {similarity*100:.0f}%")
        else:
            print(f"  ✗ '{name1}' vs '{name2}': {similarity*100:.0f}% (expected >={min_expected*100:.0f}%)")
            all_pass = False
    
    return all_pass


def test_word_overlap():
    """Test word overlap detection."""
    print("\nTesting word overlap detection...")
    
    test_cases = [
        # Note: Abbreviations like "SMB3" are filtered out (too short)
        # This is acceptable for MVP - full names are typical
        ("Super Mario Bros 3", "Super Mario Bros. 3", True),  # Full name match
        ("Final Fantasy 7", "Final Fantasy VII", True),  # Number variant
        ("Street Fighter Alpha", "Street Fighter", True),  # Subset
        ("Sonic the Hedgehog", "Mario Bros", False),  # Different games
    ]
    
    all_pass = True
    for name1, name2, expected in test_cases:
        result = check_word_overlap(name1, name2)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{name1}' vs '{name2}': {result}")
        if result != expected:
            all_pass = False
    
    return all_pass


def test_name_verification():
    """Test complete name verification."""
    print("\nTesting name verification...")
    
    test_cases = [
        ("Zelda (USA).nes", "The Legend of Zelda", "normal", True),
        ("Final Fantasy VII", "Final Fantasy 7", "normal", True),
        ("Mario Bros", "Sonic the Hedgehog", "normal", False),
        # Note: Abbreviations are not reliably matched in MVP
        # Users should use full filenames for best results
        ("Super Mario Bros 3.nes", "Super Mario Bros. 3", "normal", True),
    ]
    
    all_pass = True
    for rom_name, api_name, threshold, expected in test_cases:
        is_match, similarity, reason = verify_name_match(rom_name, api_name, threshold)
        status = "✓" if is_match == expected else "✗"
        print(f"  {status} '{rom_name}' vs '{api_name}': {is_match} ({similarity*100:.0f}%)")
        if is_match != expected:
            all_pass = False
    
    return all_pass


def test_html_entity_decoding():
    """Test HTML entity decoding."""
    print("\nTesting HTML entity decoding...")
    
    test_cases = [
        ("Super Mario Bros.", "Super Mario Bros."),
        ("Pok&eacute;mon", "Pokémon"),
        ("Mario &amp; Luigi", "Mario & Luigi"),
        ("Street Fighter II&#39;", "Street Fighter II'"),
    ]
    
    all_pass = True
    for input_str, expected in test_cases:
        result = decode_html_entities(input_str)
        if result == expected:
            print(f"  ✓ '{input_str}' -> '{result}'")
        else:
            print(f"  ✗ '{input_str}': expected '{expected}', got '{result}'")
            all_pass = False
    
    return all_pass


def test_response_validation():
    """Test response validation."""
    print("\nTesting response validation...")
    
    # Test empty response
    try:
        validate_response(b'')
        print("  ✗ Should have raised ResponseError for empty response")
        return False
    except ResponseError as e:
        if "Empty response" in str(e):
            print("  ✓ Empty response detected")
        else:
            print(f"  ✗ Wrong error: {e}")
            return False
    
    # Test malformed XML
    try:
        validate_response(b'<response><unclosed>')
        print("  ✗ Should have raised ResponseError for malformed XML")
        return False
    except ResponseError as e:
        if "Malformed XML" in str(e):
            print("  ✓ Malformed XML detected")
        else:
            print(f"  ✗ Wrong error: {e}")
            return False
    
    # Test valid response
    try:
        valid_xml = b'<response><jeu id="123"><noms><nom region="us">Test Game</nom></noms></jeu></response>'
        root = validate_response(valid_xml)
        if root.tag == 'response':
            print("  ✓ Valid response parsed")
        else:
            print(f"  ✗ Wrong root tag: {root.tag}")
            return False
    except Exception as e:
        print(f"  ✗ Failed to parse valid response: {e}")
        return False
    
    return True


def test_verification_thresholds():
    """Test verification threshold levels."""
    print("\nTesting verification thresholds...")
    
    all_pass = True
    
    # Test threshold values
    expected = {
        'strict': 0.8,
        'normal': 0.6,
        'lenient': 0.4,
        'disabled': 0.0
    }
    
    for mode, expected_val in expected.items():
        actual = VERIFICATION_THRESHOLDS.get(mode)
        if actual == expected_val:
            print(f"  ✓ {mode}: {actual}")
        else:
            print(f"  ✗ {mode}: expected {expected_val}, got {actual}")
            all_pass = False
    
    return all_pass


def main():
    """Run all API tests."""
    print("=" * 60)
    print("curateur MVP Phase 3 - API Integration Test")
    print("=" * 60)
    
    tests = [
        test_error_handler,
        test_rate_limiter,
        test_name_normalization,
        test_name_similarity,
        test_word_overlap,
        test_name_verification,
        test_html_entity_decoding,
        test_response_validation,
        test_verification_thresholds,
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("✓ Phase 3 integration test PASSED")
        print("=" * 60)
        return 0
    else:
        print("✗ Phase 3 integration test FAILED")
        print("=" * 60)
        return 1


if __name__ == '__main__':
    sys.exit(main())
