# Search Fallback Implementation Summary

## Overview

Implemented comprehensive search fallback functionality for curateur, allowing the scraper to search ScreenScraper by game name when hash-based lookups fail. The implementation includes multi-factor confidence scoring, interactive prompts, and thread-safe operation.

## Features Implemented

### 1. Configuration Options

**Location**: `config.yaml.example` - New `search:` section

- `enable_search_fallback`: Enable/disable search when hash lookup fails (default: false)
- `confidence_threshold`: Minimum score 0.0-1.0 to accept match (default: 0.7)
- `max_results`: Maximum search results to consider (default: 5)
- `interactive_search`: Enable user prompts for match selection (default: false)

**Configuration Validation**: Added `_validate_search()` to `curateur/config/validator.py`

### 2. Match Confidence Scoring

**Location**: `curateur/api/match_scorer.py` (NEW)

**Algorithm**: Multi-factor weighted scoring
- Filename similarity: 40% - Uses normalized string comparison against all regional names
- Region match: 30% - Prioritizes games in preferred regions
- File size match: 15% - Compares ROM size to ScreenScraper's reported size
- Media availability: 10% - Games with more media assets score higher
- User rating: 5% - Higher-rated games score better

**Key Functions**:
- `calculate_match_confidence()`: Main scoring function
- `_score_filename_similarity()`: Normalizes names, removes ROM tags
- `_score_region_match()`: Checks preferred region presence
- `_score_file_size()`: Handles size comparison with tolerance
- `_score_media_availability()`: Counts available media types
- `_score_user_rating()`: Normalizes ScreenScraper's 0-20 scale
- `_normalize_name()`: Removes ROM tags and punctuation

### 3. API Client Extensions

**Location**: `curateur/api/client.py`

**New Methods**:
- `search_game(rom_info, max_results)`: Public method for searching by name
- `_query_jeu_recherche(systemeid, recherche, max_results)`: Internal API call to jeuRecherche.php endpoint

**Behavior**:
- Respects rate limiting
- Uses retry with exponential backoff
- Returns list of game data dictionaries
- Integrates with existing error handling

### 4. Interactive Prompts (Thread-Safe)

**Location**: `curateur/ui/prompts.py`

**New Components**:
- Global `_prompt_lock`: Threading lock for sequential prompts
- `prompt_for_search_match()`: Thread-safe user selection interface
- `_render_confidence_bar()`: Visual confidence indicator

**Prompt Features**:
- Displays all candidates with confidence scores
- Shows visual confidence bars (█████░░░)
- Indicates threshold pass/fail (✓/✗)
- Displays game metadata (system, regions, release date, publisher)
- Options: Select by number, Skip (s), or No match (n)
- Handles keyboard interrupts gracefully

### 5. Workflow Orchestrator Updates

**Location**: `curateur/workflow/orchestrator.py`

**Constructor Changes**:
- Added search configuration parameters
- Added `unmatched_roms` dictionary to track failures

**New Methods**:
- `_search_fallback(rom_info, preferred_regions)`: Implements search logic
  - Queries search API
  - Scores all candidates
  - Either prompts user (interactive) or auto-selects (automatic)
  - Returns best match or None
- `_write_unmatched_roms(system_name)`: Writes unmatched ROM list to file

**Modified Methods**:
- `_scrape_rom()`: Updated to use ROMInfo objects, attempt search fallback on hash failure
- `scrape_system()`: Calls `_write_unmatched_roms()` after processing

**Flow**:
1. Try hash-based lookup via `query_game()`
2. If fails and search enabled → call `_search_fallback()`
3. Score all candidates
4. Interactive mode → prompt user
5. Automatic mode → select if above threshold
6. Track unmatched ROMs
7. Write unmatched_roms.txt per system

### 6. CLI Flags

**Location**: `curateur/cli.py`

