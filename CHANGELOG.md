# Changelog

All notable changes to curateur will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Distribution
- PyInstaller build configuration for standalone executables
- Platform-specific installers (Windows .exe, macOS .dmg, Linux AppImage)
- PyPI package publication
- GitHub Actions automated release workflow

## [1.0.0] - TBD

### Added
- **Core Scraping Features**
  - ScreenScraper API integration with full authentication
  - Multi-threaded parallel ROM processing
  - Configurable concurrency based on API limits
  - Hash-based ROM identification (CRC32, MD5, SHA1)
  - Name-based search fallback with confidence scoring
  - Conservative name verification to prevent false matches

- **Metadata Management**
  - ES-DE gamelist.xml generation and updating
  - Non-invasive metadata merge (preserves user edits)
  - Configurable merge strategies (prefer-existing, prefer-scraped, merge)
  - Gamelist integrity validation with match ratio thresholds
  - Metadata cache with 7-day TTL for fast re-runs

- **Media Handling**
  - Multi-media type support (boxart, screenshots, videos, manuals, etc.)
  - Region-aware media selection with preference ordering
  - Image validation (size, format, corruption detection)
  - Media organization by system and type
  - Skip existing media to avoid re-downloads
  - Dry-run mode for validation without downloads

- **ROM Scanning**
  - Cross-platform ROM directory scanning
  - ES-DE system definition parser
  - Multi-disc game support (.m3u playlists, .cue files)
  - Configurable hash size limits for large ROMs
  - ROM type detection (standard, disc, archive, contained)

- **API Rate Limiting**
  - Intelligent throttling respecting ScreenScraper quotas
  - Adaptive backoff on rate limit errors
  - Quota warning thresholds
  - Connection pool health tracking
  - Automatic client reset on repeated timeouts

- **Error Handling**
  - Hierarchical exception system (Fatal, Retryable, Skippable)
  - Exponential backoff retry with configurable attempts
  - Detailed error categorization and logging
  - Graceful degradation on API errors
  - Work queue retry mechanism for transient failures

- **User Interface**
  - Rich terminal UI with live progress tracking
  - Interactive search result selection
  - Keyboard shortcuts (pause, skip, quit)
  - Integrated logging panel
  - Performance metrics and ETA calculation
  - System-level operation display

- **Configuration**
  - Single YAML configuration file
  - Comprehensive settings for all features
  - CLI argument overrides
  - Sensible defaults for quick start
  - Example configuration with documentation

- **Workflow Orchestration**
  - Priority-based work queue (Normal, High, Critical)
  - Producer-consumer pattern for efficient processing
  - Graceful shutdown with in-flight completion
  - Progress tracking and reporting
  - Performance monitoring (throughput, API calls, memory, CPU)
  - Summary logs per scraping session

### Features by Component

#### API Client (`curateur/api/`)
- Full ScreenScraper API v2 support
- `jeuInfos.php` for hash-based lookups
- `jeuRecherche.php` for name-based search
- `ssuserInfos.php` for quota and limit checking
- Response parsing with XML validation
- Media URL selection and region prioritization
- Obfuscated developer credentials
- Platform ID mapping for all ES-DE systems

#### Scanner (`curateur/scanner/`)
- ROM file discovery with ES-DE system definitions
- Hash calculation with size-based algorithm selection
- Multi-disc detection and .m3u parsing
- Archive and compressed ROM handling
- Duplicate detection by hash

#### Gamelist (`curateur/gamelist/`)
- XML parser for existing gamelists
- XML writer with proper encoding
- Metadata merge with field-level control
- Integrity validator with configurable thresholds
- Path normalization for cross-platform compatibility
- Game entry data structures

#### Media (`curateur/media/`)
- Media downloader with resume support
- Region selector with preference ordering
- URL selector with fallback logic
- Media type definitions and mappings
- File organizer for downloaded assets
- Image validation (Pillow-based)

#### Workflow (`curateur/workflow/`)
- Orchestrator for end-to-end scraping pipeline
- Thread pool manager with semaphore-based concurrency
- Work queue with priority levels and retry tracking
- Evaluator for scrape/skip/search decisions
- Progress tracker with system-level stats
- Performance monitor with metrics collection

#### UI (`curateur/ui/`)
- Console UI with Rich library
- Live progress bars and spinners
- Interactive prompts with defaults
- Keyboard listener for non-blocking input
- Logging integration with color coding

#### Tools (`curateur/tools/`)
- Setup wizard for developer credentials
- System map generator from ScreenScraper data
- Code quality checker for CI/CD

### Configuration Options
- **ScreenScraper**: User credentials, API keys
- **Paths**: ROM, media, gamelist, ES systems XML
- **Scraping**: Mode (new_only, changed, force, skip), system filters, regions, languages
- **Media**: Enabled types, validation level, cleanup options
- **API**: Timeouts, retries, quota warnings, rate overrides
- **Runtime**: Dry-run, hash algorithm, cache settings, CRC size limit
- **Search**: Fallback enable, confidence threshold, max results, interactive mode
- **Logging**: Level, console output, file path

### Documentation
- Comprehensive README with quick start and configuration guide
- Testing strategy document with marker taxonomy
- Code quality enforcement with custom tooling
- Inline docstrings and type hints throughout

### Testing
- 204 test cases across unit, integration, and e2e levels
- Test markers: `unit`, `integration`, `e2e`, `slow`, `live`
- Mock-based API testing with respx
- Coverage tracking with pytest-cov
- CI/CD via GitHub Actions
- Fast test profile for PR checks (<2 minutes)

### Development
- Modern Python packaging (pyproject.toml, setuptools)
- Dependency constraints for reproducible builds
- Makefile targets for common tasks
- Pre-commit hook examples
- Code quality checks with custom tooling

### Requirements
- Python 3.8+
- ScreenScraper account (free or paid)
- ES-DE systems XML file
- Write access to ROM/media/gamelist directories

### Supported Platforms
- Windows (7+, 10, 11)
- macOS (10.13+)
- Linux (Ubuntu, Debian, Fedora, Arch, etc.)
- Any OS with Python 3.8+

### Distribution Formats
- PyPI package (`pip install curateur`)
- Standalone Windows executable
- macOS app bundle and DMG
- Linux AppImage
- Source installation from Git

---

## Version History

### [1.0.0] - TBD
Initial public release with full feature set.

**Beta Quality Notice**: While the core functionality is solid and well-tested, curateur
is labeled as beta quality due to limited real-world testing across diverse ROM
collections and ES-DE configurations. Please report any issues on GitHub.

---

## Upgrade Notes

### From Source to v1.0.0
If you've been running from source (git clone), you can now:
- Install from PyPI: `pip install curateur`
- Download standalone executables from GitHub Releases
- Your existing `config.yaml` will continue to work

### Configuration Changes
No breaking changes in v1.0.0. All existing configurations are forward-compatible.

---

## Roadmap

See [GitHub Issues](https://github.com/jbruns/curateur/issues) for planned features and improvements.

Potential future enhancements:
- Additional media types and sources

---

## Credits

**Powered by:**
- [ScreenScraper.fr](https://www.screenscraper.fr) - Game metadata and media API
- [ES-DE](https://es-de.org) - EmulationStation Desktop Edition

**Built with:**
- Python ecosystem and excellent libraries (httpx, lxml, Pillow, rich, PyYAML, psutil)
- GitHub Actions for CI/CD
- PyInstaller for standalone builds

**License:** GPL-3.0-or-later

---

[Unreleased]: https://github.com/jbruns/curateur/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/jbruns/curateur/releases/tag/v1.0.0
