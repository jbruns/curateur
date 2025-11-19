## Plan: Integrate WorkQueueManager and ThrottleManager

Integrate the fully-implemented but unused WorkQueueManager and ThrottleManager components into the production workflow, adding priority-based retry handling and adaptive per-endpoint rate limiting with comprehensive test coverage.

### Steps

1. **Create `APIEndpoint` enum and integrate ThrottleManager into `client.py`**
   - Create `APIEndpoint(Enum)` in `api/client.py` with values `JEU_INFOS = 'jeuInfos.php'`, `JEU_RECHERCHE = 'jeuRecherche.php'`, `MEDIA_JEU = 'mediaJeu.php'`
   - Remove `RateLimiter` import and usage (line 65)
   - Add required `throttle_manager` parameter to `ScreenScraperClient` constructor
   - Replace all `rate_limiter.wait_if_needed()` calls (lines 168, 283, 343) with `throttle_manager.wait_if_needed(endpoint.value)`
   - Enhance `throttle.py` `handle_rate_limit()` to track consecutive 429s per endpoint and apply exponential backoff multiplier (1x, 2x, 4x, 8x, capped at 8x)
   - Add `reset_backoff_multiplier(endpoint)` method called after successful request to reset consecutive 429 counter
   - Update `error_handler.py` `handle_http_status()` to accept and call `throttle_manager.handle_rate_limit(endpoint, retry_after)` on 429 responses
   - Pass `throttle_manager` reference through error handler context in `retry_with_backoff()`

2. **Add error categorization to `error_handler.py` for selective retry**
   - Create `ErrorCategory(Enum)` with values: `RETRYABLE` (429, 5xx, network), `NOT_FOUND` (404), `NON_RETRYABLE` (400), `FATAL` (403)
   - Add `categorize_error(exception)` function that returns `ErrorCategory` based on HTTP status or exception type
   - Update `retry_with_backoff()` to check error category: raise immediately on `FATAL`, skip retry on `NOT_FOUND`/`NON_RETRYABLE`, continue on `RETRYABLE`
   - On 403 (auth failure), log critical error message "Authentication failure - halting execution" and raise `SystemExit`
   - Return tuple `(exception, category)` from error handling for orchestrator decision-making

3. **Integrate WorkQueueManager into `orchestrator.py` with selective retry**
   - Change `work_queue` parameter from `Optional[WorkQueueManager]` to required `WorkQueueManager` (line 79)
   - Add `not_found_items` list to track 404 errors separately from failed items
   - Refactor `_scrape_roms_parallel()` (line 135) to populate work queue with all ROM entries as `Priority.NORMAL` items with action `'full_scrape'`
   - Replace parallel batch processing loop with work queue consumer pattern using `thread_manager.submit_batch()`
   - Wrap API calls in try/except to categorize errors using `error_handler.categorize_error()`
   - On `RETRYABLE` errors (429, 5xx): call `work_queue.retry_failed(work_item, str(error))`
   - On `NOT_FOUND` errors (404): append to `not_found_items` with `{rom_info, error}`, mark as processed
   - On `NON_RETRYABLE` errors (400): log warning and mark as processed, do not retry
   - On `FATAL` errors (403): propagate exception to halt execution
   - Call `work_queue.mark_processed(work_item)` after successful ROM processing
   - Add work queue consumption loop that continues until `work_queue.is_empty()` returns True
   - Update `scrape_system()` return to include `work_queue.get_stats()`, `work_queue.get_failed_items()`, and `not_found_items`

4. **Add work queue visibility to `console_ui.py` real-time dashboard**
   - Add work queue stats row to live display: `Queue: {pending} pending | {processed} processed | {failed} failed | {not_found} not found | {retries} retries`
   - Add `update_work_queue_stats(pending, processed, failed, not_found, retry_count)` method to ConsoleUI
   - Update Orchestrator to call `console_ui.update_work_queue_stats()` after each work item completion (success, failure, or not found)
   - Color code: pending (blue), processed (green), failed (red), not_found (yellow), retries (cyan)
   - Position work queue stats row below progress bar, above performance metrics

5. **Add not-found items logging to system summary in `orchestrator.py`**
   - After `scrape_system()` completes, append not-found items to system summary file
   - Create `_write_not_found_summary(system, not_found_items)` method
   - Write to `{gamelist_directory}/{system}_not_found.txt` with format: ROM filename, hash (if available), error message, timestamp
   - Include summary line: "Total ROMs not found in ScreenScraper: {count}"
   - Log info message: "Wrote not-found items to {system}_not_found.txt"

6. **Update CLI initialization in `cli.py` for Phase E components**
   - Add config validation after line 280: verify `api.max_retries` exists (default 3, range 1-10)
   - Initialize `ThrottleManager` after line 290 with `RateLimit(calls=requests_per_minute, window_seconds=60, adaptive=True)`
   - Use `requests_per_minute` from API response (authoritative), apply `config['api'].get('requests_per_minute')` as minimum override if present
   - Initialize `WorkQueueManager` after line 295 with `config['api']['max_retries']`
   - Pass required `throttle_manager` to `ScreenScraperClient` constructor (line 300)
   - Pass required `work_queue` to `WorkflowOrchestrator` constructor (line 305)
   - Remove deprecated `RateLimiter` initialization and imports

