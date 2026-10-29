---
id: run-eventpulse24-012
scope: single
work_items:
  - id: source-fetch-port
    intent: event-catalog-ingestion
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
status: completed
started: 2026-10-28T09:17:01.732Z
completed: 2026-10-28T10:07:28.726Z
---

# Run: run-eventpulse24-012

## Scope
single (1 work item)

## Work Items
1. **source-fetch-port** (confirm) — completed


## Current Item
(all completed)

## Files Created
- `backend/ports/fetch.py`: SourceFetchPort, FetchResult, typed FetchError subclasses
- `backend/adapters/crawl/address_policy.py`: Owned IPv4/IPv6 deny table (never is_global)
- `backend/adapters/crawl/http.py`: HttpFetchAdapter: GuardedBackend, DeadlineStream, GuardedTransport, own decompression, per-hop checks
- `backend/adapters/crawl/fake.py`: FakeFetchAdapter: validated fixture index, RFC 9110 conditionals, simulated failures
- `backend/tests/fixtures/sources/index.json`: Fake fetch fixture index
- `backend/tests/fixtures/sources/sample.rss`: Minimal RSS fixture
- `backend/tests/adapters/scripted_network.py`: In-memory network: scripted DNS, connector, streams, fake clock
- `backend/tests/adapters/test_crawl_address_policy.py`: Every deny range pinned
- `backend/tests/adapters/test_crawl_http.py`: HTTP adapter behavior on the scripted network
- `backend/tests/adapters/test_crawl_loopback.py`: Real-socket fetch through the guard
- `backend/tests/adapters/test_crawl_fake.py`: Fake adapter and registry

## Files Modified
- `backend/ports/registry.py`: fetch port key and get_fetch_port()
- `backend/config/adapters.py`: fetch adapters; SOURCE_FETCH override; REAL_ADAPTERS fetch
- `backend/config/env.py`: Source fetch settings with validation
- `backend/config/settings.py`: SOURCE_FETCH dict; httpx/httpcore loggers at WARNING
- `backend/config/checks.py`: eventpulse.E006 fake fixture index check
- `backend/adapters/logging/redaction.py`: byte_count allowlisted
- `backend/pyproject.toml`: httpx==0.28.1; http-client import contract
- `backend/uv.lock`: httpx, httpcore, idna locked
- `backend/tests/architecture/test_import_contracts.py`: http-client plants and allowed paths
- `backend/tests/config/test_adapters.py`: Fetch override tests
- `backend/tests/config/test_env.py`: Fetch settings tests
- `backend/tests/config/test_checks.py`: E006 tests
- `backend/tests/config/test_logging_config.py`: httpx/httpcore logger levels
- `.env.example`: SOURCE_FETCH documentation
- `.specs-fire/standards/tech-stack.md`: httpx recorded
- `.specs-fire/standards/coding-standards.md`: Outbound fetches only through SourceFetchPort
- `.specs-fire/intents/event-catalog-ingestion/work-items/ingest-pipeline-and-lifecycle.md`: Fetch-outcome ACs handed on

## Decisions
- **HTTP client**: httpx 0.28.1 with a guarded httpcore network backend (Framing and redirects from a mature library; address, port, time and size decisions owned here)
- **Address policy**: Own deny table; IPv6 only in 2000::/3; embedded IPv4 denied (is_global drifts between CPython releases and leaks several forms)
- **Ports and redirects**: 80/443 only; same-host redirects only (Stops internal service probes; FR-17 ToS review covers one host)
- **Deadline**: One 30 s budget across DNS, connect, TLS, headers, body, hops (Per-read timeouts alone allow slow-drip and per-address stalls)
- **Decompression**: iter_raw plus own zlib with an output budget; identity/gzip/deflate only (httpx decodes without a limit; stacked encodings multiply it)
- **Cookies**: Strip Cookie on every hop (httpx copies a policy jar into a default one, so policies don't hold)
- **DNS timeout**: One-shot daemon thread per lookup (A shared pool left idle threads, making fork() unsafe)
- **Review**: 1 suggestion applied (fake fixture read errors become port errors) (User approved)


## Summary

- Work items completed: 1
- Files created: 11
- Files modified: 17
- Tests added: 189
- Coverage: 98.4%
- Completed: 2026-10-28T10:07:28.726Z
