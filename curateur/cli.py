"""Command-line interface for curateur."""

import sys
import logging
import argparse
from pathlib import Path
from typing import Optional

from curateur import __version__
from curateur.config.loader import load_config, ConfigError
from curateur.config.validator import validate_config, ValidationError
from curateur.config.es_systems import parse_es_systems
from curateur.api.client import ScreenScraperClient
from curateur.workflow.orchestrator import WorkflowOrchestrator
from curateur.workflow.progress import ProgressTracker, ErrorLogger


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

  # Enable search fallback for unmatched ROMs
  curateur --enable-search

  # Interactive search with user prompts
  curateur --enable-search --interactive-search

  # Search with custom confidence threshold
  curateur --enable-search --search-threshold 0.8

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
    
    parser.add_argument(
        '--enable-search',
        action='store_true',
        help='Enable search fallback when hash lookup fails. Overrides config.'
    )
    
    parser.add_argument(
        '--search-threshold',
        type=float,
        metavar='SCORE',
        help='Minimum confidence score (0.0-1.0) to accept search match. Overrides config.'
    )
    
    parser.add_argument(
        '--interactive-search',
        action='store_true',
        help='Enable interactive prompts for selecting search matches. Overrides config.'
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


def _setup_logging(config: dict) -> None:
    """
    Setup logging configuration from config.
    
    Args:
        config: Configuration dictionary
    """
    logging_config = config.get('logging', {})
    
    # Get log level
    level_str = logging_config.get('level', 'INFO').upper()
    level = getattr(logging, level_str, logging.INFO)
    
    # Configure root logger
    handlers = []
    
    # Console handler
    if logging_config.get('console', True):
        console_handler = logging.StreamHandler(sys.stderr)
        console_handler.setLevel(level)
        formatter = logging.Formatter('%(levelname)s: %(message)s')
        console_handler.setFormatter(formatter)
        handlers.append(console_handler)
    
    # File handler (if configured)
    log_file = logging_config.get('file')
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        handlers.append(file_handler)
    
    # Configure root logger
    logging.basicConfig(
        level=level,
        handlers=handlers,
        force=True  # Override any existing configuration
    )


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
    
    # Setup logging from config
    _setup_logging(config)
    
    # Apply CLI overrides
    if args.systems:
        config['scraping']['systems'] = args.systems
    
    if args.dry_run:
        config['runtime']['dry_run'] = True
    
    if args.enable_search:
        if 'search' not in config:
            config['search'] = {}
        config['search']['enable_search_fallback'] = True
    
    if args.search_threshold is not None:
        if 'search' not in config:
            config['search'] = {}
        config['search']['confidence_threshold'] = args.search_threshold
    
    if args.interactive_search:
        if 'search' not in config:
            config['search'] = {}
        config['search']['interactive_search'] = True
    
    # Check for Milestone 2 flags
    if args.skip_scraped or args.update:
        print(
            "Warning: --skip-scraped and --update are Milestone 2 features "
            "and are not yet implemented.",
            file=sys.stderr
        )
    
    # Run main scraping workflow
    try:
        return run_scraper(config, args)
    except KeyboardInterrupt:
        print("\n\nScraping interrupted by user.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"\nFatal error: {e}", file=sys.stderr)
        return 1


def run_scraper(config: dict, args: argparse.Namespace) -> int:
    """
    Run the main scraping workflow.
    
    Args:
        config: Loaded configuration
        args: Parsed command-line arguments
        
    Returns:
        Exit code
    """
    # Parse es_systems.xml
    try:
        es_systems_path = Path(config['paths']['es_systems']).expanduser()
        all_systems = parse_es_systems(es_systems_path)
    except Exception as e:
        print(f"Error parsing es_systems.xml: {e}", file=sys.stderr)
        return 1
    
    # Filter systems if specified
    systems_to_scrape = config['scraping'].get('systems', [])
    if systems_to_scrape:
        systems = [s for s in all_systems if s.name in systems_to_scrape]
        if not systems:
            print(f"Error: No matching systems found for: {systems_to_scrape}", file=sys.stderr)
            return 1
    else:
        systems = all_systems
    
    # Initialize components
    api_client = ScreenScraperClient(config)
    
    # Get search configuration (with defaults)
    search_config = config.get('search', {})
    
    orchestrator = WorkflowOrchestrator(
        api_client=api_client,
        rom_directory=Path(config['paths']['roms']).expanduser(),
        media_directory=Path(config['paths']['media']).expanduser(),
        gamelist_directory=Path(config['paths']['gamelists']).expanduser(),
        dry_run=config['runtime'].get('dry_run', False),
        enable_search_fallback=search_config.get('enable_search_fallback', False),
        search_confidence_threshold=search_config.get('confidence_threshold', 0.7),
        search_max_results=search_config.get('max_results', 5),
        interactive_search=search_config.get('interactive_search', False),
        preferred_regions=config['scraping'].get('preferred_regions', ['us', 'wor', 'eu'])
    )
    
    progress = ProgressTracker()
    error_logger = ErrorLogger()
    
    # Print header
    print(f"\ncurateur v{__version__}")
    print(f"{'='*60}")
    print(f"Mode: {'DRY-RUN (no downloads)' if config['runtime'].get('dry_run') else 'Full scraping'}")
    print(f"Systems: {len(systems)}")
    if search_config.get('enable_search_fallback'):
        print(f"Search fallback: ENABLED (threshold: {search_config.get('confidence_threshold', 0.7):.1%})")
        if search_config.get('interactive_search'):
            print(f"Interactive mode: ENABLED")
    print(f"{'='*60}\n")
    
    # Process each system
    for system in systems:
        try:
            result = orchestrator.scrape_system(
                system=system,
                media_types=config['scraping'].get('media_types', ['box-2D', 'ss']),
                preferred_regions=config['scraping'].get('preferred_regions', ['us', 'wor', 'eu']),
                progress_tracker=progress
            )
            
            # Log each ROM result
            for rom_result in result.results:
                if rom_result.success:
                    media_info = f"{rom_result.media_downloaded} media files" if rom_result.media_downloaded > 0 else "no media"
                    progress.log_rom(
                        rom_result.rom_path.name,
                        'success',
                        media_info
                    )
                elif rom_result.error:
                    progress.log_rom(
                        rom_result.rom_path.name,
                        'failed',
                        rom_result.error
                    )
                    error_logger.log_error(rom_result.rom_path.name, rom_result.error)
                else:
                    progress.log_rom(
                        rom_result.rom_path.name,
                        'skipped',
                        ''
                    )
            
            progress.finish_system()
            
        except Exception as e:
            print(f"\nError processing system {system.fullname}: {e}")
            progress.finish_system()
            continue
    
    # Print final summary
    progress.print_final_summary()
    
    # Write error log if needed
    if error_logger.has_errors():
        error_logger.write_summary('scraping_errors.log')
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
