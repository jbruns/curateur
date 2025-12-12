"""
Headless logger for CI/automation environments.

Provides minimal console output without interactive UI elements.
Implements the ConsoleUI interface for drop-in compatibility.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class HeadlessLogger:
    """
    Minimal logger for headless/CI environments.

    Implements the subset of ConsoleUI interface needed by orchestrator
    and thread_pool, but outputs minimal text logs instead of Rich UI.

    Output includes:
    - System start/finish with stats
    - High-level progress milestones
    - Errors only
    - Final summary

    Does NOT output:
    - Individual ROM progress
    - Real-time pipeline updates
    - Progress bars
    - Log panel/spotlight
    """

    def __init__(self, config: dict):
        """
        Initialize headless logger.

        Args:
            config: Configuration dictionary (for consistency with ConsoleUI)
        """
        self.config = config
        self.current_system = None
        self.current_system_index = 0
        self.total_systems = 0
        self.total_roms_in_system = 0
        self.processed_in_system = 0

        # Stats tracking
        self.stats = {
            'successful': 0,
            'failed': 0,
            'skipped': 0,
            'unmatched': 0,
            'search_fallback': 0
        }

        # Pause/quit state (always False for headless)
        self._is_paused = False
        self._quit_requested = False
        self._skip_requested = False

        # No-op handler reference for cleanup compatibility
        self.log_handler = None

    def start(self) -> None:
        """Start headless logger (no-op)."""
        logger.info("Running in headless mode (minimal output)")

    def stop(self) -> None:
        """Stop headless logger (no-op)."""
        pass

    # ========================================================================
    # Properties for pause/quit state
    # ========================================================================

    @property
    def is_paused(self) -> bool:
        """Check if paused (always False for headless)."""
        return self._is_paused

    @property
    def quit_requested(self) -> bool:
        """Check if quit requested (always False for headless)."""
        return self._quit_requested

    @property
    def skip_requested(self) -> bool:
        """Check if skip requested (always False for headless)."""
        return self._skip_requested

    # ========================================================================
    # System-level methods
    # ========================================================================

    def update_header(self, system_name: str, system_num: int, total_systems: int) -> None:
        """Log system start."""
        self.current_system = system_name
        self.current_system_index = system_num
        self.total_systems = total_systems
        self.processed_in_system = 0
        logger.info(f"Processing system {system_num}/{total_systems}: {system_name}")

    def reset_pipeline_stages(self) -> None:
        """Reset for new system (no-op)."""
        self.processed_in_system = 0

    def update_scanner(self, count: int) -> None:
        """Log ROM count."""
        self.total_roms_in_system = count
        logger.info(f"  Found {count} ROMs")

    def set_system_info(self, gamelist_exists: bool, existing_entries: int) -> None:
        """Log existing gamelist info."""
        if gamelist_exists:
            logger.info(f"  Existing gamelist: {existing_entries} entries")
        else:
            logger.info("  No existing gamelist")

    def set_integrity_score(self, score: float) -> None:
        """Log gamelist integrity score."""
        if score < 1.0:
            logger.warning(f"  Gamelist integrity: {score:.1%} (some inconsistencies)")
        else:
            logger.info(f"  Gamelist integrity: {score:.1%}")

    def display_system_operation(self, system_name: str, operation: str, details: str) -> None:
        """Log system-level operation."""
        logger.info(f"  {operation}: {details}")

    def set_system_operation(self, operation: str, details: str) -> None:
        """Log system operation (alternative signature)."""
        logger.info(f"  {operation}: {details}")

    def clear_system_operation(self) -> None:
        """Clear system operation (no-op)."""
        pass

    # ========================================================================
    # ROM-level methods (minimal/no-op for headless)
    # ========================================================================

    def update_hashing_progress(self, current: int, total: int, details: str = '') -> None:
        """No-op for headless (too verbose)."""
        pass

    def update_api_fetch_stage(self, rom_name: str, action: str, cache_hit: bool = False) -> None:
        """No-op for headless (too verbose)."""
        pass

    def update_media_download_stage(self, rom_name: str, media_type: str, action: str) -> None:
        """No-op for headless (too verbose)."""
        pass

    def increment_media_validated(self, media_type: Optional[str] = None) -> None:
        """No-op for headless."""
        pass

    def increment_media_validation_failed(self, media_type: Optional[str] = None) -> None:
        """No-op for headless."""
        pass

    def increment_search_fallback(self) -> None:
        """Track search fallback count."""
        self.stats['search_fallback'] += 1

    def increment_unmatched(self) -> None:
        """Track unmatched ROM count."""
        self.stats['unmatched'] += 1

    def increment_gamelist_added(self) -> None:
        """No-op for headless."""
        pass

    def increment_gamelist_updated(self) -> None:
        """No-op for headless."""
        pass

    def increment_completed(self, success: bool = True, skipped: bool = False) -> None:
        """Track completion stats."""
        self.processed_in_system += 1
        if skipped:
            self.stats['skipped'] += 1
        elif success:
            self.stats['successful'] += 1
        else:
            self.stats['failed'] += 1

    def add_completed_game(self, game_info: Dict[str, Any]) -> None:
        """No-op for headless (no spotlight)."""
        pass

    # ========================================================================
    # Pipeline/performance methods
    # ========================================================================

    def update_pipeline_concurrency(self, max_threads: int) -> None:
        """Log concurrency level."""
        logger.info(f"Parallel processing: {max_threads} threads")

    def update_footer(self, stats: Dict[str, Any], api_quota: Optional[Dict] = None,
                     thread_stats: Optional[Dict] = None) -> None:
        """No-op for headless (no footer)."""
        pass

    def set_throttle_status(self, is_throttled: bool) -> None:
        """Log throttle warnings."""
        if is_throttled:
            logger.warning("API rate limit reached - throttling requests")

    def set_auth_status(self, status: str) -> None:
        """Log auth status."""
        if status == 'in_progress':
            logger.info("Authenticating with ScreenScraper...")
        elif status == 'complete':
            logger.info("Authentication successful")

    # ========================================================================
    # Keyboard/prompt methods (no-op for headless)
    # ========================================================================

    def prompt_confirm(self, message: str, default: str = 'y') -> bool:
        """
        Always return default for headless (no interaction).

        Args:
            message: Prompt message (ignored in headless)
            default: Default response ('y' or 'n')

        Returns:
            True if default is 'y', False otherwise
        """
        return default.lower() == 'y'

    def clear_skip_request(self) -> None:
        """No-op for headless."""
        pass

    def clear_quit_request(self) -> None:
        """No-op for headless."""
        pass

    def set_shutting_down(self) -> None:
        """No-op for headless."""
        pass

    # ========================================================================
    # Spotlight/log panel methods (no-op for headless)
    # ========================================================================

    def spotlight_next(self) -> None:
        """No-op for headless."""
        pass

    def spotlight_prev(self) -> None:
        """No-op for headless."""
        pass

    def set_log_level(self, level_key: int) -> None:
        """No-op for headless."""
        pass

    def add_log_entry(self, level: str, message: str) -> None:
        """No-op for headless (logs go through normal logging)."""
        pass

    # ========================================================================
    # Console output methods (no-op for headless)
    # ========================================================================

    def show_error(self, message: str) -> None:
        """No-op for headless (use logger.error instead)."""
        pass

    def show_warning(self, message: str) -> None:
        """No-op for headless (use logger.warning instead)."""
        pass

    def show_info(self, message: str) -> None:
        """No-op for headless (use logger.info instead)."""
        pass

    def clear(self) -> None:
        """No-op for headless."""
        pass

    def print(self, *args, **kwargs) -> None:
        """No-op for headless."""
        pass
