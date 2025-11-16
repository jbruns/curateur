"""
Interactive prompt system for user decisions

Provides confirmation prompts, multiple choice selections, and input validation.
"""

import logging
import threading
from typing import Optional, Callable, List, Dict, Any

logger = logging.getLogger(__name__)

# Global lock for thread-safe prompts
_prompt_lock = threading.Lock()


class PromptSystem:
    """
    Interactive prompt system for user decisions
    
    Features:
    - Yes/no confirmations
    - Multiple choice selections
    - Input validation
    - Default values
    
    Example:
        prompts = PromptSystem()
        
        # Yes/no confirmation
        if prompts.confirm("Continue with operation?", default='y'):
            # User confirmed
            pass
        
        # Multiple choice
        choice = prompts.choose(
            "Select quality:",
            ['low', 'medium', 'high'],
            default=1  # medium
        )
        
        # Text input with validation
        name = prompts.input_text(
            "Enter system name:",
            validator=lambda x: x.isalpha()
        )
    """
    
    def confirm(self, message: str, default: Optional[str] = None) -> bool:
        """
        Yes/no confirmation prompt
        
        Args:
            message: Prompt message
            default: 'y' | 'n' | None (no default)
        
        Returns:
            True for yes, False for no
        
        Example:
            if prompts.confirm("Delete files?", default='n'):
                delete_files()
        """
        # Build prompt string
        if default is None:
            prompt_str = f"{message} [y/n]: "
        elif default.lower() == 'y':
            prompt_str = f"{message} [Y/n]: "
        elif default.lower() == 'n':
            prompt_str = f"{message} [y/N]: "
        else:
            raise ValueError(f"Invalid default: {default}. Must be 'y', 'n', or None")
        
        while True:
            try:
                response = input(prompt_str).strip().lower()
                
                # Handle empty response (use default)
                if not response:
                    if default is None:
                        print("Please enter 'y' or 'n'")
                        continue
                    response = default.lower()
                
                # Validate response
                if response in ('y', 'yes'):
                    logger.debug(f"User confirmed: {message}")
                    return True
                elif response in ('n', 'no'):
                    logger.debug(f"User declined: {message}")
                    return False
                else:
                    print("Please enter 'y' or 'n'")
            
            except (KeyboardInterrupt, EOFError):
                logger.info("User interrupted prompt")
                print("\nOperation cancelled")
                return False
    
    def choose(
        self,
        message: str,
        choices: List[str],
        default: Optional[int] = None
    ) -> str:
        """
        Multiple choice selection
        
        Args:
            message: Prompt message
            choices: List of choice strings
            default: Default choice index (0-based), None for no default
        
        Returns:
            Selected choice string
        
        Example:
            action = prompts.choose(
                "What to do?",
                ['skip', 'retry', 'abort'],
                default=0
            )
        """
        if not choices:
            raise ValueError("Choices list cannot be empty")
        
        if default is not None and (default < 0 or default >= len(choices)):
            raise ValueError(f"Default index {default} out of range for {len(choices)} choices")
        
        # Display choices
        print(f"\n{message}")
        for i, choice in enumerate(choices):
            marker = "*" if i == default else " "
            print(f"  {marker} {i + 1}. {choice}")
        
        # Build prompt
        if default is not None:
            prompt_str = f"Enter choice [1-{len(choices)}] (default: {default + 1}): "
        else:
            prompt_str = f"Enter choice [1-{len(choices)}]: "
        
        while True:
            try:
                response = input(prompt_str).strip()
                
                # Handle empty response (use default)
                if not response:
                    if default is None:
                        print(f"Please enter a number between 1 and {len(choices)}")
                        continue
                    logger.debug(f"User selected default choice: {choices[default]}")
                    return choices[default]
                
                # Parse and validate
                try:
                    choice_num = int(response)
                    if 1 <= choice_num <= len(choices):
                        selected = choices[choice_num - 1]
                        logger.debug(f"User selected choice: {selected}")
                        return selected
                    else:
                        print(f"Please enter a number between 1 and {len(choices)}")
                except ValueError:
                    print(f"Please enter a valid number")
            
            except (KeyboardInterrupt, EOFError):
                logger.info("User interrupted prompt")
                print("\nOperation cancelled")
                if default is not None:
                    return choices[default]
                raise
    
    def input_text(
        self,
        message: str,
        default: Optional[str] = None,
        validator: Optional[Callable[[str], bool]] = None
    ) -> str:
        """
        Text input with optional validation
        
        Args:
            message: Prompt message
            default: Default value (shown in brackets)
            validator: Function to validate input (returns True if valid)
        
        Returns:
            Validated input string
        
        Example:
            # Alphanumeric only
            name = prompts.input_text(
                "Enter name:",
                validator=lambda x: x.isalnum()
            )
            
            # Minimum length
            password = prompts.input_text(
                "Enter password:",
                validator=lambda x: len(x) >= 8
            )
        """
        # Build prompt
        if default is not None:
            prompt_str = f"{message} [{default}]: "
        else:
            prompt_str = f"{message}: "
        
        while True:
            try:
                response = input(prompt_str).strip()
                
                # Handle empty response (use default)
                if not response:
                    if default is None:
                        print("Input cannot be empty")
                        continue
                    response = default
                
                # Validate if validator provided
                if validator is not None:
                    if not validator(response):
                        print("Invalid input. Please try again.")
                        continue
                
                logger.debug(f"User input: {message} -> {response}")
                return response
            
            except (KeyboardInterrupt, EOFError):
                logger.info("User interrupted prompt")
                print("\nOperation cancelled")
                if default is not None:
                    return default
                raise
    
    def input_int(
        self,
        message: str,
        default: Optional[int] = None,
        min_value: Optional[int] = None,
        max_value: Optional[int] = None
    ) -> int:
        """
        Integer input with optional range validation
        
        Args:
            message: Prompt message
            default: Default value
            min_value: Minimum allowed value (inclusive)
            max_value: Maximum allowed value (inclusive)
        
        Returns:
            Validated integer
        
        Example:
            count = prompts.input_int(
                "How many items?",
                default=10,
                min_value=1,
                max_value=100
            )
        """
        # Build validation message
        range_msg = ""
        if min_value is not None and max_value is not None:
            range_msg = f" ({min_value}-{max_value})"
        elif min_value is not None:
            range_msg = f" (min: {min_value})"
        elif max_value is not None:
            range_msg = f" (max: {max_value})"
        
        # Build prompt
        if default is not None:
            prompt_str = f"{message}{range_msg} [{default}]: "
        else:
            prompt_str = f"{message}{range_msg}: "
        
        while True:
            try:
                response = input(prompt_str).strip()
                
                # Handle empty response (use default)
                if not response:
                    if default is None:
                        print("Input cannot be empty")
                        continue
                    return default
                
                # Parse integer
                try:
                    value = int(response)
                except ValueError:
                    print("Please enter a valid integer")
                    continue
                
                # Validate range
                if min_value is not None and value < min_value:
                    print(f"Value must be at least {min_value}")
                    continue
                
                if max_value is not None and value > max_value:
                    print(f"Value must be at most {max_value}")
                    continue
                
                logger.debug(f"User input integer: {message} -> {value}")
                return value
            
            except (KeyboardInterrupt, EOFError):
                logger.info("User interrupted prompt")
                print("\nOperation cancelled")
                if default is not None:
                    return default
                raise


