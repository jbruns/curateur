"""
Textual UI Mockup for Curateur

Standalone demo with sample data to visualize the 3-tab Textual interface design.
This mockup demonstrates feasibility for replacing the Rich UI.

Run with: python curateur/ui/textual_mockup.py
"""

import logging
import random
import re
from collections import deque
from typing import List, Tuple

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical, VerticalScroll, ScrollableContainer
from textual.widgets import (
    Header,
    Footer,
    TabbedContent,
    TabPane,
    Static,
    Label,
    DataTable,
    RichLog,
    Input,
    ProgressBar,
    Switch,
    Select,
    Button,
    Tree,
    ListView,
    ListItem,
    Rule,
)
from textual.reactive import reactive
from textual.screen import ModalScreen
from rich.text import Text


# ============================================================================
# Sample Data
# ============================================================================

SAMPLE_GAMES = [
    {
        "name": "Super Mario Bros.",
        "year": 1985,
        "genre": "Platform, Action",
        "developer": "Nintendo",
        "publisher": "Nintendo",
        "players": "1-2",
        "rating": "4.8/5",
        "region": "US",
        "synopsis": "A groundbreaking platformer that revolutionized gaming and established many conventions of the genre. Players guide Mario through the Mushroom Kingdom to rescue Princess Peach from Bowser's clutches.",
    },
    {
        "name": "The Legend of Zelda",
        "year": 1986,
        "genre": "Action, Adventure",
        "developer": "Nintendo",
        "publisher": "Nintendo",
        "players": "1",
        "rating": "4.9/5",
        "region": "US",
        "synopsis": "An epic adventure that defined the action-RPG genre with its open-world exploration. Link must collect the eight fragments of the Triforce of Wisdom to rescue Princess Zelda and defeat the evil Ganon.",
    },
    {
        "name": "Metroid",
        "year": 1986,
        "genre": "Action, Platform",
        "developer": "Nintendo",
        "publisher": "Nintendo",
        "players": "1",
        "rating": "4.7/5",
        "region": "US",
        "synopsis": "A sci-fi adventure featuring Samus Aran exploring hostile alien worlds. Navigate the labyrinthine planet Zebes while collecting power-ups and battling the Space Pirates to stop Mother Brain.",
    },
    {
        "name": "Mega Man 2",
        "year": 1988,
        "genre": "Action, Platform",
        "developer": "Capcom",
        "publisher": "Capcom",
        "players": "1",
        "rating": "4.8/5",
        "region": "US",
        "synopsis": "The beloved sequel featuring eight Robot Masters and memorable boss battles. Mega Man must defeat Dr. Wily's latest robot creations and use their weapons to progress through challenging stages.",
    },
    {
        "name": "Castlevania III",
        "year": 1989,
        "genre": "Action, Platform",
        "developer": "Konami",
        "publisher": "Konami",
        "players": "1",
        "rating": "4.6/5",
        "region": "US",
        "synopsis": "Trevor Belmont's quest to defeat Dracula with multiple playable characters. Team up with Grant, Sypha, or Alucard as you journey through branching paths to reach Dracula's castle.",
    },
    {
        "name": "Contra",
        "year": 1987,
        "genre": "Action, Shooter",
        "developer": "Konami",
        "publisher": "Konami",
        "players": "1-2",
        "rating": "4.7/5",
        "region": "US",
        "synopsis": "Intense run-and-gun action with memorable co-op gameplay. Bill and Lance must fight through waves of alien enemies to destroy the Red Falcon organization's fortress.",
    },
    {
        "name": "Final Fantasy",
        "year": 1987,
        "genre": "RPG",
        "developer": "Square",
        "publisher": "Square",
        "players": "1",
        "rating": "4.5/5",
        "region": "US",
        "synopsis": "The game that launched the legendary JRPG franchise. Four Light Warriors embark on a quest to restore light to the four elemental crystals and save the world from darkness.",
    },
    {
        "name": "Dragon Quest",
        "year": 1986,
        "genre": "RPG",
        "developer": "Enix",
        "publisher": "Enix",
        "players": "1",
        "rating": "4.4/5",
        "region": "US",
        "synopsis": "The pioneering console RPG that defined the genre in Japan. As the descendant of the legendary hero Erdrick, you must rescue Princess Gwaelin and defeat the evil Dragonlord.",
    },
    {
        "name": "Ninja Gaiden",
        "year": 1988,
        "genre": "Action, Platform",
        "developer": "Tecmo",
        "publisher": "Tecmo",
        "players": "1",
        "rating": "4.6/5",
        "region": "US",
        "synopsis": "Fast-paced ninja action with cinematic cutscenes. Ryu Hayabusa travels to America to avenge his father's death and uncover a demonic conspiracy threatening the world.",
    },
    {
        "name": "Punch-Out!!",
        "year": 1987,
        "genre": "Sports, Fighting",
        "developer": "Nintendo",
        "publisher": "Nintendo",
        "players": "1",
        "rating": "4.8/5",
        "region": "US",
        "synopsis": "Little Mac's boxing journey through colorful opponents. Train with Doc Louis and fight your way through the ranks of the World Video Boxing Association to become champion.",
    },
]

# Sample log entries (level, message)
SAMPLE_LOGS = [
    (logging.INFO, "Scanning ROM directory: /roms/nes"),
    (logging.INFO, "Found 200 ROM files for processing"),
    (logging.DEBUG, "Calculating CRC hash for super_mario_bros.zip"),
    (logging.INFO, "Hash calculated: CRC32 abc12345"),
    (logging.WARNING, "Cache miss for Super Mario Bros."),
    (logging.INFO, "Fetching metadata from ScreenScraper API..."),
    (logging.DEBUG, "API response time: 245ms"),
    (logging.INFO, "Game found: Super Mario Bros. (1985)"),
    (logging.INFO, "Downloading media: screenshot"),
    (logging.INFO, "Downloading media: box2dfront"),
    (logging.DEBUG, "Media download complete: 2 files"),
    (logging.INFO, "Processing: The Legend of Zelda"),
    (logging.DEBUG, "Calculating CRC hash for zelda.zip"),
    (logging.WARNING, "API rate limit approaching (450/500 requests)"),
    (logging.INFO, "Hash calculated: CRC32 def67890"),
    (logging.INFO, "Cache hit for The Legend of Zelda"),
    (logging.DEBUG, "Using cached metadata from 2024-12-03"),
    (logging.INFO, "Downloading media: screenshot"),
    (logging.ERROR, "Failed to download screenshot: connection timeout"),
    (logging.WARNING, "Retrying download (attempt 2/3)"),
    (logging.INFO, "Download successful on retry"),
    (logging.INFO, "Processing: Metroid"),
    (logging.DEBUG, "Calculating CRC hash for metroid.zip"),
    (logging.INFO, "Hash calculated: CRC32 ghi34567"),
    (logging.WARNING, "Cache miss for Metroid"),
    (logging.INFO, "Fetching metadata from API..."),
    (logging.DEBUG, "API response time: 312ms"),
    (logging.INFO, "Game found: Metroid (1986)"),
    (logging.INFO, "Downloading media: screenshot, box2dfront, video"),
    (logging.DEBUG, "Media validation: screenshot hash match"),
    (logging.DEBUG, "Media validation: box2dfront hash match"),
    (logging.INFO, "All media downloaded successfully"),
    (logging.INFO, "Processing: Mega Man 2"),
    (logging.DEBUG, "Calculating CRC hash for megaman2.zip"),
    (logging.INFO, "Hash calculated: CRC32 jkl89012"),
    (logging.INFO, "Cache hit for Mega Man 2"),
    (logging.INFO, "Skipping media download (already exists)"),
    (logging.DEBUG, "Validating existing media files"),
    (logging.INFO, "All existing media validated"),
    (logging.INFO, "Processing: Castlevania III"),
    (logging.WARNING, "ROM name does not match database entry"),
    (logging.INFO, "Enabling search fallback for Castlevania III"),
    (logging.DEBUG, "Search query: Castlevania III"),
    (logging.INFO, "Found 3 potential matches"),
    (logging.INFO, "Best match: Castlevania III: Dracula's Curse (confidence: 0.95)"),
    (logging.INFO, "Using match with ID: 12345"),
    (logging.INFO, "Downloading media: screenshot, box2dfront"),
    (logging.DEBUG, "Media download complete: 2 files"),
    (logging.INFO, "Processing: Contra"),
    (logging.INFO, "Cache hit for Contra"),
    (logging.DEBUG, "Using cached metadata from 2024-12-02"),
    (logging.INFO, "Downloading media: screenshot"),
    (logging.WARNING, "Media already exists, skipping download"),
]

