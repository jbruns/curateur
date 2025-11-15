# Implementation TODOs

Linking each work item to the module/data-contract defined in `IMPLEMENTATION_PLAN.md`.

## MVP Phase 1 - Core Infrastructure ✓ COMPLETED
- [x] Implement `curateur.config.loader.load_config` (AT-1.1) and hook CLI `--config` parsing.
- [x] Implement `curateur.config.validator.validate_config` with schema from `config.yaml.example` (AT-1.2).
- [x] Build `parse_es_systems` and `SystemDefinition` wiring (AT-2.1).
- [x] Implement credential obfuscation system (`api/obfuscator.py`, `api/credentials.py`).
- [x] Create `tools/setup_dev_credentials.py` utility for maintainer use.
- [x] Create `tools/generate_system_map.py` utility for platform mapping.
- [x] Implement `api/system_map.py` with PLATFORM_SYSTEMEID_MAP constant.
- [x] Build main CLI entry point (`cli.py`) with MVP argument parsing.
- [x] Create project structure with proper package organization.
- [x] Add `requirements.txt` and `pyproject.toml` for dependencies.

## MVP Phase 2 - ROM Scanner (IN PROGRESS)
- [ ] Implement `scan_system` covering standard ROMs, M3U parsing, disc subdirectories (AT-2.2–2.4).
- [ ] Add conflict detection between M3U and disc subdirs (AT-2.4).
- [ ] Implement CRC32 hash calculation with size limits.
- [ ] Create ROM file type detection (standard, M3U, disc subdir).
- [ ] Build M3U playlist parser.
- [ ] Implement disc subdirectory validator.

**Phase 1 Complete**: All core infrastructure implemented and tested. Integration test passing 6/6.

## MVP Phase 3 - API Client & Verification (NOT STARTED)
- [ ] Implement `fetch_game_info` with unified error handling (AT-3.1, AT-3.3).
- [ ] Build `name_verifier.verify_match` and similarity thresholds (AT-3.2).

## MVP Phase 4 - Media Downloader (NOT STARTED)
- [ ] Implement `download_media`, region selection, and image verification (AT-4.1–4.3).
- [ ] Milestone 2: `decommission.py` handling for cleanup folder (AT-M2B.1 / AT-4.4).

## MVP Phase 5 - Gamelist Generator (NOT STARTED)
- [ ] Implement `write_gamelist` to meet AT-5.1–5.3.

## MVP Phase 6 - Runtime Integration (NOT STARTED)
- [ ] Implement `ProgressTracker` + `ErrorLogger` integration (AT-6.1–6.2).
- [ ] Implement MVP CLI flags (`--dry-run`, `--systems`) (AT-6.3).
- [ ] Milestone 2: CLI flags tied to skip/update (`--update`, `--skip-scraped`) (AT-M2A.2 / AT-6.4).

Track completion with acceptance tests in `tests/ACCEPTANCE_TESTS.md`.
