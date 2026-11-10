---
id: review-intake-and-backfill
title: Nothing stuck in review without a ticket — intake and backfill
intent: trust-loop
complexity: medium
mode: confirm
status: pending
depends_on:
  - review-queue-model
created: 2026-11-10
---

# Work Item: Nothing stuck in review without a ticket — intake and backfill

## Description

`domain/confidence.py` already sends an event with `tz_inference_confidence < 0.70` to `Gate.IN_REVIEW`, and ingestion stores it with `publication_status = in_review`. The docstring promises "never in a digest until editorial review", and no review exists, so these events are stranded today. This item makes every entry into `in_review` raise a `ReviewItem`, and it backfills the events already stuck.

## Acceptance Criteria

- [ ] Every path that writes or moves an event into `in_review` (`ingest_item.py`'s create and update paths) calls `raise_review_item(event, reason=in_review)` **in the same catalog transaction**. An event in `in_review` without an open item is an invariant violation.
- [ ] The confidence-below-0.7 extraction gate is wired through the same call, so FR-14's LLM path inherits the queue at no cost. A test drives it with a synthetic low-confidence `IncomingEvent`, because structured ingestion always writes `1.00`.
- [ ] **Backfill:** a management command, or a data migration (the plan decides which), raises an item for every existing `in_review` event that lacks one. It is idempotent: a second run raises nothing.
- [ ] An event leaving `in_review` by any route other than an editorial resolution (for example, superseded) closes or orphans its item in a defined way. The plan states which way and a test pins it.
- [ ] **Settles one open question from the brief:** events that are *published but flagged* (`Gate.PUBLISH_FLAGGED`, `tz_review_pending`) either raise a low-priority item or stay out of the queue. The plan proposes one choice for confirmation, and a test pins it.
- [ ] Tests cover:
  - the in-transaction invariant, using a probe that fails if the raise is moved outside the transaction
  - the backfill's idempotence
  - the low-extraction-confidence path
  - the flagged-event decision

## Technical Notes

`apps/ingestion/services/ingest_item.py:44` maps `Gate.IN_REVIEW` to `(IN_REVIEW, False)`, and `:212` already appends an `in_review` flag. Those are the two touch points.

## Dependencies

- review-queue-model
