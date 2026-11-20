---
id: timeline-why-this-tag
title: The Timeline block's Why-this tag — deferred, with the reason
intent: traceability-gap-closure
complexity: high
mode: validate
status: completed
depends_on:
  - timeline-hover-detail
created: 2026-11-17
run_id: run-eventpulse24-046
completed_at: 2026-11-19T15:02:43.066Z
---

# Work Item: The Timeline block's Why-this tag — deferred, with the reason

## Description

`EXPERIENCE.md` §13 line 1107 says a desktop Timeline event-block adds **location and one
Why-this Tag** on hover or focus. `timeline-block-detail-contract` and
`timeline-hover-detail` deliver the location. **This is the tag, split off deliberately on
2026-11-17 rather than dropped**, so that a later reader finds a decision instead of a
half-built spec.

**Why it is not a small addition.** Three findings from reading the code:

1. **There is no persisted tag the Timeline may read.** The two explanation kinds are
   `EventFit.tags` (per `(event, city)`, on `catalog`, owned by `ingestion`) and the
   Relevance Pulse's tags (per user per day, on `personal`, written at digest
   composition). A saved event in a given week may have no digest card at all, so there is
   nothing stored to look up.
2. **`personalization` is forbidden from reaching the Event Fit.** The import-linter
   contract *"AD-10 personalization never reaches the Event Fit"* bans
   `apps.ingestion.event_fit` from `apps.personalization`, and the Timeline lives in
   `personalization`. This is not a lint technicality: AD-10 exists because showing one
   explanation kind in place of the other is the trust-collapse failure PRD Risk 11 calls
   company-ending.
3. **So the tag must be computed per user, the way Browse computes it** — `why_this_tags`
   over `RankingInputs`. Browse assembles those from the user's chip keys, their city,
   their source visibility and their muted categories, plus `chip_keys` on each candidate
   — which `PublicEvent` (what the Timeline's catalog read returns) does not carry.

**The cost is the point of the deferral.** The Timeline is a deliberately cheap read: its
page docstring says it *"buckets nothing, sorts nothing, and decides no conflict"*, and the
server hands it a week it renders as-is. Adding four reads and a per-block ranking
assembly to reveal one word on hover changes what that surface *is*, and that is a decision
worth taking on purpose rather than inside a hover-state work item.

## Acceptance Criteria

- [ ] A decision is recorded before any code: either build the per-user tag, or amend `EXPERIENCE.md` §13 to say the Timeline block reveals location only, and why.
- [ ] **If built:** the tag is the **Relevance Pulse** kind, computed with `why_this_tags` from the user's own inputs — never the Event Fit, and never a tag invented for this surface.
- [ ] **If built:** the week read does not become N+1; the extra inputs are batched the way `get_public_events` already batches the catalog lookup.
- [ ] **If built:** a personal block still shows no tag, and a block whose catalog event is gone shows none.
- [ ] **If amended:** §13's line is changed in place with an Amendment ID, and TRACEABILITY.md's O-2 is updated to say the shortfall is now the spec's position rather than a gap.

## Technical Notes

**`mode: validate` and `complexity: high` are deliberate.** Not because the code is large,
but because the decision is architectural: it is about whether a read-only surface starts
ranking. That wants a design doc and two checkpoints, not an autopilot run.

**Read `domain/ranking.py:478` (`why_this_tags`) and
`apps/personalization/services/browse_read.py:295-380` first.** Browse is the worked
example of doing this correctly, including the source-visibility and muted-category rules
that Browse and the Digest share so they cannot drift. Any Timeline implementation must
read the same helpers for the same reason.

## Dependencies

- timeline-hover-detail (the reveal must exist before a second thing is revealed in it)
