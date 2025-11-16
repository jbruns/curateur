#!/usr/bin/env python3
"""
Phase 2 Integration Test - ROM Scanner

Tests all scanner components with fixture ROMs.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from curateur.scanner.hash_calculator import calculate_crc32, format_file_size
from curateur.scanner.m3u_parser import parse_m3u, get_disc1_file
from curateur.scanner.disc_handler import is_disc_subdirectory, get_contained_file
from curateur.scanner.rom_scanner import scan_system
from curateur.scanner.rom_types import ROMType
from curateur.config.es_systems import parse_es_systems


def test_hash_calculator():
    """Test CRC32 hash calculation."""
    print("Testing CRC32 hash calculator...")
    
    # Test with a fixture ROM
    test_file = Path(__file__).parent.parent / 'fixtures' / 'roms' / 'nes' / 'World Explorer (World).zip'
    
    if not test_file.exists():
        print(f"  ⚠ Test file not found: {test_file}")
    
    # Calculate hash
    crc = calculate_crc32(test_file, size_limit=10*1024*1024)  # 10MB limit
    
    assert crc and len(crc) == 8 and all(c in '0123456789ABCDEF' for c in crc), "Test failed"
    print(f"  ✓ Test passed")


def test_format_file_size():
    """Test file size formatting."""
    print("\nTesting file size formatting...")
    
    test_cases = [
        (500, "500 B"),
        (1024, "1.0 KB"),
        (1024 * 1024, "1.0 MB"),
        (1024 * 1024 * 1024, "1.00 GB"),
    ]
    
    for size, expected in test_cases:
        result = format_file_size(size)
        if result == expected:
            print(f"  ✓ {size} -> {result}")
        else:
            print(f"  ✗ {size}: expected '{expected}', got '{result}'")
            all_pass = False
    


def test_m3u_parser():
    """Test M3U playlist parsing."""
    print("\nTesting M3U playlist parser...")
    
    m3u_file = Path(__file__).parent.parent / 'fixtures' / 'roms' / 'psx' / 'Sample Saga.m3u'
    
    if not m3u_file.exists():
        print(f"  ⚠ Test M3U not found: {m3u_file}")
    
    try:
        disc_files = parse_m3u(m3u_file)
        print(f"  ✓ Parsed {len(disc_files)} disc files")
        
        disc1 = get_disc1_file(m3u_file)
        print(f"  ✓ Disc 1: {disc1.name}")
        
        if len(disc_files) >= 2:
            print(f"  ✓ Multi-disc game detected")
        
    except Exception as e:
        print(f"  ✗ Failed to parse M3U: {e}")


def test_disc_handler():
    """Test disc subdirectory handling."""
    print("\nTesting disc subdirectory handler...")
    
    disc_subdir = Path(__file__).parent.parent / 'fixtures' / 'roms' / 'dreamcast' / 'Demo Orbit (Disc 1).cue'
    
    if not disc_subdir.exists():
        print(f"  ⚠ Test disc subdir not found: {disc_subdir}")
        return  # Skip test
    
    # Check if it's recognized as disc subdir
    extensions = ['.cue', '.gdi']
    is_disc = is_disc_subdirectory(disc_subdir, extensions)
    
    assert is_disc, "Not recognized as disc subdirectory"
    print(f"  ✓ Disc subdirectory detected")
    
    # Get contained file
    contained = get_contained_file(disc_subdir)
    print(f"  ✓ Contained file: {contained.name}")


def test_nes_scanner():
    """Test scanning NES ROMs."""
    print("\nTesting NES ROM scanner...")
    
    # Load system definition
    es_systems_file = Path(__file__).parent.parent / 'fixtures' / 'es_systems.xml'
    systems = parse_es_systems(es_systems_file)
    nes_system = next((s for s in systems if s.platform == 'nes'), None)
    
    assert nes_system, "NES system not found in es_systems.xml"
    
    try:
        roms = scan_system(nes_system, crc_size_limit=10*1024*1024)
        print(f"  ✓ Scanned {len(roms)} ROMs")
        
        # Check that all are standard ROMs
        all_standard = all(r.rom_type == ROMType.STANDARD for r in roms)
        if all_standard:
            print(f"  ✓ All ROMs are standard type")
        else:
            print(f"  ⚠ Mixed ROM types found")
        
        # Show sample
        for rom in roms[:3]:
            has_crc = "CRC" if rom.crc32 else "no CRC"
            print(f"    - {rom.filename} ({has_crc})")
        
    except Exception as e:
        print(f"  ✗ Failed to scan: {e}")
        import traceback
        traceback.print_exc()
        assert False, "Test failed"


def test_psx_scanner():
    """Test scanning PSX ROMs (includes M3U)."""
    print("\nTesting PSX ROM scanner (with M3U)...")
    
    # Load system definition
    es_systems_file = Path(__file__).parent.parent / 'fixtures' / 'es_systems.xml'
    systems = parse_es_systems(es_systems_file)
    psx_system = next((s for s in systems if s.platform == 'psx'), None)
    
    assert psx_system, "PSX system not found in es_systems.xml"
    
    try:
        roms = scan_system(psx_system, crc_size_limit=10*1024*1024)
        print(f"  ✓ Scanned {len(roms)} ROMs")
        
        # Check for M3U
        m3u_roms = [r for r in roms if r.rom_type == ROMType.M3U_PLAYLIST]
        standard_roms = [r for r in roms if r.rom_type == ROMType.STANDARD]
        
        print(f"  ✓ M3U playlists: {len(m3u_roms)}")
        print(f"  ✓ Standard ROMs: {len(standard_roms)}")
        
        # Show details
        for rom in roms:
            rom_type_str = rom.rom_type.value
            print(f"    - {rom.filename} ({rom_type_str})")
            if rom.rom_type == ROMType.M3U_PLAYLIST:
                print(f"      Query file: {rom.query_filename}")
                print(f"      Disc files: {len(rom.disc_files or [])}")
        
    except Exception as e:
        print(f"  ✗ Failed to scan: {e}")
        import traceback
        traceback.print_exc()
        assert False, "Test failed"


def test_dreamcast_scanner():
    """Test scanning Dreamcast ROMs (includes disc subdir)."""
    print("\nTesting Dreamcast ROM scanner (with disc subdir)...")
    
    # Load system definition
    es_systems_file = Path(__file__).parent.parent / 'fixtures' / 'es_systems.xml'
    systems = parse_es_systems(es_systems_file)
    dc_system = next((s for s in systems if s.platform == 'dreamcast'), None)
    
    assert dc_system, "Dreamcast system not found in es_systems.xml"
    
    try:
        roms = scan_system(dc_system, crc_size_limit=10*1024*1024)
        print(f"  ✓ Scanned {len(roms)} ROMs")
        
        # Check for disc subdirs
        disc_roms = [r for r in roms if r.rom_type == ROMType.DISC_SUBDIR]
        
        print(f"  ✓ Disc subdirectories: {len(disc_roms)}")
        
        # Show details
        for rom in roms:
            rom_type_str = rom.rom_type.value
            print(f"    - {rom.filename} ({rom_type_str})")
            if rom.rom_type == ROMType.DISC_SUBDIR:
                print(f"      Query file: {rom.query_filename}")
                print(f"      Contained: {rom.contained_file.name if rom.contained_file else 'N/A'}")
        
    except Exception as e:
        print(f"  ✗ Failed to scan: {e}")
        import traceback
        traceback.print_exc()
        assert False, "Test failed"


def main():
    """Run all scanner tests."""
    print("=" * 60)
    print("curateur MVP Phase 2 - Scanner Integration Test")
    print("=" * 60)
    
    tests = [
        test_hash_calculator,
        test_format_file_size,
        test_m3u_parser,
        test_disc_handler,
        test_nes_scanner,
        test_psx_scanner,
        test_dreamcast_scanner,
    ]
    
    results = []
    for test in tests:
        results.append(test())
    
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("✓ Phase 2 integration test PASSED")
        print("=" * 60)
        return 0
    else:
        print("✗ Phase 2 integration test FAILED")
        print("=" * 60)
        return 1


if __name__ == '__main__':
    sys.exit(main())
