---
work_item: timeline-why-this-tag
intent: traceability-gap-closure
created: 2026-11-19
mode: validate
checkpoint_1: approved
---

# Design: The Timeline block's Why-this tag — deferred, with the reason

## Summary

`EXPERIENCE.md` §13's Density Modes table promises that a desktop Timeline event-block
adds **location and one Why-this Tag** on hover or focus. The location shipped
(`d1d6c83`, `b4ba162`), resolved server-side onto `TimelineBlockOut.place`. This design
settles the tag.

**The decision is to amend §13 to location-only**, under a new Amendment **A-24**, and to
close observation O-2 in `TRACEABILITY.md`. No code changes.

**The recommendation is not the one the work item anticipated, and two of its three stated
findings are wrong.** They are corrected below rather than quietly dropped, because a
deferral that rests on a false premise is a deferral that gets reversed the first time
somebody checks it.

## Scope

**In Scope:**

- Amending `EXPERIENCE.md` §13's hover/focus row for the Timeline event-block
- Adding the Amendment A-24 row to `EXPERIENCE.md`'s amendment list
- Updating `TRACEABILITY.md`'s FR-32 row to close O-2
- Recording the corrected cost model and the AD-10 clarification, so neither is
  rediscovered later as a reason to reverse this

**Out of Scope:**

- Any ranking computation on the Timeline read
- Any change to `TimelineBlock`, `TimelineBlockOut`, or `timeline-block.tsx`
- Any change to Browse, the Digest, or `domain/ranking.py`
- The FR-22 formula divergence (A-3) — that is `fr22-published-formula`, a separate item

## What the code actually says

Both corrections come from reading `domain/ranking.py`,
`apps/personalization/services/browse_read.py`, `apps/personalization/services/timeline.py`
and `apps/ingestion/services/catalog_read.py`.

### Correction 1 — the cost is much smaller than the work item recorded

The work item states that building the tag means "four reads and a per-block ranking
assembly". It does not.

**`why_this_tags` reads exactly one field off `RankingInputs`: `inputs.city_match`.** The
other four terms — `interest_overlap`, `recency`, `confidence`, `source_reliability` — are
*scoring* inputs. The tag function never touches them. So the real bill against the
Timeline's current five queries is:

| Need | Cost |
|---|---|
| The user's city | **0 queries** — it is a column on the `DigestPreference` row `_read_zone` already fetches |
| The event's `chip_keys` | **0 queries** — `chip_keys_for(title, description)` is a pure function over columns the batched catalog read already selects |
| `venue_country_code` | **0 queries** — the same joined `Venue` row |
| `user_chip_keys` | **+1 query** — `_read_interest_keys(user_id)` |
| `is_saved` | free — a constant `True` on this surface |

**Five queries would become six.** The batched catalog read would need to carry
`chip_keys` and `venue_country_code` (a shape change to `PublicEvent`, or a sibling
by-ids read in the shape of `PublicEventCandidate`), but that is one heavier projection,
not an extra round-trip.

### Correction 2 — AD-10 is not the blocker on this path

The import-linter contract *"AD-10 personalization never reaches the Event Fit"* forbids
`apps.ingestion.event_fit` and its submodules from `apps.personalization`. It does not
forbid `apps.ingestion.services.catalog_read`, which `personalization` already imports for
`get_public_events`.

The chip keys a Relevance Pulse tag needs come from
`chip_keys_for(title=..., description=...)` — a pure function over the event's own text,
computed inside `catalog_read._to_public_candidate`. **Nothing in the Relevance Pulse path
touches the Event Fit.**

The work item's point 3 says as much, but its point 2 reads as an architectural wall. It
is not one. A future reader who stops at point 2 would conclude the tag is impossible,
which is the wrong lesson: it is possible, cheap, and still not worth building.

## The actual reason to defer

**The tag, computed correctly, carries almost no information on this surface.**

