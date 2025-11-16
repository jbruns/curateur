#!/usr/bin/env python3
"""
Phase 4 Integration Test - Media Downloader

Tests all media downloader components with mock data and validation.
"""

import sys
import tempfile
from pathlib import Path
from io import BytesIO

sys.path.insert(0, str(Path(__file__).parent.parent))

from PIL import Image
from curateur.media import (
    MediaType,
    MEDIA_TYPE_MAP,
    get_directory_for_media_type,
    detect_region_from_filename,
    select_best_region,
    MediaURLSelector,
    ImageDownloader,
    MediaOrganizer,
    MediaDownloader,
)


def test_media_types():
    """Test media type mappings."""
    print("Testing media type mappings...")
    
    test_cases = [
        ('box-2D', 'covers'),
        ('ss', 'screenshots'),
        ('sstitle', 'titlescreens'),
        ('screenmarquee', 'marquees'),
    ]
    
    for media_type, expected_dir in test_cases:
        actual_dir = get_directory_for_media_type(media_type)
        if actual_dir == expected_dir:
            print(f"  ✓ {media_type} -> {actual_dir}")
        else:
            print(f"  ✗ {media_type}: expected {expected_dir}, got {actual_dir}")
            all_pass = False
    


def test_region_detection():
    """Test region detection from filenames."""
    print("\nTesting region detection...")
    
    test_cases = [
        ("Game (USA).nes", ['us']),
        ("Game (Japan, USA).nes", ['jp', 'us']),
        ("Game (Europe) (En,Fr,De).zip", ['eu']),  # Languages ignored
        ("Game (World).n64", ['wor']),
        ("Game Name.zip", []),  # No region
    ]
    
    for filename, expected_regions in test_cases:
        detected = detect_region_from_filename(filename)
        if detected == expected_regions:
            print(f"  ✓ '{filename}' -> {detected}")
        else:
            print(f"  ✗ '{filename}': expected {expected_regions}, got {detected}")
            all_pass = False
    


def test_region_selection():
    """Test region selection with priorities."""
    print("\nTesting region selection...")
    
    # Test case 1: ROM has USA, API has both USA and Japan
    available = ['us', 'jp', 'eu']
    rom_filename = "Game (Japan, USA).nes"
    preferred = ['us', 'wor', 'eu', 'jp']
    
    selected = select_best_region(available, rom_filename, preferred)
    if selected == 'us':
        print(f"  ✓ Multi-region ROM: selected 'us' (highest priority in ROM)")
    else:
        print(f"  ✗ Expected 'us', got '{selected}'")
        assert False, "Test failed"
    
    # Test case 2: ROM has World, API has World and USA
    available = ['us', 'wor']
    rom_filename = "Game (World).n64"
    
    selected = select_best_region(available, rom_filename, preferred)
    if selected == 'wor':
        print(f"  ✓ World ROM: selected 'wor' (from ROM)")
    else:
        print(f"  ✗ Expected 'wor', got '{selected}'")
        assert False, "Test failed"
    
    # Test case 3: ROM has no region, fallback to preferred
    available = ['eu', 'jp']
    rom_filename = "Game Name.zip"
    
    selected = select_best_region(available, rom_filename, preferred)
    if selected == 'eu':
        print(f"  ✓ No ROM region: selected 'eu' (from preferred list)")
    else:
        print(f"  ✗ Expected 'eu', got '{selected}'")
        assert False, "Test failed"
    


def test_url_selector():
    """Test media URL selection."""
    print("\nTesting media URL selector...")
    
    selector = MediaURLSelector(
        preferred_regions=['us', 'wor', 'eu'],
        enabled_media_types=['box-2D', 'ss']
    )
    
    # Mock API response media list
    media_list = [
        {'type': 'box-2D', 'region': 'us', 'url': 'http://example.com/cover_us.jpg', 'format': 'jpg'},
        {'type': 'box-2D', 'region': 'eu', 'url': 'http://example.com/cover_eu.jpg', 'format': 'jpg'},
        {'type': 'ss', 'region': 'us', 'url': 'http://example.com/screen_us.png', 'format': 'png'},
        {'type': 'sstitle', 'region': 'us', 'url': 'http://example.com/title.jpg', 'format': 'jpg'},
    ]
    
    rom_filename = "Game (USA).nes"
    selected = selector.select_media_urls(media_list, rom_filename)
    
    # Should select box-2D and ss (both enabled), both with 'us' region
    if 'box-2D' in selected and 'ss' in selected:
        if selected['box-2D']['region'] == 'us' and selected['ss']['region'] == 'us':
            print(f"  ✓ Selected 2 media types with correct regions")
        else:
            print(f"  ✗ Wrong regions selected")
            assert False, "Test failed"
    else:
        print(f"  ✗ Expected box-2D and ss, got {list(selected.keys())}")
        assert False, "Test failed"
    
    # sstitle should not be selected (not in enabled_media_types)
    if 'sstitle' not in selected:
        print(f"  ✓ Correctly filtered out non-enabled media types")
    else:
        print(f"  ✗ Should not have selected sstitle")
        assert False, "Test failed"
    