7. **Update CLI reporting and cleanup in `cli.py`**
   - Add work queue statistics section to performance summary after line 350
   - Display: processed count, failed count (retries exhausted), not-found count (404), total retry attempts
   - Display failed items list with: ROM name, action, retry count, final error message
   - Display not-found items summary: count and reference to `{system}_not_found.txt` files
   - Add throttle statistics section: total wait time, backoff events count, max backoff multiplier reached, per-endpoint wait breakdown
   - Update finally block (line 355) to log work queue state on interrupt: pending items count, failed items with details, not-found count
   - Ensure `work_queue.get_failed_items()` and `not_found_items` are logged even on exception
   - Add cleanup for throttle manager state (call `reset()` if needed)

8. **Create comprehensive test suite for WorkQueueManager (`tests/workflow/test_work_queue.py`)**
   - Test priority ordering: verify HIGH < NORMAL < LOW with 10+ items (IntEnum comparison)
   - Test FIFO within priority: add 5 NORMAL items, verify exact order returned
   - Test retry escalation: `retry_failed()` on NORMAL item promotes to HIGH priority
   - Test max retries: exceed `max_retries`, verify item moves to `failed_items` list
   - Test concurrent access: spawn 10 threads with `ThreadPoolExecutor`, each consuming 100 items
   - Test `get_stats()`: verify counts match after mixed operations (add, process, fail)
   - Test `get_failed_items()`: verify structure includes `rom_info`, `action`, `retry_count`, `error`
   - Test `get_work(timeout=1.0)`: verify returns `None` on empty queue within timeout
   - Test `mark_processed()`: verify item not returned again, appears in processed set
   - Test complex `rom_info`: use nested dicts, lists, verify serialization preserves structure

9. **Create comprehensive test suite for ThrottleManager (`tests/api/test_throttle.py`)**
   - Test sliding window: make 10 calls, wait for window/2, make 10 more, verify old calls expired
   - Test rate limit enforcement: make `calls` requests rapidly, verify next call blocks
   - Test per-endpoint isolation: max out endpoint A, verify endpoint B unaffected
   - Test 429 handling: call `handle_rate_limit(endpoint)`, verify `backoff_until` set, call history cleared
   - Test exponential backoff: trigger 429 on same endpoint 4 times, verify backoff multiplier increases: 1x, 2x, 4x, 8x (capped)
   - Test backoff multiplier reset: trigger 429, make successful request, verify multiplier resets to 1x
   - Test `retry_after` header: call `handle_rate_limit(endpoint, retry_after=30)`, verify 30s * multiplier backoff applied
   - Test concurrent same endpoint: spawn 20 threads hitting same endpoint, verify thread-safe counts
   - Test concurrent different endpoints: spawn threads hitting different endpoints, verify no cross-contamination
   - Test `reset(endpoint)`: reset one endpoint including backoff multiplier, verify others unaffected
   - Test `get_stats()`: verify includes `backoff_multiplier`, `consecutive_429s`, `recent_calls`, `backoff_remaining`

10. **Add integration tests (`tests/integration/test_phase_e_integration.py`)**
   - Test work queue retry flow: mock 429 error, verify `retry_failed()` called, item requeued as HIGH
   - Test priority escalation: fail same item with 429 twice, verify escalates to HIGH on first retry, stays HIGH
   - Test max retries failure: fail item 3 times with 429, verify appears in `get_failed_items()`
   - Test 404 handling: mock 404 error, verify item added to `not_found_items`, not retried, marked processed
   - Test not-found summary file: complete system with 404s, verify `{system}_not_found.txt` created with correct content
   - Test fatal 403 halt: mock 403 error, verify execution halts with `SystemExit` and critical log message
   - Test exponential backoff: mock 3 consecutive 429s, verify backoff times increase: t, 2t, 4t
   - Test backoff reset on success: mock 429, then successful request, verify multiplier resets
   - Test throttle with retry_after: mock 429 with `retry_after=10`, verify 10s * multiplier backoff applied
   - Test per-endpoint throttling: mock `jeuInfos.php` rate limit, verify `mediaJeu.php` unaffected
   - Test work queue visibility: verify ConsoleUI displays live queue stats including not_found counter
   - Test CLI performance summary: verify includes work queue stats (processed/failed/not_found/retries) and throttle stats
   - Test interrupt cleanup: raise `KeyboardInterrupt` mid-processing, verify pending/failed/not_found items logged
   - Test config validation: test invalid `max_retries` (0, -1, 100), verify validation errors raised

11. **Add configuration validation to `config/validator.py`**
   - Add validation rule for `api.max_retries`: must be integer, range 1-10, default 3
   - Add validation rule for `api.requests_per_minute`: optional integer override, range 1-300 if present
   - Document that `requests_per_minute` from API authentication response is authoritative
   - Document that config `requests_per_minute` is used as minimum constraint (min of API and config)
   - Add validation error messages: "api.max_retries must be between 1 and 10", "api.requests_per_minute must be between 1 and 300"
   - Update existing validation tests in config to cover new rules with edge cases (boundaries, types, missing values)