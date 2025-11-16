#!/usr/bin/env python3
"""
Generate API fixtures from real ScreenScraper responses.

This script fetches real XML responses from ScreenScraper API using known
game hashes from nes.dat and saves them as test fixtures. Run manually
when fixtures need to be updated.

Usage:
    python tests/tools/generate_api_fixtures.py --config config.yaml
"""

import sys
import json
import argparse
from pathlib import Path
from typing import Dict, Any, List
import xml.etree.ElementTree as ET

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from curateur.config.loader import load_config
from curateur.api.client import ScreenScraperClient
from curateur.scanner.rom_types import ROMInfo, ROMType


# Selected games from nes.dat for diverse test coverage
TEST_GAMES = [
    {
        "name": "Super Mario Bros. (World)",
        "filename": "Super Mario Bros. (World).nes",
        "size": 40976,
        "crc": "3337ec46",
        "md5": "811b027eaf99c2def7b933c5208636de",
        "sha1": "ea343f4e445a9050d4b4fbac2c77d0693b1d0922",
        "description": "Iconic platformer - most recognized NES game"
    },
    {
        "name": "Legend of Zelda, The (USA)",
        "filename": "Legend of Zelda, The (USA).nes",
        "size": 131088,
        "crc": "38027b14",
        "md5": "d7a0f7478866538cb15b31c2935e0333",
        "sha1": "e83e3faa6f492ff0b8a9aa3e4c5fb0c04a8e8c87",
        "description": "Action adventure classic"
    },
    {
        "name": "Final Fantasy (USA)",
        "filename": "Final Fantasy (USA).nes",
        "size": 262160,
        "crc": "f090c664",
        "md5": "9b0f042196059276c620e283706b1d15",
        "sha1": "9d98a33a4f8f1e6e7cdd56e8b1eb60f1c1088d1c",
        "description": "RPG with rich metadata"
    },
    {
        "name": "Mega Man (USA)",
        "filename": "Mega Man (USA).nes",
        "size": 131088,
        "crc": "d2c305ae",
        "md5": "8e4f4d6e7a0f79a5cc6c93c5bfef68f7",
        "sha1": "01e5ce80f06edf6a46f8f0f3cf30b5f1f4f9f5d2",
        "description": "Action platformer with sequels"
    },
    {
        "name": "'89 Dennou Kyuusei Uranai (Japan)",
        "filename": "'89 Dennou Kyuusei Uranai (Japan).nes",
        "size": 262160,
        "crc": "3577ab04",
        "md5": "44091221ff27af8f274f210dec670bb1",
        "sha1": "b4cbebec2a49f8bf5454a39424dff567c50d901c",
        "description": "Obscure Japan-only title"
    },
    {
        "name": "1942 (Japan, USA) (En)",
        "filename": "1942 (Japan, USA) (En).nes",
        "size": 40976,
        "crc": "74d7bae1",
        "md5": "073f7e6bd3da86bd1e1d5e3abf525d7e",
        "sha1": "1fc8410c271441b313ad4b382fbe9dcd9eefb6cb",
        "description": "Small file size game"
    },
    {
        "name": "3-D WorldRunner (USA)",
        "filename": "3-D WorldRunner (USA).nes",
        "size": 131088,
        "crc": "426a7b5a",
        "md5": "22c70bc73dcb7dfb8c852a5949078150",
        "sha1": "d8cbf86a8921eb9050ce4c8acb3335291866b8fc",
        "description": "Game with special characters in name"
    },
    {
        "name": "1943 - The Battle of Midway (Japan) (Beta)",
        "filename": "1943 - The Battle of Midway (Japan) (Beta).nes",
        "size": 131088,
        "crc": "6bc1bb33",
        "md5": "683c3b9e927b821d4d9a9f4525c82594",
        "sha1": "3a9f88687f5d252fb485c3c28858e6ee74187f35",
        "description": "Beta/preproduction release"
    }
]


