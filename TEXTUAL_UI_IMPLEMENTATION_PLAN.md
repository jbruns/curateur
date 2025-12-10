# Textual UI Implementation Plan

**Project:** Curateur ROM Scraper
**Goal:** Replace Rich-based console UI with Textual framework UI
**Estimated Duration:** 20 days
**Status:** Planning Complete

---

## Executive Summary

This plan outlines the complete replacement of the current Rich-based console UI (`console_ui.py`) with a modern Textual framework UI. The implementation follows a structured approach with an event-driven architecture, enabling clean separation between the scraping engine and UI layer.

**Key Decisions:**
- ✅ Complete replacement (no side-by-side support)
- ✅ Event/callback system for data flow
- ✅ Core tabs only (Overview, Details, Systems) - Config tab deferred
- ✅ Full interactive search dialog implementation

---

## Phase 1: Event System Architecture

### 1.1 Event Type Definitions

**File:** `curateur/ui/events.py` (NEW)

Create typed events for all UI updates:

```python
from dataclasses import dataclass
from typing import Optional, Literal
from datetime import datetime

@dataclass
class SystemStartedEvent:
    system_name: str
    system_fullname: str
    total_roms: int
    current_index: int
    total_systems: int

@dataclass
class ROMProgressEvent:
    rom_name: str
    system: str
    status: Literal['scanning', 'hashing', 'querying', 'downloading', 'complete', 'failed', 'skipped']
    detail: Optional[str] = None
    progress: Optional[float] = None  # 0.0-1.0

@dataclass
class HashingProgressEvent:
    completed: int
    total: int
    in_progress: bool
    skipped: int = 0

@dataclass
class APIActivityEvent:
    metadata_in_flight: int
    metadata_total: int
    search_in_flight: int
    search_total: int

@dataclass
class MediaDownloadEvent:
    media_type: str
    rom_name: str
    status: Literal['downloading', 'complete', 'failed']
    progress: Optional[float] = None

@dataclass
class LogEntryEvent:
    level: int  # logging.DEBUG, INFO, WARNING, ERROR
    message: str
    timestamp: datetime

@dataclass
class PerformanceUpdateEvent:
    api_quota_used: int
    api_quota_limit: int
    threads_in_use: int
    threads_limit: int
    throughput_history: list[int]  # ROMs/hour
    api_rate_history: list[int]    # Calls/min

@dataclass
class GameCompletedEvent:
    game_id: str
    title: str
    year: Optional[str]
    genre: Optional[str]
    developer: Optional[str]
    description: Optional[str]
    confidence: float

@dataclass
class SystemCompletedEvent:
    system_name: str
    total_roms: int
    successful: int
    failed: int
    skipped: int
```

### 1.2 Event Bus

**File:** `curateur/ui/event_bus.py` (NEW)

Thread-safe event delivery mechanism:

```python
import asyncio
from typing import Callable, Any
from collections import defaultdict
import logging

class EventBus:
    """Thread-safe event bus for UI updates"""

    def __init__(self):
        self._subscribers = defaultdict(list)
        self._queue = asyncio.Queue()
        self._logger = logging.getLogger(__name__)

    def subscribe(self, event_type: type, callback: Callable):
        """Subscribe to event type"""
        self._subscribers[event_type].append(callback)

    async def publish(self, event: Any):
        """Publish event (thread-safe from any thread)"""
        await self._queue.put(event)

    def publish_sync(self, event: Any):
        """Publish from sync context"""
        asyncio.create_task(self.publish(event))

    async def process_events(self):
        """Process events in UI thread"""
        while True:
            event = await self._queue.get()
            event_type = type(event)

            for callback in self._subscribers[event_type]:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        await callback(event)
                    else:
                        callback(event)
                except Exception as e:
                    self._logger.error(f"Error in event handler: {e}")
```