**New Arguments**:
- `--enable-search`: Enable search fallback (overrides config)
- `--search-threshold SCORE`: Set confidence threshold 0.0-1.0 (overrides config)
- `--interactive-search`: Enable interactive prompts (overrides config)

**Display Changes**:
- Header shows search status when enabled
- Shows confidence threshold
- Indicates interactive mode status

### 7. Unmatched ROM Logging

**Location**: `curateur/workflow/orchestrator.py` → `_write_unmatched_roms()`

**Output**: `{gamelist_dir}/{system}/unmatched_roms.txt`

**Format**:
```
# Unmatched ROMs for nes
# Total: 5
# These ROMs could not be matched via hash lookup or search fallback.
#
Game1.nes
Game2.nes
```

## Usage Examples

### Basic Search Fallback
```bash
curateur --enable-search
```

### Interactive Mode
```bash
curateur --enable-search --interactive-search
```

### Custom Threshold
```bash
curateur --enable-search --search-threshold 0.8
```

### Configuration File
```yaml
search:
  enable_search_fallback: true
  confidence_threshold: 0.75
  max_results: 5
  interactive_search: false
```

## Thread Safety

The implementation ensures thread-safe operation for concurrent ROM processing:

1. **Prompt Lock**: Global `_prompt_lock` in `prompts.py` ensures sequential prompts
2. **Isolated State**: Each ROM's search is independent
3. **Dictionary Tracking**: `unmatched_roms` dictionary safely tracks failures per system
4. **No Race Conditions**: File writes happen after system completion

## Default Behavior

**Search is DISABLED by default** to maintain conservative behavior:
- No search unless explicitly enabled in config or CLI
- Unmatched ROMs logged to file for manual review
- No false positives from aggressive matching

## Confidence Scoring Details

### Filename Similarity (40%)
- Removes ROM tags: (USA), [!], (Rev 1), etc.
- Normalizes: lowercase, no punctuation
- Uses SequenceMatcher ratio
- Checks all regional names, uses best match

### Region Match (30%)
- 1.0 if first preferred region present
- 0.8 if second preferred region present
- 0.6 if third preferred region present
- 0.2 minimum if any region matches
- 0.1 if game exists but wrong regions

### File Size (15%)
- 1.0 for exact match
- 0.9 for <5% difference
- 0.7 for 5-10% difference
- 0.5 for 10-20% difference
- 0.2 for >20% difference
- 0.5 if size unknown

### Media Availability (10%)
- Counts: cover, screenshot, titlescreen, marquee, box3d, video
- Normalized: 3+ media types = 1.0
- Linear scaling below 3

### User Rating (5%)
- ScreenScraper's 0-20 scale normalized to 0-1
- 0.5 if rating unavailable
- Higher ratings indicate better-documented games

## Files Modified

1. `config.yaml.example` - Added search configuration section
2. `curateur/config/validator.py` - Added search validation
3. `curateur/api/match_scorer.py` - NEW - Confidence scoring
4. `curateur/api/client.py` - Added search_game() method
5. `curateur/ui/prompts.py` - Added thread-safe search prompt
6. `curateur/workflow/orchestrator.py` - Integrated search fallback
7. `curateur/cli.py` - Added CLI flags

## Testing Considerations

The existing test suite in `tests/test_api_search.py` validates:
- Search endpoint response parsing
- Multiple result handling
- Empty result scenarios
- Partial metadata handling
- Error conditions

Additional integration testing should verify:
- End-to-end search fallback flow
- Confidence scoring accuracy
- Interactive prompt behavior
- Thread safety with concurrent ROMs
- Unmatched ROM logging

## Future Enhancements

Potential improvements:
1. Machine learning for improved scoring weights
2. Fuzzy matching algorithms (Levenshtein distance)
3. Publisher/developer name matching
4. Release date proximity scoring
5. User feedback loop to improve confidence algorithm
6. Batch search API optimization
7. Cache search results for retry scenarios