# Sample systems data with detailed statistics
SAMPLE_SYSTEMS = {
    "NES": {
        "fullname": "Nintendo Entertainment System",
        "roms": {"total": 200, "successful": 195, "failed": 3, "skipped": 2},
        "media": {
            "screenshot": {"downloaded": 195, "skipped": 2, "validated": 12, "failed": 3},
            "box2dfront": {"downloaded": 190, "skipped": 5, "validated": 15, "failed": 5},
            "video": {"downloaded": 150, "skipped": 45, "validated": 8, "failed": 2},
            "wheel": {"downloaded": 185, "skipped": 10, "validated": 10, "failed": 5},
        },
        "api": {"info_calls": 195, "search_calls": 8, "media_calls": 720},
        "gamelist": {"existing": 180, "added": 15, "updated": 175, "removed": 5},
        "cache": {"existing": 150, "new": 45, "removed": 10, "hit_rate": 0.75},
        "summary_log": """2024-12-04 19:15:32 - Starting scrape for NES
2024-12-04 19:15:33 - Found 200 ROM files
2024-12-04 19:15:35 - Loaded existing gamelist with 180 entries
2024-12-04 19:18:45 - Processed 195/200 ROMs successfully
2024-12-04 19:18:45 - Failed: 3 ROMs
2024-12-04 19:18:45 - Skipped: 2 ROMs (already complete)
2024-12-04 19:18:46 - Downloaded 720 media files
2024-12-04 19:18:47 - Cache hit rate: 75%
2024-12-04 19:18:47 - Gamelist integrity: 98.5%
2024-12-04 19:18:48 - NES scrape complete""",
    },
    "SNES": {
        "fullname": "Super Nintendo Entertainment System",
        "roms": {"total": 180, "successful": 175, "failed": 2, "skipped": 3},
        "media": {
            "screenshot": {"downloaded": 175, "skipped": 2, "validated": 8, "failed": 3},
            "box2dfront": {"downloaded": 170, "skipped": 5, "validated": 10, "failed": 5},
            "video": {"downloaded": 120, "skipped": 55, "validated": 5, "failed": 0},
            "wheel": {"downloaded": 168, "skipped": 7, "validated": 12, "failed": 3},
        },
        "api": {"info_calls": 175, "search_calls": 5, "media_calls": 633},
        "gamelist": {"existing": 165, "added": 10, "updated": 160, "removed": 3},
        "cache": {"existing": 140, "new": 35, "removed": 8, "hit_rate": 0.80},
        "summary_log": """2024-12-04 19:18:50 - Starting scrape for SNES
2024-12-04 19:18:51 - Found 180 ROM files
2024-12-04 19:18:52 - Loaded existing gamelist with 165 entries
2024-12-04 19:21:30 - Processed 175/180 ROMs successfully
2024-12-04 19:21:30 - Failed: 2 ROMs
2024-12-04 19:21:30 - Skipped: 3 ROMs (already complete)
2024-12-04 19:21:31 - Downloaded 633 media files
2024-12-04 19:21:32 - Cache hit rate: 80%
2024-12-04 19:21:32 - Gamelist integrity: 99.2%
2024-12-04 19:21:33 - SNES scrape complete""",
    },
    "Genesis": {
        "fullname": "Sega Genesis / Mega Drive",
        "roms": {"total": 150, "successful": 115, "failed": 2, "skipped": 0},
        "media": {
            "screenshot": {"downloaded": 98, "skipped": 15, "validated": 12, "failed": 1},
            "box2dfront": {"downloaded": 95, "skipped": 18, "validated": 15, "failed": 2},
            "video": {"downloaded": 45, "skipped": 68, "validated": 8, "failed": 0},
            "wheel": {"downloaded": 88, "skipped": 25, "validated": 10, "failed": 1},
        },
        "api": {"info_calls": 115, "search_calls": 12, "media_calls": 326},
        "gamelist": {"existing": 95, "added": 20, "updated": 90, "removed": 5},
        "cache": {"existing": 85, "new": 30, "removed": 4, "hit_rate": 0.65},
        "summary_log": """2024-12-04 19:21:35 - Starting scrape for Genesis
2024-12-04 19:21:36 - Found 150 ROM files
2024-12-04 19:21:37 - Loaded existing gamelist with 95 entries
2024-12-04 19:22:15 - Processed 115/150 ROMs (IN PROGRESS)
2024-12-04 19:22:15 - Failed: 2 ROMs
2024-12-04 19:22:15 - Remaining: 33 ROMs
2024-12-04 19:22:16 - Downloaded 326 media files so far
2024-12-04 19:22:16 - Cache hit rate: 65%
2024-12-04 19:22:16 - ETA: 15 minutes""",
    },
    "PSX": {
        "fullname": "Sony PlayStation",
        "roms": {"total": 317, "successful": 0, "failed": 0, "skipped": 0},
        "media": {
            "screenshot": {"downloaded": 0, "skipped": 0, "validated": 0, "failed": 0},
            "box2dfront": {"downloaded": 0, "skipped": 0, "validated": 0, "failed": 0},
            "video": {"downloaded": 0, "skipped": 0, "validated": 0, "failed": 0},
            "wheel": {"downloaded": 0, "skipped": 0, "validated": 0, "failed": 0},
        },
        "api": {"info_calls": 0, "search_calls": 0, "media_calls": 0},
        "gamelist": {"existing": 250, "added": 0, "updated": 0, "removed": 0},
        "cache": {"existing": 200, "new": 0, "removed": 0, "hit_rate": 0.0},
        "summary_log": """2024-12-04 19:22:18 - PSX queued for scraping
2024-12-04 19:22:18 - Found 317 ROM files
2024-12-04 19:22:19 - Loaded existing gamelist with 250 entries
2024-12-04 19:22:19 - Waiting for Genesis to complete...""",
    },
}