**Key Features:**
- Thread-safe event publishing from scraping threads
- Async event processing in UI thread
- Type-based subscription (subscribe by event class)
- Error isolation (handler errors don't crash event loop)

---

## Phase 2: Textual UI Application Structure

### 2.1 Main Textual App

**File:** `curateur/ui/textual_ui.py` (NEW - convert from mockup)

```python
from textual.app import App
from textual.binding import Binding
from curateur.ui.events import *
from curateur.ui.event_bus import EventBus

class CurateurUI(App):
    """Production Textual UI for curateur"""

    CSS_PATH = "textual_theme.tcss"

    BINDINGS = [
        Binding("ctrl+q", "quit_app", "Quit", show=True),
        Binding("ctrl+s", "skip_system", "Skip System", show=True),
        Binding("b", "prev_game", "Back", show=True),
        Binding("n", "next_game", "Next", show=True),
        Binding("i", "show_search_dialog", "Interactive Search", show=True),
    ]

    def __init__(self, config: dict, event_bus: EventBus):
        super().__init__()
        self.config = config
        self.event_bus = event_bus
        self.current_system = None
        self.should_quit = False
        self.should_skip_system = False

    def on_mount(self):
        """Setup event listeners"""
        self.event_bus.subscribe(SystemStartedEvent, self.on_system_started)
        self.event_bus.subscribe(ROMProgressEvent, self.on_rom_progress)
        self.event_bus.subscribe(LogEntryEvent, self.on_log_entry)
        self.event_bus.subscribe(HashingProgressEvent, self.on_hashing_progress)
        self.event_bus.subscribe(APIActivityEvent, self.on_api_activity)
        self.event_bus.subscribe(MediaDownloadEvent, self.on_media_download)
        self.event_bus.subscribe(PerformanceUpdateEvent, self.on_performance_update)
        self.event_bus.subscribe(GameCompletedEvent, self.on_game_completed)
        self.event_bus.subscribe(SystemCompletedEvent, self.on_system_completed)

        # Start event processing task
        self.run_worker(self.event_bus.process_events())

    async def on_system_started(self, event: SystemStartedEvent):
        """Handle system started event"""
        self.current_system = event
        overview_tab = self.query_one(OverviewTab)
        overview_tab.update_current_system(event)

    async def on_rom_progress(self, event: ROMProgressEvent):
        """Handle ROM progress event"""
        overview_tab = self.query_one(OverviewTab)
        overview_tab.update_rom_progress(event)

    async def on_log_entry(self, event: LogEntryEvent):
        """Handle log entry event"""
        details_tab = self.query_one(DetailsTab)
        details_tab.add_log_entry(event)

        # Show notification on Overview tab for WARNING/ERROR
        if event.level >= logging.WARNING:
            if self.current_tab == "overview":
                severity = "error" if event.level >= logging.ERROR else "warning"
                short_msg = event.message[:60] + "..." if len(event.message) > 60 else event.message
                self.notify(f"{logging.getLevelName(event.level)}: {short_msg}", severity=severity, timeout=5)

    # ... other event handlers

    def action_quit_app(self):
        """Quit the application"""
        self.should_quit = True
        self.exit()

    def action_skip_system(self):
        """Skip current system"""
        self.should_skip_system = True
        if self.current_system:
            self.notify(f"Skipping {self.current_system.system_fullname}", severity="warning", timeout=3)
```

### 2.2 Tab Implementations

Convert from mockup to production with event-driven updates:

**OverviewTab** - Current operations, spotlight, performance metrics
**DetailsTab** - Logs with filtering, active requests table
**SystemsTab** - System queue tree with detail panel
**SearchResultDialog** - Interactive search modal

---

## Phase 3: Integration with Workflow Orchestrator

### 3.1 Modify WorkflowOrchestrator

**File:** `curateur/workflow/orchestrator.py`

Add event emissions at all key points:

```python
class WorkflowOrchestrator:
    def __init__(self, ..., event_bus: Optional[EventBus] = None):
        # ... existing init
        self.event_bus = event_bus

    async def scrape_system(self, system: SystemDefinition, ...):
        """Scrape a single system with event emissions"""

        # Emit system started event
        if self.event_bus:
            await self.event_bus.publish(SystemStartedEvent(
                system_name=system.name,
                system_fullname=system.fullname,
                total_roms=len(roms),
                current_index=self.current_system_index,
                total_systems=self.total_systems
            ))

        # Scanning phase
        roms = await self._scan_roms(system)

        # Hashing phase
        for i, rom in enumerate(roms):
            hash_value = await self._hash_rom(rom)

            if self.event_bus:
                await self.event_bus.publish(HashingProgressEvent(
                    completed=i + 1,
                    total=len(roms),
                    in_progress=i < len(roms) - 1,
                    skipped=skipped_count
                ))

        # API querying phase
        for rom in roms_to_query:
            if self.event_bus:
                await self.event_bus.publish(APIActivityEvent(
                    metadata_in_flight=active_queries,
                    metadata_total=total_queries,
                    search_in_flight=active_searches,
                    search_total=total_searches
                ))

            result = await self._query_api(rom)

            if result.success:
                # Emit game completed for spotlight
                await self.event_bus.publish(GameCompletedEvent(
                    game_id=result.api_id,
                    title=result.game_info['name'],
                    year=result.game_info.get('year'),
                    genre=result.game_info.get('genre'),
                    developer=result.game_info.get('developer'),
                    description=result.game_info.get('description'),
                    confidence=1.0
                ))

        # Media downloading phase
        for media_type, rom in media_downloads:
            await self.event_bus.publish(MediaDownloadEvent(
                media_type=media_type,
                rom_name=rom.filename,
                status='downloading',
                progress=0.0
            ))

            # ... download logic

            await self.event_bus.publish(MediaDownloadEvent(
                media_type=media_type,
                rom_name=rom.filename,
                status='complete',
                progress=1.0
            ))

        # Completion
        if self.event_bus:
            await self.event_bus.publish(SystemCompletedEvent(
                system_name=system.name,
                total_roms=total,
                successful=success_count,
                failed=fail_count,
                skipped=skip_count
            ))
```

**Key Emission Points:**
- System start/complete
- ROM scanning progress
- Hashing progress (with skipped count)
- API activity (in-flight metadata and search requests)
- Media downloads (per-type, per-ROM)
- Game completions (for spotlight widget)
- Performance metrics (periodic updates)

### 3.2 Logging Integration

**File:** `curateur/ui/event_log_handler.py` (NEW)

```python
import logging
from datetime import datetime
from curateur.ui.events import LogEntryEvent
from curateur.ui.event_bus import EventBus

class EventLogHandler(logging.Handler):
    """Log handler that emits LogEntryEvent"""

    def __init__(self, event_bus: EventBus):
        super().__init__()
        self.event_bus = event_bus

    def emit(self, record: logging.LogRecord):
        """Emit log record as event"""
        event = LogEntryEvent(
            level=record.levelno,
            message=self.format(record),
            timestamp=datetime.now()
        )
        # Use sync publish since logging can happen from any thread
        self.event_bus.publish_sync(event)
```

**Integration in CLI:**
```python
# In cli.py setup_logging()
if ui_enabled:
    event_log_handler = EventLogHandler(event_bus)
    event_log_handler.setFormatter(formatter)
    logging.root.addHandler(event_log_handler)
```

---

## Phase 4: CLI Integration

### 4.1 Modify cli.py

**File:** `curateur/cli.py`

Replace ConsoleUI initialization with CurateurUI:

```python
async def run_scraper(config: dict, args: argparse.Namespace) -> int:
    """Main scraper execution with Textual UI"""

    # Initialize event bus
    event_bus = EventBus()

    # Initialize Textual UI
    ui_app = CurateurUI(config, event_bus)

    # Run UI in separate task
    ui_task = asyncio.create_task(ui_app.run_async())

    # Wait for UI to be ready
    await asyncio.sleep(0.5)

    # Setup logging with event handler
    _setup_logging(config, event_bus=event_bus)

    try:
        # Initialize components
        connection_pool = ConnectionPoolManager(...)
        throttle_manager = ThrottleManager(...)
        api_client = ScreenScraperClient(...)

        # Initialize orchestrator with event bus
        orchestrator = WorkflowOrchestrator(
            config=config,
            api_client=api_client,
            throttle_manager=throttle_manager,
            event_bus=event_bus,  # NEW
            ...
        )

        # Authenticate
        await event_bus.publish(LogEntryEvent(
            level=logging.INFO,
            message="Authenticating with ScreenScraper...",
            timestamp=datetime.now()
        ))

        user_info = await api_client.get_user_info()

        # Emit performance update with quota
        await event_bus.publish(PerformanceUpdateEvent(
            api_quota_used=user_info['requeststoday'],
            api_quota_limit=user_info['maxrequestsperday'],
            threads_in_use=0,
            threads_limit=user_info['maxthreads'],
            throughput_history=[],
            api_rate_history=[]
        ))

        # Run scraping
        for i, system in enumerate(systems):
            # Check quit signal from UI
            if ui_app.should_quit:
                logger.info("Quit requested by user")
                break

            # Check skip signal from UI
            if ui_app.should_skip_system:
                logger.info(f"Skipping {system.fullname} at user request")
                ui_app.should_skip_system = False
                continue

            result = await orchestrator.scrape_system(system, i, len(systems))

        return 0

    except Exception as e:
        logger.exception("Fatal error during scraping")
        return 1

    finally:
        # Cleanup
        logger.info("Shutting down...")
        await orchestrator.cleanup()
        await ui_app.shutdown()
        ui_task.cancel()
```

**Key Changes:**
- Remove all `console_ui = ConsoleUI(...)` code
- Replace with `event_bus` and `CurateurUI` initialization
- Pass `event_bus` to orchestrator
- Check `ui_app.should_quit` and `ui_app.should_skip_system` flags
- Remove old keyboard listener setup

---

## Phase 5: Implementation Order

### Step 1: Foundation (Days 1-2)

**Tasks:**
- [ ] Create `curateur/ui/events.py` with all event dataclasses
- [ ] Create `curateur/ui/event_bus.py` with EventBus implementation
- [ ] Create `curateur/ui/event_log_handler.py` for logging integration
- [ ] Write unit tests for EventBus:
  - [ ] Test subscription/publish
  - [ ] Test thread safety
  - [ ] Test error isolation in handlers

**Deliverables:**
- Functioning event system with tests
- Can publish/subscribe to typed events
- Thread-safe from any context

---

### Step 2: UI Shell (Days 3-4)

**Tasks:**
- [ ] Copy `textual_mockup.py` → `textual_ui.py`
- [ ] Remove all sample data (SAMPLE_LOGS, CURRENT_SYSTEM, etc.)
- [ ] Add `event_bus` parameter to `__init__`
- [ ] Implement event subscription in `on_mount()`
- [ ] Create stub event handlers (just log receipt)
- [ ] Add `should_quit` and `should_skip_system` flags
- [ ] Test UI launches and displays empty tabs

**Deliverables:**
- UI shell that launches without errors
- Can subscribe to events
- Keyboard shortcuts work (quit, skip)

---

### Step 3: Overview Tab (Days 5-7)

**Tasks:**
- [ ] Convert `CurrentSystemOperations` to use `SystemStartedEvent`
  - [ ] Update header with system name
  - [ ] Update ROM counters
  - [ ] Update progress percentages
- [ ] Convert `OverallProgress` to use `SystemCompletedEvent`
  - [ ] Track systems completed
  - [ ] Aggregate ROM stats
- [ ] Implement `HashingProgressEvent` handler
  - [ ] Update hashing section with spinner
  - [ ] Show completed/total/skipped
- [ ] Implement `APIActivityEvent` handler
  - [ ] Update API section with in-flight counts
- [ ] Implement `MediaDownloadEvent` handler
  - [ ] Update Media section with download progress
- [ ] Implement `GameSpotlightWidget` with `GameCompletedEvent`
  - [ ] Queue games as they complete
  - [ ] Auto-cycle every 10 seconds
  - [ ] Support B/N keyboard navigation
- [ ] Implement `PerformancePanel` with `PerformanceUpdateEvent`
  - [ ] Update API quota progress bar
  - [ ] Update thread counts
  - [ ] Update throughput/rate sparklines

**Deliverables:**
- Overview tab fully functional with real data
- All sections update in real-time
- Spotlight cycles through completed games
- Performance metrics displayed

---

### Step 4: Details Tab (Days 8-9)

**Tasks:**
- [ ] Implement `FilterableLogWidget` with `LogEntryEvent`
  - [ ] Add log entries to deque buffer (max 400)
  - [ ] Render visible logs (120 lines)
  - [ ] Apply log level filter
  - [ ] Apply text search filter
  - [ ] Color-code by level (DEBUG=dim, INFO=cyan, WARNING=yellow, ERROR=red)
- [ ] Implement log filter keyboard shortcuts (1-4)
  - [ ] Update filter level
  - [ ] Refresh display
  - [ ] Show notification
- [ ] Implement `ActiveRequestsTable`
  - [ ] Track in-flight API requests from events
  - [ ] Update table with ROM name, stage, duration, status
  - [ ] Remove completed requests
  - [ ] Show retry count and last failure
- [ ] Test high-volume logging (1000+ entries)
  - [ ] Ensure smooth scrolling
  - [ ] No lag in UI updates

**Deliverables:**
- Details tab with working log display
- Log filtering functional
- Active requests table updates in real-time
- Performance acceptable with high log volume

---

### Step 5: Systems Tab (Days 10-11)

**Tasks:**
- [ ] Populate Tree widget with systems from config
  - [ ] Read systems from `config['scraping']['systems']`
  - [ ] Create tree nodes with status icons
  - [ ] Update status as systems complete
- [ ] Implement `SystemDetailPanel` with real statistics
  - [ ] Subscribe to `SystemCompletedEvent`
  - [ ] Display ROM counts (total, processed, success, failed, skipped)
  - [ ] Display media stats (downloaded, validated, failed)
  - [ ] Display API stats (queries, cache hits, searches)
  - [ ] Display gamelist stats (entries, added, updated, removed)
  - [ ] Display cache stats (hit rate, misses)
- [ ] Wire up dynamic title updates
  - [ ] On tree selection, update panel title to system fullname
- [ ] Test system selection and detail display

**Deliverables:**
- Systems tab with working tree navigation
- Detail panel shows accurate statistics
- System status icons update as scraping progresses

---

### Step 6: Orchestrator Integration (Days 12-14)

**Tasks:**
- [ ] Modify `WorkflowOrchestrator.__init__()` to accept `event_bus`
- [ ] Add event emissions in `scrape_system()`:
  - [ ] `SystemStartedEvent` at start
  - [ ] `HashingProgressEvent` during hashing
  - [ ] `APIActivityEvent` during queries
  - [ ] `MediaDownloadEvent` during downloads
  - [ ] `GameCompletedEvent` for each successful match
  - [ ] `SystemCompletedEvent` at end
- [ ] Add event emissions in `_scrape_rom()`:
  - [ ] `ROMProgressEvent` for each status change (hashing, querying, downloading, complete, failed, skipped)
- [ ] Add performance metric tracking:
  - [ ] Track throughput (ROMs/hour) in circular buffer
  - [ ] Track API rate (calls/min) in circular buffer
  - [ ] Emit `PerformanceUpdateEvent` every 10 seconds
- [ ] Track active requests for ActiveRequestsTable:
  - [ ] Emit request start/complete events
  - [ ] Include retry count and failure reason
- [ ] Test event flow end-to-end:
  - [ ] Run scraper with UI
  - [ ] Verify all events emitted
  - [ ] Verify UI updates correctly

**Deliverables:**
- Orchestrator emits all necessary events
- Full data flow from scraping to UI working
- End-to-end integration tested

---

### Step 7: Interactive Search Dialog (Days 15-16)

**Tasks:**
- [ ] Convert `SearchResultDialog` from mockup to production
  - [ ] Remove sample data
  - [ ] Accept search results from API
  - [ ] Display results in left panel
  - [ ] Display selected game details in right panel
- [ ] Create search callback in orchestrator:
  - [ ] When hash lookup fails and search enabled
  - [ ] Emit event to trigger search dialog
  - [ ] Wait for user selection (async)
  - [ ] Continue with selected match or skip
- [ ] Implement modal display on search fallback:
  - [ ] `push_screen(SearchResultDialog(...))`
  - [ ] Callback receives user selection
  - [ ] Resume workflow with selection
- [ ] Handle user actions:
  - [ ] Select → use chosen match
  - [ ] Skip → mark ROM as skipped
  - [ ] Manual → prompt for manual entry (future)
  - [ ] Cancel → skip ROM
- [ ] Test search workflow integration:
  - [ ] Trigger search with missing ROM
  - [ ] Verify dialog displays
  - [ ] Verify selection continues scraping
  - [ ] Verify skip skips ROM

**Deliverables:**
- Interactive search dialog functional
- Integrates with scraping workflow
- User can select/skip/cancel
- Workflow resumes after selection

---

### Step 8: CLI Integration (Days 17-18)

**Tasks:**
- [ ] Modify `cli.py` to use `CurateurUI`:
  - [ ] Replace `ConsoleUI` initialization
  - [ ] Create `EventBus` instance
  - [ ] Create `CurateurUI` instance
  - [ ] Run UI in separate async task
- [ ] Setup `EventLogHandler`:
  - [ ] Create handler with event_bus
  - [ ] Add to root logger
  - [ ] Configure formatting
- [ ] Pass `event_bus` to orchestrator
- [ ] Implement keyboard control signals:
  - [ ] Check `ui_app.should_quit` in main loop
  - [ ] Check `ui_app.should_skip_system` per system
  - [ ] Handle pause/resume (future)
- [ ] Remove old dependencies:
  - [ ] Delete `curateur/ui/console_ui.py`
  - [ ] Delete `curateur/ui/keyboard_listener.py`
  - [ ] Remove Rich Live display code
  - [ ] Clean up unused imports
- [ ] Test full scraping workflow:
  - [ ] Single system scrape
  - [ ] Multi-system scrape
  - [ ] Quit during scraping
  - [ ] Skip system during scraping

**Deliverables:**
- CLI fully integrated with Textual UI
- Old Rich UI code removed
- Full scraping workflow functional
- Keyboard controls working

---

### Step 9: Polish & Testing (Days 19-20)

**Tasks:**
- [ ] Add notification toasts:
  - [ ] ERROR logs on Overview tab (red toast)
  - [ ] WARNING logs on Overview tab (yellow toast)
  - [ ] System completion (info toast)
  - [ ] Quota warnings (warning toast)
- [ ] Implement all keyboard shortcuts:
  - [ ] Ctrl+Q (quit) ✓
  - [ ] Ctrl+S (skip system) ✓
  - [ ] B (previous game in spotlight)
  - [ ] N (next game in spotlight)
  - [ ] 1-4 (log level filtering)
  - [ ] I (interactive search - trigger demo)
  - [ ] L (simulate log - remove from production)
- [ ] Performance testing:
  - [ ] Monitor FPS during active scraping
  - [ ] Test with high log volume (100+ logs/sec)
  - [ ] Test with large ROM collections (1000+ ROMs)
  - [ ] Optimize rendering if < 20 FPS
- [ ] Integration testing:
  - [ ] Full scrape of all systems in config
  - [ ] Test error scenarios (network failures, API errors)
  - [ ] Test edge cases (empty systems, missing media)
- [ ] Documentation updates:
  - [ ] Update README with Textual UI screenshots
  - [ ] Update config.yaml.example if needed
  - [ ] Add UI keyboard shortcuts to docs
  - [ ] Update CHANGELOG

**Deliverables:**
- Polished UI with all features working
- Performance targets met (≥20 FPS)
- Full integration testing passed
- Documentation updated

---

## Phase 6: Files to Create/Modify

### New Files

```
curateur/ui/
├── events.py                    # Event dataclasses (NEW)
├── event_bus.py                 # Event bus implementation (NEW)
├── event_log_handler.py         # Logging→events bridge (NEW)
├── textual_ui.py                # Main Textual app (from mockup)
└── textual_theme.tcss           # Already exists from mockup
```

### Modified Files

```
curateur/
├── cli.py                       # Replace ConsoleUI with CurateurUI
└── workflow/
    └── orchestrator.py          # Add event emissions throughout
```

### Deleted Files

```
curateur/ui/
├── console_ui.py                # DELETE after migration complete
└── keyboard_listener.py         # DELETE (Textual handles keyboard)
```

### Unchanged Files

**All data/logic modules remain unchanged:**
- `api/` - API client, throttling, caching
- `config/` - Configuration loading
- `gamelist/` - Gamelist generation and merging
- `media/` - Media downloading and organization
- `scanner/` - ROM scanning and hashing
- `workflow/` (except orchestrator.py) - Work queue, thread pool

**This ensures minimal risk and surgical changes.**

---

## Phase 7: Testing Strategy

### Unit Tests

**Event System:**
- [ ] `EventBus.subscribe()` registers callbacks
- [ ] `EventBus.publish()` delivers to subscribers
- [ ] `EventBus.publish_sync()` works from sync context
- [ ] Handler errors don't crash event loop
- [ ] Multiple subscribers receive same event
- [ ] Unsubscribe works (if implemented)

**Event Log Handler:**
- [ ] Emits `LogEntryEvent` for log records
- [ ] Preserves log level
- [ ] Formats message correctly
- [ ] Works from any thread

**UI Widgets:**
- [ ] `FilterableLogWidget` buffers logs correctly
- [ ] Log level filtering works
- [ ] Text search filtering works
- [ ] Color coding by level correct

### Integration Tests

**Full Workflow:**
- [ ] Run scraper with UI on small ROM set (10-20 ROMs)
- [ ] Verify all tabs display data
- [ ] Verify logs appear in Details tab
- [ ] Verify spotlight updates with games
- [ ] Verify system tree updates
- [ ] Verify performance metrics update

**Keyboard Controls:**
- [ ] Press Ctrl+Q → application quits
- [ ] Press Ctrl+S → current system skipped
- [ ] Press B/N → spotlight navigates
- [ ] Press 1-4 → log filtering changes

**Error Scenarios:**
- [ ] Network failure → error logged and displayed
- [ ] API quota exceeded → warning shown
- [ ] Missing ROM file → error logged
- [ ] Invalid config → graceful error message

### Performance Tests

**High Volume:**
- [ ] 1000 ROMs → UI remains responsive
- [ ] 100+ logs/second → no UI lag
- [ ] Multiple concurrent downloads → smooth updates

**Memory:**
- [ ] Log buffer doesn't grow unbounded (max 400 entries)
- [ ] Game spotlight queue bounded (max 20 games)
- [ ] No memory leaks during long runs

### Manual Testing

**Visual Verification:**
- [ ] All tabs render correctly
- [ ] Colors match mockup theme
- [ ] Borders are round with right-aligned titles
- [ ] Progress bars update smoothly
- [ ] Sparklines render correctly

**User Experience:**
- [ ] Tab switching is instant
- [ ] Keyboard shortcuts are intuitive
- [ ] Log scrolling is smooth
- [ ] Search dialog is easy to use
- [ ] Error messages are clear

---

## Risks & Challenges

### 1. Thread Safety

**Risk:** Race conditions between scraping thread and UI thread
**Impact:** High (data corruption, crashes)
**Mitigation:**
- Use `asyncio.Queue` in EventBus for cross-thread communication
- All UI updates go through event loop (no direct widget modification)
- Events are immutable dataclasses
- Test with ThreadSanitizer if available

### 2. Performance

**Risk:** High-frequency events (logs, progress) overwhelming UI
**Impact:** Medium (lag, low FPS)
**Mitigation:**
- Batch log events (emit every 100ms instead of immediately)
- Throttle progress updates (max 20/second)
- Use Textual's reactive caching
- Profile with `py-spy` if performance issues arise

### 3. Async Complexity

**Risk:** Mixing sync/async code incorrectly
**Impact:** High (deadlocks, crashes)
**Mitigation:**
- Keep orchestrator fully async
- Use `asyncio.create_task()` for background tasks
- Never use `asyncio.run()` inside event loop
- Document all sync/async boundaries

### 4. Data Synchronization

**Risk:** UI showing stale or inconsistent data
**Impact:** Medium (user confusion)
**Mitigation:**
- Every state change emits event immediately
- UI is single source of truth for display state
- Events are timestamped for debugging
- Add sequence numbers to events if needed

### 5. Search Dialog Blocking

**Risk:** Search dialog blocks scraping workflow
**Impact:** Low (by design, user input required)
**Mitigation:**
- Use `asyncio.Queue` for user input
- Orchestrator `await`s response
- Add timeout (5 min) for search dialog
- Allow Escape to cancel/skip

### 6. Event Ordering

**Risk:** Events processed out of order
**Impact:** Low (cosmetic issues)
**Mitigation:**
- Events processed in FIFO order (Queue guarantees)
- Add sequence numbers if strict ordering required
- Timestamp events for debugging

---

## Success Criteria

### Functional Requirements

- [ ] All 3 core tabs (Overview, Details, Systems) display real data
- [ ] Interactive search dialog works for manual ROM matching
- [ ] All keyboard shortcuts functional (Ctrl+Q, Ctrl+S, B/N, 1-4, I)
- [ ] Logs display in Details tab with filtering
- [ ] Game spotlight cycles through completed games
- [ ] System tree shows all systems with status
- [ ] Performance metrics update in real-time

### Performance Requirements

- [ ] UI maintains ≥20 FPS during active scraping
- [ ] No visible lag with 100+ logs/second
- [ ] Handles 1000+ ROM scraping without slowdown
- [ ] Memory usage stable (no leaks)

### Reliability Requirements

- [ ] No crashes during multi-system scraping
- [ ] Graceful handling of network errors
- [ ] Keyboard interrupts handled cleanly
- [ ] UI shutdown doesn't lose pending log messages

### User Experience Requirements

- [ ] All Rich UI functionality replicated
- [ ] UI is more intuitive than Rich UI
- [ ] Error messages are clear and actionable
- [ ] Performance feedback (progress bars, spinners) is smooth

### Code Quality Requirements

- [ ] Event system has >80% test coverage
- [ ] No pylint warnings
- [ ] Type hints on all public APIs
- [ ] Documentation updated

---

## Timeline Summary

| Phase | Days | Milestone |
|-------|------|-----------|
| **Foundation** | 1-2 | Event system working with tests |
| **UI Shell** | 3-4 | UI launches and subscribes to events |
| **Overview Tab** | 5-7 | Overview tab fully functional |
| **Details Tab** | 8-9 | Logs and active requests working |
| **Systems Tab** | 10-11 | System tree and details working |
| **Orchestrator** | 12-14 | Full event integration complete |
| **Search Dialog** | 15-16 | Interactive search functional |
| **CLI Integration** | 17-18 | Old UI removed, new UI integrated |
| **Polish & Test** | 19-20 | All features complete, tested, documented |

**Total: 20 days**

---

## Next Steps

1. **Review this plan** with team/stakeholders
2. **Setup development branch** (`feature/textual-ui`)
3. **Begin Phase 1** (Event System Architecture)
4. **Daily standups** to track progress and blockers
5. **Code reviews** at end of each phase
6. **Integration testing** at Phase 6 completion
7. **User acceptance testing** before Phase 8
8. **Merge to main** after Phase 9 complete

---

## Appendix: Event Emission Checklist

### Events to Emit from Orchestrator

**System Level:**
- [ ] `SystemStartedEvent` - When starting system scrape
- [ ] `SystemCompletedEvent` - When finishing system scrape

**ROM Level:**
- [ ] `ROMProgressEvent` (status='scanning') - ROM discovered
- [ ] `ROMProgressEvent` (status='hashing') - ROM hashing started
- [ ] `ROMProgressEvent` (status='querying') - API query started
- [ ] `ROMProgressEvent` (status='downloading') - Media download started
- [ ] `ROMProgressEvent` (status='complete') - ROM fully scraped
- [ ] `ROMProgressEvent` (status='failed') - ROM scraping failed
- [ ] `ROMProgressEvent` (status='skipped') - ROM skipped

**Batch Operations:**
- [ ] `HashingProgressEvent` - Batch hashing progress
- [ ] `APIActivityEvent` - Active API request counts
- [ ] `MediaDownloadEvent` - Per-media-type downloads

**Completion:**
- [ ] `GameCompletedEvent` - Successful ROM match (for spotlight)

**Performance:**
- [ ] `PerformanceUpdateEvent` - Periodic metrics update (every 10s)

**Logging:**
- [ ] `LogEntryEvent` - All log messages (via EventLogHandler)

---

**End of Implementation Plan**
