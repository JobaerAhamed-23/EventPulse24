---
run: run-eventpulse24-013
work_item: structured-parsers
intent: event-catalog-ingestion
mode: confirm
checkpoint: plan (Checkpoint 1 of 1)
approved_at: 2026-10-28T10:30:05Z
---

# Implementation Plan: Structured Source Parsers (JSON-LD, RSS, ICS)

## Approach

> **Needs your call:** decisions **S1–S6** below.

Three pure parsers turn fetched bytes into a list of `ParsedCandidate`s plus a tally of skipped items. They never call an LLM, never raise on malformed input, never render or execute content (AD-9), and never decide identity or timezone tier: they hand times over **as written** for `domain.timezones.resolve_tz` and `domain.dedup` to decide.

**Interface:**

```python
parse(method: AcquisitionMethod, content: bytes, context: SourceContext) -> ParseResult
#   jsonld -> parse_jsonld · rss -> parse_feed (RSS 2.0 + Atom) · ics, email_ics -> parse_ics

SourceContext(source_id: UUID, source_url: str)            # base URL for relative links
ParseResult(candidates: list[ParsedCandidate], skipped: Counter[str], error: str | None)
```

`error` is set when the whole document is unreadable (for example, invalid XML or ICS). The pipeline (item 6) records it as the source's parse failure. `skipped` counts items dropped by reason, such as `no_event_start`, `unparseable_start`, `no_title` or `too_many_items`.

### Decisions that need your call

| # | Question | Proposed choice | Why |
|---|---|---|---|
| **S1** | ICS library | **`icalendar==7.3.0`** (it brings in `python-dateutil`) | It is the maintained standard for parsing ICS. It handles `TZID`, `VTIMEZONE`, `VALUE=DATE`, `RECURRENCE-ID` and line unfolding. I verified it keeps the raw `TZID` param (`Eastern Standard Time`), gives `date` for all-day events and aware UTC for `Z`, and raises `ValueError` on malformed input. Writing an RFC 5545 parser ourselves is not worth the risk. |
| **S2** | RSS/Atom library | **`defusedxml==0.7.1` + stdlib `ElementTree`**, reading RSS 2.0 and Atom ourselves. `feedparser` is rejected. | Feeds are untrusted XML. defusedxml blocks entity expansion and external entities. Event feeds carry their dates in extension namespaces, which we read explicitly anyway. feedparser would add two dependencies (`feedparser-sgmllib`, `six`) and its own HTML sanitizer, which we'd bypass. |
| **S3** | Where an RSS/Atom item's event start comes from | Only explicit event fields: the RSS event module (`ev:startdate`/`ev:enddate`/`ev:location`, `http://purl.org/rss/1.0/modules/event/`) and xCal (`xcal:dtstart`/`xcal:dtend`/`xcal:location`, `urn:ietf:params:xml:ns:xcal`). **Never `pubDate`/`updated`.** Items without these fields are skipped with `no_event_start`. | A publication date is not an event time. Guessing would create wrong-time events, the class FR-60 exists to prevent. Many generic RSS feeds will therefore yield nothing, and that is correct. A source like that needs JSON-LD or ICS (or the later LLM path). |
| **S4** | JSON-LD HTML scanning | Stdlib `html.parser`, which collects only `<script type="application/ld+json">` contents (also with a `; charset=…` suffix), then `json.loads` each block. A bad block is skipped (`invalid_jsonld`) and the others are still parsed. | No HTML library is needed. Nothing is rendered or executed, and tags inside scripts are just text. |
| **S5** | Field limits (hostile or oversized input) | Title ≤ 500 characters (`Event.title`), description ≤ 10,000, venue name and city ≤ 200 and 100, truncated at a character boundary after markup stripping. A URL over 2,048 characters, or one that isn't `http(s)`, is dropped (set to `""`) rather than skipping the item. At most **5,000 items** per document; the rest count as `too_many_items`. | It matches the model's column sizes. A hostile document can't make one item fail the database insert, and it can't produce unbounded work. |
| **S6** | `source_event_id` when the source has no stable ID | **JSON-LD:** `@id`; otherwise `derived:` + 32 hex characters of sha256 over (URL, name, start as written). **RSS:** `guid`; otherwise the same derived hash using `link`. **Atom:** `id` (the spec requires it); otherwise derived. **ICS:** `domain.dedup.ics_item_id(uid, instance_start_utc)` for any series member (`RRULE` or `RECURRENCE-ID`), plain `uid` otherwise, and a derived hash if `UID` is missing. | It is never empty (design D22) and stable across re-fetches, and the hash covers the start so recurring items without IDs stay distinct. |

### The candidate (`apps/ingestion/parsers/types.py`)