# Sample active requests
SAMPLE_ACTIVE_REQUESTS = [
    {"rom": "zelda.zip", "stage": "API Fetch", "duration": 2.1, "status": "Active", "retry": 0, "last_failure": "—"},
    {"rom": "metroid.zip", "stage": "Media DL", "duration": 5.4, "status": "Active", "retry": 1, "last_failure": "Timeout"},
    {"rom": "mario3.zip", "stage": "Hashing", "duration": 0.8, "status": "Active", "retry": 0, "last_failure": "—"},
]

# Sample search results for interactive search
SAMPLE_SEARCH_RESULTS = [
    {
        "id": 12345,
        "name": "Castlevania III: Dracula's Curse",
        "year": 1989,
        "region": "US",
        "publisher": "Konami",
        "developer": "Konami",
        "players": "1",
        "confidence": 0.95,
    },
    {
        "id": 12346,
        "name": "Akumajou Densetsu",
        "year": 1989,
        "region": "JP",
        "publisher": "Konami",
        "developer": "Konami",
        "players": "1",
        "confidence": 0.88,
    },
    {
        "id": 12347,
        "name": "Castlevania III: Dracula's Curse",
        "year": 1990,
        "region": "EU",
        "publisher": "Konami",
        "developer": "Konami",
        "players": "1",
        "confidence": 0.85,
    },
    {
        "id": 67890,
        "name": "Castlevania",
        "year": 1987,
        "region": "US",
        "publisher": "Konami",
        "developer": "Konami",
        "players": "1",
        "confidence": 0.62,
    },
]

# Current system operational data
CURRENT_SYSTEM = {
    "key": "Genesis",
    "fullname": "Sega Genesis / Mega Drive",
    "hashing": {"completed": 115, "total": 150, "skipped": 3, "in_progress": True},
    "gamelist": {"existing": 95, "added": 20, "removed": 5, "updated": 90},
    "cache": {"existing": 85, "added": 30, "hit_rate": 0.65},
    "api": {
        "metadata": {"in_flight": 2, "total": 115},
        "search": {"in_flight": 1, "total": 12},
    },
    "media": {
        "in_flight": 5,
        "downloaded": 326,
        "validated": 45,
        "failed": 4,
    },
}

# Overall run progress
OVERALL_PROGRESS = {
    "systems_complete": 2,
    "systems_total": 4,
    "total_roms": 847,
    "processed": 485,
    "successful": 470,
    "skipped": 5,
    "failed": 10,
}

# ScreenScraper account info
ACCOUNT_INFO = {
    "username": "retrogamer_2024",
    "quota_used": 1247,
    "quota_limit": 20000,
    "threads_in_use": 3,
    "threads_limit": 4,
    "system_eta": "15 minutes",
}

# Generate sparkline data (40 samples for 10-second history)
THROUGHPUT_HISTORY = [random.uniform(40, 50) for _ in range(40)]
API_RATE_HISTORY = [random.uniform(10, 15) for _ in range(40)]


def create_sparkline(data: List[float], width: int = 30) -> str:
    """Create a sparkline visualization using Unicode block characters"""
    if not data or len(data) == 0:
        return "▁" * min(width, 10)

    # Take last 'width' values
    values = data[-width:]

    # Normalize to 0-7 range (8 block characters)
    min_val = min(values)
    max_val = max(values)

    if max_val == min_val:
        # All values same - show middle bar
        return "▄" * len(values)

    # Map to block characters: ▁▂▃▄▅▆▇█
    blocks = "▁▂▃▄▅▆▇█"
    chars = ""
    for val in values:
        normalized = (val - min_val) / (max_val - min_val)
        block_idx = int(normalized * 7)
        chars += blocks[block_idx]

    return chars


# ============================================================================
# Custom Widgets
# ============================================================================


class OverallProgressWidget(Container):
    """Displays overall run progress with progress bar"""

    def compose(self) -> ComposeResult:
        yield Static(id="overall-progress-header")
        yield ProgressBar(id="overall-progress-bar", total=100, show_eta=False)

    def on_mount(self) -> None:
        """Initialize overall progress display"""
        self.border_title = "Overall Progress"
        self.update_display()

    def update_display(self) -> None:
        """Render overall progress"""
        prog = OVERALL_PROGRESS
        systems_complete = prog["systems_complete"]
        systems_total = prog["systems_total"]
        processed = prog["processed"]
        total = prog["total_roms"]
        successful = prog["successful"]
        skipped = prog["skipped"]
        failed = prog["failed"]

        progress_pct = (processed / total * 100) if total > 0 else 0

        # Header text (title now in border)
        header = Text()
        # Systems line
        header.append(f"Systems: {systems_complete}/{systems_total}\n", style="white")

        # ROMs line
        header.append(f"ROMs: {processed}/{total} ", style="cyan")
        header.append(f"({progress_pct:.1f}%)", style="bright_green")
        header.append("\n")

        # Status counts with glyphs
        header.append(f"✓ {successful} ", style="bright_green")
        header.append(f"⊝ {skipped} ", style="dim yellow")
        header.append(f"✗ {failed}", style="red")

        self.query_one("#overall-progress-header", Static).update(header)

        # Update progress bar
        progress_bar = self.query_one("#overall-progress-bar", ProgressBar)
        progress_bar.update(total=total, progress=processed)


class GameSpotlightWidget(Static):
    """Displays currently scraping game with auto-cycling"""

    games = reactive(list)
    index = reactive(0)

    def on_mount(self) -> None:
        """Set up auto-cycling timer"""
        self.border_title = "Game Spotlight"
        self.games = SAMPLE_GAMES
        self.set_interval(10.0, self.next_game)
        self.update_display()

    def next_game(self) -> None:
        """Advance to next game"""
        if len(self.games) > 0:
            self.index = (self.index + 1) % len(self.games)

    def prev_game(self) -> None:
        """Go to previous game"""
        if len(self.games) > 0:
            self.index = (self.index - 1) % len(self.games)

    def watch_index(self, old_index: int, new_index: int) -> None:
        """Update display when index changes"""
        self.update_display()

    def update_display(self) -> None:
        """Render current game"""
        if not self.games:
            self.update("■ INITIALIZING GAME DATABASE ■")
            return

        game = self.games[self.index]

        # Build display text
        content = Text()
        content.append("Now Scraping: ", style="bold")
        content.append(game["name"], style="bold magenta")
        content.append(f" ({game['year']})", style="cyan")
        content.append("\n\n")

        # First metadata line: Genre and Developer
        content.append("Genre: ", style="dim")
        content.append(game["genre"], style="cyan")
        content.append(" | ", style="dim")
        content.append("Developer: ", style="dim")
        content.append(game["developer"], style="bright_green")
        content.append("\n")

        # Second metadata line: Publisher and Region
        content.append("Publisher: ", style="dim")
        content.append(game.get("publisher", "Unknown"), style="yellow")
        content.append(" | ", style="dim")
        content.append("Region: ", style="dim")
        content.append(game.get("region", "Unknown"), style="cyan")
        content.append("\n")

        # Third metadata line: Players and Rating
        content.append("Players: ", style="dim")
        content.append(game.get("players", "Unknown"), style="bright_green")
        content.append(" | ", style="dim")
        content.append("Rating: ", style="dim")
        content.append(game.get("rating", "N/A"), style="bright_magenta")
        content.append("\n\n")

        # Full synopsis (no truncation with expanded vertical space)
        content.append("Synopsis:\n", style="bold dim")
        content.append(game["synopsis"], style="white")
        content.append("\n")

        # Navigation hint
        nav_text = f"({self.index + 1}/{len(self.games)})"
        content.append("\n" + " " * (60 - len(nav_text)), style="dim")
        content.append(nav_text, style="dim")
        content.append(" [N, B] Navigate", style="dim cyan")

        self.update(content)


