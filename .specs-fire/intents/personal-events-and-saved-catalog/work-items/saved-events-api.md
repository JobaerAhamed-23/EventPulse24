---
id: saved-events-api
title: Saved Events API
intent: personal-events-and-saved-catalog
complexity: medium
mode: confirm
status: completed
depends_on:
  - personalization-write-services
created: 2026-10-29
run_id: run-eventpulse24-019
completed_at: 2026-10-29T04:52:05.374Z
---

# Work Item: Saved Events API

## Description

Exposes saving and unsaving public catalog events: `POST /api/public-events/{id}/save`, `DELETE /api/public-events/{id}/save`, and `GET /api/personal/saved-events`.

A save is the act of taking a public event from the catalog into the user's own calendar. AD-21 defines what that means structurally:

> A user's save of a public Event is a `SAVED_EVENT` row in `personal`, owned by `personalization`. It holds `event_id` by value (no FK) plus a snapshot — `start_utc`, `end_utc`, `event_version` — taken from `catalog` at save time and **thereafter updated only by AD-17 propagation**.

This work item is the HTTP surface over that. It is where a user turns "I might go to that" into "that is on my calendar", and it is the input to conflict detection against public events.

It also carries one of the trickiest requirements in the whole intent: the **save race**. A save that reads the catalog event's version, and a postponement that commits between that read and the save's own commit, must not leave a stale snapshot on the `SAVED_EVENT` row. The protocol is implemented in the service layer; this work item must expose it correctly and must not paper over it.

## Acceptance Criteria

- [ ] `POST /api/public-events/{id}/save` saves a public event for the signed-in user and returns the saved record.
- [ ] The save is **idempotent**: saving an already-saved event returns the existing record with a success response, not a 409 and not a duplicate row.
- [ ] The saved record exposes the **snapshot** — `start_utc`, `end_utc`, `event_version` — alongside the catalog event's display fields (title, venue). The display fields are resolved from `catalog` at read time; the times come from the snapshot.
- [ ] `DELETE /api/public-events/{id}/save` unsaves the event and closes any conflict pairs it participated in.
- [ ] `GET /api/personal/saved-events` lists the user's saved events.
- [ ] Saving an event that is **not in the public catalog** (unpublished, in review, superseded, or nonexistent) returns 404. Only published, non-superseded, upcoming events are saveable, because that is exactly what `ingestion`'s published read interface exposes.
- [ ] Every endpoint is scoped to the authenticated user. One user can never read or unsave another user's saved event — an attempt returns 404, not 403.
- [ ] Every endpoint is **authenticated**. An unauthenticated request returns 401.
- [ ] The **save race** is handled correctly at the API boundary: a save whose catalog event was postponed between the initial read and the commit does not return a stale snapshot as if it were current. The service's post-commit re-read and re-propagation request are exercised, not bypassed.
- [ ] A save that detects a conflict with a personal event returns the conflict payload with the three actions, exactly as the personal-event create does. A conflict between a saved public event and a personal event is the FR-58 case "a saved public event that overlaps with a Personal Event by more than 15 minutes".
- [ ] The router is registered in `config/api.py` and the OpenAPI schema regenerates cleanly (`make client`).
- [ ] The generated TypeScript client in `frontend/lib/api/` is regenerated and committed, never hand-edited (AD-19).
- [ ] The `models-personalization` and `models-ingestion` import contracts keep passing. The API reaches the catalog through `ingestion`'s published read interface, never through `apps.ingestion.models`.
- [ ] Tests cover: save succeeds; double-save is idempotent; unsave; list scoping; a cross-user attempt returning 404; saving a non-public event returning 404; a conflict with a personal event returning the three-action payload; and the save-race scenario.

## Technical Notes

The public event's display fields and its snapshot come from **two different places**, and keeping them straight is the point of this work item:

- **Display fields** (title, venue, canonical URL) are read from `catalog` through `ingestion`'s published read interface, which returns a frozen `PublicEvent` dataclass. They reflect the current state of the event, including any editorial correction.
- **Times** (`start_utc`, `end_utc`, `event_version`) come from the **snapshot** stored on the `SAVED_EVENT` row. They reflect what the user saw when they saved, updated only by AD-17 propagation.

If a user saves an event and the catalog later renames its venue, the saved item shows the new name immediately. If the event is postponed and propagation has not yet run, the saved item shows the old time — and the `event_version` on the snapshot is what lets the system detect that it is behind. That is the intended behaviour, not a bug.

The `PublicEvent` dataclass carries `event_version` — check the exact field names in `apps/ingestion/services/catalog_read.py` before writing the schema. The catalog's own `EventOut` exposes `event_version`, `start_time_utc`, `start_time_tz` and `end_time_utc`.

**Endpoint placement.** The save action is addressed by the *catalog* event id (`/api/public-events/{id}/save`), while the saved list is a *personal* collection (`/api/personal/saved-events`). That split reflects ownership: the catalog owns the event, `personalization` owns the save. Two routers may be involved, or one router with two path groups — the codebase's `config/api.py` composes routers by prefix, so decide deliberately and keep the prefixes coherent.

**Free-tier quota.** FR-48 caps free-tier saves at 1 per 24-hour period, and the UX spine specifies the inline failure message for exceeding it ("You've used your 1 free save today. Upgrade for unlimited."). That quota belongs to the Pro tier intent and needs the `identity` subscription model, which does not exist yet. **Do not build the quota here.** If the quota enforcement is skipped, note it in the test report so the Pro tier intent knows to add it. Silently shipping an unlimited save is a smaller sin than inventing a half-quota that the Pro intent has to unpick.

## Dependencies

- personalization-write-services
