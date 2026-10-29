# Code Review Report

**Run**: run-eventpulse24-012
**Intent**: event-catalog-ingestion
**Reviewed**: 2026-10-28
**Files Reviewed**: 27 (12 created, 15 modified)

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 0 | 0 | 0 |
| Security | 0 | 0 | 0 |
| Architecture | 0 | 1 | 0 |
| Testing | 0 | 0 | 0 |
| **Total** | **0** | **1** | **0** |

**Tests Status**: Passing (1034/1034 after the applied suggestion, no warnings)

---

## Files Reviewed

**Production code:**
- `backend/ports/fetch.py`, `backend/adapters/crawl/address_policy.py`, `http.py`, `fake.py` (created)
- `backend/ports/registry.py`, `backend/config/adapters.py`, `env.py`, `settings.py`, `checks.py`, `backend/adapters/logging/redaction.py` (modified)

**Tests:**
- `backend/tests/adapters/scripted_network.py` and `test_crawl_*.py` (4 files) (created)
- Config, architecture and logging tests (modified)

**Fixtures and configuration:**
- `backend/tests/fixtures/sources/index.json` and `sample.rss` (created)
- `backend/pyproject.toml`, `uv.lock`, `.env.example` (modified)

---

## Auto-Fixed Issues

No auto-fixes applied. ruff and the 13 import contracts were already clean.

---

## Probed and Dismissed

- **Redirects between an IDN host and its punycode spelling** (`bücher.example` → `xn--bcher-kva.example`): suspected of being refused as cross-host. Probe: the fetch returns 200, because httpx normalizes both spellings to the same host. No change needed.

---

## Suggestions (approved by the user and applied)

### 1. [Architecture] The fake adapter leaks `FileNotFoundError` across the port

- **File**: `backend/adapters/crawl/fake.py` (`FakeFetchAdapter.fetch`)
- **Finding**: the index is validated at construction, but the fixture file is read on each fetch. If the file is deleted or unreadable afterwards, a raw `FileNotFoundError` crosses the port. That breaks the contract that only `FetchError` subclasses come out, so item 6's error handling, written against the fake, would crash instead of recording a failure. Confirmed by a probe.
- **Change**: map `OSError` while reading a fixture to `FetchNetworkError("fixture_unreadable")`, and add a test.
- **Risk**: Low
- **Applied**: `OSError` while reading a fixture raises `FetchNetworkError("fixture_unreadable")`. Test: `test_fixture_removed_after_startup_is_a_port_error`.

**Re-run after applying:** ruff clean; 13 contracts kept; 1034 passed; 98.40% overall, 100% `domain/`.

---

## Notes (no action)

- **Uncovered defensive branches** in `http.py`: a `zlib` error during the final `flush()`, and the size check after it. Both are reachable only by malformed streams that the chunk-level checks already stop.
- **Resolver results:** `GuardedBackend.connect_tcp` trusts `getaddrinfo` to return IP sockaddrs. The real resolver always does. Only an injected test resolver could return something else.
