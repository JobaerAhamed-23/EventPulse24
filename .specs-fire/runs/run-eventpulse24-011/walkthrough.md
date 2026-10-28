---
run: run-eventpulse24-011
work_item: event-identity-and-tz-domain
intent: event-catalog-ingestion
generated: 2026-10-28
mode: confirm
---

# Implementation Walkthrough: Event Identity & Timezone Domain Logic

## Summary

The decisions ingestion depends on now exist as pure, stdlib-only code in `backend/domain/`, with 100% coverage. The four questions are:

- **Is this candidate an existing Event?** Rules (a), (b) and (c), with `resolve()`.
- **When does it happen, and how sure are we?** The FR-60 timezone tiers, with a DST policy.
- **What changed since last time?** The change kinds, and ±30 days from the original start.
- **May it be published?** The tz and extraction gates.

Nothing calls these yet. The parsers (item 4) and the pipeline (item 6) are the callers, and the ACs they must meet were written into those work items.

## Structure Overview

```text
 parsers (item 4) ── times as written, zone names, URLs ──┐
                                                           ▼
 domain/timezones.resolve_tz ─► TzResolution(zone, start_utc, end_utc, local, confidence)
                                    │                         or TzRejection(reason)
                                    ▼
 domain/dedup ─ fingerprints · canonical_url ─► Candidate ─► resolve(candidate, bound_event_id,
                                                              live events) ─► New | Matched | Ambiguous
                identity_lock_keys(candidate) ─► pg_advisory_xact_lock (item 6)
 domain/lifecycle.classify_change(stored, incoming, original_start) ─► Change(kinds, fields, is_lifecycle)
 domain/confidence.combine_gates(tz_gate, extraction_gate) ─► publish | flagged | in_review | reject
```

## Architecture

### Pattern Used

A functional core (AD-2): frozen dataclasses in, frozen dataclasses out. There is no ORM, no I/O and no Django. Thresholds, scores and caps live once, in `shared/constants.py`. The import contracts and the stdlib-only checks enforce this, and the 100% `domain/` coverage gate holds it.

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `backend/domain/confidence.py` | `Gate`, `tz_gate`, `extraction_gate`, `combine_gates`, `checked_confidence` |
| `backend/domain/timezones.py` | `canonical_zone`, `offset_zone`, `read_wall_clock` (DST), `resolve_tz` |
| `backend/domain/dedup.py` | Fingerprints, `canonical_url`, `jaccard`, `match`/`resolve`, `identity_lock_keys`, `ics_item_id` |
| `backend/domain/lifecycle.py` | `classify_time_move`, `classify_change`, `EventFacts`, `ChangeKind` |
| `backend/tests/domain/test_*.py` (5 files) | 256 unit tests, with golden values pinned |
| `backend/tests/ingestion/test_domain_parity.py` | Domain ↔ model parity |

### Modified

| File | Changes |
|------|---------|
| `backend/domain/errors.py` | `InvalidTimezoneError` |
| `backend/shared/constants.py` | `TITLE_JACCARD_MIN`, `POSTPONEMENT_WINDOW`, tz scores and caps |
| `backend/config/apps.py` | Pinned tz database only |
| `backend/pyproject.toml`, `uv.lock` | `tzdata==2026.5` |
| Standards, design doc, items 4 and 6 | Conventions, amendments, handed-on ACs |

## Domain Model

### Value Objects

| Value Object | Properties | Constraints |
|--------------|------------|-------------|
| `TzResolution` | tier, zone, start_utc, end_utc, start_time_local, confidence, reason | Zone is canonical. `start_time_local` + zone always converts back to `start_utc`. Confidence is a two-decimal `Decimal`. |
| `Candidate` / `LiveEvent` | identity values (+ `bound_source_ids`, `superseded`) | Instants are compared in UTC, at whole seconds |
| `New` / `Matched` / `Ambiguous` | resolution outcome (+ `review_signals`) | Never auto-merges more than one Event |
| `EventFacts` / `Change` | the facts compared, and the kinds ordered by precedence | A superseded Event is rejected as input |

## Key Implementation Details

### 1. Rule (a) wins, and comes from the binding

`resolve()` takes the `ExtractedRecord` binding (`bound_event_id`), never an Event's origin fields. A bound item stays bound, and any (b)/(c) hits on other Events become `review_signals`, not `Ambiguous`. That avoids unbinding a resolved item.

### 2. Conservative cross-source matching

Rules (b) and (c) both require the **same instant** and never touch an Event that already has an item from the candidate's source. Recurring instances and multi-room venue feeds can't merge. The cost is that some true duplicates stay separate until the review queue exists.

### 3. The timezone table

