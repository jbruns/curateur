"""Command-line interface for curateur."""

import sys
import logging
import argparse
import asyncio
import httpx
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
from curateur.ui.event_bus import EventBus
from curateur.ui.textual_ui import CurateurUI


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

    parser.add_argument(
        '--clear-cache',
        action='store_true',
        help='Clear metadata cache before scraping. Forces fresh API queries.'
    )

    parser.add_argument(
        '--ui',
        choices=['textual', 'headless'],
        default='textual',
        help='UI mode: textual (interactive TUI, default) or headless (minimal logging for CI/automation)'
    )

    return parser


def _setup_logging(config: dict, console_ui=None, textual_ui=None, event_bus=None) -> None:
    """
    Setup logging configuration from config.

    Args:
        config: Configuration dictionary
        console_ui: Unused parameter (kept for API compatibility)
        textual_ui: Optional CurateurUI instance for Textual UI
        event_bus: Optional EventBus instance for Textual UI logging
    """
    logging_config = config.get('logging', {})

    # Get log level
    level_str = logging_config.get('level', 'INFO').upper()
    level = getattr(logging, level_str, logging.INFO)

    # Configure root logger
    handlers = []

    # Console handler for headless mode only
    # Disable console output when Textual UI is active (it has its own display)
    if logging_config.get('console', True) and not textual_ui:
        # Use simple StreamHandler for headless mode
        console_handler = logging.StreamHandler()
        console_handler.setLevel(level)
        # Simple format for headless CI/automation
        formatter = logging.Formatter('%(levelname)s: %(message)s')
        console_handler.setFormatter(formatter)
        handlers.append(console_handler)

    # Textual UI handler - use EventLogHandler to send logs to event bus
    if textual_ui and event_bus:
        from curateur.ui.event_log_handler import EventLogHandler
        event_handler = EventLogHandler(event_bus, level=level)
        event_formatter = logging.Formatter('%(message)s')
        event_handler.setFormatter(event_formatter)
        handlers.append(event_handler)

    # File handler (if configured)
    log_file = logging_config.get('file')
    if log_file:
        try:
            log_path = Path(log_file)
            # Create parent directory if it doesn't exist
            log_path.parent.mkdir(parents=True, exist_ok=True)
            
            file_handler = logging.FileHandler(log_file)
            file_handler.setLevel(level)
            formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
            file_handler.setFormatter(formatter)
            handlers.append(file_handler)
        except (OSError, PermissionError) as e:
            print(f"Error: Could not create log file '{log_file}': {e}", file=sys.stderr)
            sys.exit(1)

    # Configure root logger
    logging.basicConfig(
        level=level,
        handlers=handlers,
        force=True  # Override any existing configuration
    )

    # Suppress httpx debug logging to prevent credential leakage in URLs
    # httpx logs full URLs at DEBUG level which would expose API credentials
    httpx_logger = logging.getLogger('httpx')
    httpx_logger.setLevel(logging.WARNING)  # Only show warnings and errors

    # Also suppress httpcore (underlying transport layer)
    httpcore_logger = logging.getLogger('httpcore')
    httpcore_logger.setLevel(logging.WARNING)

    # Suppress PIL/Pillow debug logging (verbose chunk parsing messages)
    pil_logger = logging.getLogger('PIL')
    pil_logger.setLevel(logging.INFO)  # Only show info and above


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

    # Setup initial logging from config (will be reconfigured if UI is enabled)
    # Note: We'll reconfigure this after UI initialization
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

    # Run main scraping workflow
    try:
        return asyncio.run(run_scraper(config, args))
    except KeyboardInterrupt:
        print("\n\nScraping interrupted by user.", file=sys.stderr)
        return 130
    except Exception as e:
        print(f"\nFatal error: {e}", file=sys.stderr)
        return 1


