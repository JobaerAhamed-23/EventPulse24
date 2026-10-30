---
id: ics-calendar-adapter
title: ICS/Webcal Calendar Adapter
intent: onboarding-and-account
complexity: high
mode: validate
status: completed
depends_on: []
created: 2026-10-29
run_id: run-eventpulse24-020
completed_at: 2026-10-29T10:49:13.086Z
---

# Work Item: ICS/Webcal Calendar Adapter

## Description

Builds the real implementation of `ports.calendar.CalendarPort`: **one ICS/webcal adapter, used uniformly for Google, Apple and Outlook** (AD-18). Today only `adapters/calendar/fake.py` exists.

The address is **supplied by the user**, which makes this the project's first fetch of an arbitrary user-supplied URL. The SSRF, size and decompression protections built for source fetching (AD-9, `adapters/crawl/`) apply here at least as strictly. A user can type `http://169.254.169.254/` as easily as a real calendar link.

## Acceptance Criteria

- [ ] `webcal://` and `webcals://` are normalised to `https://`. Plain `http://` is refused, or upgraded only if the design doc justifies it. Any other scheme is refused.
- [ ] **SSRF.** The fetch connects only to addresses allowed by the project's own deny table, the same policy as `adapters/crawl/address_policy.py`, checked on **every resolved address and every redirect hop**. Tests cover loopback, link-local metadata, private ranges, an IPv6-embedded IPv4 address, and a redirect from a public host to a private one.
- [ ] **Limits.** There are bounded response size, bounded decompressed size (gzip-bomb safe), a bounded number of redirects and a timeout, each a named constant. Exceeding any of them returns a typed failure and never raises an unhandled exception.
- [ ] **Revocation.** HTTP **401, 403, 404 and 410** map to one typed "revoked" outcome (FR-3: "detected on next poll and the user is prompted to reconnect"). Other failures, such as 5xx, timeouts and network errors, map to a **transient** outcome that does not mark the connection revoked. There is one test per status code.
- [ ] **Parsing** produces `ports.calendar.CalendarEntry` values. Times are aware UTC with the IANA zone preserved (AD-6), and all-day and floating times are handled the way the existing ICS parser already handles them. Recurring events are listed as simple instances only, with no RRULE expansion beyond that (FR-31 out of scope). The design doc states exactly what is produced for an `RRULE`.
- [ ] **The credential never leaks.** The URL is never logged, never put into an exception message that can reach a log, and never put into a span or trace attribute. A test drives each failure path with log capture and asserts the URL is absent. This includes `httpx`'s own logger, which logs request URLs at INFO.
- [ ] Conditional requests (`ETag` / `If-Modified-Since`) are used if the source-fetch path already supports them. They are polite to providers and relevant to OQ-7.
- [ ] The adapter is registered in `ports/registry.py` for the non-fake configuration, and the fake stays the local and CI default.
- [ ] **Import contracts stay green.** In particular, "only `adapters.crawl` imports an HTTP client" and "adapters never import each other" are either respected or amended deliberately, as the design doc decides. They are never bypassed.
- [ ] Tests run against a local test server or recorded fixtures, with no live network in CI. They cover a Google-shaped, an Apple-shaped and an Outlook-shaped ICS fixture.

## Technical Notes

**Design doc required (validate).** The central problem is a layering conflict, and it has to be solved deliberately:

- **The HTTP fetch.** `pyproject.toml` has the contract "AD-9 only adapters.crawl imports an HTTP client (source fetches go through SourceFetchPort)". The calendar adapter therefore can't import `httpx` itself. It also can't import `adapters.crawl`, because "adapters never import each other".
  - **Option A:** fetch through `SourceFetchPort`, resolved via the registry, and parse in the calendar adapter.
  - **Option B:** amend the contract to allow `adapters.calendar` too, and share the hardened client through a neutral module.
  
  Weigh which keeps a single SSRF implementation.
- **The ICS parsing.** It lives in `apps/ingestion/parsers/ics.py` and imports `apps.ingestion.parsers.*`, and an adapter must not import `apps`. Options: move the pure parts down into `domain/` or a neutral package, or have the adapter return raw bytes and let `personalization` call `ingestion`'s published parser. Either way, the catalog parser and the calendar parser **must not fork** into two ICS implementations.
- **Mapping to `CalendarEntry`.** A catalog `ExtractedRecord` and a personal `CalendarEntry` are different shapes. State the mapping.

Look at `run-eventpulse24-012` (`source-fetch-port`) for the hardened fetch's history. The review there caught the `httpx` URL-logging and gzip-bomb issues, and both apply again here.

## Dependencies

(none)
