"""Command-line interface for curateur."""

import sys
import logging
import argparse
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

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
    
    # Phase D: Initialize connection pool manager
    from curateur.api.connection_pool import ConnectionPoolManager
    conn_manager = ConnectionPoolManager(config)
    session = conn_manager.get_session(max_connections=10)
    
    # Phase E: Validate API configuration
    max_retries = config.get('api', {}).get('max_retries', 3)
    if not isinstance(max_retries, int) or max_retries < 1 or max_retries > 10:
        logger.warning(f"Invalid api.max_retries value: {max_retries}, using default: 3")
        max_retries = 3
    
    # Phase E: Initialize ThrottleManager
    from curateur.api.throttle import ThrottleManager, RateLimit
    
    # Get requests per minute from config (optional override)
    config_rpm = config.get('api', {}).get('requests_per_minute')
    
    # Initialize with a default rate limit (will be updated from API response)
    default_rpm = 120  # Conservative default
    if config_rpm and isinstance(config_rpm, int) and 1 <= config_rpm <= 300:
        default_rpm = config_rpm
        logger.info(f"Using configured requests_per_minute: {default_rpm}")
    
    throttle_manager = ThrottleManager(
        default_limit=RateLimit(calls=default_rpm, window_seconds=60),
        adaptive=True
    )
    
    # Phase E: Initialize WorkQueueManager
    from curateur.workflow.work_queue import WorkQueueManager
    work_queue = WorkQueueManager(max_retries=max_retries)
    
    # Initialize API client with throttle_manager
    api_client = ScreenScraperClient(config, throttle_manager=throttle_manager, session=session)
    
    # Phase D: Initialize thread pool manager and get API limits
    from curateur.workflow.thread_pool import ThreadPoolManager
    thread_manager = ThreadPoolManager(config)
    
    # Authenticate and get API limits for thread pool initialization
    try:
        # Get rate limits from API (first API call initializes them)
        api_limits = api_client.get_rate_limits()
        thread_manager.initialize_pools(api_limits)
    except Exception as e:
        logger.warning(f"Could not initialize thread pools from API: {e}")
        thread_manager.initialize_pools(None)  # Use defaults
    
    # Phase D: Count total ROMs for performance monitor
    total_roms = 0
    for system in systems:
        try:
            from curateur.scanner.rom_scanner import scan_system
            rom_entries = scan_system(
                system,
                rom_root=Path(config['paths']['roms']).expanduser(),
                crc_size_limit=1073741824
            )
            total_roms += len(rom_entries)
        except Exception:
            pass  # Continue counting other systems
    
    # Phase D: Initialize performance monitor
    from curateur.workflow.performance import PerformanceMonitor
    performance_monitor = PerformanceMonitor(total_roms=total_roms) if total_roms > 0 else None
    
    # Phase D: Initialize console UI (optional, based on TTY)
    from curateur.ui.console_ui import ConsoleUI
    console_ui = None
    if sys.stdout.isatty() and not config['runtime'].get('dry_run', False):
        try:
            console_ui = ConsoleUI(config)
            console_ui.start()
        except Exception as e:
            logger.warning(f"Could not initialize console UI: {e}")
    
    # Get search configuration (with defaults)
    search_config = config.get('search', {})
    
    # Initialize orchestrator with Phase D & E components
    orchestrator = WorkflowOrchestrator(
        api_client=api_client,
        rom_directory=Path(config['paths']['roms']).expanduser(),
        media_directory=Path(config['paths']['media']).expanduser(),
        gamelist_directory=Path(config['paths']['gamelists']).expanduser(),
        work_queue=work_queue,
        dry_run=config['runtime'].get('dry_run', False),
        enable_search_fallback=search_config.get('enable_search_fallback', False),
        search_confidence_threshold=search_config.get('confidence_threshold', 0.7),
        search_max_results=search_config.get('max_results', 5),
        interactive_search=search_config.get('interactive_search', False),
        preferred_regions=config['scraping'].get('preferred_regions', ['us', 'wor', 'eu']),
        thread_manager=thread_manager,
        performance_monitor=performance_monitor,
        console_ui=console_ui
    )
    
    progress = ProgressTracker()
    error_logger = ErrorLogger()
    
    # Print header (unless using console UI)
    if not console_ui:
        print(f"\ncurateur v{__version__}")
        print(f"{'='*60}")
        print(f"Mode: {'DRY-RUN (no downloads)' if config['runtime'].get('dry_run') else 'Full scraping'}")
        print(f"Systems: {len(systems)}")
        if search_config.get('enable_search_fallback'):
            print(f"Search fallback: ENABLED (threshold: {search_config.get('confidence_threshold', 0.7):.1%})")
            if search_config.get('interactive_search'):
                print(f"Interactive mode: ENABLED")
        if thread_manager and thread_manager.max_threads > 1:
            print(f"Parallel processing: {thread_manager.max_threads} threads")
        print(f"{'='*60}\n")
    
    # Process each system
    try:
        for system in systems:
            try:
                # Update UI header
                if console_ui:
                    console_ui.update_header(
                        system_name=system.name,
                        system_num=systems.index(system) + 1,
                        total_systems=len(systems)
                    )
                
                result = orchestrator.scrape_system(
                    system=system,
                    media_types=config['scraping'].get('media_types', ['box-2D', 'ss']),
                    preferred_regions=config['scraping'].get('preferred_regions', ['us', 'wor', 'eu']),
                    progress_tracker=progress
                )
                
                # Log each ROM result (if not using console UI)
                if not console_ui:
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
    finally:
        # Phase D & E: Clean up resources and log work queue state
        if console_ui:
            console_ui.stop()
        
        # Log work queue state on interrupt
        if work_queue:
            queue_stats = work_queue.get_stats()
            failed_items = work_queue.get_failed_items()
            
            if queue_stats['pending'] > 0:
                logger.warning(f"Work queue has {queue_stats['pending']} pending items")
            
            if failed_items:
                logger.warning(f"Work queue has {len(failed_items)} failed items (retries exhausted):")
                for item in failed_items[:10]:  # Log first 10
                    logger.warning(f"  - {item['rom_info'].get('filename', 'unknown')}: {item['error']}")
        
        if thread_manager:
            thread_manager.shutdown(wait=True)
        
        if conn_manager:
            conn_manager.close_session()
        
        # Reset throttle manager state
        if throttle_manager:
            throttle_manager.reset()
    
    # Print final summary (unless using console UI)
    if not console_ui:
        progress.print_final_summary()
        
        # Print performance summary if available
        if performance_monitor:
            summary = performance_monitor.get_summary()
            print(f"\nPerformance Summary:")
            print(f"  Total time: {summary['elapsed_seconds']:.1f}s")
            print(f"  ROMs/second: {summary['avg_roms_per_second']:.2f}")
            print(f"  API calls: {summary['total_api_calls']}")
            print(f"  Downloads: {summary['total_downloads']}")
            print(f"  Peak memory: {summary['peak_memory_mb']:.1f} MB")
        
        # Print work queue statistics
        if work_queue:
            queue_stats = work_queue.get_stats()
            failed_items = work_queue.get_failed_items()
            
            print(f"\nWork Queue Statistics:")
            print(f"  Processed: {queue_stats['processed']}")
            print(f"  Failed (retries exhausted): {queue_stats['failed']}")
            print(f"  Max retries per item: {queue_stats['max_retries']}")
            
            # Calculate total retry attempts
            total_retries = sum(item['retry_count'] for item in failed_items)
            print(f"  Total retry attempts: {total_retries}")
            
            if failed_items:
                print(f"\n  Failed Items:")
                for item in failed_items[:10]:  # Show first 10
                    rom_name = item['rom_info'].get('filename', 'unknown')
                    action = item['action']
                    retry_count = item['retry_count']
                    error = item['error']
                    print(f"    - {rom_name} ({action}): {retry_count} retries - {error}")
                
                if len(failed_items) > 10:
                    print(f"    ... and {len(failed_items) - 10} more")
        
        # Print throttle statistics
        if throttle_manager and api_client:
            from curateur.api.client import APIEndpoint
            
            print(f"\nThrottle Manager Statistics:")
            total_wait_time = 0.0
            max_backoff_multiplier = 1
            backoff_events = 0
            
            for endpoint in APIEndpoint:
                stats = throttle_manager.get_stats(endpoint.value)
                
                # Estimate wait time from backoff
                if stats['backoff_remaining'] > 0:
                    total_wait_time += stats['backoff_remaining']
                
                if stats['consecutive_429s'] > 0:
                    backoff_events += stats['consecutive_429s']
                
                if stats['backoff_multiplier'] > max_backoff_multiplier:
                    max_backoff_multiplier = stats['backoff_multiplier']
                
                print(f"  {endpoint.value}:")
                print(f"    Recent calls: {stats['recent_calls']}/{stats['limit']}")
                print(f"    Backoff multiplier: {stats['backoff_multiplier']}x")
                print(f"    Consecutive 429s: {stats['consecutive_429s']}")
                if stats['in_backoff']:
                    print(f"    In backoff: {stats['backoff_remaining']:.1f}s remaining")
            
            print(f"  Summary:")
            print(f"    Total backoff events: {backoff_events}")
            print(f"    Max backoff multiplier reached: {max_backoff_multiplier}x")
    
    # Write error log if needed
    if error_logger.has_errors():
        error_logger.write_summary('scraping_errors.log')
    
    return 0


if __name__ == '__main__':
    sys.exit(main())
