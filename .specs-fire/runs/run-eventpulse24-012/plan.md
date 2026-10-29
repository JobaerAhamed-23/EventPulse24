---
run: run-eventpulse24-012
work_item: source-fetch-port
intent: event-catalog-ingestion
mode: confirm
checkpoint: plan (Checkpoint 1 of 1)
approved_at: 2026-10-28T09:53:53Z
revision: 2 (plan review: 13 must-fix, 3 should-fix applied)
---

# Implementation Plan: Source Fetch Port & Adapters

## Approach

> **Needs your call**
> - **F1–F5**, unchanged from revision 1 except F3, which is now enforced at the stream level.
> - **F6:** cross-host redirects are refused (finding #13).
> - **F7:** ports 80 and 443 only (finding #2).

Add a `SourceFetchPort` with two adapters:

- **`HttpFetchAdapter`**, built on httpx and a guarded `httpcore` network backend. It decides every address and port itself from a deny table it owns, enforces one deadline across every network operation, and does its own size-capped decompression.
- **`FakeFetchAdapter`**, which serves fixtures that are validated at startup and can simulate every failure mode.

Neither adapter interprets content (AD-9). Only port errors leave either one.

**Verified on this machine** (Python 3.13.3, httpx 0.28.1):
- `is_global` is `True` for `::7f00:1`, `::ffff:0:7f00:1`, `fec0::1`, `64:ff9b::7f00:1`, `192.0.0.9` and multicast.
- httpx logs `request.url` at INFO.
- `GZipDecoder` decompresses with no `max_length`.
- `allow_env_proxies = trust_env and transport is None`.

### Decisions

| # | Decision | Choice |
|---|---|---|
| F1 | HTTP client | `httpx==0.28.1` + `httpcore==1.0.9`. The custom network backend is installed by replacing `HTTPTransport._pool`, and a tripwire test guards that. **httpx is used only for protocol framing and redirects.** It does no decoding (`iter_raw`) and no logging (its loggers are set to WARNING). |
| F2 | Fetching real feeds locally | A `SOURCE_FETCH=fake\|http` override for this port only, applied on top of `ADAPTER_MODE` |
| F3 | Limits | DNS 3 s, connect 5 s, read 15 s, write 5 s. A **30 s total deadline covers DNS, connect, TLS, the header bytes, the body, and every redirect hop**: each operation gets `min(its own timeout, time remaining)`. Maximum 10 MiB of **decoded** bytes. Maximum 5 redirects. All are settings, and the clock is injectable. |
| F4 | User-agent | Setting, defaulting to `EventPulse24-SourceFetcher/0.1 (+https://github.com/JobaerAhamed-23/EventPulse24)`. This reveals the repository URL to fetched sites. |
| F5 | Mixed DNS records | Refuse the host if **any** resolved address is denied |
| **F6** | Redirect crossing to another host (FR-17: a ToS review covers the registered source) | **Refuse it** (`fetch_blocked`, reason `cross_host_redirect`). Hosts are compared after lowercasing and stripping a leading `www.`. Same-host redirects, including `http → https`, are allowed. Without the Public Suffix List, "registrable domain" can't be computed safely, so the rule is exact host. A feed that moved hosts must be re-registered at its new URL, which re-triggers a ToS review. `FetchResult.final_url` is still returned, and item 6 gets an AC to record it. |
| **F7** | Ports | Allow **{80, 443}**, set by `SOURCE_FETCH_ALLOWED_PORTS`. They are checked on the initial URL and **again inside `connect_tcp`**, so every redirect hop is covered too. |

### Address policy (`adapters/crawl/address_policy.py`)

The deny table is owned here; `is_global` is never used. An address is allowed only if it passes these rules:

- **IPv4:** denied if it falls in any of these:

  | Range | What it is |
  |---|---|
  | 0.0.0.0/8 | "This network" |
  | 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 | Private |
  | 100.64.0.0/10 | Carrier-grade NAT |
  | 127.0.0.0/8 | Loopback |
  | 169.254.0.0/16 | Link-local, including the cloud metadata address |
  | 192.0.0.0/24 | IETF protocol assignments |
  | 192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24 | Documentation (TEST-NET-1/2/3) |
  | 192.88.99.0/24 | 6to4 relay |
  | 198.18.0.0/15 | Benchmarking |
  | 224.0.0.0/4 | Multicast |
  | 240.0.0.0/4 | Reserved, including the broadcast address |

- **IPv6:** allowed **only inside 2000::/3**, and denied inside it for:

  | Range | What it is |
  |---|---|
  | 2001::/23 | IETF assignments, including Teredo 2001::/32 |
  | 2001:db8::/32 | Documentation |
  | 2002::/16 | 6to4 |
  | 3fff::/20 | Documentation |

  Everything outside 2000::/3 is therefore denied, including every embedded-IPv4 form. Those forms are denied, never unwrapped:

  | Form | Range |
  |---|---|
  | IPv4-mapped | ::ffff:0:0/96 |
  | IPv4-compatible | ::/96 |
  | IPv4-translated | ::ffff:0:0:0/96 |
  | NAT64 | 64:ff9b::/96 and 64:ff9b:1::/48 |
  | Unique-local | fc00::/7 |
  | Link-local | fe80::/10 |
  | Site-local | fec0::/10 |
  | Multicast | ff00::/8 |

- **Tests:** one test for each range, pinning both its first address and its last address as denied, plus an allowed address just outside. That includes every address whose `is_global` result differs between Python versions, so a CPython change can't alter the policy.

### Guarded backend (`connect_tcp`)

- **Signature:** matches httpcore exactly, `connect_tcp(host, port, timeout=None, local_address=None, socket_options=None)`.
- **Order of checks:**
  1. The port must be allowed.
  2. `host` is resolved through a **timed resolver**: `getaddrinfo(host, port, type=SOCK_STREAM, proto=IPPROTO_TCP)` on a small shared thread pool, waited on for `min(dns, remaining)`. A hung lookup ends the fetch with `FetchTimeoutError`; the worker thread finishes on its own.
  3. An empty result raises `FetchNetworkError`. Results are de-duplicated, keeping their order.
  4. If any address is denied, `FetchBlockedError` is raised.
- **Connecting:** each vetted address literal (keeping an IPv6 scope id as `%scope`) is tried in turn through `httpcore.SyncBackend().connect_tcp`, with `timeout=min(connect, remaining)`.
- **The stream:** the returned stream is wrapped in a `DeadlineStream`, whose `read`, `write` and `start_tls` each get `min(timeout, remaining)` and raise `FetchTimeoutError` once the deadline has passed. That covers the TLS handshake, slowly sent headers and the body.
- **Errors:** `gaierror` and `OSError` map to `FetchNetworkError` (or `FetchTimeoutError`).
- **Dropped:** the after-connect peer re-check. The socket connects to a vetted IP literal, so the check could never fail.

### Fetch flow (`HttpFetchAdapter.fetch`)

1. **Pre-checks**, each raising `FetchBlockedError`: the URL must parse (`InvalidURL` caught), use `http`/`https`, carry no userinfo, and use an allowed port.
2. **One `httpx.Client` per fetch,** used as a context manager so it is always closed. Settings: `transport=GuardedTransport(deadline)`, `follow_redirects=True`, `max_redirects`, `trust_env=False`, and **cookies refused** (a `CookieJar` with `DefaultCookiePolicy(allowed_domains=[])`).
3. **Headers:**
   - `User-Agent`
   - `Accept-Encoding: gzip, deflate`
   - `If-None-Match` and `If-Modified-Since` when known
4. **A request hook on every hop** checks the scheme and port, and refuses a cross-host redirect (F6).
5. **The response is read with `iter_raw()`.** `Content-Encoding` is parsed:
   - absent or `identity`: the bytes are used as is
   - exactly one of `gzip`, `x-gzip` or `deflate` (zlib, falling back to raw deflate): decompressed incrementally, with `max_length = remaining budget + 1` and the `unconsumed_tail` drained
   - **stacked codings, or anything else (`br`, `zstd`, …):** `FetchContentError`
   - corrupt compressed data: `FetchContentError`

   The size limit is checked against `Content-Length` (if it is ≤ the limit for identity bodies) and against decoded bytes, so `FetchTooLargeError` never relies on the server's word.
6. **Status:**
   - **200 and 203** are the only successes.
   - **304** counts only if a validator was sent **and** the final URL equals the requested URL (no redirect). Otherwise it raises `FetchHTTPError(304)`.
   - Anything else raises `FetchHTTPError(status)`.
   - `TooManyRedirects` raises `FetchRedirectError`.
7. **Result:** for a 304, the **stored** ETag and Last-Modified are kept when the response omits them. `content_type: str | None`.
8. **Exception mapping:** an exhaustive table. `httpx.TimeoutException` and our deadline map to timeout. `httpx.TooManyRedirects` maps to redirect. `httpx.DecodingError` maps to content. `httpx.StreamError`, `httpx.InvalidURL`, `httpx.TransportError`, `httpx.HTTPError` and `OSError` map to network. Port errors raised inside the transport are unwrapped: httpcore wraps them, and the original is recovered from `__cause__`/`__context__`. A test drives each one.

### Port (`ports/fetch.py`)

- `fetch(url, *, etag=None, last_modified=None, source_id=None) -> FetchResult`.
- `FetchResult` holds `status`, `final_url`, `content_type: str | None`, `body`, `etag`, `last_modified`, and a `not_modified` property.
- **Errors** (`DomainError` subclasses):

  | Error | Code |
  |---|---|
  | `FetchError` (base) | `fetch_failed` |
  | `FetchTimeoutError` | `fetch_timeout` |
  | `FetchTooLargeError` | `fetch_too_large` |
  | `FetchBlockedError` | `fetch_blocked` |
  | `FetchHTTPError` | `fetch_http_error` (with `status: int`) |
  | `FetchRedirectError` | `fetch_too_many_redirects` |
  | `FetchContentError` | `fetch_bad_content` |
  | `FetchNetworkError` | `fetch_network_error` |

- **`details`** carries only `{"reason": <slug>}` and, for an HTTP error, `{"status": <int>}`. It **never includes a host, IP or URL**, and a test asserts that.
- **No 502 mapping** (should-fix 1). AD-11 keeps fetches out of request handlers, so there is no handler to map for. A stray one falls back to `DomainError`'s 400 with those safe details.

### Logging

- **`config/settings.py` `LOGGING`:** the `httpx` and `httpcore` loggers are set to **WARNING**, with no propagation of debug traces. httpcore traces include the connect host.
- **Our record:** one per fetch from `adapters.crawl`, with `job`, `source_id`, `status_code`, `byte_count`, `duration_ms` and `error_code`. `byte_count` is added to `ALLOWED_FIELDS`.
- **Test:** with `caplog` at DEBUG on the root logger, a full fetch with a redirect leaves **no record** whose message, args or extra fields contain the URL, the host or a resolved IP.

### Fake adapter (`adapters/crawl/fake.py`)

- **The index** (`<SOURCE_FIXTURES_DIR>/index.json`) maps a URL to:

  | Key | Meaning |
  |---|---|
  | `file` | The fixture file, which must resolve **inside** the fixtures directory (`Path.resolve().is_relative_to`), so `../../.env` is rejected |
  | `content_type` | The content type to report |
  | `etag` | Optional |
  | `last_modified` | Optional |
  | `simulate` | Optional: `timeout`, `too_large`, `blocked`, `network`, `content`, `redirects`, or `{"status": 503}` |

- **Validated once at construction,** and by a **system check `eventpulse.E006`** when `SOURCE_FETCH=fake`. A broken index or a missing directory fails `manage.py check` at startup, never on a fetch.
- **Conditional requests, per RFC 9110:**
  - `If-None-Match` takes precedence, and returns 304 **only when both sides have an ETag and they are equal**.
  - Otherwise `If-Modified-Since` is compared as a date against the entry's `last_modified`, and an entry no newer returns 304.
  - An entry with no validators never returns 304.
- An unknown URL raises `FetchHTTPError(404)`. The default directory is `backend/tests/fixtures/sources/`. In a deployment, `SOURCE_FETCH=http`, so the fake and its directory are never needed there.

### Enforcement (finding #12)

- An **import-linter `protected` contract**: `httpx` and `httpcore` may be imported only by `adapters.crawl`.
- `tests/architecture/test_import_contracts.py` plants a violation for it, matching the existing per-contract pattern.

### Handed on to item 6 (`ingest-pipeline-and-lifecycle`)

- **AC:** record `FetchResult.final_url`, and treat a `fetch_blocked` with reason `cross_host_redirect` as "source moved: re-register and review".
- **AC:** map each fetch error code onto the source's `last_error_code` and `consecutive_failures`. The fake's `simulate` provides each case.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/ports/fetch.py` | Port, result, errors |
| `backend/adapters/crawl/address_policy.py` | Deny table, `is_denied(ip)` |
| `backend/adapters/crawl/http.py` | `HttpFetchAdapter`, `GuardedTransport`, `GuardedBackend`, `DeadlineStream`, `Deadline`, the timed resolver, the decoder |
| `backend/adapters/crawl/fake.py` | `FakeFetchAdapter`, `validate_index()` |
| `backend/tests/fixtures/sources/index.json`, `sample.rss` | Minimal fixtures |
| `backend/tests/adapters/scripted_network.py` | A scripted resolver and connector; the streams record `start_tls` arguments and support delays through the injected clock |
| `backend/tests/adapters/test_crawl_address_policy.py` | Every range: first and last address, plus a neighbour |
| `backend/tests/adapters/test_crawl_http.py` | Behavior on the scripted network |
| `backend/tests/adapters/test_crawl_loopback.py` | One real-socket test against a loopback listener, with the policy and allowed ports overridden for 127.0.0.1 and its port |
| `backend/tests/adapters/test_crawl_fake.py` | Fake adapter |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/ports/registry.py` | `fetch` key, `get_fetch_port()` |
| `backend/config/adapters.py` | Both maps; the `SOURCE_FETCH` override |
| `backend/config/env.py`, `config/settings.py` | Fetch settings; `LOGGING` levels for httpx and httpcore |
| `backend/config/checks.py` | `eventpulse.E006` (fake index valid when `SOURCE_FETCH=fake`) |
| `backend/adapters/logging/redaction.py` | `byte_count` |
| `backend/pyproject.toml`, `uv.lock` | `httpx==0.28.1`; the import-linter `protected` contract |
| `backend/tests/architecture/test_import_contracts.py` | A planted violation for the new contract |
| `backend/tests/config/test_adapters.py`, `test_env.py`, `test_checks.py`, `test_logging_config.py` | Override, settings, E006, logger levels |
| `.env.example` | `SOURCE_FETCH=fake` |
| `.specs-fire/standards/tech-stack.md`, `coding-standards.md` | httpx; "outbound source fetches go only through `SourceFetchPort`", enforced by the contract |
| `ingest-pipeline-and-lifecycle.md` | The two handed-on ACs |

## Tests

| Test File | Coverage |
|-----------|----------|
| `test_crawl_address_policy.py` | First and last address of every deny range, the neighbours outside each, and the version-drifting addresses: `::7f00:1`, `::ffff:0:7f00:1`, `fec0::1`, `2002:7f00:1::`, `64:ff9b::7f00:1`, `64:ff9b:1::7f00:1`, `192.0.0.9`, 224.0.0.1 and 239.1.1.1 are all denied. Allowed: 93.184.215.14, 1.1.1.1, 2606:4700::1111, 2a00:1450::1. |
| `test_crawl_http.py` | Every row below |
| `test_crawl_loopback.py` | The real `SyncBackend` connect loop and real sockets, end to end through the guard, with an overridden policy |
| `test_crawl_fake.py` | Conditional requests, including no-ETag on both sides never giving 304; a path that escapes the directory rejected; every `simulate` mode; an unknown URL raising 404; validation at construction; E006 |
| Config, architecture | The override; settings validation; logger levels; E006; the planted import violation |

Rows covered by `test_crawl_http.py`:

- **Success and conditional requests:**
  - 200 and 203 succeed; 204 and 206 raise `FetchHTTPError`.
  - Conditional headers are sent.
  - A 304 with a validator succeeds, and the stored ETag is kept when the 304 omits it.
  - A 304 with no validator sent, or after a redirect, is refused.
- **Decoding:**
  - gzip and deflate (zlib and raw) decode.
  - **Gzip bombs:** a single layer over the limit raises `FetchTooLargeError`, checked through the decompressor's output budget.
  - Stacked `gzip, gzip`, `br` and an unknown coding raise `FetchContentError`, and so does corrupt gzip.
  - The size limit applies through `Content-Length` and through the body bytes.
- **The deadline, with an injected clock:** slow DNS (the timed resolver), slow connect across several addresses, a slow TLS handshake, headers sent a byte at a time, a slow body, and the total budget spread across 3 redirect hops.
- **Guard and redirects:**
  - A public → private redirect is refused.
  - A redirect to a public host on port 6379 is refused, and so is the initial URL `http://<public-ip>:6379/`.
  - A cross-host redirect is refused, while a same-host redirect and `http → https` are allowed.
  - 6 redirects raise `FetchRedirectError`.
  - `ftp://` and userinfo URLs are refused, and an invalid URL is mapped.
  - A host with mixed public and private records is refused. An empty `getaddrinfo` result and a `gaierror` are mapped.
- **Exceptions:** each httpx exception class in the mapping table, driven to its port error.
- **TLS:** the recorded `start_tls` shows `server_hostname` is the origin host, `verify_mode == CERT_REQUIRED` and `check_hostname is True`.
- **Proxy environment:** with `HTTPS_PROXY` and `ALL_PROXY` set to an attacker address, the guard is still reached and the proxy address is never connected to.
- **Client hygiene:**
  - A cookie set by the first hop is not sent on the next one.
  - One client per fetch, closed afterwards: the transport's close is recorded.
- **Logs:** only allowlisted fields, with no URL, host or IP at DEBUG.
- **Tripwire:** the pool's backend is a `GuardedBackend`.
- **Error details:** never a host or URL.

## Technical Details

**Order:**
1. Dependency
2. Port and errors
3. Address policy and its tests
4. Scripted network
5. Backend, deadline and resolver
6. Transport and fetch flow, with the HTTP tests
7. Loopback test
8. Fake adapter, E006 and fixtures
9. Wiring, settings and logging
10. Import contract
11. Docs and ACs
12. Gates

---
*Plan approved at Checkpoint 1 (2026-10-28T09:53:53Z).
