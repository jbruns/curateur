# Testing Strategy

Curateur needs a test suite that is CI-first while remaining easy to run and interpret locally. The plan below defines how we structure tests, what each layer should cover, and how to keep “live” and long-running suites isolated while still being runnable on demand.

## Goals
- Keep a fast default signal for every PR (finish in minutes, not hours).
- Provide confidence for releases by running deeper integration/end-to-end (E2E) checks on demand or on scheduled builds.
- Make tests self-describing and diagnosable without reading code (good names, focused assertions, tight fixtures).
- Prefer hermetic tests; allow “live” API coverage behind explicit opt-in.

## Test Taxonomy & Markers
- `unit` — single function/class with I/O mocked; milliseconds runtime.
- `integration` — multiple components together (e.g., config + validator + scanner) using real filesystem/temp dirs and stubbed network.
- `e2e` — full workflow or CLI-level runs that exercise threading and XML/media outputs.
- Cross-cutting markers:
  - `slow` — long-running; excluded from default CI matrix.
  - `live` — real ScreenScraper calls; excluded from CI by default and require credentials.
  - Combine markers as needed (`@pytest.mark.e2e @pytest.mark.slow`).
- Suggested run profiles:
  - **Fast local/CI**: `pytest -m "not slow and not live" --cov=curateur --cov-report=term-missing`.
  - **Full (no live)**: `pytest -m "not live"`.
  - **Live check**: `pytest -m "live" --maxfail=1` after exporting credentials.

## Layout & Naming
- Directory-per-package to mirror source:  
  ```
  tests/
    api/        # httpx client, throttling, caching
    config/     # loader, validator, es_systems parsing
    scanner/    # rom scanning, hashing, playlists
    media/      # downloader, URL/region selection, file validation
    gamelist/   # metadata merge, XML writer/parser, integrity rules
    workflow/   # orchestrator, queues, concurrency
    ui/         # console prompts/output formatting (non-interactive)
    tools/      # generators and maintenance scripts
    data/       # static fixtures (tiny ROMs, XML, YAML, images)
  ```
- Tests follow `test_<subject>.py`, classes `Test<Subject>`, functions `test_<behavior>` to match `pytest.ini`.
- Keep `tests/conftest.py` minimal and reusable (temp dirs, config loading, mock API server/response builders).

## Package Coverage Focus
- **config**: round-trip load/validate, schema errors, required/default handling, es_systems parsing with malformed XML samples.
- **api**: respx-backed HTTP mocks for happy/error paths, throttling/rate override math, cache behavior, name matching/confidence scoring, error categorization, credential obfuscation idempotence.
- **scanner**: ROM type detection, CRC/hash limits, m3u/disc handling, conflict detection, and directory filters.
- **media**: URL/region selection precedence, downloader resumes/skips, image validation failures, filesystem layout per media type, dry-run behavior.
- **gamelist**: metadata merge rules, integrity thresholds, XML writer formatting/encoding, parser robustness on corrupted files, path normalization.
- **workflow**: orchestrator happy path with stubbed components, retry/skip flows, work queue prioritization, evaluator decisions, progress reporting signals.
- **ui**: prompt defaults/non-interactive modes, console logging verbosity, keyboard listener safeguards (ensure tests never block).
- **tools**: system map generation with small fixture files, dev credential helper dry-run.

## Fixtures & Test Data
- Use small, committed fixtures under `tests/data` (tiny ROMs/playlists, trimmed systemesListe.xml, sample gamelist.xml/media files, minimal config.yaml).
- Build factories/helpers for ScreenScraper-like responses to avoid brittle JSON blobs.
- Prefer `tmp_path`/`tmp_path_factory` for filesystem work; keep generated files under the temp tree for easy cleanup.

## End-to-End & Live Tests
- E2E harness: invoke CLI (`python -m curateur.cli ...`) or orchestrator with stubbed API/media layers; assert on produced gamelist.xml, media directory layout, and logs.
- Live runs: gated by `@pytest.mark.live` and environment/config presence (e.g., credentials in config fixture). Keep them short (few ROMs) and assert on contract-level behavior, not specific asset bytes.

## Observability & Failure Clarity
- Assert on structured return objects, status enums, and log messages (`caplog`) to surface failure reasons.
- When using concurrency, add deterministic seeds and timeouts; avoid sleeps by using event-driven waits.
- Use snapshots/golden files sparingly; prefer semantic assertions (parsed XML dicts, media file manifests).

## Coverage Targets & Quality Gates
- Target >85% line coverage overall, >95% for pure logic modules (config, scanner utilities, selectors).
- Fail CI on unknown pytest markers (`--strict-markers` already enabled) and keep flakiness budget at zero (no reruns).
- Add contract tests when introducing new config fields or API payloads.

## CI Execution Plan
- **PR gate**: fast profile (`not slow and not live`) with coverage XML + junit output for reporting.
- **Nightly/weekly**: add `-m "not live"` to run slow E2E/integration suites.
- **Manual live**: documented command plus required env/config; optional throttle to respect API quotas.

## Manual Developer Workflow
- Start with package-level focus: `pytest tests/api -m "not live"` when changing the API client.
- Run E2E before releasing: `pytest tests -m "e2e and not live"`.
- Inspect reports: coverage at `coverage.xml`, junit at `.reports/` (choose a consistent path when wiring CI).
