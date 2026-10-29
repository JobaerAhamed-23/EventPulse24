---
run: run-eventpulse24-012
work_item: source-fetch-port
intent: event-catalog-ingestion
generated: 2026-10-28
mode: confirm
---

# Implementation Walkthrough: Source Fetch Port & Adapters

## Summary

Ingestion now has a single, hardened way to retrieve source content: `SourceFetchPort` (`ports.registry.get_fetch_port()`). There are two adapters:

- **`HttpFetchAdapter`** fetches over the network. It reaches only public addresses (our own deny table) on ports 80 and 443. It follows only same-host redirects, holds one 30 s deadline across every network operation, decompresses within a 10 MiB budget, never sends cookies, and logs only ids and counts.
- **`FakeFetchAdapter`** is the default. It serves validated fixtures and can simulate every failure.

Only typed `FetchError`s cross the port. An import contract guarantees no other code can make HTTP requests.

## Structure Overview

```text
 pipeline (item 6) ──► get_fetch_port() ──► SourceFetchPort.fetch(url, etag, last_modified, source_id)
                           │ settings.ADAPTERS["fetch"]  (ADAPTER_MODE, overridden by SOURCE_FETCH)
            ┌──────────────┴───────────────┐
   FakeFetchAdapter                  HttpFetchAdapter ── per fetch: Deadline(30 s), one httpx.Client
   index.json (E006 at startup)        │ request hook (every hop): scheme · userinfo · port · same host · strip Cookie
   RFC 9110 conditionals               ▼
   simulate: timeout | too_large |   GuardedTransport (httpx) ─► httpcore pool ─► GuardedBackend.connect_tcp
             blocked | network |       │                          port ∈ {80,443} → getaddrinfo (timed thread)
             content | redirects |     │                          → any address denied? refuse → connect vetted IP
             {status}                  │                          → DeadlineStream (read/write/TLS ≤ remaining)
                                       ▼
                         iter_raw → own zlib decode (output budget) → FetchResult | FetchError
```

## Architecture

### Pattern Used

Ports and adapters (AD-2). httpx is reduced to a framing and redirect engine. Every policy decision (address, port, host, time, size, encoding, cookies, logging) is made in code we own and test. An `http-client` import contract keeps httpx, httpcore, requests and urllib3 inside `adapters.crawl`.

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `backend/ports/fetch.py` | Port, `FetchResult`, 8 error types |
| `backend/adapters/crawl/address_policy.py` | Deny table, `is_denied()` |
| `backend/adapters/crawl/http.py` | HTTP adapter, guard, deadline, transport, decoder |
| `backend/adapters/crawl/fake.py` | Fake adapter, `load_index()` |
| `backend/tests/fixtures/sources/{index.json,sample.rss}` | Minimal fixtures (item 4 adds the real ones) |
| `backend/tests/adapters/scripted_network.py` | In-memory network for tests |
| `backend/tests/adapters/test_crawl_*.py` (4 files) | 165 tests |

### Modified

| File | Changes |
|------|---------|
| `backend/ports/registry.py` | `get_fetch_port()` |
| `backend/config/adapters.py`, `env.py`, `settings.py`, `checks.py` | Wiring, settings, logger levels, E006 |
| `backend/adapters/logging/redaction.py` | `byte_count` |
| `backend/pyproject.toml`, `uv.lock` | `httpx==0.28.1`; the `http-client` contract |
| Config, architecture and logging tests | Coverage for the above |
| `.env.example`, standards, item 6 | Documentation and handed-on ACs |

## Key Implementation Details

### 1. Connect-time SSRF guard

`GuardedBackend.connect_tcp` is the only place a socket is opened. It works in this order:

1. Check the port.
2. Resolve the host, with a timeout.
3. Refuse the host if **any** address is denied.
4. Connect to each vetted IP literal in turn.

TLS still verifies the origin hostname: a test records `server_hostname` and checks `CERT_REQUIRED`. Redirects re-enter `connect_tcp`, so a rebinding host is caught on its second hop.

### 2. An address policy we own

`ipaddress.is_global` treats `::7f00:1`, `::ffff:0:7f00:1`, `fec0::1`, NAT64 and some multicast as global, and its tables differ between CPython releases. The policy instead allows IPv6 only in 2000::/3, minus the special ranges inside it, and denies every embedded-IPv4 form. Each range is pinned at both ends.

### 3. One deadline across everything

`Deadline.budget(op_timeout)` returns `min(op_timeout, remaining)` and raises once the budget is spent. These all draw on it:

- DNS (a one-shot daemon thread joined with that budget)
- each connect attempt
- the TLS handshake, every read and every write (through `DeadlineStream`)
- every redirect hop

That defeats slow-drip headers and per-address stalls.

### 4. Size-safe decoding

The body is read with `iter_raw()` and decompressed by `_Decoder` using `max_length`. It never produces more than the remaining budget plus one byte. Only identity, gzip and deflate are accepted (zlib or raw deflate). Stacked or unknown encodings are refused, and so are truncated or corrupt streams. Raw and decoded sizes are both capped.

### 5. Things httpx would otherwise do

