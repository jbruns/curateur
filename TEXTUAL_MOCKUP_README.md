# Textual UI Mockup for Curateur

This directory contains a visual mockup of a Textual-based UI to replace the existing Rich UI in curateur. The mockup demonstrates a modern, tab-based interface with sample data.

## What's Included

### Files

1. **`curateur/ui/textual_mockup.py`** (~1057 lines)
   - Main Textual application with 4-tab interface
   - Comprehensive sample data for all features
   - Custom widgets with progress bars and visual indicators
   - Keyboard controls and reactive updates

2. **`curateur/ui/textual_theme.tcss`** (~506 lines)
   - CSS styling matching Rich UI's retro theme
   - Color palette: magenta, cyan, bright magenta, bright green
   - Widget-specific styles for all components including progress bars

## Features Demonstrated

### Tab 1: Overview Tab

**Two-column layout** for efficient space usage:

**Left Column (25% width):**

- **Overall Progress**: Run-wide progress summary with progress bar
  - Systems complete vs total (e.g., 2/4)
  - Total ROMs processed vs total (e.g., 485/847)
  - Progress percentage
  - Success, skipped, and failed counts with glyphs (✓, ⊝, ✗)
  - Visual progress bar showing completion

- **Current System Operations**: Real-time progress for the system being processed
  - System name in border title (e.g., "Sega Genesis / Mega Drive")
  - Organized into sections with separators and glyphs for quick scanning:
    - **Hashing** section: Progress count and inline bar (115/150 - 76.7%), spinner when active, ⊝ skipped count
    - **Cache** section: Hit rate with inline bar, ✓ existing, + added
    - **Gamelist** section: ✓ existing, + added, − removed, ↻ updated
    - **API** section: Metadata and Search requests (spinner when active, in-flight count, total count)
    - **Media** section: ⬇ downloading, ✓ downloaded, ✓ validated, ✗ failed

**Right Column (75% width):**

- **Game Spotlight**: Auto-cycling game display (10-second interval) with expanded metadata
  - Shows recently scraped games with comprehensive information
  - Keyboard navigation: ← → arrows
  - Displays: name, year, genre, developer, publisher, region, players, rating, full synopsis
  - Expanded vertical space allows full synopsis text without truncation

- **Performance Panel**: Compact visual metrics with sparklines and account info
  - Throughput: ROMs per hour with sparkline history
  - API rate: Calls per minute with sparkline history
  - ScreenScraper account name (logged in as...) and API threads (in use/limit)
  - API quota: Usage with inline progress bar (1247/20000 - 6.2%)
  - System ETA: Time to complete current system
  - Memory usage, CPU usage

### Tab 2: Details Tab

Two-panel layout with round borders and right-aligned titles:

- **Logs**: Live log viewer with filtering
  - Regex filtering via input box
  - Level filtering: 1=ERROR, 2=WARNING, 3=INFO, 4=DEBUG
  - Color-coded by level
  - 50+ sample log entries
  - Round border with title embedded (right-aligned)

- **Active Requests (3/4 concurrent)**: Currently processing ROMs
  - Shows ROM name, stage, duration, status, retry count, last failure reason
  - Updates in real-time
  - Round border with title embedded (right-aligned)

### Tab 3: Systems Tab

Two-panel layout with round borders and right-aligned titles:

- **System Queue** (left panel): Tree view with status icons
  - ROMs count per system
  - Progress percentage with status icons (✓=complete, ⚡=active, ⏸=pending)
  - Round border with title embedded (right-aligned)

- **System Detail Panel** (right panel): Detailed stats for selected system
  - Title matches selected system name (e.g., "Nintendo Entertainment System")
  - ROM statistics (total, successful, failed, skipped)
  - Media breakdown by type (downloaded/validated/failed counts)
  - API call statistics
  - Gamelist statistics
  - Cache statistics
  - Round border with dynamic title (right-aligned)

### Tab 4: Config Tab ⚙️

**Interactive runtime settings control** - change scraping behavior on the fly!

Two-column layout with four panels (round borders, right-aligned titles), each corresponding to a configuration group from `config.yaml.example`:

**Left Column:**

- **API Settings** (magenta border):
  - Request Timeout (s): 15/30/45/60 (default: 30)
  - Max Retries: 0-5 (default: 3)
  - Retry Backoff (s): 1/3/5/10 (default: 5)
  - Quota Warning: 80-99% (default: 95%)

