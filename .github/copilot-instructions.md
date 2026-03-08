# Copilot Instructions for curateur

## Build & Test Commands

Always use the project's virtualenv (`.venv`) for local development. Create it if it doesn't exist, and activate it before running any commands.

```bash
# Set up virtualenv (one-time)
python -m venv .venv && source .venv/bin/activate

# Install (editable, with dev dependencies)
pip install -e ".[dev]"

# Lint and format check
ruff check curateur/ tests/ && ruff format --check curateur/ tests/

# Auto-format
ruff format curateur/ tests/

# Run fast tests (default CI profile)
pytest -m "not slow and not live" --cov=curateur --cov-report=term-missing

# Run a single test file or specific test
pytest tests/api/test_client.py
pytest tests/api/test_client.py::TestQueryGame::test_successful_query

# Run tests for one package
pytest tests/scanner/ -m "not live"

# Full suite (excluding live API tests)
pytest -m "not live"
```

## Architecture

curateur is an async-first Python CLI that scrapes ROM metadata and media from the ScreenScraper API and produces ES-DE-compatible `gamelist.xml` files.

**Data flow**: `CLI (cli.py) → WorkflowOrchestrator → [ScreenScraperClient, MediaDownloader, GamelistGenerator]`

- **cli.py**: Argparse entry point; loads config, initializes UI, runs the orchestrator via asyncio.
- **config/**: YAML config loading (`loader.py`), validation that collects all errors before raising (`validator.py`), and ES-DE `es_systems.xml` parsing (`es_systems.py`).
- **api/**: Async httpx-based ScreenScraper client with sliding-window rate limiting (`ThrottleManager`), disk-based JSON metadata cache (7-day TTL), connection pooling with automatic reset, and a three-tier error hierarchy (`FatalAPIError`, `RetryableAPIError`, `SkippableAPIError`).
- **scanner/**: ROM discovery, hashing, m3u/multi-disc handling, file type detection.
- **media/**: Region-aware media URL selection, async downloading with skip/resume, image validation via Pillow.
- **gamelist/**: Metadata merge rules, XML writer/parser, integrity threshold checking.
- **workflow/**: `WorkflowOrchestrator` coordinates the pipeline. Concurrency is asyncio coroutines with semaphore-based limits (not threads). `WorkQueueManager` uses priority-based asyncio.Queue (HIGH for retries, NORMAL, LOW). Staggered worker startup avoids thundering herd.
- **ui/**: `EventBus` decouples orchestrator from rendering. Supports headless (logging) and interactive (Textual TUI) modes.
- **tools/**: Standalone CLIs for system map generation and dev credential setup.

## Key Conventions

- **Async throughout**: All I/O operations use `async def`/`await`. Concurrency is managed with `asyncio.Semaphore` and `asyncio.Lock`, not threading.
- **Config injection**: Components receive a config dict—no global state. This enables isolation in tests.
- **Dataclasses for DTOs**: `@dataclass` for data transfer objects; `@dataclass(frozen=True)` for events.
- **Enums for categories**: `Priority`, `ErrorCategory`, `APIEndpoint`, etc.
- **Logging**: Per-module `logger = logging.getLogger(__name__)`.
- **Type hints**: Full type annotation on function signatures and dataclass fields; use `from typing import ...` for Python 3.8 compat.
- **Imports**: Absolute imports (`from curateur.api import ...`). Use `TYPE_CHECKING` blocks to break circular dependencies.
- **Docstrings**: Google-style on classes and public methods.
- **Formatting**: Ruff with 88-char line length, double quotes, isort-compatible import ordering. Lint rules: E, F, W, I.
- **Error handling**: Categorize API errors as fatal/retryable/skippable. The orchestrator skips individual ROM failures without aborting the run.
- **Subpackage `__init__.py`**: Each exports public API via `__all__`.

## Testing Conventions

- **Markers** (strict): `@pytest.mark.unit`, `@pytest.mark.integration`, `@pytest.mark.e2e`, `@pytest.mark.slow`, `@pytest.mark.live`. Always apply at least one.
- **HTTP mocking**: Use `respx` (httpx-compatible mock transport) for API tests.
- **Config fixtures**: Use the `make_config()` factory fixture from `conftest.py` to create test configs with overrides.
- **Filesystem**: Use `tmp_path` / `tmp_path_factory` for all generated files.
- **Async tests**: Decorate with `@pytest.mark.asyncio`.
- **Test naming**: Files `test_<subject>.py`, classes `Test<Subject>`, functions `test_<behavior>`.
- **Test data**: Static fixtures live in `tests/data/`.
