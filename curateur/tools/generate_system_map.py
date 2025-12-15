#!/usr/bin/env python3
"""
System Map Generator Utility

This tool generates the PLATFORM_SYSTEMEID_MAP constant by matching
ES-DE platform identifiers with ScreenScraper system IDs.

Usage:
    python -m curateur.tools.generate_system_map \\
        --es-systems path/to/es_systems.xml \\
        --systemes-liste path/to/systemesListe.xml

The systemesListe.xml can be fetched from:
    https://api.screenscraper.fr/api2/systemesListe.php?devid=xxx&devpassword=yyy&softname=curateur_1.0.0&output=XML

This is a maintenance tool - run it when:
- ScreenScraper adds new systems
- es_systems.xml is updated with new platforms
- The mapping needs to be refreshed
"""

import sys
from pathlib import Path
from typing import Dict, List, Tuple
from lxml import etree

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def parse_es_systems(xml_path: Path) -> Dict[str, str]:
    """
    Parse es_systems.xml to extract platform -> fullname mapping.

    Returns:
        Dict mapping platform ID to fullname
    """
    tree = etree.parse(str(xml_path))
    root = tree.getroot()

    mapping = {}

    for system_elem in root.findall("system"):
        platform_elem = system_elem.find("platform")
        fullname_elem = system_elem.find("fullname")

        if platform_elem is None or fullname_elem is None:
            continue

        # Handle nested <name> in platformid
        name_elem = platform_elem.find("name")
        if name_elem is not None and name_elem.text:
            platform = name_elem.text.strip().lower()
        elif platform_elem.text:
            platform = platform_elem.text.strip().lower()
        else:
            continue

        fullname = fullname_elem.text.strip() if fullname_elem.text else None

        if platform and fullname:
            mapping[platform] = fullname

    return mapping


def parse_systemes_liste(xml_path: Path) -> Dict[int, List[str]]:
    """
    Parse systemesListe.xml to extract systemeid -> common names.

    Returns:
        Dict mapping system ID to list of common names
    """
    tree = etree.parse(str(xml_path))
    root = tree.getroot()

    mapping = {}

    for systeme_elem in root.findall(".//systeme"):
        id_elem = systeme_elem.find("id")
        noms_elem = systeme_elem.find(".//noms_commun")

        if id_elem is None or noms_elem is None:
            continue

        try:
            system_id = int(id_elem.text.strip())
        except (ValueError, AttributeError):
            continue

        if noms_elem.text:
            # Split comma-separated names
            names = [n.strip() for n in noms_elem.text.split(",") if n.strip()]
            mapping[system_id] = names

    return mapping


def match_systems(
    es_platforms: Dict[str, str], ss_systems: Dict[int, List[str]]
) -> Tuple[Dict[str, int], List[str], List[Tuple[str, List[int]]]]:
    """
    Match ES-DE platforms to ScreenScraper system IDs.

    Returns:
        Tuple of (matches, unmatched_platforms, ambiguous_matches)
    """
    matches = {}
    unmatched = []
    ambiguous = []

    for platform, fullname in es_platforms.items():
        fullname_lower = fullname.lower()
        potential_matches = []

        # Search for matches in ScreenScraper system names
        for system_id, names in ss_systems.items():
            for name in names:
                if fullname_lower == name.lower():
                    potential_matches.append(system_id)
                    break

        if len(potential_matches) == 1:
            matches[platform] = potential_matches[0]
        elif len(potential_matches) > 1:
            ambiguous.append((platform, potential_matches))
            # Use first match as default
            matches[platform] = potential_matches[0]
        else:
            unmatched.append(platform)

    return matches, unmatched, ambiguous


def generate_python_code(matches: Dict[str, int]) -> str:
    """Generate Python code for the mapping constant."""
    lines = ["PLATFORM_SYSTEMEID_MAP = {"]

    # Sort by platform name
    for platform in sorted(matches.keys()):
        system_id = matches[platform]
        lines.append(f"    '{platform}': {system_id},")

    lines.append("}")

    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate platform to systemeid mapping"
    )
    parser.add_argument(
        "--es-systems", required=True, type=Path, help="Path to es_systems.xml"
    )
    parser.add_argument(
        "--systemes-liste",
        required=True,
        type=Path,
        help="Path to systemesListe.xml from ScreenScraper API",
    )
    parser.add_argument(
        "--output", type=Path, help="Output file path (default: print to stdout)"
    )

    args = parser.parse_args()

    # Validate input files
    if not args.es_systems.exists():
        print(f"Error: {args.es_systems} not found", file=sys.stderr)
        sys.exit(1)

    if not args.systemes_liste.exists():
        print(f"Error: {args.systemes_liste} not found", file=sys.stderr)
        sys.exit(1)

    # Parse input files
    print("Parsing es_systems.xml...", file=sys.stderr)
    es_platforms = parse_es_systems(args.es_systems)
    print(f"  Found {len(es_platforms)} platforms", file=sys.stderr)

    print("Parsing systemesListe.xml...", file=sys.stderr)
    ss_systems = parse_systemes_liste(args.systemes_liste)
    print(f"  Found {len(ss_systems)} ScreenScraper systems", file=sys.stderr)

    # Match systems
    print("Matching platforms to system IDs...", file=sys.stderr)
    matches, unmatched, ambiguous = match_systems(es_platforms, ss_systems)
    print(f"  Matched: {len(matches)}", file=sys.stderr)
    print(f"  Unmatched: {len(unmatched)}", file=sys.stderr)
    print(f"  Ambiguous: {len(ambiguous)}", file=sys.stderr)

    # Report issues
    if unmatched:
        print("\nUnmatched platforms:", file=sys.stderr)
        for platform in sorted(unmatched):
            fullname = es_platforms[platform]
            print(f"  - {platform}: {fullname}", file=sys.stderr)

    if ambiguous:
        print("\nAmbiguous matches (using first):", file=sys.stderr)
        for platform, system_ids in ambiguous:
            print(f"  - {platform}: {system_ids}", file=sys.stderr)

    # Generate code
    code = generate_python_code(matches)

    if args.output:
        args.output.write_text(code)
        print(f"\nMapping written to {args.output}", file=sys.stderr)
    else:
        print("\n" + "=" * 60)
        print(code)
        print("=" * 60)


if __name__ == "__main__":
    main()
