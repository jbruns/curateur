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

## MVP Phase 2 - ROM Scanner ✓ COMPLETED
- [x] Implement `scan_system` covering standard ROMs, M3U parsing, disc subdirectories (AT-2.2–2.4).
- [x] Add conflict detection between M3U and disc subdirs (AT-2.4).
- [x] Implement CRC32 hash calculation with size limits.
- [x] Create ROM file type detection (standard, M3U, disc subdir).
- [x] Build M3U playlist parser.
- [x] Implement disc subdirectory validator.
- [x] Create comprehensive integration tests (7/7 passing).

**Phase 2 Complete**: All ROM scanning components implemented and tested with fixture data.

## MVP Phase 3 - API Client & Verification ✓ COMPLETED
- [x] Implement `fetch_game_info` with unified error handling (AT-3.1, AT-3.3).
- [x] Build `name_verifier.verify_match` and similarity thresholds (AT-3.2).
- [x] Create API client with jeuInfos.php endpoint.
- [x] Implement retry logic with exponential backoff.
- [x] Add rate limiting (API-provided limits).
- [x] Parse and validate API XML responses.
- [x] Create API integration tests (9/9 passing).

**Phase 3 Complete**: ScreenScraper API client with error handling, rate limiting, name verification, and response parsing.

**Phase 1 Complete**: Core infrastructure (6/6 tests passing).  
**Phase 2 Complete**: ROM scanner (7/7 tests passing).  
**Phase 3 Complete**: API client (9/9 tests passing).  
**Phase 4 Complete**: Media downloader (8/8 tests passing).  
**Phase 5 Complete**: Gamelist generator (7/7 tests passing + extra fields preservation).  
**Phase 6 Complete**: Runtime integration (MVP workflow complete).  
**End-to-End Test**: Phases 1+2 integration verified ✓

## MVP Phase 4 - Media Downloader ✓ COMPLETED
- [x] Implement `download_media`, region selection, and image verification (AT-4.1–4.3).
- [x] Create media type mappings (ScreenScraper → ES-DE directories).
- [x] Implement region detection and prioritization.
- [x] Build URL selector with region filtering.
- [x] Create image downloader with validation (Pillow).
- [x] Implement media file organizer (ES-DE structure).
- [x] Build integrated MediaDownloader class.
- [x] Create comprehensive integration tests (8/8 passing).

**Phase 4 Complete**: Media downloader with region prioritization, image validation, and ES-DE organization.

Note: Milestone 2 `decommission.py` handling for cleanup folder (AT-M2B.1 / AT-4.4) is deferred to post-MVP.

## MVP Phase 5 - Gamelist Generator ✓ COMPLETED
- [x] Implement GameEntry and GamelistMetadata data structures.
- [x] Create XML writer with ES-DE format compliance.
- [x] Build gamelist parser and merger (preserves user edits).
- [x] Implement path handler for ROM and media relative paths.
- [x] Create integrated GamelistGenerator class.
- [x] Build comprehensive integration tests (7/7 passing).
- [x] Add extra_fields preservation for unknown XML elements.

**Phase 5 Complete**: Gamelist generator with XML I/O, intelligent merging, HTML entity handling, ES-DE compliance, and unknown field preservation. See `PHASE5_COMPLETE.md` for full documentation.

## MVP Phase 6 - Runtime Integration ✓ COMPLETED
- [x] Implement workflow orchestrator connecting scanner → API → media → gamelist.
- [x] Create progress tracker with system/ROM counts and statistics.
- [x] Implement error logger with summary reporting.
- [x] Add `--dry-run` flag for preview mode.
- [x] Add `--systems` flag for selective scraping.
- [x] Update CLI with full workflow integration.
- [x] Complete phase documentation.

**Phase 6 Complete**: End-to-end scraping workflow with progress tracking, error handling, dry-run mode, and system filtering. See `PHASE6_COMPLETE.md` for full documentation.

**MVP Status:** ✓ ALL PHASES COMPLETE

### Milestone 2 Features (NOT YET IMPLEMENTED)
- [ ] Skip mode: `--skip-scraped` flag (AT-M2A.2 / AT-6.4)
- [ ] Update mode: `--update` flag
- [ ] Checkpoint/resume functionality
- [ ] Rich console UI with split panels
- [ ] Multi-threaded downloads
- [ ] Media hash verification
- [ ] Decommissioned media management

Track completion with acceptance tests in `tests/ACCEPTANCE_TESTS.md`.
