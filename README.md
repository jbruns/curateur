# curateur

ScreenScraper-powered ROM metadata and media scraper that produces ES-DE-ready `gamelist.xml` files and organizes downloaded assets.

## What it does
- Scans ES-DE systems from `es_systems.xml`, handling standard ROMs, multi-disc directories, and `.m3u` playlists with conflict detection.
- Authenticates against ScreenScraper with adaptive throttling, retry/backoff, quota awareness, and optional API response caching.
- Fetches metadata and media, merges into existing gamelists with configurable strategies (preserve user edits, refresh fields, or full reset).
- Downloads and validates media by type, honors region/language preferences, and can clean disabled asset types.
- Generates ES-DE-compatible `gamelist.xml` files and stores per-ROM/media hashes for change detection.
- Ships a Rich-powered console UI for live progress, throttling status, and keyboard controls when running interactively.

## Quick start
Requirements: Python 3.8+, ScreenScraper account, ES-DE `es_systems.xml`, and ROM/media output directories with write access.

```bash
git clone <repository-url>
cd curateur
python -m venv .venv && source .venv/bin/activate
pip install -e .

# Create your config
cp config.yaml.example config.yaml
```

Edit `config.yaml` with your ScreenScraper user credentials plus paths for ROMs, media, gamelists, and `es_systems.xml`.

Run a scrape:
```bash
curateur                       # scrape all systems from es_systems.xml
curateur --systems nes snes    # limit to specific systems
curateur --dry-run             # validate and query API without downloading media
curateur --enable-search       # allow name-based search fallback when hashes miss
curateur --clear-cache         # drop cached API responses before running
```

## Configuration guide
`config.yaml.example` documents every field; key sections to set:
- `screenscraper.user_id` / `screenscraper.user_password`: your ScreenScraper login.
- `paths`: `roms`, `media`, `gamelists`, `es_systems` (supports `%ROMPATH%` in ES-DE XML).
- `scraping`: systems allowlist, scrape mode (`new_only | changed | force | skip`), metadata merge strategy, region/language preferences, integrity threshold for gamelists, optional auto-favorite rules.
- `media`: enabled media types, validation mode (`disabled | normal | strict`), image size floor, optional cleanup of disabled asset types.
- `api`: request timeout, retry counts/backoff, quota warning threshold, optional rate-limit overrides (capped to API limits).
- `runtime`: dry-run toggle, hash algorithm and size cap for CRC, cache enablement, rate-limit override block.
- `search`: enable hash-miss fallback, confidence threshold, max results, optional interactive prompts.
- `logging`: level, console toggle, optional log file path.

Metadata cache: stored alongside each gamelist directory in `.cache/metadata_cache.json` with a 7-day TTL. Use `--clear-cache` to wipe it before a run.

Outputs:
- `gamelists/` (per system) with hashes and integrity validation.
- `media/` organized by system and media type.
- `scraping_errors.log` if failures occur, plus optional configured log file.

## Project layout
- `curateur/cli.py`: CLI entrypoint and runtime wiring.
- `curateur/config/`: config loading/validation and ES-DE parser.
- `curateur/scanner/`: ROM discovery, hashing, playlist/disc handling.
- `curateur/api/`: ScreenScraper client, throttle manager, cache, error handling.
- `curateur/media/`: media selection, validation, and path mapping.
- `curateur/gamelist/`: metadata merge rules and XML writer.
- `curateur/workflow/`: orchestrator, queues, threading, performance monitor, progress tracking.
- `curateur/ui/`: optional Rich console UI.
- `curateur/tools/`: maintenance scripts (see below).

## Development
- Install dev extras: `pip install -e .[dev]`.
- Run tests (pytest markers are strict by default):
  - Fast profile: `pytest -m "not slow and not live" --cov=curateur --cov-report=term-missing`
  - Full without live: `pytest -m "not live"`
  - Live API checks (requires credentials): `pytest -m "live" --maxfail=1`
- Make targets: `make test`, `make check-corruption`, `make check-quality`, `make lint` (strict).
- Testing approach is detailed in `TESTING_STRATEGY.md` (taxonomy, fixtures, and marker guidance).
- Package entrypoint is `curateur`; during development you can also run `python -m curateur.cli ...`.

### Dependencies & constraints
- Ranges are bounded to allow patch/minor updates while blocking breaking majors (`requirements.txt`, `pyproject.toml`).
- For reproducible installs, use the pinned set: `pip install -e .[dev] -c constraints.txt` (or `pip install -r requirements.txt -c constraints.txt`).
- To refresh pins: create a clean venv, install from `requirements.txt`, run the test suite, then `pip freeze | grep -vE '^(pip|setuptools|wheel)==|^-e ' > constraints.txt`.
- Keep the ranges and the constraints file in sync when updating dependencies.

### Maintainer tools
- Code quality scanner: `python3 curateur/tools/code_quality_check.py curateur/` (see `curateur/tools/README.md`).
- Update ScreenScraper platform mapping: `python -m curateur.tools.generate_system_map --es-systems es_systems.xml --systemes-liste systemesListe.xml`.
- Developer credentials (maintainers only): `python -m curateur.tools.setup_dev_credentials` to refresh obfuscated values in `curateur/api/credentials.py`.

## Tips & behavior notes
- Dry-run leaves filesystem untouched while exercising scanning, API queries, validation, and logging.
- Name verification strictness is configurable; set `scraping.name_verification` to `disabled` when testing against sparse data.
- Media validation can be expensive; start with `disabled` or `normal` before enabling `strict`.
- Interactive search prompts require a TTY; CI/non-interactive runs should leave `interactive_search` off.
- The console UI is enabled automatically on TTY runs (disabled for dry-run) and provides live throttle and queue visibility with keyboard shortcuts for skip/quit.

## License
License information is pending; use is currently limited to collaborators until finalized.