```python
@dataclass(frozen=True)
class ParsedCandidate:
    source_event_id: str
    title: str                     # plain text, ≤ 500
    canonical_url: str             # absolute http(s) as given, or ""; domain.dedup normalizes it
    start: datetime                # naive wall-clock time, or aware with the source's fixed offset
    start_zone: str | None         # zone name as written (TZID / tz), Windows names mapped to IANA
    start_raw: str                 # the text exactly as written, kept for ExtractedRecord.payload
    end: datetime | None           # same representation as start; overnight roll applied
    end_raw: str | None
    all_day: bool
    venue_name: str                # plain text, or ""
    venue_city: str
    venue_country: str             # ISO-3166 alpha-2 when given, else ""
    description: str               # plain text, ≤ 10,000
    status: StatusHint             # scheduled | postponed | cancelled
    sold_out: bool
    series_id: UUID | None         # shared.ids.series_id(source_id, series_key)
    raw: dict[str, str]            # the as-written fields, for the payload
```

### Per-format rules

- **JSON-LD**
  - **What counts as an event:** every node whose `@type` (a string or a list) is `Event` or one of schema.org's Event subtypes (a fixed, tested set), found in top-level objects, arrays and `@graph`.
  - **`EventSeries`:** the series itself is never emitted. Its `subEvent`(s) are emitted with `series_id` derived from the series' `@id`, or from its derived key.
  - **Dates:** `startDate` and `endDate` are parsed with `datetime.fromisoformat`. A date-only value is an all-day event.
  - **Status:** `eventStatus` (`EventCancelled`, `EventPostponed`, `EventRescheduled` mapped to scheduled, `EventScheduled`) accepts the full `https://schema.org/` IRI, the `http://` IRI, or the bare name.
  - **Sold out:** `offers` (a dict or a list) with any `availability` of `SoldOut`.
  - **Location:**
    - a `Place` gives `name` plus `address`, which may be a `PostalAddress` (`addressLocality`, `addressCountry`) or a plain string
    - a `VirtualLocation` gives no venue
    - a plain string is taken as the venue name

    The location's `timezone`, if present, becomes `start_zone`.
- **RSS 2.0 / Atom**
  - **What is read:** `title`, `link` (or Atom `link rel=alternate`), `guid`/`id`, `description`/`summary`/`content`, and the S3 event fields.
  - **Location:** `ev:location` and `xcal:location` become the venue name.
  - **Dates:** ISO 8601 only. An unparseable date is skipped as `unparseable_start`.
  - **Root:** a document that isn't `<rss>` or Atom `<feed>` (`not_a_feed`) is an error. So is invalid XML, or XML defusedxml refuses.
- **ICS** (`icalendar`)
  - **Parsing:** `Calendar.from_ical(bytes)` returns an `error` on `ValueError`. Each `VEVENT` is read for `UID`, `SUMMARY`, `DTSTART` (required, otherwise `no_event_start`), `DTEND` or `DURATION`, `STATUS` (`CANCELLED` maps to cancelled; `TENTATIVE` and `CONFIRMED` map to scheduled), `LOCATION` (venue name), `URL` and `DESCRIPTION`.
  - **Times are as written:**
    - `TZID` gives the wall-clock time (naive), with `start_zone` set to the TZID mapped through the **Windows → IANA table**
    - `Z` gives aware UTC
    - floating gives naive, with no zone
    - `VALUE=DATE` gives local midnight and sets `all_day`
  - **Series:** a master with `RRULE` is emitted once, for its own `DTSTART`. Instances are never expanded. Each `RECURRENCE-ID` override is emitted as its own candidate. Both carry `series_id(source_id, UID)` and `ics_item_id(UID, instance_start_utc)`, so an override of the master's own instance updates that same source item.
  - **Instance start for the ID:** taken from `RECURRENCE-ID`, converted to UTC with icalendar's resolved zone. A floating `RECURRENCE-ID` is read as UTC, **for the ID only**, so it stays stable.
  - **Reuse:** `parse_ics` takes bytes, so the later email-ICS mailbox path calls the same function.
- **Windows zone names** (`apps/ingestion/parsers/windows_zones.py`): an explicit table of the common Outlook/Exchange names (US, Canada, Mexico, Europe, UK, India, China, Japan, Australia, NZ, Brazil and others, about 40 names), taken from CLDR's `windowsZones` "001" column. Each target must pass `domain.timezones.canonical_zone` in a test. An unmapped name passes through unchanged, `canonical_zone` ignores it, and the venue tz takes over (as the AC says).
- **Shared normalization** (`apps/ingestion/parsers/text.py`, `times.py`):
  - **`plain_text(value, limit)`:** strips tags with `html.parser`, drops `<script>`/`<style>` content, unescapes entities, removes control characters, collapses whitespace and truncates.
  - **All-day events:** start at 00:00. `end` is the exclusive next-midnight `DTEND`, or `start + 1 day` when there is none.
  - **Overnight roll:** if `end < start` and both use the same representation (naive, or the same offset), `end += 1 day`. If it is still before the start, `end` becomes `None` and the item counts in `skipped["end_before_start"]`; the item itself is still emitted.
  - **Relative links:** resolved against `context.source_url`, then the http(s) check is applied.

### What the pipeline gets (and doesn't)

Parsers give **no** UTC instants, **no** tz tiers, **no** fingerprints and **no** identity decisions. Item 6 calls:

