---
run: run-eventpulse24-037
work_item: timeline-block-detail-contract
intent: traceability-gap-closure
date: 2026-11-17
---

# Code Review: Send the Timeline block its location — FR-32 (contract)

## Findings

### 1. The per-day rebuild dropped the new field — **found and fixed during implementation**

`_add_block`'s loop constructs a fresh `TimelineBlock` per covered day, naming each field.
A field added to the dataclass and to both construction sites is still **silently dropped**
there: `place` was set on the source block and absent from every block that reached a day.

The failure mode is the quiet one — no error, no type complaint, just a screen that reveals
nothing and a developer concluding the frontend is broken. Fixed, with a comment at the
rebuild saying why the field list must be kept in step, and `TestTheRebuild` now covers it.

### 2. Checked and found sound

| Concern | Finding |
|---|---|
| Extra queries | None. `get_public_events` already `select_related`s the venue; `TestTheCost` pins it |
| Nullability spelling | `str \| None`, matching `name` and `state` — the block now has three fields meaning "the server has nothing to state" and one spelling for all three |
| Unknown vs absent | A catalog event that has gone gives `None`, the same degradation `name` and `state` make. Not conflated with "an event with no venue" |
| Precedence location | Server-side (`_place_of`), so the Timeline and the Pulse Card cannot disagree about one event's place |
| Empty-string venue | `venue.name or venue_city or None` — an empty name falls through to the city rather than rendering a blank. Covered |
| AD-10 | The block carries one already-chosen string; the client picks nothing |

## Scope note

**The Why-this tag was removed from this item at the checkpoint**, not forgotten. Three
findings drove it: no persisted tag this surface may read; an import contract barring
`personalization` from the Event Fit; and a per-user computation needing four extra reads
on a surface whose design is to decide nothing. Recorded in `timeline-why-this-tag`
(`complexity: high`, `mode: validate`) because the real question is architectural — whether
a read-only surface starts ranking.

## Verdict

**Approved.** One real defect, caught in implementation and now covered by a test that did
not exist before.