def create_inline_progress_bar(progress: int, total: int, width: int = 24) -> str:
    """Create an inline progress bar using block characters"""
    if total == 0:
        filled = 0
    else:
        filled = int((progress / total) * width)

    bar = "█" * filled + "░" * (width - filled)
    return bar


class CurrentSystemOperations(Container):
    """Displays detailed progress for the current system"""

    def compose(self) -> ComposeResult:
        # Hashing section
        yield Static(id="hashing-content")

        # Cache section
        yield Rule(line_style="heavy")
        yield Static(id="cache-content")

        # Gamelist section
        yield Rule(line_style="heavy")
        yield Static(id="gamelist-content")

        # API section
        yield Rule(line_style="heavy")
        yield Static(id="api-content")

        # Media section
        yield Rule(line_style="heavy")
        yield Static(id="media-content")

    def on_mount(self) -> None:
        """Initialize system operations display"""
        self.border_title = CURRENT_SYSTEM["fullname"]
        self.update_display()

    def update_display(self) -> None:
        """Render current system operations"""
        sys = CURRENT_SYSTEM
        account = ACCOUNT_INFO

        # Hashing section
        hash_data = sys["hashing"]
        hash_pct = (hash_data["completed"] / hash_data["total"] * 100) if hash_data["total"] > 0 else 0
        hash_content = Text()
        hash_content.append("Hashing", style="bold cyan")

        # Show spinner if hashing is in progress
        if hash_data.get("in_progress", False):
            spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
            spinner = spinner_chars[hash_data["completed"] % len(spinner_chars)]
            hash_content.append(f" {spinner}", style="bright_magenta")

        hash_content.append(f"\n{hash_data['completed']}/{hash_data['total']} ", style="white")
        hash_content.append(f"({hash_pct:.1f}%)", style="bright_green")

        # Show skipped count if any
        if hash_data.get("skipped", 0) > 0:
            hash_content.append(f" ⊝ {hash_data['skipped']}", style="dim yellow")

        self.query_one("#hashing-content", Static).update(hash_content)

        # Cache section
        cache = sys["cache"]
        cache_hit_rate = cache["hit_rate"]
        cache_content = Text()
        cache_content.append("Cache\n", style="bold cyan")
        cache_content.append(f"{cache_hit_rate:.1%} Hit Rate", style="bright_magenta")
        cache_content.append(f"\n✓ {cache['existing']} ", style="white")
        cache_content.append(f"+ {cache['added']}", style="bright_green")
        self.query_one("#cache-content", Static).update(cache_content)

        # Gamelist section
        gl = sys["gamelist"]
        gamelist_content = Text()
        gamelist_content.append("Gamelist\n", style="bold cyan")
        gamelist_content.append(f"✓ {gl['existing']} ", style="white")
        gamelist_content.append(f"+ {gl['added']} ", style="bright_green")
        gamelist_content.append(f"− {gl['removed']} ", style="red")
        gamelist_content.append(f"↻ {gl['updated']}", style="yellow")
        self.query_one("#gamelist-content", Static).update(gamelist_content)

        # API section
        api = sys["api"]
        api_content = Text()
        api_content.append("API\n", style="bold cyan")

        # Metadata requests
        metadata = api["metadata"]
        spinner_chars = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        metadata_spinner = spinner_chars[metadata["in_flight"] % len(spinner_chars)]
        api_content.append("Metadata: ", style="dim")
        if metadata["in_flight"] > 0:
            api_content.append(f"{metadata_spinner} {metadata['in_flight']} ", style="yellow")
        else:
            api_content.append("Idle ", style="dim")
        api_content.append(f"✓ {metadata['total']}\n", style="bright_green")

        # Search requests
        search = api["search"]
        search_spinner = spinner_chars[search["in_flight"] % len(spinner_chars)]
        api_content.append("Search: ", style="dim")
        if search["in_flight"] > 0:
            api_content.append(f"{search_spinner} {search['in_flight']} ", style="yellow")
        else:
            api_content.append("Idle ", style="dim")
        api_content.append(f"✓ {search['total']}", style="bright_green")

        self.query_one("#api-content", Static).update(api_content)

        # Media section
        media = sys["media"]
        media_content = Text()
        media_content.append("Media\n", style="bold cyan")

        # Media downloads
        if media["in_flight"] > 0:
            media_content.append(f"⬇ {media['in_flight']} ", style="yellow")
        media_content.append(f"✓ {media['downloaded']} ", style="bright_green")
        media_content.append(f"✓ {media['validated']} ", style="cyan")
        media_content.append(f"✗ {media['failed']}", style="red")

        self.query_one("#media-content", Static).update(media_content)


class PerformancePanel(Container):
    """Displays performance metrics with sparklines"""

    def on_mount(self) -> None:
        """Initialize performance panel"""
        self.border_title = "Performance Metrics"

    def compose(self) -> ComposeResult:
        throughput_spark = create_sparkline(THROUGHPUT_HISTORY, width=30)
        api_spark = create_sparkline(API_RATE_HISTORY, width=30)

        account = ACCOUNT_INFO
        quota_pct = (account["quota_used"] / account["quota_limit"] * 100) if account["quota_limit"] > 0 else 0
        quota_bar = create_inline_progress_bar(account["quota_used"], account["quota_limit"], 30)

        yield Static(
            f"[bold]Throughput:[/bold] [green]{throughput_spark}[/green] [cyan]45.2 ROMs/hr[/cyan]",
            id="throughput",
        )
        yield Static(
            f"[bold]API Rate:[/bold]   [yellow]{api_spark}[/yellow] [cyan]12.3 calls/min[/cyan]",
            id="api-rate",
        )
        yield Static(
            f"[bold]Logged in as:[/bold] [bright_magenta]{account['username']}[/bright_magenta] | "
            f"[bold]Threads:[/bold] {account['threads_in_use']}/{account['threads_limit']}",
            id="account-info",
        )
        yield Static(
            f"[bold]API Quota:[/bold] {account['quota_used']}/{account['quota_limit']} ({quota_pct:.1f}%) [yellow]{quota_bar}[/yellow]",
            id="api-quota",
        )
        yield Static(
            f"[bold]System ETA:[/bold] [yellow]{account['system_eta']}[/yellow] | "
            f"[bold]Memory:[/bold] 145 MB | [bold]CPU:[/bold] 12%",
            id="eta-stats",
        )


