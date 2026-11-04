---
id: notice-and-mute-api
title: The strip needs something to read and the mute needs somewhere to write — the notice API
intent: event-state-sync
complexity: medium
mode: confirm
status: pending
depends_on:
  - state-change-notice-model
created: 2026-11-04
---

# Work Item: The strip needs something to read and the mute needs somewhere to write — the notice API

## Description

The in-app half of FR-54 is a dismissible strip on the digest home and a banner on the Detail screen, decided during capture against FR-10's standing refusal of a notifications inbox. Both need a read. FR-55's per-event mute needs a write, from the Detail screen.

This is the API slice for `state-change-notice-model`: three endpoints through `delivery`'s router, generated into the frontend client by AD-19.

## Acceptance Criteria

- [ ] A read returning the signed-in user's **unseen** notices, newest first, bounded — the strip shows a few, not a history, and there is no inbox to page through.
- [ ] A **dismiss** write that marks a notice seen. Dismissal is what makes FR-54's "one-time, never repeats" true, so it is a real write and not client state.
- [ ] A **mute set/clear** write, per event, from the Detail screen (FR-55).
- [ ] The Detail read reports whether **this** event is muted and whether it has an undismissed notice, so the banner and the control render from one round trip.
- [ ] Every endpoint is **session-scoped**; a user can neither read nor dismiss nor mute another user's notices. Tested as an authorization case, not assumed from the router.
- [ ] Dismissing an already-dismissed notice, and muting an already-muted event, are **idempotent** and answer success.
- [ ] A notice for an event the user has since un-saved still reads and dismisses cleanly rather than 404-ing.
- [ ] The OpenAPI schema regenerates and the frontend client is rebuilt in the same change (AD-19: the contract is generated, never hand-written).
- [ ] Contract tests cover each endpoint's shape, the empty case, and the authorization case.

## Technical Notes

`apps/delivery/api.py` is the router this belongs in — the same one `delivery-and-reminders` filled for the reminder plan endpoints, and the existing session and error conventions there apply unchanged.

The empty case is the common one: most users, most days, have no unseen notices. The read should cost nothing when there is nothing, and the strip must not force a request on every digest load if the digest response can carry the flag — worth checking against `DigestOut` before adding a second round trip to the home screen's critical path.
