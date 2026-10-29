---
run: run-eventpulse24-020
work_item: ics-calendar-adapter
intent: onboarding-and-account
generated: 2026-10-29
mode: validate
---

# Implementation Walkthrough: ICS Calendar Adapter (AD-18)

## Summary

One ICS/webcal adapter that serves Google, Apple and Outlook — and the shared parser
both importers now use, moved into a new `formats/` layer so the catalog parser and the
calendar parser **cannot** fork.

The item's central problem is a layering conflict. The catalog already parses ICS, in
`apps/ingestion/parsers/ics.py`. The calendar adapter must also parse ICS, and it lives
in `adapters/`. Under AD-2, `adapters` may not import `apps` — so the two importers
could not share a parser where either of them sits. Left alone, they would have grown
two ICS parsers, and the two would drift: the same feed imported through the catalog and
through a calendar connection would produce two different identities for one event.

The resolution is a **new layer between `adapters` and `ports`**: `formats`. A format
layer reads bytes and produces values. It opens no socket, touches no database, and
knows nothing about Django. The catalog's parser and the calendar's adapter both call it,
and the fork is prevented *structurally* — by an import-linter contract and an AST
allowlist — not by convention.

---

## Structure Overview

```
backend/
├── formats/                        ← NEW LAYER (AD-2)
│   ├── __init__.py
│   ├── text.py                     ← format-agnostic text stripping + the caps
│   ├── times.py                    ← format-agnostic time helpers
│   └── ics/
│       ├── __init__.py
│       ├── events.py               ← the `IcsEvent` the parser hands over
│       ├── parser.py               ← the ONE ICS parser
│       └── windows_zones.py        ← the Windows-TZID → IANA mapping
│
├── apps/ingestion/parsers/
│   ├── ics.py                      ← the catalog's *view* of the parser's output
│   ├── text.py                     ← now delegates to formats/text.py
│   ├── feeds.py, jsonld.py         ← now delegate to formats/times.py
│   └── types.py                    ← the caps now come from formats/text.py
│
├── adapters/calendar/ics.py        ← NEW: the real CalendarPort implementation
├── ports/calendar.py               ← the port: three typed outcomes
└── ports/fetch.py                  ← `FetchLimits` lives here now
```

The layering after this item:

```
config | worker  →  apps | adapters  →  formats  →  ports  →  domain  →  shared
```

---

## The Four Decisions

### 1. A new `formats` layer, proved to be a leaf