- **Runtime Settings** (bright magenta border):
  - Dry Run Mode: ON/OFF (default: OFF)
  - Hash Algorithm: CRC32/MD5/SHA1 (default: CRC32)
  - CRC Size Limit: 0.5-4 GiB or None (default: 1 GiB)
  - Enable Cache: ON/OFF (default: ON)
  - Override Limits: ON/OFF (default: OFF)
    - Max Workers: 1-5 (default: 1, disabled unless override enabled)
    - Req/Min: 30-300 (default: 60, disabled unless override enabled)
    - Daily Quota: 5k-50k (default: 10k, disabled unless override enabled)

**Right Column:**

- **Logging Settings** (cyan border):
  - Log Level: DEBUG/INFO/WARNING/ERROR (default: INFO)
  - Console Logging: ON/OFF (default: ON)
  - File Logging: ON/OFF (default: OFF)

- **Search Settings** (bright green border):
  - Search Fallback: ON/OFF (default: OFF)
  - Confidence: 50-90% (default: 70%)
  - Max Results: 1/3/5/7/10 (default: 5)
  - Interactive: ON/OFF (default: OFF)

All changes show interactive notifications and update immediately! Rate limit override fields dynamically enable/disable based on the override toggle. Labels are compact to fit more settings on screen.

## Running the Mockup

### Prerequisites

1. **Install Textual**:
   ```bash
   pip install textual
   ```

2. **Navigate to project directory**:
   ```bash
   cd /Users/jbruns/src/curateur
   ```

### Launch

```bash
python -m curateur.ui.textual_mockup
```

Or:

```bash
python curateur/ui/textual_mockup.py
```

### Keyboard Controls

**All Tabs:**
- **Ctrl+Q**: Quit the application
- **Ctrl+S**: Skip current system
- **B** / **N**: Navigate back/next game in spotlight (Overview tab)
- **I**: Show interactive search dialog (demo)
- **L**: Simulate a new log entry (demo - shows notification feature)
- **Tab**: Switch between tabs
- **Mouse**: Click to interact with tables and tabs

**Log Filtering (Details Tab Only):**
- **1**: Filter logs to show ERROR and above
- **2**: Filter logs to show WARNING and above
- **3**: Filter logs to show INFO and above (default)
- **4**: Filter logs to show DEBUG and above (all logs)

**Context-Aware Features:**
- Log filter controls (1-4) only function when the Details tab is active
- Navigation keys (B/N) only function when the Overview tab is active
- When WARNING or ERROR logs are added while the Overview tab is active, a notification toast appears
- Pressing tab-specific keys on other tabs shows helpful guidance messages

### Interactive Search Dialog

When a ROM cannot be automatically matched, an interactive search dialog appears:

**Layout**: Modal overlay with:
- **Left panel**: List of search results with confidence scores
- **Right panel**: Detailed information about selected result

**Features**:
- **Color-coded confidence**: Green (≥90%), Yellow (≥75%), Red (<75%)
- **Keyboard navigation**: Arrow keys to browse results
- **Quick actions**:
  - **Select [Enter]**: Use the highlighted match
  - **Skip ROM [S]**: Skip this ROM and continue
  - **Manual Search [M]**: Perform a manual search with custom query
  - **Cancel [Esc]**: Cancel and return to automatic mode

**Details shown**: Game ID, title, year, region, publisher, developer, players, confidence score

**Demo**: Press **I** in the mockup to see a sample interactive search dialog for "castlevania3_bad_name.zip"

## Design Highlights

### Architecture

