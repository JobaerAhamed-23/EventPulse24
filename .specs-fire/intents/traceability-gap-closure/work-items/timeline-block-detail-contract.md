---
id: timeline-block-detail-contract
title: Send the Timeline block its location and one Why-this tag — FR-32 (contract)
intent: traceability-gap-closure
complexity: medium
mode: confirm
status: pending
depends_on: []
created: 2026-11-17
---

# Work Item: Send the Timeline block its location and one Why-this tag — FR-32 (contract)

## Description

`EXPERIENCE.md` §13 line 1107 specifies the desktop Timeline event-block's hover/focus state:
it **adds** *"location (`Text.Meta`) and 1 Why-this Tag (read-only at MVP)"*.

**The data is not there to add.** `TimelineBlockOut` carries exactly eight fields — `id`,
`kind`, `name`, `conflict`, `state`, `start_time_utc`, `start_time_tz`, `end_time_utc`. No
venue, no location, no tags. So the UI work is blocked on the API, and this item is the API
half: the server decides the place string and *which* single tag, and sends both.

Splitting it this way is not ceremony. AD-10 forbids the client choosing the tag at render,
and AD-19 makes the OpenAPI schema the contract the frontend type is generated from — so the
contract has to land, and be regenerated, before a component can read it.

## Acceptance Criteria

- [ ] `TimelineBlockOut` gains a nullable place field and a nullable single-tag field.
- [ ] **The server picks the one tag.** The payload carries one tag or null — never a list the client narrows. A personal event has no Why-this tag and sends null.
- [ ] The place field follows the Pulse Card's existing precedence (`venue_name || location || venue_city`), resolved **server-side**, so the two surfaces cannot disagree about the same event's place.
- [ ] A block whose catalog event is gone sends null for both rather than a guess — consistent with how `name` already degrades.
- [ ] The timeline read is **not** made N+1 by the addition; the extra fields come from the same query that already builds the week.
- [ ] `make openapi` regenerates `frontend/lib/api/openapi.json` and `make client` regenerates `frontend/lib/api/schema.ts`; **neither is hand-edited** (AD-19).
- [ ] Backend tests cover: a public block with both fields, a public block with neither, and a personal block (place possible, tag always null).
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
