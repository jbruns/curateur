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
    try:
        from curateur import __version__
        from curateur.api.obfuscator import obfuscate, deobfuscate
        from curateur.api.credentials import get_dev_credentials
        from curateur.api.system_map import get_systemeid, PLATFORM_SYSTEMEID_MAP
        from curateur.config.loader import load_config
        from curateur.config.validator import validate_config
        from curateur.config.es_systems import parse_es_systems, SystemDefinition
        print("  ✓ All imports successful")
        return True
    except ImportError as e:
        print(f"  ✗ Import failed: {e}")
        return False


def test_obfuscation():
    """Test credential obfuscation."""
    print("\nTesting credential obfuscation...")
    from curateur.api.obfuscator import obfuscate, deobfuscate
    
    test_data = "sensitive_credential_123"
    obfuscated = obfuscate(test_data)
    deobfuscated = deobfuscate(obfuscated)
    
    if deobfuscated == test_data:
        print("  ✓ Obfuscation round-trip successful")
        return True
    else:
        print(f"  ✗ Round-trip failed: {test_data} != {deobfuscated}")
        return False


def test_dev_credentials():
    """Test developer credential retrieval."""
    print("\nTesting developer credentials...")
    from curateur.api.credentials import get_dev_credentials
    
    try:
        creds = get_dev_credentials()
        required_keys = ['devid', 'devpassword', 'softname']
        
        if all(key in creds for key in required_keys):
            print(f"  ✓ Credentials retrieved: softname={creds['softname']}")
            return True
        else:
            print(f"  ✗ Missing keys in credentials: {creds.keys()}")
            return False
    except Exception as e:
        print(f"  ✗ Failed to get credentials: {e}")
        return False


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
    
    all_pass = True
    for platform, expected_id in test_cases:
        try:
            systemeid = get_systemeid(platform)
            if systemeid == expected_id:
                print(f"  ✓ {platform} -> {systemeid}")
            else:
                print(f"  ✗ {platform}: expected {expected_id}, got {systemeid}")
                all_pass = False
        except Exception as e:
            print(f"  ✗ {platform}: {e}")
            all_pass = False
    
    return all_pass


def test_es_systems():
    """Test ES systems parsing."""
    print("\nTesting ES systems parser...")
    from curateur.config.es_systems import parse_es_systems
    
    test_file = Path(__file__).parent.parent / 'tests' / 'fixtures' / 'es_systems.xml'
    
    if not test_file.exists():
        print(f"  ✗ Test file not found: {test_file}")
        return False
    
    try:
        systems = parse_es_systems(test_file)
        if len(systems) >= 3:
            print(f"  ✓ Parsed {len(systems)} systems")
            for system in systems:
                print(f"    - {system.name} ({system.platform})")
            return True
        else:
            print(f"  ✗ Expected at least 3 systems, got {len(systems)}")
            return False
    except Exception as e:
        print(f"  ✗ Failed to parse: {e}")
        return False


def test_config_loading():
    """Test configuration loading."""
    print("\nTesting config loading...")
    from curateur.config.loader import load_config
    from curateur.config.validator import validate_config
    
    test_file = Path(__file__).parent.parent / 'tests' / 'fixtures' / 'test_config.yaml'
    
    if not test_file.exists():
        print(f"  ✗ Test config not found: {test_file}")
        return False
    
    try:
        config = load_config(test_file)
        print("  ✓ Config loaded")
        
        validate_config(config)
        print("  ✓ Config validated")
        
        # Check dev credentials were injected
        if 'devid' in config['screenscraper']:
            print("  ✓ Dev credentials injected")
        else:
            print("  ✗ Dev credentials not injected")
            return False
        
        return True
    except Exception as e:
        print(f"  ✗ Failed: {e}")
        return False


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
    
    results = []
    for test in tests:
        results.append(test())
    
    print("\n" + "=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"Results: {passed}/{total} tests passed")
    
    if passed == total:
        print("✓ Phase 1 integration test PASSED")
        print("=" * 60)
        return 0
    else:
        print("✗ Phase 1 integration test FAILED")
        print("=" * 60)
        return 1


if __name__ == '__main__':
    sys.exit(main())
