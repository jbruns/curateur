# Implementation TODOs

Linking each work item to the module/data-contract defined in `IMPLEMENTATION_PLAN.md`.

## Core Infrastructure
- [ ] Implement `curateur.config.loader.load_config` (AT-1.1) and hook CLI `--config` parsing.
- [ ] Implement `curateur.config.validator.validate_config` with schema from `config.yaml.example` (AT-1.2).
- [ ] Build `parse_es_systems` and `SystemDefinition` wiring (AT-2.1).

## ROM Scanner
- [ ] Implement `scan_system` covering standard ROMs, M3U parsing, disc subdirectories (AT-2.2–2.4).
- [ ] Add conflict detection between M3U and disc subdirs (AT-2.4).

## API Client & Verification
- [ ] Implement `fetch_game_info` with unified error handling (AT-3.1, AT-3.3).
- [ ] Build `name_verifier.verify_match` and similarity thresholds (AT-3.2).

## Media Downloader
- [ ] Implement `download_media`, region selection, and image verification (AT-4.1–4.3).
- [ ] Milestone 2: `decommission.py` handling for cleanup folder (AT-4.4).

## Gamelist Generator
- [ ] Implement `write_gamelist` to meet AT-5.1–5.3.

## Runtime
- [ ] Implement `ProgressTracker` + `ErrorLogger` integration (AT-6.1–6.2).
- [ ] Implement CLI flags (`--dry-run`, `--systems`, `--update`, `--skip-scraped`) (AT-6.3–6.4).

Track completion with acceptance tests in `tests/ACCEPTANCE_TESTS.md`.
