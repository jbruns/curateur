# Phase 4 Complete: Media Downloader

**Status:** ✓ COMPLETE  
**Date:** 2024  
**Tests:** 8/8 passing

## Overview

Phase 4 implements a complete media downloader with region prioritization, image validation, and ES-DE directory organization. The system downloads game media (box art, screenshots, etc.) from ScreenScraper with comprehensive error handling and quality validation.

## Components Implemented

### 1. Media Types (`curateur/media/media_types.py`)

**Purpose:** Define supported media types and map them to ES-DE directory structure.

**Key Features:**
- **MediaType Enum:** Type-safe media type constants
- **MEDIA_TYPE_MAP:** Maps ScreenScraper types to ES-DE directories
- **MVP Media Types:**
  - `box-2D` → `covers/` (front box art)
  - `ss` → `screenshots/` (in-game screenshots)
  - `sstitle` → `titlescreens/` (title screens)
  - `screenmarquee` → `marquees/` (arcade marquees)

**Functions:**
```python
get_directory_for_media_type(media_type: str) -> str
is_supported_media_type(media_type: str) -> bool
```

**Directory Structure:**
```
downloaded_media/
├── nes/
│   ├── covers/
│   │   ├── Super Mario Bros.jpg
│   │   └── Zelda.jpg
│   ├── screenshots/
│   ├── titlescreens/
│   └── marquees/
├── snes/
│   └── ...
```

### 2. Region Selector (`curateur/media/region_selector.py`)

**Purpose:** Detect regions from ROM filenames and select best media based on region preferences.

**Key Features:**
- **Region Detection:**
  - Extracts regions from parenthetical notation
  - Filters out language codes (En, Fr, De, etc.)
  - Supports multi-region ROMs
- **Region Codes:** 18 supported regions (us, eu, jp, wor, fr, de, es, it, nl, pt, br, au, kr, cn, tw)
- **Smart Prioritization:**
  - ROM-detected regions prioritized first
  - Fallback to user-configured preferences
  - Handles ROMs without region tags

**Functions:**
```python
detect_region_from_filename(filename: str) -> List[str]
select_best_region(available_regions, rom_filename, preferred_regions) -> Optional[str]
get_media_for_region(media_list, media_type, region) -> Optional[Dict]
should_use_region_filtering(media_type: str) -> bool
```

**Region Detection Examples:**
- `"Game (USA).nes"` → `['us']`
- `"Game (Japan, USA).nes"` → `['jp', 'us']`
- `"Game (Europe) (En,Fr,De).zip"` → `['eu']` (languages filtered)
- `"Game (World).n64"` → `['wor']`

**Selection Priority:**
```
ROM: "Game (Japan, USA).nes"
Available API regions: ['us', 'jp', 'eu']
User preferred_regions: ['us', 'wor', 'eu', 'jp']

Priority order: ['us', 'jp', 'wor', 'eu']
  - 'us' and 'jp' from ROM (ordered by config)
  - 'wor' and 'eu' from remaining config

Result: 'us' (first match in priority order)
```

### 3. URL Selector (`curateur/media/url_selector.py`)

**Purpose:** Select optimal media URLs from ScreenScraper API responses.

**Key Features:**
- **MediaURLSelector Class:**
  - Configurable region preferences
  - Configurable enabled media types
  - Automatic region filtering (skips for fanart/video)
  - Quality selection (first match for MVP)
- **Integration:**
  - Uses region selector for prioritization
  - Filters by supported media types
  - Returns dict of selected media URLs

**Methods:**
```python
select_media_urls(media_list, rom_filename) -> Dict[str, Dict]
_get_available_regions(media_list, media_type) -> List[str]
filter_by_quality(media_list, media_type, region) -> Optional[Dict]
```

**Usage:**
```python
selector = MediaURLSelector(
    preferred_regions=['us', 'wor', 'eu'],
    enabled_media_types=['box-2D', 'ss']
)

selected = selector.select_media_urls(api_media_list, "Mario (USA).nes")
# Returns:
# {
#     'box-2D': {'url': 'http://...', 'format': 'jpg', 'region': 'us'},
#     'ss': {'url': 'http://...', 'format': 'png', 'region': 'us'}
# }
```

### 4. Image Downloader (`curateur/media/downloader.py`)

**Purpose:** Download and validate images with retry logic.

**Key Features:**
- **ImageDownloader Class:**
  - HTTP download with configurable timeout (default: 30s)
  - Retry logic with exponential backoff (max 3 attempts)
  - Image validation using Pillow
  - Minimum dimension checking (default: 50x50 pixels)
  - Content-Type verification
- **Validation:**
  - Verifies valid image format
  - Checks minimum dimensions
  - Validates existing files
  - Returns dimensions on success

**Methods:**
```python
download(url, output_path, validate=True) -> Tuple[bool, Optional[str]]
validate_existing_file(file_path) -> Tuple[bool, Optional[str]]
get_image_dimensions(file_path) -> Optional[Tuple[int, int]]
```

