"""Command-line interface for curateur."""

import sys
import argparse
from pathlib import Path
from typing import Optional

from curateur import __version__
from curateur.config.loader import load_config, ConfigError
from curateur.config.validator import validate_config, ValidationError


def create_parser() -> argparse.ArgumentParser:
    """Create and configure argument parser."""
    parser = argparse.ArgumentParser(
        prog='curateur',
        description='ScreenScraper ROM Metadata & Media Scraper for ES-DE',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Scrape all systems using default config
  curateur

  # Scrape specific systems only
  curateur --systems nes snes genesis

  # Dry-run mode (no downloads)
  curateur --dry-run

  # Use custom config file
  curateur --config /path/to/config.yaml

For more information, see IMPLEMENTATION_PLAN.md
        """
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s {__version__}'
    )
    
    parser.add_argument(
        '--config',
        type=Path,
        metavar='PATH',
        help='Path to config.yaml (default: ./config.yaml)'
    )
    
    parser.add_argument(
        '--systems',
        nargs='+',
        metavar='SYSTEM',
        help='System short names to scrape (e.g., nes snes). Overrides config.'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Scan and query API without downloading media. Overrides config.'
    )
    
    # Milestone 2 flags (not yet implemented but documented)
    parser.add_argument(
        '--skip-scraped',
        action='store_true',
        help='[Milestone 2] Skip ROMs already in gamelist with complete metadata'
    )
    
    parser.add_argument(
        '--update',
        action='store_true',
        help='[Milestone 2] Re-scrape all ROMs and update metadata/media'
    )
    
    return parser


def main(argv: Optional[list] = None) -> int:
    """
    Main entry point for curateur CLI.
    
    Args:
        argv: Command-line arguments (default: sys.argv)
        
    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    parser = create_parser()
    args = parser.parse_args(argv)
    
    # Load and validate configuration
    try:
        config = load_config(args.config)
        validate_config(config)
    except (ConfigError, ValidationError) as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error loading config: {e}", file=sys.stderr)
        return 1
    
    # Apply CLI overrides
    if args.systems:
        config['scraping']['systems'] = args.systems
    
    if args.dry_run:
        config['runtime']['dry_run'] = True
    
    # Check for Milestone 2 flags
    if args.skip_scraped or args.update:
        print(
            "Warning: --skip-scraped and --update are Milestone 2 features "
            "and are not yet implemented.",
            file=sys.stderr
        )
    
    # TODO: Main scraping logic will go here
    print("curateur v{} - MVP Phase 1 (Configuration loaded successfully)".format(__version__))
    print(f"Config loaded from: {args.config or 'config.yaml'}")
    print(f"User: {config['screenscraper'].get('user_id', 'NOT SET')}")
    print(f"Developer credentials: {'✓ Configured' if config['screenscraper'].get('devid') else '✗ Missing'}")
    print(f"Systems to scrape: {config['scraping'].get('systems') or 'all'}")
    print(f"Dry-run mode: {config['runtime'].get('dry_run', False)}")
    print("\nNote: Full scraping implementation in progress...")
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