class FilterableLogWidget(Container):
    """Log viewer with filtering capabilities"""

    log_level = reactive(logging.INFO)
    filter_text = reactive("")

    def compose(self) -> ComposeResult:
        yield Input(placeholder="Filter logs (regex)...", id="log-filter")
        yield RichLog(id="logs", highlight=True, wrap=True, markup=True)

    def on_mount(self) -> None:
        """Initialize logs"""
        self.border_title = "Logs (Filter: 1-ERROR, 2-WARNING, 3-INFO, 4-DEBUG)"
        self.load_logs()

    def load_logs(self) -> None:
        """Load sample logs into the RichLog widget"""
        log_widget = self.query_one("#logs", RichLog)
        log_widget.clear()

        for level, message in SAMPLE_LOGS:
            if level >= self.log_level:
                self.append_log(level, message)

    def append_log(self, level: int, message: str) -> None:
        """Append a single log entry"""
        # Check filter
        if self.filter_text:
            try:
                if not re.search(self.filter_text, message, re.IGNORECASE):
                    return
            except re.error:
                pass  # Invalid regex, skip filtering

        log_widget = self.query_one("#logs", RichLog)

        # Color by level
        level_name = logging.getLevelName(level)
        colors = {
            "DEBUG": "dim white",
            "INFO": "cyan",
            "WARNING": "yellow",
            "ERROR": "red",
        }
        color = colors.get(level_name, "white")

        text = Text()
        text.append(f"[{level_name:8}] ", style=color)
        text.append(message)

        log_widget.write(text)

        # Notify on WARNING/ERROR if Overview tab is active
        if level >= logging.WARNING:
            try:
                if self.app.current_tab == "overview":
                    severity = "error" if level >= logging.ERROR else "warning"
                    # Truncate long messages for notification
                    short_message = message[:60] + "..." if len(message) > 60 else message
                    self.app.notify(
                        f"{level_name}: {short_message}",
                        severity=severity,
                        timeout=5
                    )
            except Exception:
                pass

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle filter text changes"""
        if event.input.id == "log-filter":
            self.filter_text = event.value
            self.load_logs()  # Rebuild with filter

    def set_log_level(self, level: int) -> None:
        """Set log level filter"""
        self.log_level = level
        self.load_logs()  # Rebuild with new level


class ActiveRequestsTable(Container):
    """Table showing currently active requests"""

    def compose(self) -> ComposeResult:
        table = DataTable()
        yield table

    def on_mount(self) -> None:
        """Initialize table"""
        self.border_title = "Active Requests (3/4 concurrent)"
        table = self.query_one(DataTable)
        table.add_columns("ROM", "Stage", "Duration", "Status", "Retry", "Last Failure")

        for req in SAMPLE_ACTIVE_REQUESTS:
            table.add_row(
                req["rom"],
                req["stage"],
                f"{req['duration']:.1f}s",
                req["status"],
                str(req["retry"]),
                req["last_failure"]
            )


class QueueStatusPanel(Container):
    """Shows work queue statistics"""

    def compose(self) -> ComposeResult:
        yield Static(
            "[bold]QUEUE STATUS[/bold]\nPending: 47 | Processed: 150 | Failed: 5 | Retries: 2",
            id="queue-stats",
        )


class SystemDetailPanel(VerticalScroll):
    """Detailed statistics panel for selected system"""

    selected_system = reactive("NES")

    def compose(self) -> ComposeResult:
        yield Static(id="system-detail-content")

    def on_mount(self) -> None:
        """Initialize detail panel"""
        self.update_details(self.selected_system)

    def watch_selected_system(self, old: str, new: str) -> None:
        """Update detail panel when system changes"""
        # Update border title to match selected system
        if new in SAMPLE_SYSTEMS:
            self.border_title = SAMPLE_SYSTEMS[new]["fullname"]
        self.update_details(new)

    def update_details(self, system_key: str) -> None:
        """Render details for the selected system"""
        if system_key not in SAMPLE_SYSTEMS:
            return

        system = SAMPLE_SYSTEMS[system_key]
        content = Text()

        # ROM Statistics
        content.append("● ROM STATISTICS\n", style="bold cyan")
        roms = system["roms"]
        content.append(f"  Total:      {roms['total']:>4}\n", style="white")
        content.append(f"  Successful: {roms['successful']:>4}\n", style="bright_green")
        content.append(f"  Failed:     {roms['failed']:>4}\n", style="red")
        content.append(f"  Skipped:    {roms['skipped']:>4}\n\n", style="yellow")

        # Media Statistics
        content.append("● MEDIA DOWNLOADS\n", style="bold cyan")
        for media_type, stats in system["media"].items():
            total = stats["downloaded"] + stats["skipped"]
            content.append(f"  {media_type}:\n", style="bright_magenta")
            content.append(f"    Downloaded: {stats['downloaded']:>3}  ", style="bright_green")
            content.append(f"Skipped: {stats['skipped']:>3}  ", style="yellow")
            content.append(f"Validated: {stats['validated']:>3}  ", style="cyan")
            content.append(f"Failed: {stats['failed']:>2}\n", style="red")
        content.append("\n")

        # API Transactions
        content.append("● API TRANSACTIONS\n", style="bold cyan")
        api = system["api"]
        content.append(f"  Info Calls:   {api['info_calls']:>4}\n", style="white")
        content.append(f"  Search Calls: {api['search_calls']:>4}\n", style="white")
        content.append(f"  Media Calls:  {api['media_calls']:>4}\n\n", style="white")

        # Gamelist Statistics
        content.append("● GAMELIST STATISTICS\n", style="bold cyan")
        gamelist = system["gamelist"]
        content.append(f"  Existing: {gamelist['existing']:>4}\n", style="white")
        content.append(f"  Added:    {gamelist['added']:>4}\n", style="bright_green")
        content.append(f"  Updated:  {gamelist['updated']:>4}\n", style="cyan")
        content.append(f"  Removed:  {gamelist['removed']:>4}\n\n", style="red")

        # Cache Statistics
        content.append("● CACHE STATISTICS\n", style="bold cyan")
        cache = system["cache"]
        content.append(f"  Existing:  {cache['existing']:>4}\n", style="white")
        content.append(f"  New:       {cache['new']:>4}\n", style="bright_green")
        content.append(f"  Removed:   {cache['removed']:>4}\n", style="red")
        content.append(f"  Hit Rate:  {cache['hit_rate']:.1%}\n\n", style="bright_magenta")

        # Summary Log
        content.append("● SUMMARY LOG\n", style="bold cyan")
        content.append(system["summary_log"], style="dim white")

        # Update the content Static
        self.query_one("#system-detail-content", Static).update(content)


# ============================================================================
# Tab Containers
# ============================================================================


class OverviewTab(Container):
    """Overview tab with game spotlight and performance metrics"""

    def compose(self) -> ComposeResult:
        with Horizontal():
            # Left column (25% width): Progress and system operations
            with Vertical(id="left-column"):
                yield OverallProgressWidget(id="overall-progress")
                yield CurrentSystemOperations(id="current-system")

            # Right column (75% width): Spotlight and performance
            with Vertical(id="right-column"):
                yield GameSpotlightWidget(id="spotlight")
                yield PerformancePanel(id="performance")


class DetailsTab(Container):
    """Details tab with logs and active requests"""

    def compose(self) -> ComposeResult:
        yield FilterableLogWidget(id="filterable-logs")
        yield ActiveRequestsTable(id="active-requests")


class SystemsTab(Container):
    """Systems tab with tree view and detailed stats"""

    def compose(self) -> ComposeResult:
        with Horizontal():
            # Left side: Tree view of systems
            tree = Tree("Systems", id="systems-tree")
            tree.show_root = True
            tree.show_guides = True
            yield tree

            # Right side: Detail panel
            yield SystemDetailPanel(id="system-detail-panel")

    def on_mount(self) -> None:
        """Populate the tree with systems"""
        tree = self.query_one("#systems-tree", Tree)
        tree.border_title = "System Queue"

        # Add systems to tree
        for system_key, system_data in SAMPLE_SYSTEMS.items():
            roms = system_data["roms"]
            total = roms["total"]
            successful = roms["successful"]

            # Calculate progress
            progress_pct = (successful / total * 100) if total > 0 else 0

            # Status icon
            if progress_pct == 100:
                status = "✓"
            elif progress_pct > 0:
                status = "⚡"
            else:
                status = "⏸"

            # Add node with status
            label = f"{status} {system_data['fullname']} ({successful}/{total})"
            tree.root.add_leaf(label, data=system_key)

        # Expand root by default
        tree.root.expand()

        # Select first system by default
        if tree.root.children:
            tree.select_node(tree.root.children[0])
            # Trigger detail panel update
            detail_panel = self.query_one("#system-detail-panel", SystemDetailPanel)
            detail_panel.selected_system = "NES"

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        """Handle tree selection"""
        if event.node.data:
            detail_panel = self.query_one("#system-detail-panel", SystemDetailPanel)
            detail_panel.selected_system = event.node.data


class ConfigTab(Container):
    """Config tab with runtime settings controls in two-column layout"""

    def compose(self) -> ComposeResult:
        # Two-column layout
        with Horizontal(id="config-columns"):
            # Left Column: API and Runtime Settings
            with VerticalScroll(id="config-left-column"):
                # API Settings
                with Container(classes="config-section", id="api-settings-section"):
                    with Horizontal(classes="config-row"):
                        yield Label("Request Timeout (s):", classes="config-label")
                        yield Select(
                            [("15", 15), ("30", 30), ("45", 45), ("60", 60), ("90", 90)],
                            value=30,
                            id="request-timeout",
                            compact=True
                        )

                    with Horizontal(classes="config-row"):
                        yield Label("Max Retries:", classes="config-label")
                        yield Select(
                            [("0", 0), ("1", 1), ("2", 2), ("3", 3), ("4", 4), ("5", 5)],
                            value=3,
                            id="max-retries",
                            compact=True
                        )

                    with Horizontal(classes="config-row"):
                        yield Label("Retry Backoff (s):", classes="config-label")
                        yield Select(
                            [("1", 1), ("3", 3), ("5", 5), ("10", 10)],
                            value=5,
                            id="retry-backoff",
                            compact=True
                        )

                # Runtime Settings
                with Container(classes="config-section", id="runtime-settings-section"):
                    with Horizontal(classes="config-row"):
                        yield Label("CRC Size Limit:", classes="config-label")
                        yield Select(
                            [("0.5 GiB", 0.5), ("1 GiB", 1), ("2 GiB", 2), ("4 GiB", 4), ("None", 0)],
                            value=1,
                            id="crc-size-limit",
                            compact=True
                        )

                    with Horizontal(classes="config-row"):
                        yield Label("Override Limits:", classes="config-label")
                        yield Switch(value=False, id="rate-limit-override")

                    with Horizontal(classes="config-row"):
                        yield Label("  Max Workers:", classes="config-label")
                        yield Select(
                            [("1", 1), ("2", 2), ("3", 3), ("4", 4), ("5", 5)],
                            value=1,
                            id="override-max-workers",
                            disabled=True,
                            compact=True
                        )

            # Right Column: Logging and Search Settings
            with VerticalScroll(id="config-right-column"):
                # Logging Settings
                with Container(classes="config-section", id="logging-settings-section"):
                    with Horizontal(classes="config-row"):
                        yield Label("Log Level:", classes="config-label")
                        yield Select(
                            [("DEBUG", "DEBUG"), ("INFO", "INFO"), ("WARNING", "WARNING"), ("ERROR", "ERROR")],
                            value="INFO",
                            id="log-level-select",
                            compact=True
                        )

                # Search Settings
                with Container(classes="config-section", id="search-settings-section"):
                    with Horizontal(classes="config-row"):
                        yield Label("Search Fallback:", classes="config-label")
                        yield Switch(value=False, id="enable-search-fallback")

                    with Horizontal(classes="config-row"):
                        yield Label("Confidence:", classes="config-label")
                        yield Select(
                            [("50%", 0.5), ("60%", 0.6), ("70%", 0.7), ("80%", 0.8), ("90%", 0.9)],
                            value=0.7,
                            id="confidence-threshold",
                            compact=True
                        )

                    with Horizontal(classes="config-row"):
                        yield Label("Max Results:", classes="config-label")
                        yield Select(
                            [("1", 1), ("3", 3), ("5", 5), ("7", 7), ("10", 10)],
                            value=5,
                            id="max-search-results",
                            compact=True
                        )

                    with Horizontal(classes="config-row"):
                        yield Label("Interactive:", classes="config-label")
                        yield Switch(value=False, id="interactive-search")

    def on_mount(self) -> None:
        """Set border titles for config sections"""
        self.query_one("#api-settings-section", Container).border_title = "API Settings"
        self.query_one("#runtime-settings-section", Container).border_title = "Runtime Settings"
        self.query_one("#logging-settings-section", Container).border_title = "Logging Settings"
        self.query_one("#search-settings-section", Container).border_title = "Search Settings"

    def on_switch_changed(self, event: Switch.Changed) -> None:
        """Handle switch changes"""
        # Enable/disable rate limit override fields
        if event.switch.id == "rate-limit-override":
            try:
                self.query_one("#override-max-workers", Select).disabled = not event.value
                self.query_one("#override-rpm", Select).disabled = not event.value
                self.query_one("#override-quota", Select).disabled = not event.value
            except Exception:
                pass

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle select dropdown changes"""
        # If log filter changed, update the filterable log widget
        if event.select.id == "log-level-select":
            try:
                log_widget = self.app.query_one(FilterableLogWidget)
                # Convert string level to numeric
                level_map = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40}
                log_widget.set_log_level(level_map.get(event.value, 20))
            except Exception:
                pass