- `resolve_tz(start, source_zone=start_zone, venue_tz=…, end=end)`
- `title_fingerprint`, `venue_fingerprint` and `canonical_url`

That split is what the work item's "hand raw facts to the domain" means.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/apps/ingestion/parsers/__init__.py` | `parse()` dispatcher, exports |
| `backend/apps/ingestion/parsers/types.py` | `SourceContext`, `ParsedCandidate`, `StatusHint`, `ParseResult`, limits |
| `backend/apps/ingestion/parsers/text.py` | `plain_text`, `http_url`, `derived_id` |
| `backend/apps/ingestion/parsers/times.py` | `parse_iso`, the all-day and overnight rules |
| `backend/apps/ingestion/parsers/jsonld.py` | JSON-LD parser |
| `backend/apps/ingestion/parsers/feeds.py` | RSS 2.0 / Atom parser |
| `backend/apps/ingestion/parsers/ics.py` | ICS parser |
| `backend/apps/ingestion/parsers/windows_zones.py` | Windows → IANA table |
| `backend/tests/fixtures/sources/` | `venue-events.html` (JSON-LD: offset, `@graph`, cancelled, sold out, `EventSeries`), `broken-jsonld.html`, `events.rss` (ev: module: offset, naive + venue, no tz, `pubDate` only), `events.atom` (xCal), `broken.rss`, `calendar.ics` (TZID Windows name, UTC, floating, all-day, cancelled, RRULE master + RECURRENCE-ID override), `broken.ics`, `hostile.html` (script injection, 50 KB title, deep nesting, `javascript:` URL) |
| `backend/tests/ingestion/parsers/test_jsonld.py`, `test_feeds.py`, `test_ics.py`, `test_text_and_times.py`, `test_windows_zones.py`, `test_dispatch.py` | Tests (no database) |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/pyproject.toml`, `uv.lock` | `icalendar==7.3.0`, `defusedxml==0.7.1`. `tzdata` stays pinned at 2026.5, checked after locking. |
| `backend/tests/fixtures/sources/index.json` | Fake-adapter entries for the new fixtures, so item 6/9 can fetch them |
| `.specs-fire/standards/tech-stack.md`, `coding-standards.md` | The libraries; "parsers hand times over as written and never decide identity or tier" |

## Tests

| Test File | Coverage |
|-----------|----------|
| `test_jsonld.py` | Every event in the fixture, field by field. `@graph` and arrays. A subtype and a `@type` list. `EventSeries` → `subEvent` with a shared `series_id`. The `eventStatus` IRI variants. Sold out from a list of offers. A string address and a `PostalAddress`. `VirtualLocation`. A date-only value becomes all-day. An offset is kept aware, a naive value stays naive. One bad block doesn't stop the others. `@id` vs a derived ID (stable, never empty). A relative URL is resolved. |
| `test_feeds.py` | RSS with `ev:` and Atom with xCal. `pubDate`-only items are skipped (`no_event_start`). An unparseable date is skipped. `guid` vs a derived ID. Markup is stripped from the description. Invalid XML and a non-feed root return `error`. **A billion-laughs payload and an external entity are refused** (`error`, no expansion, no file read). |
| `test_ics.py` | A Windows TZID mapped to IANA with a naive wall-clock time. UTC stays aware. Floating stays naive. All-day gets a next-midnight end, or +1 day. `DURATION`. Cancelled. A master plus a `RECURRENCE-ID` override: distinct `ics_item_id`s, a shared `series_id`, and the override of the master's own instance gives the **same** ID. A missing `UID` gives a derived ID. Malformed input returns `error`. |
| `test_text_and_times.py` | `<script>`/`<style>` content dropped. Entities and control characters handled. Truncation at the exact limit. A `javascript:`/`data:`/overlong URL is dropped. Overnight roll and its failure. ISO variants with `Z`, an offset, naive, and date-only. |
| `test_windows_zones.py` | Every target passes `canonical_zone`; an unmapped name passes through unchanged. |
| `test_dispatch.py` | Each `AcquisitionMethod` reaches its parser (`email_ics` → ICS). `api`, `partnership` and `crawl` return `error="unsupported_method"`. **Every fixture's `ParseResult` never raises**, and that includes `hostile.html`, random bytes and an empty input. The 5,000-item cap holds. |
| Existing | Import contracts, the stdlib/alias checks and the full suite stay green |

## Technical Details

**No Django in parsers:** they import `domain`, `shared` and their libraries only. `AcquisitionMethod` comes from `apps.ingestion.models` for the dispatcher alone, which is allowed inside the app. Tests run without the database.

**Order:**
1. Dependencies (verify the tzdata pin)
2. `types`, `text`, `times`
3. Windows zones
4. JSON-LD
5. Feeds
6. ICS
7. Dispatcher
8. Fixtures and index entries
9. Tests alongside each step
10. Docs
11. Gates

---
*Plan approved at Checkpoint 1 (2026-10-28T10:30:05Z).