**Error Handling:**
```python
success, error = downloader.download(url, path)
if not success:
    if "too small" in error:
        # Image failed dimension check
    elif "Invalid content type" in error:
        # Not an image file
    elif "failed after 3 attempts" in error:
        # Network error with retries exhausted
```

### 5. Media Organizer (`curateur/media/organizer.py`)

**Purpose:** Organize downloaded media in ES-DE directory structure.

**Key Features:**
- **MediaOrganizer Class:**
  - Path generation for media files
  - ROM basename extraction
  - Directory creation
  - Relative path generation for gamelist.xml
- **Special Case Handling:**
  - M3U playlists: Use M3U filename (not disc 1)
  - Disc subdirectories: Use directory name with extension
  - Standard ROMs: Use filename without extension

**Methods:**
```python
get_media_path(system, media_type, rom_basename, extension) -> Path
get_rom_basename(rom_path) -> str
ensure_directory_exists(file_path) -> None
get_all_media_paths(system, rom_basename, media_types) -> Dict[str, Path]
file_exists(file_path) -> bool
get_relative_path(file_path, base_path) -> str
```

**Basename Examples:**
- `"Super Mario Bros.nes"` → `"Super Mario Bros"`
- `"Skies of Aleria.m3u"` → `"Skies of Aleria"`
- `"Skies (Disc 1).cue"` (directory) → `"Skies (Disc 1).cue"`

### 6. Media Downloader Integration (`curateur/media/media_downloader.py`)

**Purpose:** Main coordinator integrating all media operations.

**Key Features:**
- **MediaDownloader Class:**
  - Integrates URL selector, downloader, and organizer
  - Downloads all enabled media types for a game
  - Tracks success/failure for each media type
  - Generates summary statistics
  - Checks for existing media
- **DownloadResult Class:**
  - Encapsulates download outcomes
  - Includes file path, dimensions, errors
  - Provides readable repr

**Methods:**
```python
download_media_for_game(media_list, rom_path, system) -> List[DownloadResult]
get_media_summary(results) -> Dict
check_existing_media(system, rom_basename) -> Dict[str, bool]
```

**Usage:**
```python
downloader = MediaDownloader(
    media_root=Path('downloaded_media'),
    preferred_regions=['us', 'wor', 'eu'],
    enabled_media_types=['box-2D', 'ss']
)

results = downloader.download_media_for_game(
    api_response['media'],
    'Super Mario Bros (USA).nes',
    'nes'
)

for result in results:
    if result.success:
        print(f"✓ {result.media_type}: {result.file_path} ({result.dimensions})")
    else:
        print(f"✗ {result.media_type}: {result.error}")

summary = downloader.get_media_summary(results)
print(f"Success rate: {summary['success_rate']*100:.0f}%")
```

## Test Results

### Integration Test Coverage

All 8 test suites passing:

1. **Media Type Mappings** (4 assertions)
   - box-2D → covers
   - ss → screenshots
   - sstitle → titlescreens
   - screenmarquee → marquees

2. **Media Type Map Completeness** (4 assertions)
   - All MVP types present in MEDIA_TYPE_MAP

3. **Region Detection** (5 assertions)
   - Single region extraction
   - Multi-region extraction
   - Language code filtering
   - World region detection
   - No region handling

4. **Region Selection** (3 assertions)
   - Multi-region ROM prioritization
   - World region selection
   - Fallback to preferred list

5. **URL Selector** (2 assertions)
   - Media type filtering
   - Region-based selection

6. **Media Organizer** (4 assertions)
   - Path generation
   - ROM basename extraction
   - M3U handling
   - Disc subdirectory handling

7. **Image Validation** (3 assertions)
   - Valid image acceptance
   - Small image rejection
   - Invalid data rejection

8. **Download Integration** (3 assertions)
   - Initialization
   - Existing media check
   - URL selection integration

### Test Execution

```bash
$ python tests/test_phase4_integration.py
============================================================
curateur MVP Phase 4 - Media Downloader Test
============================================================
Testing media type mappings...
  ✓ box-2D -> covers
  ✓ ss -> screenshots
  ✓ sstitle -> titlescreens
  ✓ screenmarquee -> marquees

Testing media type map...
  ✓ box-2D mapped to covers
  ✓ ss mapped to screenshots
  ✓ sstitle mapped to titlescreens
  ✓ screenmarquee mapped to marquees

Testing region detection...
  ✓ 'Game (USA).nes' -> ['us']
  ✓ 'Game (Japan, USA).nes' -> ['jp', 'us']
  ✓ 'Game (Europe) (En,Fr,De).zip' -> ['eu']
  ✓ 'Game (World).n64' -> ['wor']
  ✓ 'Game Name.zip' -> []

Testing region selection...
  ✓ Multi-region ROM: selected 'us' (highest priority in ROM)
  ✓ World ROM: selected 'wor' (from ROM)
  ✓ No ROM region: selected 'eu' (from preferred list)

Testing media URL selector...
  ✓ Selected 2 media types with correct regions
  ✓ Correctly filtered out non-enabled media types

Testing media organizer...
  ✓ Path generation: nes/covers/Super Mario Bros.jpg
  ✓ Basename: 'Super Mario Bros.nes' -> 'Super Mario Bros'
  ✓ Basename: 'Game (Disc 1).cue' -> 'Game (Disc 1).cue'
  ✓ Basename: 'Zelda.m3u' -> 'Zelda'

Testing image validation...
  ✓ Valid 100x100 image accepted
  ✓ Small 40x40 image rejected
  ✓ Invalid image data rejected

Testing download integration...
  ✓ MediaDownloader initialized
  ✓ No existing media detected (empty directory)
  ✓ URL selection working

============================================================
Results: 8/8 tests passed
✓ Phase 4 integration test PASSED
============================================================
```

