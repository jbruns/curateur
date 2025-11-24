"""
Keyboard listener for non-blocking keyboard input during workflow execution

Provides pause/resume, skip system, and quit controls without impacting performance.
Uses pynput for cross-platform keyboard event handling in a separate thread.
"""

import logging
import threading
from typing import Optional

logger = logging.getLogger(__name__)


class KeyboardListener:
    """
    Non-blocking keyboard listener for workflow controls
    
    Runs in a separate thread using pynput.keyboard.Listener to detect keypresses
    without blocking the main event loop or impacting workflow performance.
    
    Controls:
    - P: Toggle pause/resume (finishes current ROMs, then waits)
    - S: Request skip current system (with confirmation)
    - Q: Request quit (with confirmation)
    
    Features:
    - Thread-safe state management with locks
    - Graceful fallback if pynput unavailable (SSH/tmux)
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
        self._listener: Optional[object] = None
        self._listener_active = False
        
        # Console UI callback for extended controls
        self.console_ui = console_ui
    
    def start(self) -> bool:
        """
        Start keyboard listener in background thread
        
        Returns:
            True if listener started successfully, False if pynput unavailable
        """
        try:
            # Import pynput only when starting (allows graceful failure)
            from pynput import keyboard
            
            logger.debug("pynput imported successfully")
            
            def on_press(key):
                """Handle key press events"""
                try:
                    # Get character from key
                    char = None
                    if hasattr(key, 'char'):
                        char = key.char
                    
                    # Handle special keys (arrows)
                    if hasattr(key, 'name'):
                        key_name = key.name
                        
                        # Handle arrow keys for spotlight navigation
                        if key_name == 'left' and self.console_ui:
                            self.console_ui.spotlight_prev()
                            return
                        elif key_name == 'right' and self.console_ui:
                            self.console_ui.spotlight_next()
                            return
                    
                    if char is None:
                        return
                    
                    char = char.lower()
                    
                    # Handle pause/resume (toggle)
                    if char == 'p':
                        with self._lock:
                            self._is_paused = not self._is_paused
                            state = "paused" if self._is_paused else "resumed"
                            logger.info(f"Keyboard control: Processing {state}")
                    
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
            
            # Create and start listener
            logger.debug("Creating keyboard listener...")
            self._listener = keyboard.Listener(on_press=on_press)
            
            logger.debug("Starting keyboard listener...")
            self._listener.start()
            self._listener_active = True
            
            logger.info("Keyboard listener started successfully")
            return True
        
        except ImportError as e:
            logger.warning(f"pynput not available - keyboard controls disabled: {e}")
            return False
        except Exception as e:
            logger.warning(f"Could not start keyboard listener: {e}", exc_info=True)
            return False
    
    def stop(self) -> None:
        """Stop keyboard listener"""
        if self._listener and self._listener_active:
            try:
                self._listener.stop()
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
