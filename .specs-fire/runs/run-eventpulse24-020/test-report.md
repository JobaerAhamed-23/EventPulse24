---
run: run-eventpulse24-020
work_item: ics-calendar-adapter
intent: onboarding-and-account
generated: 2026-10-29
status: passing
---

# Test Report: ICS Calendar Adapter (AD-18)

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Item-scoped | 177 | 0 | 0 | 98.87% (whole backend) |
| **Total (whole backend)** | **2536** | **0** | **0** | **98.87%** |

The 177 item-scoped tests are a subset of the 2536-test backend suite. The whole backend
suite is **2536 passed, 0 failed** in 171.63s; coverage is **98.87%** across 5571
statements with **148 files at 100%**.

## Test Commands

```bash
# The item's own tests
cd backend && .venv/bin/python -m pytest tests/formats/ tests/ingestion/parsers/ \
    tests/adapters/test_calendar_ics.py tests/adapters/test_calendar_fetch.py -q

# The whole backend suite, with coverage
cd backend && .venv/bin/python -m pytest tests/ -q --cov

# The linter
cd backend && .venv/bin/python -m ruff check .

# The import contracts
cd backend && .venv/bin/lint-imports
```

## What Was Added

| File | Tests | Covers |
|------|-------|--------|
| `backend/tests/adapters/test_calendar_ics.py` | 79 | The adapter: the fetch, the three outcomes, the identity rule, the limits, the logs |
| `backend/tests/ingestion/parsers/test_ics.py` | 34 | The catalog's view of an ICS file: the `ParsedCandidate`s |
| `backend/tests/formats/ics/test_parser.py` | 34 | The format's view of the same file: the times as written |
| `backend/tests/adapters/test_calendar_fetch.py` | 14 | The SSRF policy under the calendar's one relaxation |
| `backend/tests/architecture/test_formats_pure.py` | 16 | `formats` is a leaf: no socket, no database, no Django |

**The two ICS suites are deliberately separate.** `tests/formats/ics/test_parser.py` pins
the *format* — the times as written, the zones, the all-day spans, the floating times. The
catalog's own suite pins the *catalog* — the identity decision, the URL resolved against
the source's base, the status hint, the venue name, the series id. The same file, read two
ways, proven independently: the shared parser cannot drift without one of them failing,
and neither importer can quietly change what the other one means.

## The Properties Pinned

### The fetch (AD-9, AD-13)

- The adapter **never opens a socket**. It resolves `SourceFetchPort` from the registry and
  calls `fetch()` — the hardened client in `adapters/crawl/` does the address policy, the
  size limits, the deadline and the decompression budget, *unchanged*. There is no second,
  weaker copy of the SSRF policy in the calendar path.
- The one relaxation is `allow_cross_host_redirect=True`: every provider redirects the
  address the user pasted to a CDN host. It relaxes the **host**, never the **address** —
  a redirect to a private address is still refused, because the check happens at connect
  time on every hop (`test_a_redirect_to_a_private_address_is_refused_even_when_cross_host_is_allowed`).
- A private address behind a public host is refused (DNS rebinding) — the check is at
  connect time, not at the URL.
- A non-standard port, credentials in the URL, and a redirect loop are each refused.
- A gzip bomb is refused: the body is read raw and decompressed with an output budget, so
  neither a bomb nor a stacked encoding can exceed `max_bytes`.
- The fetch's log line carries **no URL**: the secret ICS URL *is* the credential, so the
  log line holds ids and counts only (`test_the_fetch_log_line_carries_no_url`).

### The three outcomes (FR-3)

- `401`, `403`, `404`, `410` → `CalendarRevokedError`: the user must reconnect.
- Everything else that failed — including a `429` and any other `4xx` → `CalendarTransientError`.
  A provider's bad afternoon never asks the user to reconnect a working calendar.
- Our own refusal — a blocked scheme, a blocked address, an oversized body →
  `CalendarRefusedError`, which is *not* a revocation.

