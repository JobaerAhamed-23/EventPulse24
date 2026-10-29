---
run: run-eventpulse24-013
work_item: structured-parsers
intent: event-catalog-ingestion
generated: 2026-10-28
status: passed
---

# Test Report: Structured Source Parsers (JSON-LD, RSS, ICS)

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Parser unit tests (no database, no network) | 273 new | 0 | 0 | **100%** of `apps/ingestion/parsers/` (489 statements) |
| Architecture checks generated for the 8 new modules | 8 new | 0 | 0 | — |
| **Total suite** | **1315** (1034 before + 281 new) | 0 | 0 | **98.70%** overall · 100% `domain/` |

## Acceptance Criteria Validation

- ✅ **Normalized candidate type:** `ParsedCandidate` carries `source_event_id`, title, canonical URL, `start` as written plus `start_zone` and `start_raw`, an optional end, venue name/city/country, status hints (cancelled, postponed, sold out) and an optional `series_id`.
- ✅ **JSON-LD:**
  - every `Event` subtype (parametrized over the full set) and `@type` lists
  - `@graph` and arrays
  - the `eventStatus` IRI variants, and `SoldOut` from a dict or list of offers
  - `EventSeries` → `subEvent`s with a shared `series_id`
  - only `ld+json` scripts are read, and HTML is never rendered or executed
- ✅ **RSS 2.0 / Atom:**
  - `guid`/`id` used as `source_event_id`
  - items without an `ev:`/xCal start are counted (`no_event_start`), and `pubDate` is never used
  - an unparseable start is counted
- ✅ **ICS:**
  - `UID`; `DTSTART`/`DTEND` with UTC, `TZID` (including Windows names) or floating time; `DURATION`; `STATUS:CANCELLED`
  - `RECURRENCE-ID` overrides become distinct candidates sharing `series_id`, and an override of the master's own instance **replaces** it, in either file order (from the code-review fix)
  - no RRULE expansion
  - `parse_ics` is reused for `email_ics`
- ✅ **Pure, never raises, strips markup:**
  - every fixture through every parser, plus empty, NUL, seeded random, `<`×10k and repeated ICS headers: no exceptions
  - malformed documents return `error`
  - `hostile.html` is fully sanitized: `<script>`, `<style>`, `<iframe>` and `onerror` removed, the 50 KB title capped at 500, `javascript:` dropped, control characters removed
- ✅ **Recorded fixtures**, each with a valid and a malformed file per method:
  - an explicit offset
  - no offset but a venue city
  - no timezone at all
  - a cancelled event
  - a recurring ICS series
- ✅ **Libraries pinned and recorded:** `icalendar==7.3.0` and `defusedxml==0.7.1`. `tzdata` stays at 2026.5.
- ✅ **Malformed, oversized and injection inputs** are covered (see above), as are a billion-laughs payload and an external-entity payload, both refused.
- ✅ **Import contracts:** 13 kept.
- ✅ **ICS IDs** come from `domain.dedup.ics_item_id` (tested against its output).
- ✅ **Windows zone names** map through an explicit table, each target checked against `canonical_zone`. Unmapped names pass through.
- ✅ **Times as written:** naive for a wall-clock time, aware with the source's offset, `Z` as UTC. A differently-written `DTEND` is aligned to the start's representation and never converted to UTC on its own (4 alignment cases tested).
- ✅ **Deferred design-review items:**
  - derived IDs are stable and never empty
  - all-day events get a next-midnight end
  - overnight ends roll forward, and impossible ends are dropped and counted
  - the as-written times are kept in `raw` and `start_raw`

## Tests Written

- `tests/ingestion/parsers/test_jsonld.py` (63): the fixture field by field, every subtype, status and offers variants, containers, location forms, skip reasons, charset and comment handling, caps, series
- `tests/ingestion/parsers/test_feeds.py` (15): RSS `ev:`, Atom xCal, no `pubDate` fallback, all-day and overnight, XML bomb and XXE refused, a DTD reference accepted, error cases, caps
- `tests/ingestion/parsers/test_ics.py` (25): Windows TZID, UTC, floating, all-day, `DURATION`, cancelled, series and overrides, a floating or date `RECURRENCE-ID`, end alignment (4), one bad `VEVENT` isolated, errors, caps
- `tests/ingestion/parsers/test_helpers.py` (148): `plain_text`, `http_url`, `derived_id`, `parse_iso`, all-day and overnight rules, every Windows zone, dispatch per method, a contained parser failure, every fixture × every parser, garbage × every parser

## Test Commands

```bash
make test-backend
make coverage-backend
cd backend && uv run pytest -q tests/ingestion/parsers --cov=apps.ingestion.parsers
```

## Coverage Details

| Module | Lines |
|--------|-------|
| `apps/ingestion/parsers/` (8 modules) | 100% |
| Overall | 98.69% |

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| The first hostile fixture embedded a raw `</script>` inside JSON-LD, which ended the block early (as browsers do), so the sanitizer was never exercised | Low | Fixed: the fixture escapes `</` the way real sites do. Sanitizing is now verified field by field. |
| Garbage-input test data used `os.urandom`, so it wasn't reproducible | Low | Fixed: seeded `random.Random("parsers")` |
| Code review: document-local JSON-LD `@id`s collided, overlong IDs exceeded the column, and duplicate IDs (an ICS override before its master) lost data | High | Fixed with your approval (3 fixes, 22 tests); see review-report.md |

## Ready for Completion

- [x] All tests passing (1315/1315, re-run after the code-review fixes)
- [x] Coverage target met (98.70% overall; 100% parsers and `domain/`)
- [x] All acceptance criteria validated
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-013*
