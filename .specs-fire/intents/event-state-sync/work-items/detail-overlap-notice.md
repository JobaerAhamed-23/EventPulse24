---
id: detail-overlap-notice
title: Someone else moved the event and now it clashes — the calm overlap notice
intent: event-state-sync
complexity: medium
mode: confirm
status: in_progress
depends_on:
  - saved-event-lifecycle-state
created: 2026-11-04
---

# Work Item: Someone else moved the event and now it clashes — the calm overlap notice

## Description

FR-55: *"A postponed event that conflicts with another saved event: user is notified; the system surfaces a calm 'this overlaps with [other event]' message in the Detail Screen."*

TRACEABILITY.md marks FR-55 as an **inferred-only design gap**, assuming FR-58's conflict prompt covers it. It does not. FR-58's prompt is a forced choice — three actions, no dismiss, no X, and the flow cannot complete until one is chosen — because the user is *creating* the conflict and can still not create it. A conflict that arrives because a venue moved a date is not the user's doing and there is nothing for them to decline. Interrupting them with a modal they cannot meaningfully answer is the wrong register for a product whose whole positioning is calm.

Decided during capture (2026-11-04): follow the PRD text. This item closes the traceability gap **by decision**, replacing an assumption with a designed answer.

## Acceptance Criteria

- [ ] A **non-blocking, non-modal** overlap notice on the Detail screen naming the other event. No forced choice, no three-action pattern, and it never blocks a flow.
- [ ] It is **visibly distinct from FR-58's conflict prompt**, so a user who has seen both does not read a state change as something they must resolve.
- [ ] It reuses the **same `CONFLICT_PAIR` rows** that propagation re-evaluated, read through the existing `read_detail_conflict` (`detail_conflict.py:113`) rather than a second detection path. AD-21 allows exactly one overlap function and forbids detection at render.
- [ ] The existing **conflict indicator on the Pulse Card and Timeline stays symmetric** — the pair is the same pair, and a state-change-born conflict shows the same 8–10px amber indicator as any other, because it *is* the same kind of fact.
- [ ] The notice **degrades** when the other side is gone: `detail_conflict.py:100-110` already builds a named-but-titleless side so the client says "event no longer available" rather than rendering a blank. That path must still work here.
- [ ] A conflict **closed** by a cancellation disappears from the Detail screen without the user acting.
- [ ] Nothing in this item writes a `ConflictResolution`. FR-58 records one for every prompt because every prompt is answered; this notice is not a prompt and has no answer to record.
- [ ] Tests: a postponement creating a new overlap surfaces it; a cancellation closing one removes it; the missing-side degradation; and a test asserting this path **never** raises the FR-58 forced prompt.

## Technical Notes

`read_detail_conflict` already reads the caller's active pair for a saved event and batches the catalog title read. The likely shape of this item is extending what it returns — the pair's provenance, so the client can tell a user-created conflict from a propagated one — rather than a new read.

**Traceability consequence:** when this lands, TRACEABILITY.md's FR-55 row moves from `PARTIAL (inferred only)` to `FULL`, citing this item's design rather than `conflict-prompt-desktop.html`. The brief records this as a pending PRD/traceability amendment; it should be made, not left implicit.
