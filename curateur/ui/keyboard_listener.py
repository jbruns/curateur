"""
Keyboard listener for non-blocking keyboard input during workflow execution

Provides pause/resume, skip system, and quit controls without impacting performance.
Uses terminal input polling in a separate thread - only active when terminal has focus.
"""

import logging
import sys
import termios
import tty
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class KeyboardListener:
    """
    Non-blocking keyboard listener for workflow controls
    
    Runs in a separate thread polling terminal input to detect keypresses
    without blocking the main event loop or impacting workflow performance.
    Only responds to input when the terminal window has focus.
    
    Controls:
    - P: Toggle pause/resume (finishes current ROMs, then waits)
    - S: Request skip current system (with confirmation)
    - Q: Request quit (with confirmation)
    - Arrow Left/Right: Navigate game spotlight
    - 1-4: Set log level filter (ERROR/WARNING/INFO/DEBUG)
    
    Features:
    - Thread-safe state management with locks
    - Only captures input when terminal has focus
    - Graceful fallback if terminal not available (non-TTY)
    - Ignores duplicate key presses while action pending
    
    Example:
        listener = KeyboardListener()
        if listener.start():
            # Keyboard controls available
            if listener.is_paused:
                # Wait for resume
                pass
        else:
            # Keyboard controls unavailable - use Ctrl-C
            pass
    """
    
    def __init__(self, console_ui=None):
        """
        Initialize keyboard listener with thread-safe state flags
        
        Args:
            console_ui: Optional ConsoleUI instance for UI callback methods
        """
        self._lock = threading.Lock()
        
        # State flags
        self._is_paused = False
        self._skip_requested = False
        self._quit_requested = False
        
        # Action pending flags (prevent duplicate key presses)
        self._skip_pending = False
        self._quit_pending = False
        
        # Listener tracking
        self._listener_thread: Optional[threading.Thread] = None
        self._listener_active = False
        self._stop_event = threading.Event()
        
        # Console UI callback for extended controls
        self.console_ui = console_ui
        
        # Terminal settings backup
        self._old_terminal_settings = None
    
    def start(self) -> bool:
        """
        Start keyboard listener in background thread
        
        Returns:
            True if listener started successfully, False if terminal not available
        """
        # Check if stdin is a TTY (terminal)
        if not sys.stdin.isatty():
            logger.warning("stdin is not a TTY - keyboard controls disabled")
            return False
        
        try:
            # Save current terminal settings
            self._old_terminal_settings = termios.tcgetattr(sys.stdin)
            
            # Start listener thread
            self._stop_event.clear()
            self._listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
            self._listener_thread.start()
            self._listener_active = True
            
            logger.info("Keyboard listener started successfully (terminal-focused)")
            return True
        
        except Exception as e:
            logger.warning(f"Could not start keyboard listener: {e}", exc_info=True)
            return False
    
    def _listen_loop(self):
        """
        Main listener loop running in background thread
        
        Polls terminal for input without blocking. Only active when terminal has focus.
        """
        try:
            # Set terminal to raw mode for single-char input
            tty.setcbreak(sys.stdin.fileno())
            
            while not self._stop_event.is_set():
                # Check if input is available (non-blocking with timeout)
                import select
                ready, _, _ = select.select([sys.stdin], [], [], 0.1)
                
                if ready:
                    char = sys.stdin.read(1)
                    self._handle_key(char)
        
        except Exception as e:
            logger.error(f"Error in keyboard listener loop: {e}", exc_info=True)
        finally:
            # Restore terminal settings
            if self._old_terminal_settings:
                try:
                    termios.tcsetattr(sys.stdin, termios.TCSADRAIN, self._old_terminal_settings)
                except Exception as e:
                    logger.error(f"Error restoring terminal settings: {e}")
    
    def _handle_key(self, char: str):
        """
        Handle a single keypress
        
        Args:
            char: Character pressed (may be escape sequence for special keys)
        """
        try:
            # Handle escape sequences for arrow keys
            if char == '\x1b':  # ESC
                # Read next two characters for arrow key sequence
                import select
                ready, _, _ = select.select([sys.stdin], [], [], 0.1)
                if ready:
                    seq = sys.stdin.read(2)
                    if seq == '[D':  # Left arrow
                        if self.console_ui:
                            self.console_ui.spotlight_prev()
                        return
                    elif seq == '[C':  # Right arrow
                        if self.console_ui:
                            self.console_ui.spotlight_next()
                        return
                return
            
            char = char.lower()
            
            # Handle prompt response (Y/N)
            if self.console_ui and self.console_ui.prompt_active:
                if char in ('y', '\n', '\r'):
                    self.console_ui.prompt_response = True
                    logger.debug("Keyboard control: Prompt confirmed (Y)")
                    return
                elif char == 'n':
                    self.console_ui.prompt_response = False
                    logger.debug("Keyboard control: Prompt declined (N)")
                    return
            
            # Handle pause/resume (toggle)
            if char == 'p':
                with self._lock:
                    self._is_paused = not self._is_paused
                    state = "paused" if self._is_paused else "resumed"
                    logger.info(f"Keyboard control: Processing {state}")
            
            # Handle spotlight navigation
            elif char == 'n':
                if self.console_ui:
                    self.console_ui.spotlight_next()
                    logger.debug("Keyboard control: Spotlight next")
            
            elif char == 'b':
                if self.console_ui:
                    self.console_ui.spotlight_prev()
                    logger.debug("Keyboard control: Spotlight previous")
            
            # Handle skip request
            elif char == 's':
                with self._lock:
                    # Only honor first press until action handled
                    if not self._skip_pending:
                        self._skip_requested = True
                        self._skip_pending = True
                        logger.debug("Keyboard control: Skip system requested")
            
            # Handle quit request
            elif char == 'q':
                with self._lock:
                    # Only honor first press until action handled
                    if not self._quit_pending:
                        self._quit_requested = True
                        self._quit_pending = True
                        logger.debug("Keyboard control: Quit requested")
            
            # Handle log level filter keys (1-4)
            elif char in ('1', '2', '3', '4') and self.console_ui:
                level_key = int(char)
                self.console_ui.set_log_level(level_key)
                logger.debug(f"Keyboard control: Log level filter set to {level_key}")
        
        except Exception as e:
            logger.error(f"Error handling key press: {e}", exc_info=True)
    
    def stop(self) -> None:
        """Stop keyboard listener"""
        if self._listener_active:
            try:
                self._stop_event.set()
                if self._listener_thread:
                    self._listener_thread.join(timeout=1.0)
                self._listener_active = False
                logger.debug("Keyboard listener stopped")
            except Exception as e:
                logger.error(f"Error stopping keyboard listener: {e}", exc_info=True)
    
    @property
    def is_paused(self) -> bool:
        """Check if processing is paused"""
        with self._lock:
            return self._is_paused
    
    @property
    def skip_requested(self) -> bool:
        """Check if skip system requested"""
        with self._lock:
            return self._skip_requested
    
    @property
    def quit_requested(self) -> bool:
        """Check if quit requested"""
        with self._lock:
            return self._quit_requested
    
    def clear_skip_request(self) -> None:
        """Clear skip request flag after handling"""
        with self._lock:
            self._skip_requested = False
            self._skip_pending = False
            logger.debug("Skip request cleared")
    
    def clear_quit_request(self) -> None:
        """Clear quit request flag after handling"""
        with self._lock:
            self._quit_requested = False
            self._quit_pending = False
            logger.debug("Quit request cleared")
