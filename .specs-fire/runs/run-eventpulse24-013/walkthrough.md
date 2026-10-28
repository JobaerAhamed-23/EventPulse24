---
run: run-eventpulse24-013
work_item: structured-parsers
intent: event-catalog-ingestion
generated: 2026-10-28
mode: confirm
---

# Implementation Walkthrough: Structured Source Parsers (JSON-LD, RSS, ICS)

## Summary

Fetched bytes can now be turned into event candidates without an LLM. `apps.ingestion.parsers.parse(method, content, context)` reads:

- JSON-LD in HTML pages
- RSS 2.0 and Atom feeds that carry explicit event times
- ICS calendars (and, later, emailed ICS attachments)

It returns `ParsedCandidate`s with every time **exactly as written**, plus counted skip reasons. It never raises.

Text is stripped to plain text and URLs are restricted to http(s). XML bombs and external entities are refused. Item IDs are guaranteed unique per document, stable, non-empty and short enough for the column.

## Structure Overview

```text
 fetch (run 012) ──bytes──► parse(method, content, SourceContext(source_id, final_url))
                              │ jsonld ─► jsonld.parse_jsonld   (html.parser → ld+json → schema.org Events)
                              │ rss    ─► feeds.parse_feed      (defusedxml → RSS 2.0 / Atom, ev:/xCal times)
                              │ ics, email_ics ─► ics.parse_ics (icalendar → VEVENTs, Windows TZIDs → IANA)
                              ▼
                 ParseResult(candidates, skipped Counter, error)   ← never raises
                   ParsedCandidate: start (naive | fixed offset), start_zone, start_raw, end,
                                    title/description (plain text), canonical_url (http(s)),
                                    venue name/city/country, status, sold_out, series_id, raw
                              ▼
 pipeline (item 6) ─► domain.timezones.resolve_tz · domain.dedup fingerprints/resolve · catalog writes
```

## Architecture

### Pattern Used

A functional core inside the owning app. The parsers are pure functions with no database, network or LLM, so they can be tested exhaustively and reused (the mailbox path calls `parse_ics` with attachment bytes). They own only format reading and two normalizations: all-day spans and overnight ends. Timezones and identity remain the domain's decisions (run 011).

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `apps/ingestion/parsers/__init__.py` | `parse()` dispatcher; contains any parser failure |
| `apps/ingestion/parsers/types.py` | `SourceContext`, `ParsedCandidate`, `StatusHint`, `ParseResult`, field limits |
| `apps/ingestion/parsers/text.py` | `plain_text`, `http_url`, `item_id`, `absolute_iri`, `derived_id` |
| `apps/ingestion/parsers/times.py` | `parse_iso`, `all_day_span`, `roll_overnight` |
| `apps/ingestion/parsers/jsonld.py` | JSON-LD / schema.org parser |
| `apps/ingestion/parsers/feeds.py` | RSS / Atom parser |
| `apps/ingestion/parsers/ics.py` | ICS parser |
| `apps/ingestion/parsers/windows_zones.py` | 50 Windows → IANA mappings |
| `tests/ingestion/parsers/` (4 modules) | 273 tests |
| `tests/fixtures/sources/` (8 files) | Valid, broken and hostile fixtures for each format |

### Modified

| File | Changes |
|------|---------|
| `backend/pyproject.toml`, `uv.lock` | `icalendar==7.3.0`, `defusedxml==0.7.1` (`tzdata` stays 2026.5) |
| `tests/fixtures/sources/index.json` | Fake-adapter entries for every new fixture |
| Standards; item 6 | Libraries; parser rules; handed-on parsing ACs |

## Domain Model

### Value Objects

| Value Object | Properties | Constraints |
|--------------|------------|-------------|
| `ParsedCandidate` | ID, title, URL, start / `start_zone` / `start_raw`, end, all-day flag, venue, description, status, sold out, `series_id`, `raw` | The ID is never empty and at most 512 characters. Text is plain and capped. The URL is absolute http(s) or empty. The end is in the start's representation. |
| `ParseResult` | candidates, skipped (a Counter), error | One candidate per ID. A higher priority (an ICS override) replaces; an equal-priority repeat is counted. |

## Key Implementation Details

### 1. Times exactly as written

| Source writes | Candidate gets |
|---|---|
| Naive time (no zone) | Naive `start` |
| Fixed offset | Aware `start` with that offset |
| `Z` | Aware UTC `start` |
| ICS `TZID` | Naive wall-clock `start` plus `start_zone`, with Windows names mapped to IANA |
| Date only | Local midnight, `all_day`, and an exclusive next-midnight end |

An ICS `DTEND` written in a different form (for example `Z` under a `TZID` start) is converted into the **start's** representation, because `resolve_tz` reads both in the same frame. Overnight ends roll forward one day; an end more than a day before its start is dropped and counted.

### 2. Item IDs that never merge distinct events