- **Logging:** its loggers are pinned to WARNING, because they log full URLs, query tokens included.
- **Proxies:** proxy environment variables are ignored, because a custom transport is passed.
- **Cookies:** cookie policies don't survive httpx copying the jar, so the per-hop hook strips `Cookie` instead.

## Security Considerations

| Concern | Approach |
|---------|----------|
| SSRF to internal services and metadata | Own deny table; refuse if any address is denied; connect only to vetted IPs; ports 80 and 443 only, checked per hop |
| DNS rebinding | Re-resolved and re-vetted at every connect, and the socket connects to the vetted literal |
| Redirect laundering past the ToS review (FR-17) | Same-host redirects only; `cross_host_redirect` is surfaced to item 6 |
| Decompression bombs | Own decoder with an output budget; stacked encodings refused |
| Slowloris and stalls | One total deadline across all operations |
| Leaking URLs or tokens in logs | Our record is ids only; httpx and httpcore at WARNING; a DEBUG-level test |
| Cross-source state | One client per fetch; no cookies |
| Bypassing the port | The `http-client` import contract, with planted-violation tests |

## Performance Considerations

| Requirement | Implementation |
|-------------|----------------|
| Bounded resources per fetch | 10 MiB, 30 s and 5 redirects (all settings); a client per fetch, closed |
| DNS that never returns | A daemon thread joined with a timeout; only a hung lookup outlives its fetch |
| Fork safety (Celery prefork) | No thread pool, so no idle threads are left behind |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| HTTP client | httpx + a guarded httpcore backend | A mature framing engine; we own the policy |
| Address policy | Own deny table | `is_global` drifts and leaks |
| Ports and redirects | 80/443; same host only | Internal services; FR-17 |
| Deadline | One budget for everything | Closes the gaps per-read timeouts leave |
| Decompression | Our own, with a budget | httpx has no limit |
| Cookies | Stripped per hop | Policy jars don't hold in httpx |
| DNS timeout | One-shot thread | A shared pool broke fork safety |

## Deviations from Plan

- **Cookies:** the plan used a refusing `CookieJar` policy. A test showed httpx discards it (its `Client.cookies` setter copies the jar into a default one), so cookies are stripped in the per-hop hook instead.
- **DNS:** the plan used a shared `ThreadPoolExecutor`. Its idle threads made a later `fork()` unsafe (the uuid7 fork test warned), so it was replaced with one-shot daemon threads.
- **Import contract:** a `forbidden` contract (matching the repository's `llm-sdk` and `stripe-sdk`), not `protected`. It also covers `requests` and `urllib3`.
- **Code review:** 1 fix approved, so the fake adapter's fixture read errors are now port errors.

## Dependencies Added

| Package | Why Needed |
|---------|------------|
| `httpx==0.28.1` | HTTP framing and redirects for `adapters.crawl.http` only |
| `httpcore==1.0.9`, `idna==3.20` (transitive) | httpx's transport, and IDNA hosts |

## How to Verify

1. **Run the adapter tests**
   ```bash
   cd backend && uv run pytest -q tests/adapters/test_crawl_*.py
   ```
   Expected: 165 passed. No network is used, except one loopback socket.

2. **Run all the gates**
   ```bash
   make lint-backend && make manage ARGS="check" && make coverage-backend
   ```
   Expected: 13 contracts kept, no issues, 1034 passed, 98.40% overall, no warnings.

3. **Check that the guard refuses internal targets**
   ```bash
   cd backend && SOURCE_FETCH=http uv run python manage.py shell -c "from ports.registry import get_fetch_port; get_fetch_port().fetch('http://169.254.169.254/latest/meta-data/')"
   ```
   Expected: `FetchBlockedError` (reason `address`), with no connection attempted.

4. **Fetch a real feed** (needs internet)
   ```bash
   cd backend && SOURCE_FETCH=http uv run python manage.py shell -c "from ports.registry import get_fetch_port; r = get_fetch_port().fetch('https://www.python.org/blogs/'); print(r.status, len(r.body), r.content_type)"
   ```
   Expected: `200`, a byte count, and `text/html…`.

## Test Coverage

- Tests added: 189. The suite went from 845 to 1034.
- Coverage: 98.40% overall, 100% `domain/`, 99% `adapters/crawl/http.py`.
- Status: all passing, no warnings

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing
- [x] No critical issues
- [x] Documentation updated: tech stack, coding standards, `.env.example`, item 6 ACs
- [x] Developer notes captured

## Developer Notes

- **Never replace `address_policy.is_denied` with `ipaddress.is_global`.** The tests pin why.
- **Upgrading httpx:** `GuardedTransport` replaces the private `HTTPTransport._pool`, and `test_transport_pool_uses_the_guarded_backend` is the tripwire. Also re-check that `Client.cookies` still discards custom jars, because the hook relies on stripping instead.
- **Testing error paths in the pipeline:** add `simulate` entries to a fixture index rather than mocking the port.
- **`SOURCE_FETCH=http` locally** fetches real feeds while every other adapter stays fake. The fake's fixture directory then isn't checked (E006 is skipped).
- **A `cross_host_redirect` block means the source moved.** Re-register the new URL, which triggers a new ToS review. Don't widen the redirect rule.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-012*
