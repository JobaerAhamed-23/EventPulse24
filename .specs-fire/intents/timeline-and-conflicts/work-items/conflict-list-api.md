---
id: conflict-list-api
title: The conflict list — every pair, both sides, by name
intent: timeline-and-conflicts
complexity: medium
mode: confirm
status: completed
depends_on: []
created: 2026-10-31
run_id: run-eventpulse24-022
completed_at: 2026-10-31T06:57:19.065Z
---

# Work Item: The conflict list — every pair, both sides, by name

## Description

`GET /api/personal/conflicts`: the signed-in user's `ConflictPair` rows, active and resolved, each with **both sides readable** — kind, name, start and end — so `/conflicts` (and later the Timeline) can show a pair without a second round trip per side.

`ConflictPair`'s docstring already says the Pulse Card indicator, the Timeline indicator and `/conflicts` all read these rows; nothing lists them yet. The hard part is the saved side: a `SavedEvent` holds no title of its own (`_saved_side` names it `saved {event_id}`), because the title lives in `catalog`. It has to be read through the catalog's published read service and joined in the application layer (AD-2 / AD-3), never by a cross-schema query.

## Acceptance Criteria

- [ ] `GET /api/personal/conflicts` returns `{active: [...], resolved: [...]}` for the **caller only**; another user's pairs are never readable, and an anonymous caller gets 401.
- [ ] Each pair carries: `pair_id`, `kind` (`time` / `duplicate`), `status`, both sides as `{kind, id, name, start_time_utc, end_time_utc, start_time_tz}`, and for an active pair the **allowed actions** (the same `RESOLUTIONS_BY_KIND` the resolve endpoint enforces — one source, not a second list). A resolved pair carries its `resolution` and when it was resolved.
- [ ] **A saved side is named by its catalog title**, read through the catalog's published interface in one batched read for the whole list (no per-pair query). A saved side whose catalog event is gone reads as an explicit "event no longer available" state, not a crash and not a blank name.
- [ ] `cleared_by_state_change` pairs are **not** presented as a user's choice: they are either excluded or returned in their own clearly-named group — decided and documented in the endpoint description.
- [ ] Ordering: active pairs by the earlier side's start time, soonest first; resolved pairs by resolution time, newest first.
- [ ] The query count is bounded and independent of the number of pairs (a test asserts it).
- [ ] Pydantic schemas and the regenerated client (`make client`); no hand-written types (AD-19).
- [ ] Tests: ownership; both side kinds in both positions of the normalised pair; a deleted saved event; each status; ordering; the query bound.

## Technical Notes

The pair is stored normalised (`left` / `right`, sorted by `(kind, id)`), so "which side is mine to move" is not in the row. For the list, present both sides symmetrically; the resolve flow (see `saved-public-conflict-resolution`) is where the asymmetry is decided.

## Dependencies

(none)