### The identity rule

`domain.dedup.ics_item_id` is the single authority for both importers, and the adapter's
`_uid` implements exactly the catalog's rule:

- A plain event keeps its bare UID.
- An `RRULE` master is keyed by its own start instant.
- A `RECURRENCE-ID` override is keyed by its recurrence instant — so the override of a
  master's **own** instance gets the **same** id as that master, and replaces it. The
  importer must never see both, or the second would violate the unique constraint and the
  user would lose an event.
- An override of a **later** instance gets its own id, because it is a different event.

### The times

The parser hands over times *as written*; the adapter resolves them, because a personal
calendar has no venue registry to resolve them later.

- A UTC time stays aware.
- A `TZID` time is a wall clock with an IANA zone; its end is read in the start's zone.
- A floating time names no moment and is dropped (it cannot be placed).
- An all-day event names a *day*, not a time of day; with no zone it is read at UTC
  midnight — the convention every provider uses.
- An end that cannot be aligned with the start's representation is dropped rather than
  guessed at.

### The logs (AD-13)

The calendar's log line carries integer counts and a reason-slug → count map. A slug is
one of our own names (`no_event_start`, `floating_time`, `unplaceable_time`) — never a
title, a uid, a URL or a zone. The redaction allowlist was widened to include those fields
so they are *readable* in production rather than `[redacted]`, and the project-logger list
was widened to include the new `formats` layer so a logger there is redacted like any
other of ours.

## Coverage

```
TOTAL                                             5571     63    99%
148 files skipped due to complete coverage.
Required test coverage of 80.0% reached. Total coverage: 98.87%
```

The files this item changed are at 100% except three pre-existing gaps elsewhere in the
codebase (`apps/identity/*`, `adapters/throttle/redis.py`, `config/asgi.py` and friends —
all touched by earlier items in this run or by work not yet done).

## Lint and Contracts

```
ruff check .
All checks passed!

ruff format --check .
331 files already formatted

lint-imports
Contracts: 17 kept, 0 broken.
```

The `single-ics-parser` contract is still **KEPT** after the file moves — the fork is
prevented *structurally*, not by convention:

```
AD-2 only formats.ics parses iCalendar files KEPT (1 ignored import)
```

That single ignored import is the catalog parser calling into `formats.ics` — the one
direction that is allowed. The calendar adapter calls the same module, so neither importer
can grow its own ICS parser.

## Defects the Suite Found and the Review Fixed

The suite was green on the first pass, but the code review found six defects the suite
*could not* see, and all six are now fixed and regression-tested. They are listed in full
in `review-report.md`; the two that changed behaviour are worth naming here:

1. **A floating-time `RRULE` master was silently dropped from the catalog.** The catalog
   parser's `_instance_utc` assumed a `datetime`; a floating master's `start_instant` is
   `None`, so the master produced **no candidate at all** — a silent regression that
   contradicted the parser module's own "behaviour is unchanged" claim. Fixed by keying a
   floating master on its wall clock read as UTC — the same reading a floating
   `RECURRENCE-ID` gets — and pinned by
   `test_a_floating_series_master_is_read_and_keyed_as_utc`.

2. **The calendar's own limits were dead constants.** D7 requires the calendar's bounds to
   be handed to the shared client, but `SourceFetchPort.fetch` had no `limits` parameter,
   so `MAX_ICS_BYTES` and the five timeouts were never used and the calendar fetched with
   the *source's* 10 MB budget. Fixed by moving `FetchLimits` into `ports/fetch.py` (the
   port never imports Django) and threading per-call limits through the transport; pinned
   by `test_the_fetch_carries_the_calendar_s_own_limits` and
   `test_a_per_call_limit_is_the_one_that_applies`.

## Test Result

**Passing.** 2536 passed, 0 failed, 98.87% coverage, ruff clean, 17/17 import contracts
kept.