| Source | ID used |
|---|---|
| Native ID: `guid`, Atom `id`, or a JSON-LD `@id` that is an **absolute IRI** | The ID itself |
| ICS series member | `ics_item_id(UID, instance UTC)` |
| No usable ID | `derived:` hash of (URL, title, start as written) |

- Blank-node and fragment `@id`s (`_:b0`, `#event`) are treated as missing, because they are local to one document.
- IDs over 512 characters become `long:` + sha256.
- `ParseResult.add` keeps one candidate per ID, and an ICS override always beats its master's instance, whatever the file order.

### 3. Untrusted input

- **HTML** is only scanned for `ld+json` scripts, never rendered.
- **XML** goes through defusedxml, which refuses entity declarations and external entities, while a plain DTD reference (RSS 0.91) is accepted without being fetched.
- **Text** has `<script>`, `<style>`, `<template>` and `<noscript>` content dropped, entities decoded, control characters removed and lengths capped.
- **URLs** must be http(s) and at most 2,048 characters.
- **Items** are capped at 5,000 per document.

### 4. No guessed event times

An RSS or Atom item's start comes only from `ev:startdate` or `xcal:dtstart`. `pubDate` and `updated` are never used. Generic news feeds yield nothing, visibly, with `skipped["no_event_start"]`.

## Security Considerations

| Concern | Approach |
|---------|----------|
| XML bombs and XXE | defusedxml refuses them (tested: billion laughs, `file:///etc/passwd`) |
| Script and HTML injection | Markup stripped, script and style content dropped (tested: `hostile.html`) |
| `javascript:` / `data:` URLs | Dropped by `http_url` |
| Resource exhaustion | Caps on items, title, description and venue fields; parsers can't raise |
| Wrong-time events | No `pubDate` fallback; times as written; the domain decides the tier |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| ICS library | icalendar 7.3.0 | A maintained RFC 5545 parser that keeps the raw `TZID` |
| Feed parsing | defusedxml + ElementTree | Untrusted XML; fewer dependencies than feedparser |
| RSS start | `ev:` / xCal only | A publication time is not an event time |
| Times | As written, with the end aligned | The domain decides UTC and tier |
| IDs | Absolute IRIs or native IDs, hashed if long, else derived; one per document | Rule (a) must never merge distinct events |

## Deviations from Plan

- **Code review** (3 fixes, approved by you): blank-node and fragment `@id`s now use derived IDs; IDs over 512 characters are hashed; `ParseResult.add` keeps one candidate per ID, with ICS overrides winning. As a result, `calendar.ics` yields **8** candidates, not 9: the first-week override replaces its master's instance.
- **Hostile fixture:** regenerated with `<\/` escaping, as real sites do. The first version ended its own script block early, so it never exercised the sanitizer.

## Dependencies Added

| Package | Why Needed |
|---------|------------|
| `icalendar==7.3.0` (pulls in `python-dateutil`) | ICS parsing |
| `defusedxml==0.7.1` | Safe parsing of untrusted XML feeds |

## How to Verify

1. **Run the parser tests**
   ```bash
   cd backend && uv run pytest -q tests/ingestion/parsers --cov=apps.ingestion.parsers
   ```
   Expected: 273 passed, 100% coverage.

2. **Run all the gates**
   ```bash
   make lint-backend && make coverage-backend
   ```
   Expected: 13 contracts kept, 1315 passed, 98.71% overall.

3. **Parse a fixture by hand**
   ```bash
   cd backend && uv run python -c "import uuid,pathlib; from apps.ingestion.parsers import parse, SourceContext; r = parse('ics', pathlib.Path('tests/fixtures/sources/calendar.ics').read_bytes(), SourceContext(uuid.uuid4(), 'https://x.test/')); print(len(r.candidates), dict(r.skipped)); print(r.candidates[0])"
   ```
   Expected: `8 {'no_event_start': 1}`, and a Book Club candidate with a naive 19:30 start and `start_zone='America/New_York'`.

## Test Coverage

- Tests added: 281 (273 parser tests plus 8 generated architecture checks). The suite went from 1034 to 1315.
- Coverage: 98.71% overall, 100% `apps/ingestion/parsers/`, 100% `domain/`.
- Status: all passing

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing
- [x] No critical issues
- [x] Documentation updated: tech stack, coding standards, item 6 ACs
- [x] Developer notes captured

## Developer Notes

- **Pass `fetch_result.final_url`** as `SourceContext.source_url`. Relative links resolve against it.
- **The parsers never return UTC.** Always call `resolve_tz(c.start, source_zone=c.start_zone, venue_tz=…, end=c.end)`.
- **ICS overrides replace their master's instance** inside one parse. Across parses, the same `ics_item_id` makes the pipeline update that one source item.
- **Adding a format:** write `parse_x(content, context) -> ParseResult`, use `result.add()`, never `candidates.append`, register it in `PARSERS`, and add fixtures to `test_every_fixture_through_every_parser_never_raises`.
- **New fixtures** belong in `tests/fixtures/sources/index.json` too, so the fake fetch adapter serves them to pipeline tests.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-013*
