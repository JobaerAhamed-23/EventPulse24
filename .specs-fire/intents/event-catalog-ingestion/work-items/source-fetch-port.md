---
id: source-fetch-port
title: Source Fetch Port & Adapters
intent: event-catalog-ingestion
complexity: medium
mode: confirm
status: pending
depends_on: []
created: 2026-10-28
---

# Work Item: Source Fetch Port & Adapters

## Description

Add the port through which ingestion retrieves source content. It has two adapters:

- **HTTP:** a hardened HTTP adapter in `adapters/crawl/`.
- **Fake:** an adapter that serves recorded fixtures, which is the default for local runs and tests.

Fetched content is untrusted input (AD-9). The adapter only returns bytes and metadata and never interprets them.

## Acceptance Criteria

- [ ] `ports/fetch.py` defines `SourceFetchPort.fetch(url, *, etag=None, last_modified=None) -> FetchResult`. `FetchResult` carries the status, final URL, content type, body bytes, etag and last-modified. It supports a 304 not-modified result.
- [ ] HTTP adapter in `adapters/crawl/http.py`:
  - connect and read timeouts
  - a maximum body size (abort above it)
  - a capped redirect count
  - `http`/`https` schemes only
  - a fixed, identifying user-agent
- [ ] SSRF guard: the adapter refuses to connect when the target (and every redirect hop) resolves to a loopback, private, link-local, multicast or reserved address. The check happens at connect time, so DNS rebinding cannot bypass it.
- [ ] Typed domain errors for timeout, too large, blocked address, HTTP error and network error. No raw library exception leaks out of the adapter.
- [ ] The fake adapter in `adapters/crawl/fake.py` maps URLs to fixture files under `backend/tests/fixtures/sources/`. Unknown URLs raise the same "HTTP error" type as the real adapter.
- [ ] The port is registered in `ports/registry.py` and wired in `config/adapters.py`. Selection comes from settings, and the fake is the local and test default.
- [ ] Logs carry the source id, status, size and duration, and never body content (AD-13).
- [ ] The HTTP client library is chosen, pinned and recorded in `.specs-fire/standards/tech-stack.md`.
- [ ] Tests cover, with the HTTP layer mocked and no live network:
  - each error type
  - the size cap
  - a redirect into a private IP being refused
  - 304 handling
  - the fake returning fixtures

## Technical Notes

- **Spine references:** AD-9 (untrusted input), AD-2 (ports and adapters), AD-13 (no content in logs).
- **Why the SSRF guard:** source URLs are operator-entered, but the guard is cheap insurance.
- **`robots.txt` and crawl politeness** belong to the later crawl intent. Feeds and ICS are fetched directly.
- **Scope:** this port fetches public source content. It is separate from `CalendarPort`, which handles credential-bearing personal ICS (AD-18).

## Dependencies

(none)