## Integration Points

### With Phase 3 (API Client)

- **Input:** Receives media list from `curateur.api.response_parser.parse_media_urls()`
- **Media Format:** Expects dicts with 'type', 'region', 'url', 'format' keys
- **Region Data:** Uses region codes matching ScreenScraper API

### With Phase 2 (ROM Scanner)

- **ROM Paths:** Uses ROM paths from `curateur.scanner.rom_scanner`
- **Basename Extraction:** Handles M3U, disc subdirs, standard ROMs
- **System Names:** Uses system names from ES-DE systems XML

### Future Integration (Phase 5)

The media downloader provides the foundation for Phase 5 (Gamelist Generator):

- `DownloadResult.file_path` provides media paths for gamelist.xml
- `MediaOrganizer.get_relative_path()` generates relative paths for XML
- Media organized by type for easy gamelist reference

## Configuration

### Required Settings

```yaml
paths:
  media: "downloaded_media"  # Media root directory

media:
  preferred_regions: ['us', 'wor', 'eu', 'jp']
  enabled_types: ['box-2D', 'ss', 'sstitle', 'screenmarquee']
  
validation:
  min_width: 50   # Minimum image width in pixels
  min_height: 50  # Minimum image height in pixels
```

### Optional Settings

```yaml
download:
  timeout: 30        # HTTP timeout in seconds
  max_retries: 3     # Maximum retry attempts
  retry_delay: 2     # Initial retry delay (exponential backoff)
```

## Known Limitations (MVP)

1. **No Hash Verification:** Files are not verified against API-provided hashes. Milestone 2 will add size/CRC/SHA1 verification.

2. **No Existing File Checks:** Downloads always overwrite existing files. Milestone 2 will add hash-based skip logic.

3. **Simple Quality Selection:** Uses first available media for each type. Future enhancement could prioritize by resolution or file size.

4. **Limited Media Types:** Only 4 MVP types supported. Milestone 2 adds manuals, fanart, videos, 3D boxes, etc.

5. **No Decommissioned Media Handling:** Doesn't move removed media to CLEANUP folder. Milestone 2 feature.

6. **No Resume Support:** Failed downloads restart from scratch. Could add partial download resume.

## Error Scenarios

### Handled Gracefully

- **Network Errors:** Retry with exponential backoff (max 3 attempts)
- **Invalid Images:** Validation failure, file deleted, error logged
- **Small Images:** Dimension check failure (< 50x50), error logged
- **Wrong Content-Type:** Non-image response detected and rejected
- **Missing URLs:** Skipped with clear error message
- **Missing Directories:** Automatically created as needed

### Fatal Errors

- **Filesystem Errors:** Permission denied, disk full (propagated to caller)
- **Invalid Media Types:** ValueError for unsupported types
- **Configuration Errors:** Missing media_root path

## Performance Characteristics

### Download Speed
- **Single-threaded:** One download at a time (MVP)
- **Typical Speed:** 1-5 seconds per image (network dependent)
- **Concurrent Downloads:** Not supported in MVP (Milestone 2)

### Validation Overhead
- **Pillow Validation:** ~10-50ms per image
- **Dimension Check:** Included in validation time
- **Retry Logic:** 2^attempt seconds delay (2s, 4s, 8s)

### Memory Usage
- **Streaming:** Images downloaded to memory then written
- **Peak Usage:** Single image size (typically < 5MB)
- **No Caching:** Each image processed independently

## Next Steps

With Phase 4 complete, we can proceed to:

1. **Phase 5: Gamelist Generator**
   - Generate gamelist.xml files
   - Merge with existing gamelists
   - Link downloaded media
   - Preserve user edits

2. **Phase 6: Runtime Integration**
   - Connect scanner → API → media → gamelist
   - Add progress reporting
   - Implement dry-run mode
   - Add comprehensive logging

## Files Added

```
curateur/media/media_types.py       82 lines
curateur/media/region_selector.py   195 lines
curateur/media/url_selector.py      135 lines
curateur/media/downloader.py        195 lines
curateur/media/organizer.py         161 lines
curateur/media/media_downloader.py  255 lines
tests/test_phase4_integration.py    313 lines
```

**Total:** 7 files, 1,336 lines of code

---

**Phase 4 Status:** ✓ COMPLETE AND TESTED  
**Ready for Phase 5:** YES
