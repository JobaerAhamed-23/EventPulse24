---
run: run-eventpulse24-012
work_item: source-fetch-port
intent: event-catalog-ingestion
generated: 2026-10-28
status: passed
---

# Test Report: Source Fetch Port & Adapters

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Adapter: scripted network (real httpx and httpcore, no sockets) | 75 new | 0 | 0 | `adapters/crawl/http.py` 99% |
| Adapter: address policy | 58 new | 0 | 0 | 100% |
| Adapter: fake and registry | 30 new | 0 | 0 | `adapters/crawl/fake.py` 100% |
| Adapter: real socket (loopback) | 2 new | 0 | 0 | the real connect loop |
| Wiring and architecture (config, checks, env, logging, import contract) | 24 new | 0 | 0 | — |
| **Total suite** | **1034** (845 before + 189 new) | 0 | 0 | **98.40%** overall · 100% `domain/` |

There are no test warnings. A fork-safety warning that this run introduced was fixed (see Issues Found).

## Acceptance Criteria Validation

From `source-fetch-port.md`, as amended by the approved plan (revision 2):

- ✅ **Port:** `SourceFetchPort.fetch(url, *, etag, last_modified, source_id) -> FetchResult`, with a 304 (`not_modified`) result. The stored ETag and Last-Modified are kept when a 304 omits them, and `content_type` is `str | None`.
- ✅ **HTTP adapter:** connect, read and write timeouts plus a **total deadline** across DNS, connect, TLS, header bytes, body and every hop (tested with an injected clock). Size limit on the decoded body, with its own decompression. Capped redirects. `http`/`https` only. A fixed user-agent.
- ✅ **SSRF guard at connect time:**
  - **Addresses:** decided by our own deny table, with every range pinned at both ends. Mixed DNS records are refused. Every hop is re-resolved and re-vetted, and the DNS-rebinding test is refused on its second hop.
  - **Ports:** only 80 and 443.
  - **Redirects:** cross-host redirects are refused.
  - **Proxy environment:** it can't bypass the guard.
- ✅ **Typed errors:**
  - timeout, too large, blocked, HTTP (with status), redirects, content and network
  - every httpx exception class is mapped
  - port errors wrapped by httpcore are unwrapped
  - error details never contain a host or URL
- ✅ **Fake adapter:** fixtures validated at construction and by system check `eventpulse.E006`, with path containment. Conditional requests follow RFC 9110, and having no validator never gives a 304. An unknown URL raises `FetchHTTPError(404)`. Every failure mode can be simulated.
- ✅ **Wiring:** the port is registered (`get_fetch_port()`). The `SOURCE_FETCH` override swaps only this port. Real mode uses the HTTP adapter. The fake is the default.
- ✅ **Logs:** only `job`, `source_id`, `status_code`, `byte_count`, `duration_ms` and `error_code`. The httpx and httpcore loggers are at WARNING. A DEBUG-level capture shows no URL, host, IP or query token.
- ✅ **HTTP client chosen, pinned and recorded:** `httpx==0.28.1`. An import contract (`http-client`) proves only `adapters.crawl` imports an HTTP client.
- ✅ **Tests mock the HTTP layer with no live network:** every error type, the size limit, a redirect into a private IP, 304 handling, and the fake serving fixtures.

## Tests Written

- `tests/adapters/test_crawl_address_policy.py` (58): every deny range at its first and last address; the addresses whose `is_global` result differs between CPython versions; allowed neighbours
- `tests/adapters/test_crawl_http.py` (75):
  - success and conditional requests
  - encodings, gzip bombs and the size limit
  - the deadline (DNS, hung DNS, connect, TLS, a drip-fed header, body, hops)
  - guard, ports and redirects
  - TLS hostname and `CERT_REQUIRED`
  - proxies, cookies and closing
  - the httpx tripwire
  - the exception mapping
  - logs
- `tests/adapters/test_crawl_loopback.py` (2): a real-socket fetch through the guard; the real policy refusing the same listener
- `tests/adapters/test_crawl_fake.py` (30): conditionals, simulation, index validation, a fixture removed after startup (a port error, from the code-review fix), the registry building each adapter
- Config, checks, env, logging (+15): the override, E006, settings validation, logger levels
- `tests/architecture/test_import_contracts.py` (+5): three planted violations and two allowed paths for `http-client`. The SDK coverage test now includes crawl.

## Test Commands

```bash
make test-backend
make coverage-backend   # ≥80% overall, 100% domain/
make lint-backend       # ruff + 13 import contracts
```

## Coverage Details

| Module | Lines |
|--------|-------|
| `ports/fetch.py` | 100% |
| `adapters/crawl/address_policy.py` | 100% |
| `adapters/crawl/fake.py` | 100% |
| `adapters/crawl/http.py` | 99% (uncovered: a `zlib` error during the final `flush()`, and the size check after it, both defensive) |
| Overall | 98.40% |

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| **Cookies were sent on redirect hops despite a refusing cookie policy.** httpx's `Client.cookies` setter copies the jar into a new default-policy jar. | High | Fixed: the per-hop request hook strips `Cookie`, and the misleading jar was removed. Tested. |
| **The shared DNS `ThreadPoolExecutor` left idle threads,** making any later `fork()` unsafe (the uuid7 fork test warned) | Medium | Fixed: one-shot daemon thread per lookup |
| `raise error from exc` made an exception its own `__cause__` when it was already a `FetchError` | Low | Fixed: re-raise as is, plus a cycle guard in the unwrap |
| The redirect-deadline test summed only 24 s, so it couldn't fail | Low | Fixed: three hops of 12 s |
| The loopback teardown waited 5 s, because a closed listener doesn't wake `accept()` on Linux | Low | Fixed: a wake-up connection, and the server stops on EOF |

## Ready for Completion

- [x] All tests passing (1034/1034 after the code-review fix, no warnings)
- [x] Coverage target met (98.40% overall; 100% `domain/`)
- [x] All acceptance criteria validated
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-012*