# ============================================================================
# Confirmation Dialogs
# ============================================================================


class ConfirmDialog(ModalScreen):
    """Generic confirmation dialog"""

    CSS = """
    ConfirmDialog {
        align: center middle;
    }

    #confirm-dialog {
        width: 60;
        height: 12;
        border: thick $warning;
        background: $surface;
    }

    #confirm-header {
        dock: top;
        height: 3;
        background: $warning;
        color: $text;
        padding: 1 2;
    }

    #confirm-message {
        height: 1fr;
        padding: 2;
        content-align: center middle;
    }

    #confirm-buttons {
        dock: bottom;
        height: 3;
        background: $surface-darken-1;
        padding: 0 2;
    }

    #confirm-buttons Button {
        margin: 0 1;
    }
    """

    def __init__(self, title: str, message: str, confirm_variant: str = "error"):
        super().__init__()
        self.dialog_title = title
        self.dialog_message = message
        self.confirm_variant = confirm_variant

    def compose(self) -> ComposeResult:
        with Container(id="confirm-dialog"):
            yield Static(f"[bold]{self.dialog_title}[/bold]", id="confirm-header")
            yield Static(self.dialog_message, id="confirm-message")

            with Horizontal(id="confirm-buttons"):
                yield Button("Yes", variant=self.confirm_variant, id="yes-btn")
                yield Button("No", variant="primary", id="no-btn")

    def on_mount(self) -> None:
        """Focus the No button by default (safer)"""
        self.query_one("#no-btn", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "yes-btn":
            self.dismiss(True)
        elif event.button.id == "no-btn":
            self.dismiss(False)

    def on_key(self, event) -> None:
        """Handle keyboard shortcuts"""
        if event.key == "y":
            self.dismiss(True)
        elif event.key == "n" or event.key == "escape":
            self.dismiss(False)


class QuitConfirmDialog(ModalScreen):
    """Confirmation dialog for quitting the application"""

    CSS = """
    QuitConfirmDialog {
        align: center middle;
    }

    #quit-dialog {
        width: 70;
        height: 18;
        border: thick $error;
        background: $surface;
    }

    #quit-header {
        dock: top;
        height: 3;
        background: $error;
        color: white;
        padding: 1 2;
    }

    #quit-content {
        height: 1fr;
        padding: 2;
    }

    #quit-stats {
        background: $surface-darken-1;
        border: solid $accent;
        padding: 1 2;
        margin: 0 0 1 0;
    }

    #quit-warning {
        color: $warning;
        margin: 1 0;
    }

    #quit-buttons {
        dock: bottom;
        height: 3;
        background: $surface-darken-1;
        padding: 0 2;
    }

    #quit-buttons Button {
        margin: 0 1;
    }
    """

    def __init__(self, current_system: str, processed: int, total: int):
        super().__init__()
        self.current_system = current_system
        self.processed = processed
        self.total = total

    def compose(self) -> ComposeResult:
        with Container(id="quit-dialog"):
            yield Static("[bold]⚠ Confirm Quit[/bold]", id="quit-header")

            with Container(id="quit-content"):
                with Container(id="quit-stats"):
                    stats = Text()
                    stats.append("Current Progress:\n", style="bold cyan")
                    stats.append(f"  System: ", style="white")
                    stats.append(f"{self.current_system}\n", style="bright_magenta")
                    stats.append(f"  Processed: ", style="white")
                    stats.append(f"{self.processed}/{self.total} ROMs\n", style="cyan")
                    remaining = self.total - self.processed
                    stats.append(f"  Remaining: ", style="white")
                    stats.append(f"{remaining} ROMs", style="yellow")
                    yield Static(stats)

                yield Static(
                    "[bold]Are you sure you want to quit?[/bold]\n\n"
                    "• Unsaved progress will be lost\n"
                    "• The current scraping session will be interrupted",
                    id="quit-warning"
                )

            with Horizontal(id="quit-buttons"):
                yield Button("Quit [Y]", variant="error", id="quit-yes-btn")
                yield Button("Continue Scraping [N]", variant="success", id="quit-no-btn")

    def on_mount(self) -> None:
        """Focus the No button by default (safer)"""
        self.query_one("#quit-no-btn", Button).focus()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "quit-yes-btn":
            self.dismiss(True)
        elif event.button.id == "quit-no-btn":
            self.dismiss(False)

    def on_key(self, event) -> None:
        """Handle keyboard shortcuts"""
        if event.key == "y":
            self.dismiss(True)
        elif event.key == "n" or event.key == "escape":
            self.dismiss(False)


# ============================================================================
# Interactive Search Screen
# ============================================================================


class SearchResultDialog(ModalScreen):
    """Modal dialog for selecting search results during interactive search"""

    CSS = """
    SearchResultDialog {
        align: center middle;
    }

    #search-dialog {
        width: 90;
        height: 30;
        border: thick $primary;
        background: $surface;
    }

    #search-header {
        dock: top;
        height: 3;
        background: $primary;
        color: white;
        padding: 1 2;
    }

    #rom-info {
        dock: top;
        height: 3;
        background: $surface-darken-1;
        padding: 1 2;
    }

    #results-container {
        height: 1fr;
        border: solid $secondary;
        background: $surface-darken-1;
    }

    #result-details {
        dock: right;
        width: 35;
        border-left: solid $accent;
        background: $surface;
        padding: 1 2;
    }

    #search-results {
        width: 1fr;
        padding: 1;
    }

    #action-buttons {
        dock: bottom;
        height: 3;
        background: $surface-darken-1;
        padding: 0 2;
    }

    .result-item {
        padding: 0 1;
        height: 3;
    }

    .result-item:hover {
        background: $accent 20%;
    }

    ListView > .result-item--highlight {
        background: $primary;
    }
    """

    def __init__(self, rom_filename: str, search_results: List[dict]):
        super().__init__()
        self.rom_filename = rom_filename
        self.search_results = search_results
        self.selected_index = 0

    def compose(self) -> ComposeResult:
        with Container(id="search-dialog"):
            yield Static("[bold]Interactive Search - Match Required[/bold]", id="search-header")
            yield Static(f"[bold]ROM File:[/bold] [cyan]{self.rom_filename}[/cyan]", id="rom-info")

            with Horizontal(id="results-container"):
                with Container(id="search-results"):
                    yield ListView(*self._create_result_items(), id="result-list")

                yield Static(id="result-details")

            with Horizontal(id="action-buttons"):
                yield Button("Select [Enter]", variant="primary", id="select-btn")
                yield Button("Skip ROM [S]", variant="warning", id="skip-btn")
                yield Button("Manual Search [M]", id="manual-btn")
                yield Button("Cancel [Esc]", variant="error", id="cancel-btn")

    def _create_result_items(self) -> list:
        """Create ListItem widgets for each search result"""
        items = []
        for idx, result in enumerate(self.search_results):
            confidence_pct = result["confidence"] * 100

            # Confidence color coding
            if confidence_pct >= 90:
                conf_color = "bright_green"
            elif confidence_pct >= 75:
                conf_color = "yellow"
            else:
                conf_color = "red"

            text = Text()
            text.append(f"{idx + 1}. ", style="dim")
            text.append(f"{result['name']}", style="bold cyan")
            text.append(f" ({result['year']}) ", style="white")
            text.append(f"[{result['region']}] ", style="bright_magenta")
            text.append(f"{confidence_pct:.0f}%", style=conf_color)

            item = ListItem(Static(text), classes="result-item")
            items.append(item)

        return items

    def on_mount(self) -> None:
        """Update detail panel when mounted"""
        self.update_details(0)

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        """Update detail panel when selection changes"""
        self.selected_index = event.list_view.index
        self.update_details(self.selected_index)

    def update_details(self, index: int) -> None:
        """Update the detail panel with selected result info"""
        if index < 0 or index >= len(self.search_results):
            return

        result = self.search_results[index]
        details = Text()

        details.append("══ Match Details ══\n\n", style="bold magenta")

        details.append("Game ID: ", style="bold cyan")
        details.append(f"{result['id']}\n", style="white")

        details.append("Title: ", style="bold cyan")
        details.append(f"{result['name']}\n", style="white")

        details.append("Year: ", style="bold cyan")
        details.append(f"{result['year']}\n", style="white")

        details.append("Region: ", style="bold cyan")
        details.append(f"{result['region']}\n", style="bright_magenta")

        details.append("Publisher: ", style="bold cyan")
        details.append(f"{result['publisher']}\n", style="white")

        details.append("Developer: ", style="bold cyan")
        details.append(f"{result['developer']}\n", style="white")

        details.append("Players: ", style="bold cyan")
        details.append(f"{result['players']}\n", style="white")

        confidence_pct = result["confidence"] * 100
        if confidence_pct >= 90:
            conf_style = "bold bright_green"
        elif confidence_pct >= 75:
            conf_style = "bold yellow"
        else:
            conf_style = "bold red"

        details.append("\nConfidence: ", style="bold cyan")
        details.append(f"{confidence_pct:.1f}%", style=conf_style)

        self.query_one("#result-details", Static).update(details)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "select-btn":
            selected_result = self.search_results[self.selected_index]
            self.dismiss(("selected", selected_result))
        elif event.button.id == "skip-btn":
            self.dismiss(("skip", None))
        elif event.button.id == "manual-btn":
            self.dismiss(("manual", None))
        elif event.button.id == "cancel-btn":
            self.dismiss(("cancel", None))

    def on_key(self, event) -> None:
        """Handle keyboard shortcuts"""
        if event.key == "enter":
            selected_result = self.search_results[self.selected_index]
            self.dismiss(("selected", selected_result))
        elif event.key == "s":
            self.dismiss(("skip", None))
        elif event.key == "m":
            self.dismiss(("manual", None))
        elif event.key == "escape":
            self.dismiss(("cancel", None))


# ============================================================================
# Main Application
# ============================================================================


class TextualMockupApp(App):
    """Curateur Textual UI Mockup"""

    CSS_PATH = "textual_theme.tcss"

    # Track current active tab
    current_tab = reactive("overview")

    BINDINGS = [
        Binding("ctrl+q", "request_quit", "Quit", show=True),
        Binding("b", "prev_game", "Back", show=False),
        Binding("n", "next_game", "Next", show=False),
        Binding("ctrl+s", "skip_system", "Skip System", show=True),
        Binding("1", "filter_logs(40)", "1:ERROR", show=False),
        Binding("2", "filter_logs(30)", "2:WARN", show=False),
        Binding("3", "filter_logs(20)", "3:INFO", show=False),
        Binding("4", "filter_logs(10)", "4:DEBUG", show=False),
        Binding("i", "show_search_dialog", "Interactive Search", show=True),
        Binding("l", "simulate_log", "Simulate Log", show=False),
    ]

    def compose(self) -> ComposeResult:
        """Compose the application layout"""
        yield Header(show_clock=True)

        with TabbedContent(initial="overview"):
            with TabPane("Overview", id="overview"):
                yield OverviewTab()
            with TabPane("Details", id="details"):
                yield DetailsTab()
            with TabPane("Systems", id="systems"):
                yield SystemsTab()
            with TabPane("Config", id="config"):
                yield ConfigTab()

        yield Footer()

    def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
        """Track which tab is currently active"""
        self.current_tab = event.tab.id

    def action_filter_logs(self, level: int) -> None:
        """Filter logs by level (only available on Details tab)"""
        # Show different notification based on current tab
        if self.current_tab != "details":
            self.notify(
                "Log filtering is only available on the Details tab",
                severity="warning",
                timeout=3
            )
            return

        try:
            log_widget = self.query_one(FilterableLogWidget)
            log_widget.set_log_level(level)

            level_name = logging.getLevelName(level)
            self.notify(f"Log filter set to: {level_name}", timeout=2)
        except Exception:
            pass

    def action_prev_game(self) -> None:
        """Navigate to previous game in spotlight"""
        if self.current_tab != "overview":
            self.notify(
                "Game navigation is only available on the Overview tab",
                severity="warning",
                timeout=3
            )
            return

        try:
            spotlight = self.query_one(GameSpotlightWidget)
            spotlight.prev_game()
        except Exception:
            pass

    def action_next_game(self) -> None:
        """Navigate to next game in spotlight"""
        if self.current_tab != "overview":
            self.notify(
                "Game navigation is only available on the Overview tab",
                severity="warning",
                timeout=3
            )
            return

        try:
            spotlight = self.query_one(GameSpotlightWidget)
            spotlight.next_game()
        except Exception:
            pass

    def action_simulate_log(self) -> None:
        """Simulate a new log entry (demo feature)"""
        import random

        test_logs = [
            (logging.WARNING, "API rate limit approaching threshold (92%)"),
            (logging.ERROR, "Failed to download screenshot for mario_bros.zip"),
            (logging.WARNING, "Retrying API request after 429 Too Many Requests"),
            (logging.ERROR, "ROM hash mismatch detected: zelda.zip"),
            (logging.WARNING, "Cache miss for metadata request"),
            (logging.ERROR, "Unable to parse gamelist.xml - malformed XML"),
        ]

        level, message = random.choice(test_logs)

        try:
            log_widget = self.query_one(FilterableLogWidget)
            log_widget.append_log(level, message)
        except Exception:
            self.notify("Log widget not available (Details tab not loaded)", severity="warning", timeout=3)

    def action_show_search_dialog(self) -> None:
        """Show interactive search dialog (demo)"""
        rom_filename = "castlevania3_bad_name.zip"

        def handle_result(result: tuple) -> None:
            """Handle the search dialog result"""
            action, data = result
            if action == "selected":
                self.notify(
                    f"Selected: {data['name']} ({data['year']}) - Confidence: {data['confidence']*100:.0f}%",
                    severity="information",
                    timeout=5,
                )
            elif action == "skip":
                self.notify("ROM skipped", severity="warning", timeout=3)
            elif action == "manual":
                self.notify("Manual search requested (not implemented in mockup)", timeout=3)
            elif action == "cancel":
                self.notify("Search cancelled", timeout=2)

        # Show the search dialog
        self.push_screen(
            SearchResultDialog(rom_filename, SAMPLE_SEARCH_RESULTS),
            handle_result
        )

    def action_request_quit(self) -> None:
        """Quit the application"""
        self.exit()

    def action_skip_system(self) -> None:
        """Skip current system"""
        current_system = CURRENT_SYSTEM["fullname"]
        self.notify(
            f"Skipping {current_system} - moving to next system",
            severity="warning",
            timeout=3
        )


if __name__ == "__main__":
    app = TextualMockupApp()
    app.run()