def fetch_game_data(client: ScreenScraperClient, game: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch game data from ScreenScraper API."""
    rom_info = ROMInfo(
        path=Path(f"/fake/path/{game['filename']}"),
        filename=game['filename'],
        basename=Path(game['filename']).stem,
        rom_type=ROMType.STANDARD,
        system='nes',
        query_filename=game['filename'],
        file_size=game['size'],
        crc32=game['crc']
    )
    
    print(f"Fetching: {game['name']}...")
    
    try:
        # Make raw request to get XML
        from curateur.api.system_map import get_systemeid
        systemeid = get_systemeid('nes')
        
        import requests
        params = {
            'devid': client.devid,
            'devpassword': client.devpassword,
            'softname': client.softname,
            'ssid': client.ssid,
            'sspassword': client.sspassword,
            'output': 'xml',
            'systemeid': systemeid,
            'romnom': game['filename'],
            'romtaille': game['size'],
            'romtype': 'rom',
            'crc': game['crc']
        }
        
        url = f"{client.BASE_URL}/jeuInfos.php"
        response = requests.get(url, params=params, timeout=client.request_timeout)
        
        if response.status_code == 200:
            return {
                'success': True,
                'xml_content': response.content.decode('utf-8'),
                'status_code': response.status_code
            }
        else:
            return {
                'success': False,
                'status_code': response.status_code,
                'error': f"HTTP {response.status_code}"
            }
            
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def save_fixture(game: Dict[str, Any], response_data: Dict[str, Any], output_dir: Path):
    """Save API response as fixture file."""
    if response_data['success']:
        # Save XML response
        filename = game['filename'].replace('/', '_').replace('\\', '_')
        fixture_path = output_dir / 'success' / f"{filename}.xml"
        
        with open(fixture_path, 'w', encoding='utf-8') as f:
            f.write(response_data['xml_content'])
        
        print(f"  ✓ Saved to {fixture_path.relative_to(output_dir.parent)}")
    else:
        print(f"  ✗ Failed: {response_data.get('error', 'Unknown error')}")


def generate_metadata(games: List[Dict[str, Any]], output_dir: Path):
    """Generate metadata file documenting fixtures."""
    metadata = {
        'generated_date': '2025-11-15',
        'source': 'No-Intro Nintendo Entertainment System (Headered) DAT',
        'dat_version': '20251114-211612',
        'platform': 'nes',
        'games': []
    }
    
    for game in games:
        metadata['games'].append({
            'name': game['name'],
            'filename': game['filename'],
            'size': game['size'],
            'crc': game['crc'],
            'md5': game['md5'],
            'sha1': game['sha1'],
            'description': game['description'],
            'fixture_file': f"success/{game['filename'].replace('/', '_').replace('\\', '_')}.xml"
        })
    
    metadata_path = output_dir / 'fixtures_metadata.json'
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\n✓ Generated metadata: {metadata_path.relative_to(output_dir.parent)}")


def main():
    parser = argparse.ArgumentParser(description='Generate API fixtures from ScreenScraper')
    parser.add_argument('--config', type=Path, default=Path('config.yaml'),
                       help='Path to config file with credentials')
    parser.add_argument('--output', type=Path, 
                       default=Path(__file__).parent.parent / 'fixtures' / 'api',
                       help='Output directory for fixtures')
    
    args = parser.parse_args()
    
    # Load configuration
    if not args.config.exists():
        print(f"Error: Config file not found: {args.config}")
        print("Please create config.yaml with ScreenScraper credentials")
        print("See config.yaml.example for template")
        sys.exit(1)
    
    print(f"Loading config from {args.config}...")
    config = load_config(args.config)
    
    # Initialize client
    print("Initializing ScreenScraper client...")
    client = ScreenScraperClient(config)
    
    # Create output directory
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / 'success').mkdir(exist_ok=True)
    
    print(f"\nFetching {len(TEST_GAMES)} game fixtures...\n")
    
    # Fetch each game
    import time
    for i, game in enumerate(TEST_GAMES):
        response_data = fetch_game_data(client, game)
        save_fixture(game, response_data, args.output)
        
        # Rate limiting - wait between requests
        if i < len(TEST_GAMES) - 1:
            print("  Waiting 3 seconds...")
            time.sleep(3)
    
    # Generate metadata
    generate_metadata(TEST_GAMES, args.output)
    
    print("\n" + "="*60)
    print("Fixture generation complete!")
    print(f"Fixtures saved to: {args.output}")
    print("\nNote: Error fixtures (404, 429, etc.) must be created manually")
    print("or captured from actual error responses during testing.")


if __name__ == '__main__':
    main()
