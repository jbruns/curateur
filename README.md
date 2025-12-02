# curateur

[ScreenScraper](https://www.screenscraper.fr)-powered ROM metadata and media scraper that produces [ES-DE](https://es-de.org)-ready `gamelist.xml` files, and organizes downloaded media.

**BETA QUALITY**: curateur is designed to use a minimally-invasive approach, only making changes to fields it specifically manages in `gamelist.xml` files, but the program has not been extensively tested with a wide variety of setups.

## What it does
- Does a very similar job to [Skraper](https://www.skraper.net) - scans your ROMs, pairs them with as many types of media as you like (boxart, screenshots, manuals, videos, ...), sourced from [ScreenScraper](https://www.screenscraper.fr).
- **Core features:**
  - Cross-platform: should work on anything that can run Python (Windows, Linux, Mac; single-board computers)
  - Single file configuration: configure once in YAML. Override on command line if needed.
  - Region preference order + language preference: compares ROM region and your configured preferences to what's available from ScreenScraper.
  - Audits to your liking: easily narrow the workflow to just added ROMs, or do an exhaustive audit of all metadata and media assets 
  - ES-DE first: supports anything which uses ES-DE as its frontend (RetroBat, EmuDeck, and of course Android handhelds)
  - Designed to be a true curator of your collection: leaves your preferences alone, only updating what it's supposed to, with the most appropriate match for your ROMs.

## How it does it
curateur is designed to be as fast as possible, and as thorough as you want it to be.

- Multi-threaded: metadata fetches and media downloads are optimized for throughput, while respecting the limits imposed on your user account by ScreenScraper. Note that for the best possible speed, you'll need to contribute financially or otherwise to ScreenScraper; see their terms for details.
- Cache: data received from ScreenScraper is retained for extremely fast resumes, end-to-end audits, and ongoing updates. Unless you specifically direct, media is not re-downloaded if not required. To avoid eating into your API quota unnecessarily, successful metadata requests are not repeated.
- Conservative matching: ROM name, size, and hash are validated against what ScreenScraper responds with, so we're sure we have the right game.
- Massive collections: thousands of ROMs across many systems are no problem.
- Set and forget: Initial data population is designed to be hands-off. Metadata and media can be updated on an ongoing basis, as an automated task.

## Quick start
Requirements: Python 3.8+, ScreenScraper account, ES-DE [`es_systems.xml`](https://gitlab.com/es-de/emulationstation-de/-/tree/master/resources/systems), and ROM/media output directories with write access.

### For best results
- Use ROM collections which are **uncompressed** and follow No-Intro or Redump standard naming patterns.
- Organize disc-based systems which support .m3u files (for example, PSX) in an ES-DE friendly way:
  - hidden directory `.multidisc` inside your `roms/<system>` directory
  - `.m3u` files created for multi-disc titles; curateur will seek out the first disc's `.cue` file and use that to scrape metadata
  - **TODO**: curateur could offer a tool to help organize this way!

### Initial Setup

```bash
git clone https://github.com/jbruns/curateur
cd curateur
python -m venv .venv && source .venv/bin/activate
pip install -e .

# Create your config
cp config.yaml.example config.yaml
```

Edit `config.yaml` with your ScreenScraper user credentials plus paths for ROMs, media, gamelists, and `es_systems.xml`.

Run a scrape:
```bash
python -m curateur.cli                       # scrape all systems from es_systems.xml
python -m curateur.cli --systems nes snes    # limit to specific systems 
python -m curateur.cli --dry-run             # validate and query API without downloading media
python -m curateur.cli --enable-search       # allow name-based search fallback when hashes miss
python -m curateur.cli --clear-cache         # drop cached API responses before running
```

## Configuration guide
`config.yaml.example` documents every field; key sections to set:
- `screenscraper.user_id` / `screenscraper.user_password`: your ScreenScraper login.
- `paths`: `roms`, `media`, `gamelists`, `es_systems` (supports `%ROMPATH%` in ES-DE Systems XML - this file does not need to be modified).
- `scraping`: systems allowlist, scrape mode (`new_only | changed | force | skip`), metadata merge strategy, region/language preferences, integrity threshold for gamelists, optional auto-favorite rules.
- `media`: enabled media types, validation mode (`disabled | normal | strict`), image size floor, optional cleanup of disabled asset types.
- `api`: request timeout, retry counts/backoff, quota warning threshold, optional rate-limit overrides (capped to API limits).
- `runtime`: dry-run toggle, hash algorithm and size cap for CRC, cache enablement, rate-limit override block.
- `search`: enable hash-miss fallback, confidence threshold, max results, optional interactive prompts.
- `logging`: level, console toggle, optional log file path.

Metadata cache: stored alongside each gamelist directory in `.cache/metadata_cache.json` with a 7-day TTL. Use `--clear-cache` to wipe it before a run.

Outputs:
- `gamelists/` (per system) with hashes and integrity validation.
- `downloaded_media/` organized by system and media type.
- `gamelists/<system>/curateur_summary_<date>_<time>.log` for summary of work performed. 

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