`formats/` sits between the applications and the ports. It may import the stdlib,
`icalendar` (the ICS format's own grammar) and its own siblings. Nothing else — no
Django, no `httpx`, no database.

Two gates prove it, and they are independent of each other:

- **The graph gate** — an import-linter contract, `single-ics-parser`: only `formats.ics`
  may import `icalendar`. The calendar adapter and the catalog parser both reach the
  parser through `formats.ics`, so neither can grow its own. The one ignored import is
  the catalog calling into `formats` — the only direction allowed.
- **The allowlist gate** — `backend/tests/architecture/test_formats_pure.py` walks the
  AST of every file in `formats/` and fails on any import outside the allowlist. A
  planted-source test exercises the three reaches that would break it (a socket, the
  database, a project package), so the rule is proved, not merely asserted.

The second gate exists because the first cannot see everything: import-linter sees the
*graph*, not whether a format module reaches for `django.conf.settings` from inside a
function.

### 2. The adapter never opens a socket

`adapters/calendar/ics.py` resolves `SourceFetchPort` from the registry and calls
`fetch()`. The hardened client in `adapters/crawl/` does the address policy, the size
limits, the deadline and the decompression budget — *unchanged*.

This is the reason the calendar path has no second SSRF implementation: it does not
have a first one. A calendar feed is fetched by the same code as an RSS page, with
different numbers.

The one thing the calendar asks for that a source fetch does not is
`allow_cross_host_redirect=True`: every provider redirects the address the user pasted to
a CDN host. That relaxes the **host**, never the **address**. The address policy still
runs at connect time on every hop, so:

- a redirect to a private address is refused;
- a public host that resolves to a private address is refused (DNS rebinding);
- a non-standard port, credentials in the URL and a redirect loop are each refused.

### 3. The calendar's own bounds, handed to the same client

A calendar feed is a different shape from an RSS page: a year of events is a few hundred
kilobytes, so 5 MB is roughly ten years of events — and a tighter bound is worth having
on a user-supplied URL. The adapter declares its own numbers:

```python
MAX_ICS_BYTES = 5 * 1024 * 1024
MAX_REDIRECTS = 5
CONNECT_TIMEOUT = 5.0
READ_TIMEOUT = 15.0
TOTAL_TIMEOUT = 30.0
DNS_TIMEOUT = 3.0
```

and hands them to the shared client as a `FetchLimits`. The *shape* of `FetchLimits`
lives in `ports/fetch.py` — because a caller whose content is a different shape may want
its own bounds, and `ports` never imports Django. The adapter's class in
`adapters/crawl/http.py` is a thin subclass whose only job is *reading the settings*.

The decompression budget, the deadline and the size cap are therefore the **same code**
in both paths. Only the numbers differ. That is what D7 asked for, and it is why the
constants are not duplicated in a second copy of the guard.

### 4. Three outcomes, not one

A calendar credential can be in three states, and conflating any two of them is a
user-facing bug:

| Outcome | When | What the user sees |
|---|---|---|
| `CalendarRevokedError` | 401, 403, 404, 410 | "Please reconnect it." |
| `CalendarTransientError` | 5xx, a timeout, a network error, a malformed feed, a `429` | "We'll try again." |
| `CalendarRefusedError` | we refused: a blocked scheme, a blocked address, an oversized body | a problem with the address |

Only the first marks a connection revoked. A provider's bad afternoon must never ask the
user to reconnect a working calendar — and a `429` or a `400` caused by our own request
is our fault, not the credential's.

Whether a blocked fetch was *our* refusal is asked of the transport, not decided from a
hand-copied list of reason strings:

```python
if exc.is_policy_refusal:
    raise CalendarRefusedError(details={"reason": reason}) from None
```

---

## The Parser's Contract

`formats/ics/parser.py` hands over the times **as written** — because the same file is
read by two importers that place them differently:

- The **catalog** resolves a time against the *venue's* zone, later in the pipeline.
- The **calendar adapter** resolves it against the *event's own* zone, here — a personal
  calendar has no venue registry to resolve it later.

So the parser's output carries the representation *and* the zone together:

| Written as | The parser hands over |
|---|---|
| `20261106T003000Z` | an aware UTC datetime |
| `DTSTART;TZID=Eastern Standard Time:20261105T193000` | a naive wall clock + `start_zone="America/New_York"` |
| `DTSTART:20261108T090000` | a naive wall clock, no zone — a floating time |
| `DTSTART;VALUE=DATE:20261114` | a naive midnight, `all_day=True` |

The calendar adapter then places each:

- **UTC** → stays aware.
- **TZID** → resolved in its own zone; its end is read in the start's zone, so a
  `DTEND` in UTC is converted *into* the start's frame.
- **Floating** → names no moment, so it is **dropped**. There is no defensible guess.
- **All-day** → a *day*, not a time of day; with no zone it is read at UTC midnight, the
  convention every provider uses.

An end that cannot be aligned with the start's representation is dropped rather than
guessed at — the four combinations (TZID/floating, TZID/date, UTC/TZID, UTC/floating)
are each pinned.

---

## The Identity Rule

One event, one id — across both importers. `domain.dedup.ics_item_id` is the single
authority, and the adapter's `_uid` implements exactly the catalog's rule:

| Event | Id |
|---|---|
| A plain event | its bare UID |
| An `RRULE` master | `ics_item_id(uid, start_instant)` |
| A `RECURRENCE-ID` override of the master's **own** instance | `ics_item_id(uid, recurrence_id)` — **the same id as the master**, so it replaces it |
| A `RECURRENCE-ID` override of a **later** instance | its own id — it is a different event |

The third row is the one that matters. A master generates an instance for the week it
starts; an override for that same week is *the same event, moved*. If the two were given
different ids, the importer would insert both and violate the unique constraint — and the
user would lose an event. The override therefore wins, whichever comes first in the file,
and the master instance it replaces is never emitted.

---

## The Credential

The secret ICS URL **is** the credential (AD-18). Three rules follow, and all three are
enforced:

1. **It never reaches a log.** The hardened client's log line carries ids and counts
   only. The adapter's own log line carries integer counts and a reason-slug → count map
   — a slug is one of our own names (`no_event_start`, `floating_time`,
   `unplaceable_time`), never a title, a uid, a URL or a zone.
2. **It never reaches an exception.** Every exception leaving the adapter is a
   `CalendarError` carrying a reason slug, raised `from None`. No traceback can carry it
   either.
3. **It never reaches the wire in cleartext.** `http://` is refused *at write time*, in
   `apps/personalization.services.calendar_connections`, so the user hears about it
   while they are still typing — not at the first poll, with a stored connection they
   cannot use. `webcal://` and `webcals://` are the iCloud spelling and are normalised to
   `https://` at fetch time; the *stored* credential keeps the form the user typed,
   because normalising at write time would change what the user recognises.

---

## Where the Money Is Spent

The adapter is thin — roughly 350 lines, most of them docstrings that say *why*. The
work is in getting the boundaries right:

- **The fetch.** One `httpx.Client` per fetch, closed afterwards; no cookie is ever sent
  (httpx copies the jar into a default-policy one, so the header is dropped on every hop
  instead).
- **The decompression.** The body is read raw and decompressed *here*, with an output
  budget — so neither a gzip bomb nor a stacked encoding can exceed `max_bytes`. A
  calendar feed compresses extremely well, which is exactly the shape of a bomb.
- **The override bookkeeping.** `by_uid` and `overridden`, so the override wins and the
  master instance it replaces is never emitted.

---

## What the Tests Prove

177 item-scoped tests, in five files:

| File | Tests | Proves |
|---|---|---|
| `tests/adapters/test_calendar_ics.py` | 79 | The adapter: the fetch, the three outcomes, the identity rule, the limits, the logs |
| `tests/ingestion/parsers/test_ics.py` | 34 | The catalog's view of an ICS file |
| `tests/formats/ics/test_parser.py` | 34 | The format's view of the same file |
| `tests/adapters/test_calendar_fetch.py` | 14 | The SSRF policy under the calendar's one relaxation |
| `tests/architecture/test_formats_pure.py` | 16 | `formats` is a leaf |

The two ICS suites are deliberately separate, and that is the point: the **format's** view
(the times as written, the zones, the all-day spans) and the **catalog's** view (the
identity decision, the URL resolved against the source's base, the status hint, the venue
name, the series id) are pinned independently, so the shared parser cannot drift without
one of them failing — and neither importer can quietly change what the other one means.

The fetch tests run on a **scripted network** — real httpx, real httpcore, no socket — so
the SSRF policy is proven through the actual client rather than against a mock.

One note on the fixtures: the address policy *denies* the TEST-NET ranges, so a test that
used `93.184.216.34` would have passed for the wrong reason — it would have been
refused as a private address before the behaviour under test was ever reached. The
calendar fetch tests use real public addresses instead.

---

## What Comes Next

`calendar-sync-and-polling` puts the schedule on top of this: a worker that polls each
connection, hands the feed to this adapter, and writes the events — reconciling the
override-replaces-master rule against what is already stored, so a moved event updates
rather than duplicates.

`calendar-connect-api` puts the HTTP endpoints over it: connect, disconnect, reconnect,
with the credential encrypted at rest and never returned to the browser.

---

## Result

**Complete.** 2536 passed, 0 failed; 98.87% coverage (148 files at 100%); ruff clean;
17/17 import contracts kept. The six review blockers were fixed and regression-tested,
including one silent regression the suite itself could not see — a floating-time `RRULE`
master that was being dropped from the catalog entirely.