Explicit claims beat inferred ones, and conflicts go to review at 0.60. UTC instants are absolute. Fixed offsets are allowed only as `Etc/GMT±N` and are flagged at 0.85. DST caps (fold 0.80, gap 0.65) apply only to naive times. The end time follows the start's policy.

### 4. Fingerprints are versioned and multilingual

The fingerprint steps are NFKC and casefold, then accent folding for Latin, Greek and Cyrillic only, then words built by Unicode category (marks stay with their letters), then bigrams for unspaced scripts. The stored form keeps content and stop words separately, which makes the stop-word fallback symmetric.

### 5. Lock keys are stable across processes

The keys use blake2b with a personalization string (`hash()` is salted per process), skip empty parts, and come back sorted. Item 6 commits one transaction per item.

## Security Considerations

| Concern | Approach |
|---------|----------|
| Credentials in source URLs | `canonical_url` drops userinfo |
| Hostile zone names (`../etc/passwd`, `localtime`) | `canonical_zone` allows only IANA areas, `Etc/GMT±N` and `UTC`, and catches every zoneinfo error |
| Hostile or huge titles | Tokens are capped at 64 characters and the fingerprint at 512 |
| Malformed URLs | Every `urlsplit`, `.port` and IDNA failure gives `""`, which never matches |

## Performance Considerations

| Requirement | Implementation |
|-------------|----------------|
| Candidate lookup | The domain receives only the Events found through the existing indexes (rule b: venue + instant; rule c: URL) |
| Determinism | `Fraction` Jaccard, `Decimal` gates, sorted tokens, pinned tzdata |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Rule (c) | Same URL and same instant; never within one source | P1: recurring instances can never merge |
| Offset-only times | `Etc/GMT±N` at 0.85, or reject | P2 (revised): IANA names only, kept visible to a human |
| Conflicting claims | The more specific claim sets the instant; 0.60, `in_review` | FR-60's wrong-time class |
| `start_time_local` | Derived from the instant | Always converts back (amends D8) |
| Timezone database | `tzdata==2026.5` only | Same instants everywhere |
| Review | 3 suggestions applied | You approved |

## Deviations from Plan

The plan's eight departures were approved at the checkpoint and recorded in the design doc and work items. During execution:

- **Tokenizer:** Thai and Indic words were being split at their vowel marks by a `\w` regex. It now tokenizes by Unicode category, with golden tests.
- **Code review:** 3 fixes, approved by you:
  - zone aliases are no longer a change
  - percent-escaped unreserved characters in URLs are decoded
  - IPv6 hosts keep their brackets

## Dependencies Added

| Package | Why Needed |
|---------|------------|
| `tzdata==2026.5` (runtime, now direct) | The only timezone database, so every environment computes the same instants. It was already installed transitively via kombu. |

## How to Verify

1. **Run the domain tests**
   ```bash
   cd backend && uv run pytest -q tests/domain
   ```
   Expected: all pass. No database is needed, and Django is configured only by pytest-django.

2. **Run all the gates**
   ```bash
   make lint-backend && make coverage-backend
   ```
   Expected: 12 contracts kept, 845 passed, 98.16% overall and 100% `domain/`.

3. **Try it by hand**
   ```bash
   cd backend && uv run python -c "from datetime import datetime; from domain.timezones import resolve_tz; print(resolve_tz(datetime(2026,3,8,2,30), venue_tz='America/New_York'))"
   ```
   Expected: `reason='C1'`, `confidence=Decimal('0.65')` (the DST gap), `start_time_local='2026-03-08T03:30:00'`.

## Test Coverage

- Tests added: 266. The suite went from 579 to 845.
- Coverage: 98.16% overall, 100% for `domain/` (457 statements).
- Status: all passing

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing
- [x] No critical issues
- [x] Documentation updated: standards, design amendments, handed-on ACs
- [x] Developer notes captured

## Developer Notes

- **Don't edit v1 fingerprints.** Any change to tokenization, folding or hashing means a `v2` and a backfill. The golden tests fail otherwise, on purpose.
- **Confidence values are Decimals.** `tz_gate(0.7)` raises `TypeError` by design.
- **`resolve_tz` raises on a bad venue tz** (`InvalidTimezoneError`). Validate venue zones with `canonical_zone` on write (item 5's `register_venue`).
- **`classify_change` returns several kinds.** Item 6 appends one state change per kind, each bumping `event_version` by 1. `REINSTATED` has no model choice yet; the parity test fails until item 6 decides.
- **Supply the original start.** `classify_change` needs it, not the current start (an AC on item 6).
- **Outside Django** (a script), call `zoneinfo.reset_tzpath(to=())` yourself if you need the pinned database. `ConfigConfig.ready()` does it for every Django process.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-011*
