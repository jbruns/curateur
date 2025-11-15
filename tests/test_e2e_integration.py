#!/usr/bin/env python3
"""
End-to-End Integration Test (Phases 1 + 2)

Tests the complete workflow from config loading to ROM scanning.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from curateur.config.loader import load_config
from curateur.config.validator import validate_config
from curateur.config.es_systems import parse_es_systems, get_systems_by_name
from curateur.scanner.rom_scanner import scan_system
from curateur.api.system_map import get_systemeid


def test_full_workflow():
    """Test complete workflow from config to scanning."""
    print("End-to-End Integration Test")
    print("=" * 60)
    
    # Step 1: Load configuration
    print("\n[1/5] Loading configuration...")
    config_path = Path(__file__).parent.parent / 'tests' / 'fixtures' / 'test_config.yaml'
    
    try:
        config = load_config(config_path)
        print(f"  ✓ Config loaded: {config_path}")
        print(f"    User: {config['screenscraper']['user_id']}")
        print(f"    Dev credentials: {config['screenscraper']['softname']}")
    except Exception as e:
        print(f"  ✗ Failed to load config: {e}")
        return False
    
    # Step 2: Validate configuration
    print("\n[2/5] Validating configuration...")
    
    try:
        validate_config(config)
        print(f"  ✓ Configuration is valid")
        print(f"    Media types: {', '.join(config['scraping']['media_types'])}")
        print(f"    CRC limit: {config['scraping']['crc_size_limit']} bytes")
    except Exception as e:
        print(f"  ✗ Validation failed: {e}")
        return False
    
    # Step 3: Parse ES systems
    print("\n[3/5] Parsing ES systems...")
    es_systems_path = Path(config['paths']['es_systems']).resolve()
    
    try:
        systems = parse_es_systems(es_systems_path)
        print(f"  ✓ Parsed {len(systems)} systems")
        
        for system in systems:
            print(f"    - {system.name} ({system.platform})")
    except Exception as e:
        print(f"  ✗ Failed to parse systems: {e}")
        return False
    
    # Step 4: Map platforms to system IDs
    print("\n[4/5] Mapping platforms to ScreenScraper system IDs...")
    
    try:
        for system in systems:
            systemeid = get_systemeid(system.platform)
            print(f"  ✓ {system.platform} -> systemeid {systemeid}")
    except Exception as e:
        print(f"  ✗ Failed to map platform: {e}")
        return False
    
    # Step 5: Scan all systems
    print("\n[5/5] Scanning ROM directories...")
    
    total_roms = 0
    crc_size_limit = config['scraping']['crc_size_limit']
    
    for system in systems:
        try:
            roms = scan_system(system, crc_size_limit=crc_size_limit)
            total_roms += len(roms)
            
            if roms:
                print(f"  ✓ {system.name}: {len(roms)} ROM(s)")
                for rom in roms:
                    print(f"      - {rom.filename} ({rom.rom_type.value})")
            else:
                print(f"  ℹ {system.name}: No ROMs found")
                
        except Exception as e:
            print(f"  ✗ {system.name}: Failed to scan: {e}")
            return False
    
    # Summary
    print("\n" + "=" * 60)
    print("Integration Test Summary")
    print("=" * 60)
    print(f"✓ Configuration loaded and validated")
    print(f"✓ {len(systems)} systems parsed from ES-DE config")
    print(f"✓ All platforms mapped to ScreenScraper system IDs")
    print(f"✓ {total_roms} ROMs scanned across {len(systems)} systems")
    print("\n✓ End-to-End Integration Test PASSED")
    print("=" * 60)
    
    return True


def main():
    """Run end-to-end test."""
    success = test_full_workflow()
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(main())