```
TextualMockupApp
├── Header (app title + clock)
├── TabbedContent
│   ├── OverviewTab (Two-column layout)
│   │   ├── Left Column (25% width)
│   │   │   ├── OverallProgressWidget (systems count + ROM stats with glyphs + progress bar)
│   │   │   └── CurrentSystemOperations (system name in border title)
│   │   │       ├── Rule separator
│   │   │       ├── Hashing (title + spinner + count + skipped)
│   │   │       ├── Rule separator
│   │   │       ├── Cache (title + hit rate bar + ✓/+ glyphs)
│   │   │       ├── Rule separator
│   │   │       ├── Gamelist (title + ✓/+/−/↻ glyphs with counts)
│   │   │       ├── Rule separator
│   │   │       ├── API (title + Metadata/Search in-flight + totals)
│   │   │       ├── Rule separator
│   │   │       └── Media (title + ⬇/✓/✗ glyphs for downloads)
│   │   └── Right Column (75% width)
│   │       ├── GameSpotlightWidget (expanded with full metadata)
│   │       │   └── Displays: name, year, genre, developer, publisher, region, players, rating, full synopsis
│   │       └── PerformancePanel (sparklines, account + threads, API quota, system ETA)
│   ├── DetailsTab (two panels, round borders, right-aligned titles)
│   │   ├── FilterableLogWidget (Logs - regex filter + level filter)
│   │   └── ActiveRequestsTable (Active Requests - ROM, stage, duration, status, retry, last failure)
│   ├── SystemsTab (two panels, round borders, right-aligned titles)
│   │   ├── Tree "System Queue" (systems list with status icons)
│   │   └── SystemDetailPanel (dynamic title = selected system name)
│   │       └── Stats: ROM, media, API, gamelist, cache
│   └── ConfigTab (two-column layout)
│       ├── Left Column (50% width)
│       │   ├── API Settings (round border, right-aligned title)
│       │   │   └── request_timeout, max_retries, retry_backoff, quota_warning_threshold
│       │   └── Runtime Settings (round border, right-aligned title)
│       │       └── dry_run, hash_algorithm, crc_size_limit, enable_cache, rate_limit_override
│       └── Right Column (50% width)
│           ├── Logging Settings (round border, right-aligned title)
│           │   └── level, console, file
│           └── Search Settings (round border, right-aligned title)
│               └── enable_search_fallback, confidence_threshold, max_results, interactive_search
├── Footer (keyboard shortcuts)
└── SearchResultDialog (Modal - interactive search)
    ├── Header (match required)
    ├── ROM info display
    ├── Results list (left) + Details panel (right)
    └── Action buttons (Select/Skip/Manual/Cancel)
```

### Retro Color Theme

Matches the existing Rich UI aesthetic:

