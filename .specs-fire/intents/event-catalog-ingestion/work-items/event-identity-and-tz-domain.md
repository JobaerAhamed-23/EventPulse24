---
id: event-identity-and-tz-domain
title: Event Identity & Timezone Domain Logic
intent: event-catalog-ingestion
complexity: medium
mode: confirm
status: pending
depends_on: []
created: 2026-10-28
---

# Work Item: Event Identity & Timezone Domain Logic

## Description

Build the pure, stdlib-only decision logic that ingestion relies on:

- Event Identity fingerprints and the three structural match rules (FR-15, AD-4)
- the ±30-day postponement rule
- timezone tier resolution with its confidence gates (FR-60, AD-6)

No Django and no I/O, so every rule is exhaustively unit-testable.

## Acceptance Criteria

- [ ] `domain/dedup.py` provides:
  - `title_fingerprint(title)`: normalized, stable token set
  - `venue_fingerprint(name, city)`
  - `jaccard(a, b)`
- [ ] A match function returns which rule matched, or none:
  1. Same `(source_id, source_event_id)`.
  2. Same `(venue_fingerprint, start_time_utc)` **and** title-fingerprint Jaccard ≥ 0.80.
  3. Same canonical URL.
- [ ] No embedding or cosine input exists anywhere in the API (AD-4).
- [ ] Recurring instances are never matched across different start times, and `series_id` never merges. In particular, rule (c) (same canonical URL) does not match two candidates whose start times differ when either carries a `series_id` (`catalog-data-model-design.md` D4).
- [ ] `series_id(source_id, series_key)` returns a deterministic `uuid5` (`catalog-data-model-design.md` D11).
- [ ] A postponement classifier takes the old and new UTC start: a move within ±30 days keeps the same `event_id`, and a move beyond it means "supersede".
- [ ] A change classifier compares the stored and incoming normalized fields. It returns the lifecycle kinds (time moved, cancelled, sold out, venue or detail change) and "no change".
- [ ] A timezone resolver:
  - **`full`**: an offset or IANA tz from the source gives confidence 1.0.
  - **`partial`**: no offset but a known venue resolves through the venue tz, with a computed confidence.
  - **`none`**: no tz and no venue means reject.
- [ ] The resolver applies the gates (`catalog-data-model-design.md` D6), inclusive at each lower bound. Thresholds come from `shared/constants.py` (`TZ_INFERENCE_CONFIDENCE_DIGEST = 0.70` and `TZ_INFERENCE_CONFIDENCE_AUTO_PUBLISH = 0.90`, added by `catalog-data-model`):
  - ≥0.90: publish, no flag. Exactly 0.90 auto-publishes.
  - 0.70–0.89: publish **and** flag `tz_review_pending` (still digest-eligible, FR-60).
  - <0.70 with a resolved tz: `in_review`, not digest-eligible until editorial review (AD-6).
  - no resolvable tz (`none` tier): reject.
- [ ] The resolver converts local time plus IANA tz to UTC with `zoneinfo`. DST gaps and folds are handled explicitly: the policy is documented and tested.
- [ ] `import-linter` `domain-pure` still passes, and the stdlib-only test still passes.
- [ ] Table-driven unit tests cover:
  - each match rule, positive and negative
  - Jaccard exactly at 0.80 and just below it
  - ±30 days exactly at the boundary
  - each timezone tier
  - a DST spring-forward gap and a fall-back fold
  - a non-existent IANA zone

## Technical Notes

- PRD FR-15 and FR-60. Spine AD-4 and AD-6.
- **Deferred here from the `catalog-data-model` design review:**
  - **Concurrent cross-source matching:** two sources ingesting the same happening at once could both miss each other and create two live Events. The domain exposes a deterministic **lock key** for a candidate (for example, a hash of `venue_fingerprint` and the UTC start date). `ingest-pipeline-and-lifecycle` takes a Postgres advisory lock on it around match-then-write.
  - **Rule (c) for a series with no `series_id`:** when a source exposes a recurring event as separate items sharing one URL but gives no series key, rule (c) must still not merge instances with different start times. Decide and test whether "same URL, different start" ever matches.
- **Haiku date-arithmetic risk (AD-8):** this is the reason the logic is deterministic code and not delegated to a model.
- **Fingerprint normalization** (case, punctuation, stop words, unicode NFKC) must be stable across versions. Changing it later changes identity, so document it.

## Dependencies

(none)