async def run_scraper(config: dict, args: argparse.Namespace) -> int:
    """
    Run the main scraping workflow (async).

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

    # Phase D: Create connection pool manager
    from curateur.api.connection_pool import ConnectionPoolManager

    pool_manager = ConnectionPoolManager(config)

    # Create initial client with conservative pool size (will be updated after auth)
    client = pool_manager.create_client(max_connections=10)
    logger.debug(f"HTTP connection pool created (initial size: 10, will scale after authentication)")

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

    # Initialize EventBus for UI events
    # Note: Events are emitted by orchestrator/API client/media downloader
    # For console UI mode, events are emitted but not displayed
    # For Textual UI mode (standalone), events drive the UI updates
    event_bus = EventBus()

    # Initialize API client with throttle_manager and event_bus
    api_client = ScreenScraperClient(
        config,
        throttle_manager=throttle_manager,
        client=client,
        connection_pool_manager=pool_manager,
        event_bus=event_bus
    )

    # Phase D: Initialize UI based on mode
    from curateur.ui.headless_logger import HeadlessLogger
    textual_ui = None
    textual_ui_task = None
    headless_logger = None

    if sys.stdout.isatty() and not config['runtime'].get('dry_run', False):
        if args.ui == 'textual':
            # Textual UI mode - initialize and start immediately
            try:
                textual_ui = CurateurUI(config, event_bus)
                logger.debug("Textual UI initialized successfully")

                # Reconfigure logging to use EventLogHandler for Textual UI
                _setup_logging(config, textual_ui=textual_ui, event_bus=event_bus)
                logger.debug("Logging reconfigured for Textual UI")

                # Start Textual UI in background task immediately
                logger.info("Starting Textual UI in background task...")
                textual_ui_task = asyncio.create_task(textual_ui.run_async())
                # Give UI a moment to initialize
                await asyncio.sleep(0.5)
                logger.debug("Textual UI task created and running")
            except Exception as e:
                logger.error(f"Could not initialize Textual UI: {e}", exc_info=True)
                print(f"Error: Failed to initialize Textual UI: {e}", file=sys.stderr)
                return 1
        else:
            # Headless mode - minimal console logging
            headless_logger = HeadlessLogger(config)
            headless_logger.start()
            _setup_logging(config)  # Simple logging for headless
            logger.debug("Headless logger initialized")
    else:
        # Non-TTY or dry-run: force headless mode
        headless_logger = HeadlessLogger(config)
        headless_logger.start()
        _setup_logging(config)
        logger.debug("Headless logger initialized (non-TTY)")


    # Phase E: Initialize thread pool manager
    from curateur.workflow.thread_pool import ThreadPoolManager
    thread_manager = ThreadPoolManager(config, console_ui=headless_logger, textual_ui=textual_ui)

    # Authenticate with ScreenScraper and get user limits
    logger.debug("Starting authentication")

    # Emit authentication started event
    from curateur.ui.events import AuthenticationEvent
    if event_bus:
        await event_bus.publish(AuthenticationEvent(status='authenticating', username=None))

    try:
        logger.debug("Calling api_client.get_user_info()")
        user_limits = await api_client.get_user_info()
        logger.debug(f"Authentication successful: {user_limits}")

        # Emit authentication success event
        if event_bus:
            await event_bus.publish(AuthenticationEvent(
                status='authenticated',
                username=user_limits.get('id')
            ))

        # Initialize throttle manager with initial quota values from authentication
        await api_client.throttle_manager.update_quota(user_limits)
        logger.debug(f"Throttle manager initialized with quota: {user_limits.get('requeststoday', 0)}/{user_limits.get('maxrequestsperday', 0)}")

        # Initialize thread pool with actual API limits
        thread_manager.initialize_pools(user_limits)
        logger.debug(f"Thread pool initialized with {thread_manager.max_concurrent} concurrent tasks")

        # Scale connection pool to match concurrency limitlimit
        if 'maxthreads' in user_limits:
            max_concurrent = user_limits['maxthreads']
            # Close old client and create new one with scaled pool
            await client.aclose()
            pool_size = max_concurrent + 1 if max_concurrent >= 1 else max_concurrent
            client = pool_manager.create_client(max_connections=pool_size)
            api_client.client = client  # Update API client's reference
            logger.info(f"Scaled connection pool to {pool_size} connections (aligned to API concurrency limit)")

        # Update throttle manager concurrency limit to match API maxthreads
        if 'maxthreads' in user_limits:
            throttle_manager.update_concurrency_limit(user_limits['maxthreads'])

        # Update throttle manager with initial quota
        await throttle_manager.update_quota(user_limits)

    except SystemExit:
        # Authentication failed - exit already logged
        raise
    except Exception as e:
        logger.error(f"Unexpected error during authentication: {e}")
        raise SystemExit(1)

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

    # Get search configuration (with defaults)
    search_config = config.get('search', {})

    # Initialize orchestrator with Phase D & E components
    orchestrator = WorkflowOrchestrator(
        api_client=api_client,
        rom_directory=Path(config['paths']['roms']).expanduser(),
        media_directory=Path(config['paths']['media']).expanduser(),
        gamelist_directory=Path(config['paths']['gamelists']).expanduser(),
        work_queue=work_queue,
        config=config,
        dry_run=config['runtime'].get('dry_run', False),
        enable_search_fallback=search_config.get('enable_search_fallback', False),
        search_confidence_threshold=search_config.get('confidence_threshold', 0.7),
        search_max_results=search_config.get('max_results', 5),
        interactive_search=search_config.get('interactive_search', False),
        preferred_regions=config['scraping'].get('preferred_regions', ['us', 'wor', 'eu']),
        thread_manager=thread_manager,
        performance_monitor=performance_monitor,
        throttle_manager=throttle_manager,
        clear_cache=args.clear_cache,
        event_bus=event_bus,
        textual_ui=textual_ui
    )

    # Connect orchestrator to Textual UI for search response handling
    if textual_ui:
        textual_ui.orchestrator = orchestrator
        from curateur.ui.events import SearchResponseEvent
        event_bus.subscribe(SearchResponseEvent, orchestrator.handle_search_response)

    progress = ProgressTracker()
    error_logger = ErrorLogger()

    # Print header in headless mode only
    if headless_logger and not textual_ui:
        print(f"\ncurateur v{__version__}")
        print(f"{'='*60}")
        print(f"Mode: {'DRY-RUN (no downloads)' if config['runtime'].get('dry_run') else 'Full scraping'}")
        print(f"Systems: {len(systems)}")
        if search_config.get('enable_search_fallback'):
            print(f"Search fallback: ENABLED (threshold: {search_config.get('confidence_threshold', 0.7):.1%})")
            if search_config.get('interactive_search'):
                print(f"Interactive mode: ENABLED")
        if thread_manager and thread_manager.max_concurrent > 1:
            print(f"Parallel processing: {thread_manager.max_concurrent} threads")
        print(f"{'='*60}\n")

    # Process each system
    try:
        # Convert ES-DE directory names to ScreenScraper media types
        from curateur.media.media_types import convert_directory_names_to_media_types
        configured_media = config['media'].get('media_types', ['covers', 'screenshots'])
        media_types_to_scrape = convert_directory_names_to_media_types(configured_media)

        # Fallback to defaults if no valid media types
        if not media_types_to_scrape:
            media_types_to_scrape = ['box-2D', 'ss']

        for system in systems:
            try:
                # Check for quit request from Textual UI
                if textual_ui and textual_ui.should_quit:
                    logger.info("Quit requested from Textual UI - graceful shutdown")
                    # Stop workers gracefully
                    if thread_manager:
                        await thread_manager.stop_workers()
                    break

                # Check for skip request from Textual UI
                if textual_ui and textual_ui.should_skip_system:
                    logger.info(f"Skip system requested from Textual UI: {system.name}")
                    textual_ui.should_skip_system = False  # Reset flag for next system
                    progress.finish_system()
                    continue

                result = await orchestrator.scrape_system(
                    system=system,
                    media_types=media_types_to_scrape,
                    preferred_regions=config['scraping'].get('preferred_regions', ['us', 'wor', 'eu']),
                    progress_tracker=progress,
                    current_system_index=systems.index(system),
                    total_systems=len(systems)
                )

                # Log each ROM result in headless mode only
                if headless_logger and not textual_ui:
                    for rom_result in result.results:
                        if rom_result.success:
                            media_info = (
                                f"{rom_result.media_downloaded} media files"
                                if rom_result.media_downloaded > 0
                                else "no media"
                            )
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

                # Pass stats when using Textual UI (since log_rom isn't called)
                if textual_ui:
                    progress.finish_system(
                        succeeded=result.scraped,
                        failed=result.failed,
                        skipped=result.skipped
                    )
                else:
                    progress.finish_system()

            except KeyboardInterrupt:
                logger.info("Interrupted by user, stopping pipeline tasks gracefully...")
                if thread_manager:
                    await thread_manager.stop_workers()

                # Log work queue state before UI shutdown
                if work_queue:
                    queue_stats = work_queue.get_stats()
                    failed_items = work_queue.get_failed_items()

                    if queue_stats['pending'] > 0:
                        logger.warning(f"Work queue has {queue_stats['pending']} pending items")

                    if failed_items:
                        logger.warning(f"Work queue has {len(failed_items)} failed items (retries exhausted):")
                        for item in failed_items[:10]:  # Log first 10
                            logger.warning(f"  - {item['rom_info'].get('filename', 'unknown')}: {item['error']}")

                raise
            except Exception as e:
                logger.error(f"Error processing system {system.fullname}: {e}", exc_info=True)
                print(f"\nError processing system {system.fullname}: {e}")
                progress.finish_system()
                continue
    finally:
        # Phase D & E: Clean up resources
        
        # Stop Textual UI first if running
        if textual_ui_task and not textual_ui_task.done():
            logger.info("Shutting down Textual UI...")
            logger.debug(f"UI task state: done={textual_ui_task.done()}, cancelled={textual_ui_task.cancelled()}")
            try:
                # Call shutdown which will call exit()
                await textual_ui.shutdown()
                logger.debug("Shutdown method completed, waiting for UI task to finish...")
                
                # Wait for the UI task to complete (exit should have been called)
                # Give it a reasonable timeout to exit gracefully
                try:
                    await asyncio.wait_for(textual_ui_task, timeout=2.0)
                    logger.debug("UI task completed successfully")
                except asyncio.TimeoutError:
                    logger.warning("UI task did not complete within timeout, forcing cancellation")
                    textual_ui_task.cancel()
                    try:
                        await textual_ui_task
                    except asyncio.CancelledError:
                        logger.debug("UI task cancelled")
            except Exception as e:
                logger.warning(f"Error during Textual UI shutdown: {e}")
                logger.debug("Exception details:", exc_info=True)
        
        # Reconfigure logging to console after UI shutdown
        if textual_ui:
            _setup_logging(config)
            logger.info("Textual UI has shut down successfully")
            print("\n" + "="*60)
            print("curateur: shutting down remaining resources...")
            print("="*60)
        
        # Shutdown thread manager
        if thread_manager:
            print("Stopping worker threads...")
            await thread_manager.shutdown(wait=True)
            print("Worker threads stopped")

        # Close HTTP client
        if client:
            print("Closing HTTP connections...")
            await client.aclose()
            print("HTTP connections closed")

        # Reset throttle manager state
        if throttle_manager:
            throttle_manager.reset()

        # Stop headless logger if active
        if headless_logger:
            headless_logger.stop()
        
        if textual_ui:
            print("Shutdown complete")
            print("="*60 + "\n")

    # Print final summary in headless mode only
    if headless_logger and not textual_ui:
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