def test_media_organizer():
    """Test media file organization."""
    print("\nTesting media organizer...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        media_root = Path(tmpdir)
        organizer = MediaOrganizer(media_root)
        
        # Test path generation
        path = organizer.get_media_path('nes', 'box-2D', 'Super Mario Bros', 'jpg')
        expected = media_root / 'nes' / 'covers' / 'Super Mario Bros.jpg'
        
        if path == expected:
            print(f"  ✓ Path generation: {path.relative_to(media_root)}")
        else:
            print(f"  ✗ Expected {expected}, got {path}")
            assert False, "Test failed"
        
        # Test ROM basename extraction
        test_cases = [
            ("Super Mario Bros.nes", "Super Mario Bros"),
            ("Game (Disc 1).cue", "Game (Disc 1).cue"),  # Disc subdir
            ("Zelda.m3u", "Zelda"),  # M3U playlist
        ]
        
        for rom_path, expected_basename in test_cases:
            basename = organizer.get_rom_basename(rom_path)
            assert basename == expected_basename, f"'{rom_path}': expected '{expected_basename}', got '{basename}'"
            print(f"  ✓ Basename: '{rom_path}' -> '{basename}'")


def test_image_validator():
    """Test image validation."""
    print("\nTesting image validation...")
    
    downloader = ImageDownloader(min_width=50, min_height=50)
    
    # Create a valid test image
    img = Image.new('RGB', (100, 100), color='red')
    img_bytes = BytesIO()
    img.save(img_bytes, format='JPEG')
    img_data = img_bytes.getvalue()
    
    is_valid, error = downloader._validate_image_data(img_data)
    if is_valid:
        print(f"  ✓ Valid 100x100 image accepted")
    else:
        print(f"  ✗ Valid image rejected: {error}")
        assert False, "Test failed"
    
    # Create an image that's too small
    small_img = Image.new('RGB', (40, 40), color='blue')
    small_bytes = BytesIO()
    small_img.save(small_bytes, format='JPEG')
    small_data = small_bytes.getvalue()
    
    is_valid, error = downloader._validate_image_data(small_data)
    if not is_valid and "too small" in error.lower():
        print(f"  ✓ Small 40x40 image rejected")
    else:
        print(f"  ✗ Small image should be rejected")
        assert False, "Test failed"
    
    # Test invalid data
    is_valid, error = downloader._validate_image_data(b"not an image")
    if not is_valid:
        print(f"  ✓ Invalid image data rejected")
    else:
        print(f"  ✗ Invalid data should be rejected")
        assert False, "Test failed"
    


def test_download_integration():
    """Test integrated download workflow."""
    print("\nTesting download integration...")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        media_root = Path(tmpdir)
        
        # Initialize downloader with all components
        downloader = MediaDownloader(
            media_root=media_root,
            preferred_regions=['us', 'wor', 'eu'],
            enabled_media_types=['box-2D', 'ss']
        )
        
        # Check directory structure
        rom_basename = downloader.organizer.get_rom_basename("Mario.nes")
        if rom_basename == "Mario":
            print(f"  ✓ MediaDownloader initialized")
        else:
            print(f"  ✗ Initialization failed")
            assert False, "Test failed"
        
        # Test existing media check
        existing = downloader.check_existing_media('nes', 'Mario')
        if not any(existing.values()):
            print(f"  ✓ No existing media detected (empty directory)")
        else:
            print(f"  ✗ Should not find existing media in empty directory")
            assert False, "Test failed"
        
        # Test URL selection
        media_list = [
            {'type': 'box-2D', 'region': 'us', 'url': 'http://example.com/cover.jpg', 'format': 'jpg'},
        ]
        
        selected = downloader.url_selector.select_media_urls(media_list, "Mario (USA).nes")
        assert 'box-2D' in selected, "URL selection failed"
        print(f"  ✓ URL selection working")


def test_media_type_map():
    """Test MEDIA_TYPE_MAP completeness."""
    print("\nTesting media type map...")
    
    # Check all MVP types are mapped
    mvp_types = ['box-2D', 'ss', 'sstitle', 'screenmarquee']
    
    for media_type in mvp_types:
        if media_type in MEDIA_TYPE_MAP:
            print(f"  ✓ {media_type} mapped to {MEDIA_TYPE_MAP[media_type]}")
        else:
            print(f"  ✗ {media_type} not in MEDIA_TYPE_MAP")
            all_pass = False
    


def main():
    """Run all Phase 4 tests."""
    print("=" * 60)
    print("curateur MVP Phase 4 - Media Downloader Test")
    print("=" * 60)
    
    tests = [
        test_media_types,
        test_media_type_map,
        test_region_detection,
        test_region_selection,
        test_url_selector,
        test_media_organizer,
        test_image_validator,
        test_download_integration,
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("✓ Phase 4 integration test PASSED")
        print("=" * 60)
        return 0
    else:
        print("✗ Phase 4 integration test FAILED")
        print("=" * 60)
        return 1


if __name__ == '__main__':
    sys.exit(main())