`RANKING_TAG_ORDER` is `discovery, nearby, tonight, tomorrow, weekend, saved`, with chip
tags appended after the fixed set. `RANKING_MAX_TAGS` is 3, and §13 asks for **one** tag —
so the block would show `tags[0]`. On the Timeline:

- **`discovery` never fires.** It requires `serendipity=True`, which is a digest-slot
  decision. The Timeline has no slots.
- **`is_saved` is universally `True`.** Every public block on the Timeline *is* a saved
  event — that is what the surface is.
- **The time tags are relative to `now`.** `tonight`, `tomorrow` and `weekend` are computed
  against the current clock, and the Timeline navigates by arbitrary week. For any week but
  the current one, none of them fire.

That leaves exactly two outcomes:

1. **The user has a city and the event is in it** → `nearby`, on every block, all week.
   The same word on everything explains nothing.
2. **No city** (`DigestPreference.city` is nullable and means "not known"), **or an
   out-of-town event, or any non-current week** → the first surviving tag is `saved`. On a
   surface that shows only saved events, "why is this here?" answers "because you saved
   it." That is a tautology.

The one genuinely informative tag — `matches_<chip_key>` — sorts **last**, after every
fixed tag, and is reachable only when no fixed tag applies at all.

So the tag is cheap to build and would say nothing. That is the reason to defer, and it is
a better reason than cost because it does not change when the query budget does.

## Key Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Build the per-user tag, or amend §13? | **Amend §13 to location-only** | The correctly-computed tag is near-constant (`nearby`) or tautological (`saved`) in the common cases, and the informative chip tag sorts last and is usually unreachable. |
| Is cost the reason? | **No — and the overstatement is corrected in writing** | The work item's "four reads" is wrong; the true delta is one query. Leaving it unchallenged would invite a reversal on inspection. |
| Is AD-10 the blocker? | **No — and that is recorded** | The contract bars the Event Fit. `why_this_tags` + `chip_keys_for` reach it not at all. Recording this stops a future reader re-litigating a wall that does not exist. |
| Which explanation kind, if it is ever built? | **Relevance Pulse, via `why_this_tags`** | Unchanged from the work item, and non-negotiable: never the Event Fit, never a tag invented for this surface. AD-10 exists because substituting one kind for the other is PRD Risk 11's trust collapse. |
| Amendment ID | **A-24** | The ledger ends at A-23. Its own note on A-3 says the right close for a divergence is a *new* ID rather than stretching an old one to cover a change it never made. |
| Any backend or frontend change? | **None** | `TimelineBlock`, `TimelineBlockOut` and `timeline-block.tsx` are untouched. This is a documentation change. |
| Does this violate §13's own anti-pattern on hiding trust signals? | **No — and the amendment says so explicitly** | "Adaptive density must not hide the trust signals (Why-this Tags, Confidence Pulse, Source Badge)" governs the **Pulse Card**, whose mobile default exposes all three. The Timeline block's default shows none of them at any density, so nothing is being hidden — the promise is being withdrawn before it was ever made good. §13 already routes the full Why-this breakdown to the Detail Screen and explicitly keeps it off the Timeline. |

## Technical Approach

### Architecture

```
  The Timeline read, unchanged — five queries, no ranking:

    GET /api/personal/timeline?week=YYYY-MM-DD
        │
        ├─ 1. DigestPreference ....... the zone (city column present, unread)
        ├─ 2. personal events ........ overlapping the week
        ├─ 3. saved events ........... overlapping the week
        ├─ 4. conflict pairs ......... active + keep_both
        └─ 5. get_public_events() .... ONE batched catalog read
                                       → PublicEvent: no chip_keys, no
                                         venue_country_code, no reliability
        ↓
    TimelineBlock{ kind, id, name, times, tz, conflict, state, place }
        ↓
    timeline-block.tsx — reveals `place` on group-hover / group-focus-within


  The path NOT taken (recorded so it is not rediscovered):

    + DigestPreference.city ................ 0 queries (same row)
    + chip_keys / venue_country_code ....... 0 queries (heavier projection)
    + _read_interest_keys(user_id) ......... +1 query
    + is_saved = True ...................... constant
        ↓
    why_this_tags(inputs=…, …)[0]
        ↓
    "nearby" on every block, or "saved" — a tautology on a saved-events surface
```

