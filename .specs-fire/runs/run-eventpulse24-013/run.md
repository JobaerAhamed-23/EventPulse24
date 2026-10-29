---
id: run-eventpulse24-013
scope: single
work_items:
  - id: structured-parsers
    intent: event-catalog-ingestion
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
status: completed
started: 2026-10-28T10:14:25.622Z
completed: 2026-10-28T10:41:48.650Z
---

# Run: run-eventpulse24-013

## Scope
single (1 work item)

## Work Items
1. **structured-parsers** (confirm) — completed


## Current Item
(all completed)

## Files Created
- `backend/apps/ingestion/parsers/__init__.py`: parse() dispatcher by acquisition method; never raises
- `backend/apps/ingestion/parsers/types.py`: SourceContext, ParsedCandidate, StatusHint, ParseResult (one candidate per id), limits
- `backend/apps/ingestion/parsers/text.py`: plain_text, http_url, item_id, absolute_iri, derived_id
- `backend/apps/ingestion/parsers/times.py`: parse_iso, all-day span, overnight roll
- `backend/apps/ingestion/parsers/jsonld.py`: schema.org Events from ld+json blocks; EventSeries
- `backend/apps/ingestion/parsers/feeds.py`: RSS 2.0/Atom via defusedxml; ev:/xCal times only
- `backend/apps/ingestion/parsers/ics.py`: VEVENTs via icalendar; times as written; overrides win
- `backend/apps/ingestion/parsers/windows_zones.py`: Windows -> IANA zone table
- `backend/tests/ingestion/parsers/__init__.py`: Parser tests
- `backend/tests/ingestion/parsers/test_jsonld.py`: Parser tests
- `backend/tests/ingestion/parsers/test_feeds.py`: Parser tests
- `backend/tests/ingestion/parsers/test_ics.py`: Parser tests
- `backend/tests/ingestion/parsers/test_helpers.py`: Parser tests
- `backend/tests/fixtures/sources/venue-events.html`: Parser fixture
- `backend/tests/fixtures/sources/broken-jsonld.html`: Parser fixture
- `backend/tests/fixtures/sources/events.rss`: Parser fixture
- `backend/tests/fixtures/sources/events.atom`: Parser fixture
- `backend/tests/fixtures/sources/broken.rss`: Parser fixture
- `backend/tests/fixtures/sources/calendar.ics`: Parser fixture
- `backend/tests/fixtures/sources/broken.ics`: Parser fixture
- `backend/tests/fixtures/sources/hostile.html`: Parser fixture

## Files Modified
- `backend/pyproject.toml`: icalendar==7.3.0, defusedxml==0.7.1
- `backend/uv.lock`: Locked icalendar and defusedxml (tzdata stays 2026.5)
- `backend/tests/fixtures/sources/index.json`: Fake-adapter entries for the new fixtures
- `.specs-fire/standards/tech-stack.md`: icalendar and defusedxml
- `.specs-fire/standards/coding-standards.md`: Parser purity and as-written times
- `.specs-fire/intents/event-catalog-ingestion/work-items/ingest-pipeline-and-lifecycle.md`: Parsing ACs handed on

## Decisions
- **ICS library**: icalendar 7.3.0 (Maintained RFC 5545 parser; keeps TZID as written)
- **Feed parsing**: defusedxml + ElementTree, own RSS/Atom reading (Untrusted XML; no feedparser sanitizer to bypass)
- **RSS event start**: ev:/xCal only, never pubDate (A publication time is not an event time (FR-60))
- **Times**: As written; end aligned to the start's representation (The domain resolver decides UTC and tier)
- **IDs**: Absolute IRIs or native ids, hashed when over 512; derived otherwise; one candidate per id (Rule (a) must never merge distinct events (review fixes))
- **Review**: 3 identity fixes applied (User approved)


## Summary

- Work items completed: 1
- Files created: 21
- Files modified: 6
- Tests added: 281
- Coverage: 98.71%
- Completed: 2026-10-28T10:41:48.650Z
