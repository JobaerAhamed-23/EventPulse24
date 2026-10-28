---
id: run-eventpulse24-011
scope: single
work_items:
  - id: event-identity-and-tz-domain
    intent: event-catalog-ingestion
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
status: completed
started: 2026-10-28T08:13:45.603Z
completed: 2026-10-28T09:14:37.195Z
---

# Run: run-eventpulse24-011

## Scope
single (1 work item)

## Work Items
1. **event-identity-and-tz-domain** (confirm) — completed


## Current Item
(all completed)

## Files Created
- `backend/domain/confidence.py`: tz_gate, extraction_gate, combine_gates over two-decimal Decimals
- `backend/domain/timezones.py`: canonical_zone, FR-60 tier resolution (rows A1-C2), DST detection and caps, end time, derived start_time_local
- `backend/domain/dedup.py`: Versioned fingerprints, canonical_url, Jaccard, rules (a)/(b)/(c), resolve(), identity_lock_keys, ics_item_id
- `backend/domain/lifecycle.py`: ±30 days from the original start; change classifier with precedence and multiple kinds
- `backend/tests/domain/test_confidence.py`: Gate boundaries and input validation
- `backend/tests/domain/test_timezones.py`: Every table row, DST, zones, end time, round trip
- `backend/tests/domain/test_dedup.py`: Golden fingerprints, URLs, rules, resolve, lock keys
- `backend/tests/domain/test_lifecycle.py`: Time moves and change kinds
- `backend/tests/domain/test_domain_api.py`: AD-4: no embedding or similarity inputs in the domain API
- `backend/tests/ingestion/test_domain_parity.py`: Domain lifecycle facts and change kinds stay in step with the model

## Files Modified
- `backend/domain/errors.py`: InvalidTimezoneError(ValidationError), code invalid_timezone
- `backend/shared/constants.py`: TITLE_JACCARD_MIN, POSTPONEMENT_WINDOW, tz scores and DST caps (Decimal)
- `backend/config/apps.py`: zoneinfo.reset_tzpath(to=()) and clear_cache in ready()
- `backend/pyproject.toml`: Direct dependency tzdata==2026.5
- `backend/uv.lock`: tzdata locked as a direct dependency
- `backend/tests/shared/test_constants.py`: Thresholds; every score and cap in its gate band
- `backend/tests/config/test_project.py`: TZPATH is empty and tzdata is IANA 2026e
- `.specs-fire/standards/coding-standards.md`: Where identity and tz decisions live; fingerprint versioning; Decimal confidences; canonical zones
- `.specs-fire/standards/tech-stack.md`: tzdata pin
- `.specs-fire/intents/event-catalog-ingestion/work-items/catalog-data-model-design.md`: Amendments from run 011 (D8, D14, D4)
- `.specs-fire/intents/event-catalog-ingestion/work-items/structured-parsers.md`: ACs: ics_item_id, Windows zone names, times as written
- `.specs-fire/intents/event-catalog-ingestion/work-items/ingest-pipeline-and-lifecycle.md`: ACs: original start, advisory locks, binding-based rule (a), one state change per kind, combined gates

## Decisions
- **Rule (c)**: Same normalized URL and same instant; never against an Event bound from the candidate's source (P1: recurring instances can never merge, with or without a series_id)
- **Offset-only times**: UTC instants absolute; whole-hour offsets map to Etc/GMT±N at 0.85 (flagged); others rejected (P2 as revised: AD-6 IANA names only, but visible to a human)
- **Conflicting tz claims**: The more specific claim sets the instant; confidence 0.60 (in_review) (Wrong-time events are the class FR-60 prevents)
- **start_time_local**: Derived from start_utc and the zone (Always converts back; the as-written text stays in payload (amends D8))
- **Timezone database**: tzdata==2026.5 only (reset_tzpath) (Dev, CI and production compute the same instants)
- **Review suggestions**: All 3 applied: zone aliases, unreserved escapes, IPv6 brackets (User approved)


## Summary

- Work items completed: 1
- Files created: 10
- Files modified: 12
- Tests added: 266
- Coverage: 98.16%
- Completed: 2026-10-28T09:14:37.195Z
