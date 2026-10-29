---
id: run-eventpulse24-018
scope: single
work_items:
  - id: real-feeds-and-e2e-proof
    intent: event-catalog-ingestion
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
status: completed
started: 2026-10-28T15:37:15.026Z
completed: 2026-10-28T16:59:11.153Z
---

# Run: run-eventpulse24-018

## Scope
single (1 work item)

## Work Items
1. **real-feeds-and-e2e-proof** (confirm) — completed


## Current Item
(all completed)

## Files Created
- `backend/config/management/commands/seed_local_stack.py`: The idempotent seed command: proof sources, venues, the editorial group and the operator
- `backend/config/local_feeds.json`: The real MMFA feed set with its recorded robots/ToS note
- `backend/config/local_feeds.fixtures.json`: The CI feed set: one fixture per acquisition method
- `backend/tests/e2e/test_end_to_end.py`: The sixteen end-to-end tests: seed, tick, ingest, catalog API, tick again
- `backend/tests/e2e/conftest.py`: The broker and outbox seam recordings
- `backend/tests/e2e/mutation_probe_e2e.py`: Nine mutation probes proving the suite catches real bugs
- `backend/tests/e2e/__init__.py`: Makes tests/e2e a package so its conftest is scoped to it
- `backend/tests/ingestion/test_seed_local_stack.py`: The seed command own logic: duration parser, --list and the four refusals
- `backend/tests/fixtures/sources/events.jsonld.html`: The JSON-LD fixture: two plain events and a two-instance series

## Files Modified
- `backend/apps/ingestion/services/source_registry.py`: Added find_source_by_url, a published lookup so a client can find a source before registering a duplicate
- `backend/apps/ingestion/services/venue_registry.py`: Added find_venue, the same lookup by the venue fingerprint
- `backend/tests/fixtures/sources/index.json`: Registered the JSON-LD fixture URL for the fake fetch adapter
- `README.md`: The new Local ingestion section: seeding, triggering, reading, the fetch adapter and the manual real-feed run

## Decisions
- **Which real feeds**: The MMFA JSON-LD page and its iCal feed (Both are the publisher own public listings; robots allows them and the crawl delay is honoured)
- **Which real methods**: JSON-LD and ICS, not RSS (MMFA WordPress feeds return 500 and every reachable robots-clear RSS feed lacks the ev: namespace the parser requires; the fixture set still covers all three)
- **How the feed data is stored**: Two committed JSON files, one per feed set (The ToS/robots note and the cadence travel with the feed instead of living in prose)
- **How the editorial group permissions are named**: Derived from ContentType at run time (A hard-coded codename breaks when a model is renamed; deriving it also lets the command refuse a half-migrated database)
- **Assigned or appended**: Assigned with permissions.set (A stale grant must not survive; the test proves the next run removes one added by hand)
- **The local operator rights**: Staff, in the editorial group, never superuser (AD-14 and plan decision D2; the command demotes it if something else made it a superuser)
- **How the second tick is forced**: Backdate last_attempted_at (Without it the nothing-changed assertion would pass vacuously)
- **Whether CI touches the network**: Never (The fake fetch adapter is the default; the real run is a documented manual step with SOURCE_FETCH=http)


## Summary

- Work items completed: 1
- Files created: 9
- Files modified: 4
- Tests added: 37
- Coverage: 99.08%
- Completed: 2026-10-28T16:59:11.153Z
