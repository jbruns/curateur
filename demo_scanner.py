#!/usr/bin/env python3
"""
ROM Scanner Demonstration

Shows the scanner in action with fixture ROMs.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from curateur.config.es_systems import parse_es_systems
from curateur.scanner.rom_scanner import scan_system
from curateur.scanner.hash_calculator import format_file_size
from curateur.scanner.rom_types import ROMType


def main():
    """Demonstrate ROM scanner with all fixture systems."""
    
    print("=" * 70)
    print("ROM Scanner Demonstration")
    print("=" * 70)
    
    # Load systems
    es_systems_file = Path(__file__).parent / 'tests' / 'fixtures' / 'es_systems.xml'
    systems = parse_es_systems(es_systems_file)
    
    print(f"\nFound {len(systems)} systems in es_systems.xml")
    print()
    
    total_roms = 0
    
    # Scan each system
    for system in systems:
        print(f"System: {system.fullname} ({system.name})")
        print(f"  Platform: {system.platform}")
        print(f"  ROM Path: {system.path}")
        print(f"  Extensions: {', '.join(system.extensions)}")
        print(f"  M3U Support: {'Yes' if system.supports_m3u() else 'No'}")
        print()
        
        try:
            roms = scan_system(system, crc_size_limit=10*1024*1024)
            
            if not roms:
                print(f"  No ROMs found")
                print()
                continue
            
            print(f"  Found {len(roms)} ROM(s):")
            print()
            
            for rom in roms:
                total_roms += 1
                
                # ROM type icon
                type_icon = {
                    ROMType.STANDARD: "📦",
                    ROMType.M3U_PLAYLIST: "💿",
                    ROMType.DISC_SUBDIR: "📁"
                }.get(rom.rom_type, "❓")
                
                print(f"  {type_icon} {rom.filename}")
                print(f"     Type: {rom.rom_type.value}")
                print(f"     Size: {format_file_size(rom.file_size)}")
                
                if rom.crc32:
                    print(f"     CRC32: {rom.crc32}")
                else:
                    print(f"     CRC32: (not calculated - file too large)")
                
                # Type-specific details
                if rom.rom_type == ROMType.M3U_PLAYLIST:
                    print(f"     Disc 1: {rom.query_filename}")
                    print(f"     Total Discs: {len(rom.disc_files or [])}")
                    if rom.disc_files:
                        for i, disc in enumerate(rom.disc_files, 1):
                            print(f"       Disc {i}: {disc.name}")
                
                elif rom.rom_type == ROMType.DISC_SUBDIR:
                    print(f"     Contained File: {rom.query_filename}")
                
                print(f"     Gamelist Path: {rom.get_gamelist_path()}")
                print(f"     Media Basename: {rom.get_media_basename()}")
                print()
        
        except Exception as e:
            print(f"  ✗ Error scanning system: {e}")
            print()
    
    print("=" * 70)
    print(f"Total: {total_roms} ROMs across {len(systems)} systems")
    print("=" * 70)


if __name__ == '__main__':
    main()