### API Changes

None. `TimelineBlockOut` keeps its current nine fields; the generated frontend client in
`frontend/lib/api/` is unaffected, and `backend/tests/api/test_contract.py` sees no schema
change.

### Database Changes

None.

## Affected Files

| File | Action | Purpose |
|------|--------|---------|
| `_bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/EXPERIENCE.md` | Modify | §13 Density Modes: the hover/focus Timeline row drops the Why-this Tag and keeps location, tagged `(Amendment A-24)`; the amendment list gains the A-24 row |
| `_bmad-output/planning-artifacts/traceability/TRACEABILITY.md` | Modify | FR-32's note: "O-2 partly closed — §13's Why-this tag is open as `timeline-why-this-tag`" becomes O-2 **closed**, §13 amended |
| `.specs-fire/intents/traceability-gap-closure/work-items/timeline-why-this-tag-design.md` | Create | This document |

## Integration Points

| System | Type | Purpose |
|--------|------|---------|
| `EXPERIENCE.md` §13 | Spec amendment | The surface contract the Timeline block is built against |
| `TRACEABILITY.md` FR-32 / O-2 | Ledger update | Converts an open shortfall into a recorded position |
| `domain/ranking.py` | Read-only reference | `why_this_tags`, `RANKING_TAG_ORDER`, `RANKING_MAX_TAGS` — the behaviour the deferral reasons about |
| `apps/personalization/services/browse_read.py` | Read-only reference | The worked example of computing the tag correctly, if it is ever built |

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| A later doc-trace re-opens this as a coverage gap | Medium | The amendment ID lives in §13, O-2 closes in the traceability ledger, and this design doc holds the reasoning. A reader finds a decision, not a hole. |
| The amendment reads as removing a trust signal | Medium | A-24 states that the Timeline block never showed Why-this Tags, Confidence or Source Badge at any density, and names the Pulse Card and Detail Screen as the surfaces that do. |
| FR-25's preference graph later makes the tag informative | Low | Written as a deferral with a named condition rather than a deletion: if a preference-graph term ever makes `matches_<chip>` reachable and meaningful here, the decision is revisitable on that evidence. |
| A docs-only change has no test to keep it true | Low | Acceptance is a documentation-state check. A ledger assertion is possible but belongs to the `time-bomb-tests` pattern, not here. |
| Someone reverses the deferral on the cost argument | Low | The corrected cost (5 → 6 queries) is stated in this doc, so the cheaper-than-you-think case is already answered. |

## Implementation Checklist

- [ ] Amend `EXPERIENCE.md` §13's "Hovered / focused (Timeline event-block, desktop)" row to location-only, tagged `(Amendment A-24)`
- [ ] Add the A-24 row to `EXPERIENCE.md`'s amendment list, in the form A-21 / A-22 / A-23 use
- [ ] State within A-24 why this is not a trust-signal removal (the anti-pattern's scope is the Pulse Card; the Detail Screen owns the breakdown)
- [ ] Record in A-24 the real reason: the tag is near-constant or tautological on a saved-events surface
- [ ] Update `TRACEABILITY.md`'s FR-32 row — O-2 **closed**, not partly closed
- [ ] Verify no other document still lists `timeline-why-this-tag` as open work
- [ ] Confirm zero code change: no diff under `backend/` or `frontend/`

---
*Generated by specs.md - fabriqa.ai FIRE Flow | Checkpoint 1 approved: 2026-11-19*
