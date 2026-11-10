---
id: notice-and-mute-api
title: The strip needs something to read and the mute needs somewhere to write —
  the notice API
intent: event-state-sync
complexity: medium
mode: confirm
status: completed
depends_on:
  - state-change-notice-model
created: 2026-11-04
run_id: run-eventpulse24-025
completed_at: 2026-11-10T10:25:14.746Z
---

# Work Item: The strip needs something to read and the mute needs somewhere to write — the notice API

## Description

The in-app half of FR-54 is a dismissible strip on the digest home and a banner on the Detail screen, decided during capture against FR-10's standing refusal of a notifications inbox. Both need a read. FR-55's per-event mute needs a write, from the Detail screen.

This is the API slice for `state-change-notice-model`: three endpoints through `delivery`'s router, generated into the frontend client by AD-19.

## Acceptance Criteria

> **Amended during execution.** The two criteria below were written before the
> `state-change-notice-model` design settled the strip's key, and they were amended to
> match the decision that design (D4) already made and that this item implements. The
> amendment is recorded here rather than left for a reader to discover.

- [ ] A read returning the signed-in user's **undismissed** notices, newest first, bounded — the strip shows a few, not a history, and there is no inbox to page through.
      - **Amended from "unseen" to "undismissed".** The strip is keyed on `dismissed_at`, not `seen_at`: it is a queue, and closing an item should empty it. A `GET` that marks notices seen would be a `GET` that writes — the shape CSRF exists to stop — so `mark_seen` is not called by this API at all.
- [ ] A **dismiss** write that closes a notice (sets `dismissed_at`). Dismissal is what makes FR-54's "one-time, never repeats" true, so it is a real write and not client state.
      - **Amended from "marks a notice seen".** The dismissal records the first sighting too, so `seen_at` moves with it — but the write's effect is the *closure*, and the closure is what the criterion is about.
- [ ] A **mute set/clear** write, per event, from the Detail screen (FR-55).
- [ ] The Detail read reports whether **this** event is muted and whether it has a notice, so the banner and the control render from one round trip.
      - **Amended from "an undismissed notice".** The banner reports the **newest notice for the event, whatever its dismissal state** — the rule `latest_notice_for_event` already stated and that this item's `services.notice_state` now owns. Dismissing the strip on the digest home must not hide "this event was cancelled" from the event's own page; `dismissed_at` rides on the wire so the client can tell the two states apart.
- [ ] Every endpoint is **session-scoped**; a user can neither read nor dismiss nor mute another user's notices. Tested as an authorization case, not assumed from the router.
- [ ] Dismissing an already-dismissed notice, and muting an already-muted event, are **idempotent** and answer success.
- [ ] A notice for an event the user has since un-saved still reads and dismisses cleanly rather than 404-ing.
- [ ] The OpenAPI schema regenerates and the frontend client is rebuilt in the same change (AD-19: the contract is generated, never hand-written).
- [ ] Contract tests cover each endpoint's shape, the empty case, and the authorization case.

## Technical Notes

`apps/delivery/api.py` is the router this belongs in — the same one `delivery-and-reminders` filled for the reminder plan endpoints, and the existing session and error conventions there apply unchanged.

The empty case is the common one: most users, most days, have no unseen notices. The read should cost nothing when there is nothing, and the strip must not force a request on every digest load if the digest response can carry the flag — worth checking against `DigestOut` before adding a second round trip to the home screen's critical path.
