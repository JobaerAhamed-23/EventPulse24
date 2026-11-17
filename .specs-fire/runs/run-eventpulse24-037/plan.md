---
run: run-eventpulse24-037
work_item: timeline-block-detail-contract
intent: traceability-gap-closure
mode: confirm
checkpoint: plan
approved_at: 2026-11-17 (scope decision)
---

# Implementation Plan: Send the Timeline block its location — FR-32 (contract)

## Approach

Add one nullable `place` field to the Timeline's block, resolved on the server, and
regenerate the contract. The hover reveal that consumes it is the next work item.

**Scope narrowed at the checkpoint: the location only.** `EXPERIENCE.md` §13 also names one
Why-this tag, and three findings moved it into its own item (`timeline-why-this-tag`):

1. **No persisted tag this surface may read.** `EventFit.tags` is per `(event, city)` on
   `catalog`; the Relevance Pulse's tags are per user *per day*, written at digest
   composition — and a saved event in a given week may have no digest card at all.
2. **An import contract bars the route that looks easiest.** *"AD-10 personalization never
   reaches the Event Fit"* forbids `apps.ingestion.event_fit` from `apps.personalization`,
   where the Timeline lives. Not a technicality: substituting one explanation kind for the
   other is the trust-collapse failure PRD Risk 11 calls company-ending.
3. **So it would have to be computed per user**, as `browse_read.py` does — four extra
   reads (chip keys, city, source visibility, muted categories) plus `chip_keys` on each
   candidate, which `PublicEvent` does not carry. That changes what a deliberately cheap
   read-only surface is.

**The place costs nothing extra.** `get_public_events` already does
`.select_related("venue", "source")` and `PublicEvent` already carries `venue_name` and
`venue_city`. The field is a projection of data the week read has in hand — no new query,
no N+1.

**The precedence lives on the server.** `pulse-card.tsx` resolves
`venue_name || location || venue_city` in the browser for the digest. Doing the same on the
server here keeps the block a projection the client renders without deciding (AD-10), and
stops two surfaces disagreeing about one event's place.

**A personal event's place is its own.** `PersonalEvent` has a location of its own; a
personal block sends it when there is one. A block whose catalog event has disappeared sends
`null` — the same degradation `name` and `state` already make, rather than a guess.

## Files to Modify

| File | Changes |
|------|---------|
| `backend/apps/personalization/services/timeline.py` | `TimelineBlock.place`; fill it for both block kinds |
| `backend/apps/personalization/schemas.py` | `TimelineBlockOut.place`; carry it in `from_block` |
| `frontend/lib/api/openapi.json`, `frontend/lib/api/schema.ts` | **Regenerated** by `make client` (AD-19) |

## Files to Create

| File | Purpose |
|------|---------|
| `backend/tests/personalization/test_timeline_place.py` | The projection, for both kinds and both absences |

## Tests

| Test File | Coverage |
|-----------|----------|
| `test_timeline_place.py` | a public block carries its venue name; falls back to the city when there is no venue name; sends null when the catalog event is gone; a personal block carries its own location, and null when it has none; the week read makes no extra queries per block |

## Technical Details

**`place` is `str | None`, matching `name` and `state`.** The existing nullable fields on
this block all mean "the server has nothing to state", and a fourth spelling of absence
would make the client narrow three ways.

**The query-count assertion is worth having.** The whole reason the place is free is that
`select_related` already loaded the venue; a later refactor that drops it would silently add
one query per saved event per week-read. `CaptureQueriesContext` pins that.

## Verification

`make test-backend`, `make lint-backend`, `make client`. No frontend behaviour changes in
this item — the regenerated type is consumed by the next one.

---
*Plan approved at checkpoint (the scope question answered 2026-11-17 was the checkpoint).*
