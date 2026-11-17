---
id: timeline-block-detail-contract
title: Send the Timeline block its location — FR-32 (contract)
intent: traceability-gap-closure
complexity: medium
mode: confirm
status: completed
depends_on: []
created: 2026-11-17
run_id: run-eventpulse24-037
completed_at: 2026-11-17T15:37:59.704Z
---

# Work Item: Send the Timeline block its location — FR-32 (contract)

## Description

`EXPERIENCE.md` §13 line 1107 specifies the desktop Timeline event-block's hover/focus state:
it **adds** *"location (`Text.Meta`) and 1 Why-this Tag (read-only at MVP)"*.

**The data is not there to add.** `TimelineBlockOut` carries exactly eight fields — `id`,
`kind`, `name`, `conflict`, `state`, `start_time_utc`, `start_time_tz`, `end_time_utc`. No
venue, no location, no tags. So the UI work is blocked on the API, and this item is the API
half: the server decides the place string and *which* single tag, and sends both.

**Scope decided 2026-11-17: the location only.** The tag is split out into
`timeline-why-this-tag`, because there is no persisted tag this surface may read
(`personalization` is barred from the Event Fit by an import contract, and the Relevance
Pulse's tags are per user per day and may not exist for a given saved event), so it would
have to be computed per block from four extra reads. That changes what a deliberately cheap
read-only surface is, and it is a decision to take on purpose rather than inside this item.

Splitting the contract from the UI is not ceremony either: AD-19 makes the OpenAPI schema
the contract the frontend type is generated from, so it has to land and be regenerated
before a component can read it.

## Acceptance Criteria

- [ ] `TimelineBlockOut` gains a nullable place field.
- [ ] The place is resolved **server-side** with the same precedence the Pulse Card uses (`venue_name` then `venue_city`), so the two surfaces cannot disagree about one event's place.
- [ ] A block whose catalog event is gone sends null rather than a guess — consistent with how `name` and `state` already degrade.
- [ ] A **personal** block sends its own location when it has one, and null otherwise.
- [ ] The timeline read is **not** made N+1 by the addition; the extra fields come from the same query that already builds the week.
- [ ] `make openapi` regenerates `frontend/lib/api/openapi.json` and `make client` regenerates `frontend/lib/api/schema.ts`; **neither is hand-edited** (AD-19).
- [ ] Backend tests cover: a public block with a venue, a public block whose catalog event is gone, and a personal block with and without a location.
- [ ] `make lint-backend`, `make lint-imports` and `make test-backend` pass.

## Technical Notes

**AD-10 is the whole reason this is a backend item.** The client renders decisions; it does
not make them. "Show the first of the tags" is a decision, and making it in
`timeline-block.tsx` would be the same class of error as re-bucketing a confidence score at
render — the failure AD-10 exists to prevent.

**Match the Pulse Card's vocabulary, not a new one.** `pulse-card.tsx` already computes
`place = card.venue_name || card.location || card.venue_city` and renders tags through
`tagLabel()` from `lib/digest-labels`. The Timeline should end up labelling the same tag the
same way; putting the precedence on the server is what guarantees it.

**Keep the read a single query.** `app/timeline/page.tsx` is a server component that renders
what the server sent and buckets nothing. Adding a per-block venue lookup would turn one
week-read into fifty.

**Nullable, not optional-and-absent.** The existing fields use `string | null` in the
generated schema; follow that so the frontend's narrowing stays uniform.

## Dependencies

(none)