- **Primary**: Magenta (borders, headers)
- **Secondary**: Cyan (highlights, text)
- **Accent**: Bright Magenta (active elements)
- **Success**: Bright Green (success indicators)
- **Warning**: Yellow (warnings)
- **Error**: Red (errors)
- **Surface**: Dark gray background (#1a1a1a)

### Border Styling

All tabs use round borders with embedded titles for a polished, consistent appearance:

**Overview Tab:**
- **Left column**: Titles aligned left ("Overall Progress", system name)
- **Right column**: Titles aligned right ("Game Spotlight", "Performance Metrics")

**Details Tab:**
- All panels: Titles aligned right ("Logs", "Active Requests")

**Systems Tab:**
- All panels: Titles aligned right ("System Queue", selected system name)
- Detail panel title dynamically updates to match selected system

**Round borders**: Softer, more polished appearance than sharp corners
**Color-coded**: Each widget uses a distinct color (primary, accent, secondary, success)

### Glyph System

Current System Operations uses glyphs and color to convey information at a glance:

**Status Glyphs:**
- **✓** (checkmark) - Existing/successful items (white)
- **+** (plus) - Added/new items (bright green)
- **−** (minus) - Removed items (red)
- **↻** (circular arrows) - Updated items (yellow)
- **⬇** (down arrow) - Currently downloading (yellow)
- **✗** (x mark) - Failed items (red)
- **⊝** (circled minus) - Skipped items (dim yellow)

**Activity Indicators:**
- **⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏** (spinner) - Active operations: hashing in progress, API requests in flight (bright magenta)
- "Idle" - No active requests (dim)

This glyph-based approach reduces visual clutter and enables faster scanning of system status.

### Code Comparison

- **Rich UI**: 1,868 lines (`console_ui.py`)
- **Textual Mockup**: ~1057 lines (`textual_mockup.py` + sample data)
- **Note**: Mockup includes comprehensive sample data, 4 tabs with progress bars
- Production version would use live data streams, reducing code significantly
- Progress bars and visual indicators provide better at-a-glance status

### Advantages Over Rich UI

1. **Built-in Widgets**: DataTable, RichLog, ProgressBar, Input
2. **Reactive Programming**: Automatic UI updates when data changes
3. **CSS Styling**: Separation of presentation and logic
4. **Native Keyboard Handling**: No custom listener needed
5. **Tab Management**: Built-in tabbed interface
6. **Better Performance**: Optimized rendering engine
7. **Maintainability**: Cleaner, more declarative code structure

## Sample Data

The mockup uses realistic sample data:

- **Overall Progress**: 2/4 systems complete, 847 total ROMs, 485 processed, ✓ 470 successful, ⊝ 5 skipped, ✗ 10 failed
- **10 Games**: Classic NES titles with comprehensive metadata (name, year, genre, developer, publisher, region, players, rating, full synopsis)
- **50+ Log Entries**: Mix of INFO, WARNING, ERROR, DEBUG levels
- **4 Systems**: NES, SNES, Genesis (active), PSX at different completion stages
- **Current System**: Genesis (in-progress) with:
  - Hashing: 115/150 ROMs (76.7%), 3 skipped, active (spinner)
  - Cache hit rate: 65% (85 existing, 30 added)
  - Gamelist: 95 existing, 20 added, 5 removed, 90 updated
  - API: Metadata (2 in-flight, 115 total), Search (1 in-flight, 12 total)
  - Media: 5 downloading, 326 downloaded, 45 validated, 4 failed
- **Account Info**: ScreenScraper username, API threads (3/4 in use), API quota (1247/20000 - 6.2%), system ETA
- **Performance History**: 40 data points for throughput and API rate sparklines
- **Active Requests**: 3 concurrent ROM processing operations with retry counts and last failure reasons
- **Search Results**: 4 sample matches for "Castlevania III" with varying confidence levels (95%, 88%, 85%, 62%)

## Next Steps for Production

To convert this mockup into a production-ready UI:

### Phase 1: Integration (Estimated: 8-10 hours)

1. Create `TextualUIBridge` adapter (~100 lines)
   - Thread-safe communication between orchestrator and UI
   - Implement `call_from_thread()` for safe updates

2. Replace sample data with real data sources
   - Connect to `PerformanceMonitor` for metrics
   - Connect to `WorkflowOrchestrator` for progress
   - Connect to logging system for live logs

3. Add CLI flag support
   - `--ui textual` vs `--ui rich`
   - Allow A/B testing

### Phase 2: Testing (Estimated: 4-6 hours)

1. Test with real scraping workflows
2. Verify thread safety under load
3. Test all keyboard controls
4. Validate performance (no overhead vs Rich UI)

### Phase 3: Full Replacement (Estimated: 2-4 hours)

1. Make Textual UI the default
2. Remove Rich UI code (`console_ui.py`, `keyboard_listener.py`)
3. Update documentation
4. Release as new major version

### Total Estimated Effort

- **Mockup to Production**: 14-20 hours
- **Testing & Polish**: 4-6 hours
- **Total**: 18-26 hours

## Success Criteria

The mockup successfully demonstrates:

- ✅ **Visual Appeal**: Retro theme matching Rich UI
- ✅ **4-Tab Interface**: Clear separation of concerns (Overview/Details/Systems/Config)
- ✅ **Game Spotlight**: Auto-cycling with navigation
- ✅ **Performance Viz**: Sparklines for throughput/API rate
- ✅ **Filterable Logs**: Regex + level filtering
- ✅ **Progress Tracking**: Per-system and overall
- ✅ **Interactive Config**: Runtime settings with Switches, Selects, and Buttons
- ✅ **Keyboard Controls**: Intuitive navigation
- ✅ **Responsiveness**: Smooth rendering
- ✅ **Code Quality**: Clean, maintainable
- ✅ **Feasibility**: Proves Textual can replace Rich UI

## Technical Notes

### Reactive Programming Model

Textual uses a reactive system where changes to reactive variables automatically trigger UI updates:

```python
class GameSpotlightWidget(Static):
    games = reactive(list)  # Reactive variable
    index = reactive(0)

    def watch_index(self, old, new):
        # Called automatically when index changes
        self.update_display()
```

### CSS Variables

The theme uses CSS variables for easy customization:

```css
$primary: ansi_magenta;
$secondary: ansi_cyan;
$accent: ansi_bright_magenta;
```

### Widget Composition

Widgets are composed declaratively:

```python
def compose(self) -> ComposeResult:
    yield GameSpotlightWidget()
    yield OperationalMetrics()
    yield PerformancePanel()
```

## Troubleshooting

### Import Error: No module named 'textual'

**Solution**: Install Textual
```bash
pip install textual
```

### CSS Parsing Errors

**Issue**: Color names not recognized

**Solution**: Use ANSI color names (e.g., `ansi_magenta` not `magenta`)

### Slow Performance

**Issue**: UI feels sluggish

**Solution**: Textual renders efficiently by default. Check terminal emulator performance.

## Questions or Feedback

For questions about the mockup or to provide feedback on the design:

1. Review the implementation in `textual_mockup.py`
2. Test all keyboard controls
3. Try switching between tabs
4. Evaluate the visual design against the Rich UI
5. Consider the code simplicity and maintainability

## License

This mockup is part of curateur and follows the same GPL-3.0-or-later license.
