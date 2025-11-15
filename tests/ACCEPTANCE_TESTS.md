# Curateur Acceptance Test Plan

Traceable acceptance scenarios tied directly to the module contracts and data models defined in `IMPLEMENTATION_PLAN.md`.

## 1. Configuration Lifecycle
- [ ] **AT-1.1 Load Sample Config**: `curateur.config.loader.load_config` loads `config.yaml.example` without raising and resolves relative paths.
- [ ] **AT-1.2 Validation Failures**: Invalid media type (`video-hd`) triggers `ConfigValidationError` with actionable message.
- [ ] **AT-1.3 CLI Override**: Supplying `--config` CLI flag updates the path passed to `load_config`.

## 2. System & ROM Parsing
- [ ] **AT-2.1 es_systems Parsing**: `parse_es_systems` converts sample `es_systems.xml` into `SystemDefinition` objects (No-Intro platform IDs).
- [ ] **AT-2.2 No-Intro Filename Regions**: `scan_system` detects region codes `(USA)`, `(Europe)` from filenames like `Example Adventure (USA).zip`.
- [ ] **AT-2.3 Redump Disc Handling**: Disc subdirectory samples (e.g., `Demo Orbit (Disc 1).cue/`) produce `RomEntry` records with `rom_type="disc_subdir"` and correct `primary_identifier`.
- [ ] **AT-2.4 M3U Playlist Linking**: M3U referencing `.multidisc/` entries populates auxiliary metadata (`disc1_path`).
- [ ] **AT-2.5 Multi-Region Filenames**: Filenames with two or three region tags (e.g., `Dual Strike (USA, Europe).zip`, `Trio Dash (USA, Europe, Japan).zip`) detect all regions; `(World)` remains a standalone region.
- [ ] **AT-2.6 Language/Revision Indicators**: Complex suffixes like `Game Name '98 (USA) (En,Fr,De,Es,It,Nl) (RE).cue` parse language sets and revision flags without breaking base name extraction.

## 3. API Client & Verification
- [ ] **AT-3.1 Request Construction**: `fetch_game_info` builds jeuInfos.php request using disc-subdir metadata (filename/size/CRC from contained file).
- [ ] **AT-3.2 Name Verification Thresholds**: `verify_match` accepts `(USA)` vs localized titles when similarity ≥ configured threshold.
- [ ] **AT-3.3 Error Handling**: HTTP 429 response triggers exponential backoff and succeeds on retry; HTTP 403 raises `FatalError`.

## 4. Media Download & Naming
- [ ] **AT-4.1 Region Prioritization**: Media selection favors ROM-detected region (No-Intro naming) before fallback order.
- [ ] **AT-4.2 File Naming Consistency**: Disc-subdir paths emit gamelist `<path>./<dir>` (no slash) and media saved as `<dir>.jpg`.
- [ ] **AT-4.3 Verification Failures**: 32x32 image triggers rejection, file removal, and logged warning.
- [ ] **AT-4.4 Cleanup Folder Routing** (Milestone 2): Decommissioned assets move to `<paths.media>/CLEANUP/<system>/<media_type>/`.

## 5. Gamelist Generation
- [ ] **AT-5.1 XML Schema Compliance**: Output passes ES-DE validation tool (provider node + game entries).
- [ ] **AT-5.2 HTML Entity Decoding**: API synopsis containing `&amp;` is written as `&` in XML text nodes.
- [ ] **AT-5.3 Atomic Write**: Interruption mid-write leaves previous gamelist intact (temp file cleanup verified).

## 6. Workflow & Logging
- [ ] **AT-6.1 Progress Tracker**: `ProgressTracker` shows `[current/total]` updates and final summary per system.
- [ ] **AT-6.2 Error Summary**: `ErrorLogger` writes deterministic `curateur_summary.log` for sample failures.
- [ ] **AT-6.3 CLI Flags**: `--dry-run` executes scanning + API validation without downloading media, logging intent.
- [ ] **AT-6.4 Skip/Update Modes** (Milestone 2): Decision table outcomes verified across ROMs with missing media, complete media, and metadata gaps.

Each acceptance test should reference fixture ROM sets (No-Intro/Redump style) committed under `tests/fixtures/` when available.
