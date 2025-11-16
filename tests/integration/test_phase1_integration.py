#!/usr/bin/env python3
"""
Phase 1 Integration Test

Verifies that all Phase 1 components work together correctly.
Run this after completing Phase 1 to ensure everything is integrated.
"""

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

def test_imports():
    """Test that all modules can be imported."""
    print("Testing module imports...")
    from curateur import __version__
    from curateur.api.obfuscator import obfuscate, deobfuscate
    from curateur.api.credentials import get_dev_credentials
    from curateur.api.system_map import get_systemeid, PLATFORM_SYSTEMEID_MAP
    from curateur.config.loader import load_config
    from curateur.config.validator import validate_config
    from curateur.config.es_systems import parse_es_systems, SystemDefinition
    print("  ✓ All imports successful")


def test_obfuscation():
    """Test credential obfuscation."""
    print("\nTesting credential obfuscation...")
    from curateur.api.obfuscator import obfuscate, deobfuscate
    
    test_data = "sensitive_credential_123"
    obfuscated = obfuscate(test_data)
    deobfuscated = deobfuscate(obfuscated)
    
    assert deobfuscated == test_data, f"Round-trip failed: {test_data} != {deobfuscated}"
    print("  ✓ Obfuscation round-trip successful")


def test_dev_credentials():
    """Test developer credential retrieval."""
    print("\nTesting developer credentials...")
    from curateur.api.credentials import get_dev_credentials
    
    creds = get_dev_credentials()
    required_keys = ['devid', 'devpassword', 'softname']
    
    assert all(key in creds for key in required_keys), \
        f"Missing keys in credentials: {creds.keys()}"
    print(f"  ✓ Credentials retrieved: softname={creds['softname']}")


def test_system_map():
    """Test platform to systemeid mapping."""
    print("\nTesting system map...")
    from curateur.api.system_map import get_systemeid
    
    test_cases = [
        ('nes', 3),
        ('snes', 4),
        ('psx', 57),
        ('genesis', 1),
    ]
    
    for platform, expected_id in test_cases:
        systemeid = get_systemeid(platform)
        assert systemeid == expected_id, \
            f"{platform}: expected {expected_id}, got {systemeid}"
        print(f"  ✓ {platform} -> {systemeid}")


def test_es_systems():
    """Test ES systems parsing."""
    print("\nTesting ES systems parser...")
    from curateur.config.es_systems import parse_es_systems
    
    test_file = Path(__file__).parent.parent / 'fixtures' / 'es_systems.xml'
    
    assert test_file.exists(), f"Test file not found: {test_file}"
    
    systems = parse_es_systems(test_file)
    assert len(systems) >= 3, f"Expected at least 3 systems, got {len(systems)}"
    print(f"  ✓ Parsed {len(systems)} systems")
    for system in systems:
        print(f"    - {system.name} ({system.platform})")


def test_config_loading():
    """Test configuration loading."""
    print("\nTesting config loading...")
    from curateur.config.loader import load_config
    from curateur.config.validator import validate_config
    
    test_file = Path(__file__).parent.parent / 'fixtures' / 'test_config.yaml'
    
    assert test_file.exists(), f"Test config not found: {test_file}"
    
    config = load_config(test_file)
    print("  ✓ Config loaded")
    
    validate_config(config)
    print("  ✓ Config validated")
    
    # Check dev credentials were injected
    assert 'devid' in config['screenscraper'], "Dev credentials not injected"
    print("  ✓ Dev credentials injected")


def main():
    """Run all integration tests."""
    print("=" * 60)
    print("curateur MVP Phase 1 - Integration Test")
    print("=" * 60)
    
    tests = [
        test_imports,
        test_obfuscation,
        test_dev_credentials,
        test_system_map,
        test_es_systems,
        test_config_loading,
    ]
    
    failed = 0
    for test in tests:
        try:
            test()
        except Exception as e:
            print(f"  ✗ Test failed: {e}")
            failed += 1
    
    print("\n" + "=" * 60)
    passed = len(tests) - failed
    total = len(tests)
    print(f"Results: {passed}/{total} tests passed")
    
    if failed == 0:
        print("✓ Phase 1 integration test PASSED")
        print("=" * 60)
        return 0
    else:
        print("✗ Phase 1 integration test FAILED")
        print("=" * 60)
        return 1


if __name__ == '__main__':
    sys.exit(main())
