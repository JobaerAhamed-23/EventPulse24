---
id: reliability-recompute-and-escalation
title: The score that remembers — history, weekly recompute, and escalation
intent: trust-loop
complexity: high
mode: validate
status: pending
depends_on:
  - editorial-review-commands
  - event-report-api
  - reliability-score-domain
created: 2026-11-10
---

# Work Item: The score that remembers — history, weekly recompute, and escalation

## Description

FR-16's score is updated "at least weekly", and its spike rule compares this week with last week. A single field on `Source` cannot answer "what was it last week?", so the score needs a history. `SourceReliabilityScore` is a PRD Glossary term, and the Spine's naming row lists it verbatim. This item persists the score, defines which facts count as observations, recomputes on a schedule, and escalates through the queue.

## Acceptance Criteria

- [ ] **`SourceReliabilityScore`** lives in `catalog`, owned by `ingestion`. It is one row per (source, computation), with the score, the positive and negative counts, and the computed-at timestamp, and it is append-only. The current score is readable cheaply, through a denormalised field on `Source` or a latest-row read, as the design decides. A source with no row reads as the 0.50 prior.
- [ ] **What counts as an observation is decided and written down:**
  - an editorial **reject**: negative
  - an **approve**: positive
  - an **edit**: the design decides. It is arguably negative, since the source was wrong.
  - a **user report**: counts only when **upheld**. The design defines "upheld", for example a report on an event the editor then rejected or edited, and specifies how one editorial verdict on an event with five reports is counted: once or five times. Several reports must not multiply one verdict.
  - **dismissals (FR-25)**: a named, unimplemented input.
- [ ] **A recompute job** is enqueued from the existing `worker.tasks.tick` (`config/celery.py` has no django-celery-beat, and the schedule lives in Postgres), so every source is recomputed at least weekly. It is idempotent within a period: a re-run writes no duplicate row. It uses only the `reliability-score-domain` functions.
- [ ] **Escalation:** when `should_escalate` or `is_spike` is true, the job calls `raise_review_item(source, reason=source_reliability)`. A source that is already escalated is bumped, not duplicated.
- [ ] **Never removal (FR-16):** no path in this item pauses, hides or deprioritises ingestion of a source. A test asserts the source's status and ingestion schedule are unchanged after an escalation.
- [ ] Tests cover:
  - the observation counting for each verdict, including the five-reports-one-verdict case
  - recompute idempotence
  - the weekly guarantee: a source not recomputed for 7 days is due
  - escalation on the low-score path and on the spike path
  - no duplicate escalation
  - the never-removal assertion

## Technical Notes

High complexity, so this item gets a design doc. The cross-database question matters: report facts live in `personal`, and the score lives in `catalog`. AD-3 forbids `ingestion` reading `personal`. Either the report's verdict-relevant facts reach `catalog` when the `ReviewItem` is bumped (counts only, no identity), or the observation is recorded at **resolution time** by `editorial-review-commands` from the item's own tallies. The second option keeps the job single-database. The design must pick one and show that it holds the wall.

## Dependencies

- editorial-review-commands
- event-report-api
- reliability-score-domain