def prompt_for_search_match(
    rom_filename: str,
    candidates: List[tuple[Dict[str, Any], float]],
    threshold: float = 0.7
) -> Optional[Dict[str, Any]]:
    """
    Thread-safe prompt for user to select best search match.
    
    Displays candidates with confidence scores and allows user to:
    - Select a specific match by number
    - Skip (no match)
    - Reject all and mark as unmatched
    
    Args:
        rom_filename: Original ROM filename
        candidates: List of (game_data, confidence_score) tuples, sorted by score
        threshold: Confidence threshold for display context
        
    Returns:
        Selected game data dictionary, or None if user skipped/rejected
    """
    # Acquire lock for thread-safe prompting
    with _prompt_lock:
        print("\n" + "="*80)
        print(f"Search results for: {rom_filename}")
        print("="*80)
        
        if not candidates:
            print("No candidates found.")
            return None
        
        # Display candidates with numbering
        for i, (game_data, score) in enumerate(candidates, 1):
            # Get game name (prefer English, fall back to first available)
            names = game_data.get('names', {})
            display_name = names.get('en') or names.get('us') or next(iter(names.values()), 'Unknown')
            
            # Get region info
            regions = ', '.join(names.keys()) if names else 'unknown'
            
            # Get system info
            system = game_data.get('system', 'Unknown System')
            
            # Confidence indicator
            confidence_bar = _render_confidence_bar(score)
            threshold_indicator = " ✓" if score >= threshold else " ✗"
            
            print(f"\n{i}. {display_name}")
            print(f"   System: {system}")
            print(f"   Regions: {regions}")
            print(f"   Confidence: {score:.1%} {confidence_bar}{threshold_indicator}")
            
            # Show additional metadata hints
            if 'releasedate' in game_data:
                print(f"   Release: {game_data['releasedate']}")
            if 'publisher' in game_data:
                print(f"   Publisher: {game_data['publisher']}")
        
        print("\n" + "-"*80)
        print("Options:")
        print("  1-{}: Select match by number".format(len(candidates)))
        print("  s: Skip this ROM (try again later)")
        print("  n: No match (mark as unmatched)")
        print("-"*80)
        
        # Prompt for selection
        while True:
            try:
                response = input("\nYour choice: ").strip().lower()
                
                if not response:
                    print("Please enter a choice")
                    continue
                
                # Skip
                if response == 's':
                    logger.info(f"User skipped search match for {rom_filename}")
                    print("Skipped.")
                    return None
                
                # No match
                if response == 'n':
                    logger.info(f"User rejected all matches for {rom_filename}")
                    print("Marked as unmatched.")
                    return None
                
                # Numeric selection
                try:
                    choice = int(response)
                    if 1 <= choice <= len(candidates):
                        selected_game, selected_score = candidates[choice - 1]
                        selected_name = selected_game.get('names', {}).get('en', 'Selected game')
                        logger.info(
                            f"User selected match #{choice} for {rom_filename}: "
                            f"{selected_name} (confidence: {selected_score:.1%})"
                        )
                        print(f"Selected: {selected_name}")
                        return selected_game
                    else:
                        print(f"Please enter a number between 1 and {len(candidates)}")
                        continue
                except ValueError:
                    print("Invalid choice. Please enter a number, 's', or 'n'")
                    continue
                    
            except (KeyboardInterrupt, EOFError):
                logger.info(f"User interrupted search match prompt for {rom_filename}")
                print("\nSkipped.")
                return None


def _render_confidence_bar(score: float, width: int = 20) -> str:
    """
    Render a visual confidence bar.
    
    Args:
        score: Confidence score 0.0-1.0
        width: Width of bar in characters
        
    Returns:
        ASCII bar representation
    """
    filled = int(score * width)
    empty = width - filled
    return f"[{'█' * filled}{'░' * empty}]"
