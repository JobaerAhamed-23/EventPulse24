---
id: calendar-connection-controls
title: Disconnect and Reconnect — The Promise Onboarding Makes
intent: unwired-surfaces
complexity: high
mode: validate
status: completed
depends_on: []
created: 2026-11-13
run_id: run-eventpulse24-031
completed_at: 2026-11-13T07:16:04.817Z
---

# Work Item: Disconnect and Reconnect — The Promise Onboarding Makes

## Description

Onboarding tells the user twice that they can disconnect a calendar:

- *"Read-only access. You can disconnect anytime."* — `onboarding-flow.tsx:76`
- *"read-only · disconnect any time in Settings"* — `calendar-step.tsx:436`

There is no settings screen for calendars. `DELETE /api/personal/calendars/{connection_id}`
and `POST /api/personal/calendars/{connection_id}/reconnect` are both built and tested, and
neither has a caller. The product makes a promise it cannot keep, and points at a screen
that does not exist.

`calendar-step.tsx:146` already reads `status === "needs_reconnect"` and `last_error_kind` —
the UI **detects** the broken state and has no way to offer the fix.

This was a scheduled deferral that was never picked up: `calendar-connect-api.md:20` says
the API is what *"onboarding step 1 (and, later, Settings → Sources)"* uses.

`settings-desktop.html` §`#calendar-sync` already specifies the surface: a section headed
"Calendar sync", one row per provider with a connected-state line
(`● Connected as maya@gmail.com`) and a ghost **Disconnect** button; Apple and Outlook rows
read "Pro — Phase 2".

## Acceptance Criteria

- [ ] A signed-in user can see their calendar connections and each one's status on a
      settings screen
- [ ] **Disconnect** removes the connection through `DELETE /api/personal/calendars/{id}`
- [ ] Disconnect is **confirmed before it completes**, and the confirmation says what is lost:
      that connection's imported events are purged (`calendar-sync-and-polling.md:42`)
- [ ] **Reconnect** is offered for a connection whose status is `needs_reconnect`, through
      `POST /api/personal/calendars/{id}/reconnect`, and is **not** offered for a healthy one
- [ ] After a disconnect, the list reflects it without a manual reload
- [ ] The onboarding copy's promise resolves — "disconnect any time in Settings" names a
      route a user can reach from the UI without knowing the URL
- [ ] **No secret address is rendered, logged, or placed in a URL** (AD-13,
      `calendar-connect-api.md:35`) — a test asserts the address appears nowhere in the DOM
- [ ] A user with no connections sees an honest empty state, not an error
- [ ] Tests cover: list, disconnect, the confirmation gate, reconnect offered only for
      `needs_reconnect`, a refused disconnect, and the address never rendering
- [ ] Every test is verified by a mutation probe that makes it fail

## Technical Notes

- **Follow the five-step settings-route house pattern** documented in
  `digest-settings-route.md`: `force-dynamic`, session read + `homeRoute` redirect,
  `SettingsStates` for not-signed-in, `SettingsStates` for unavailable data, then the page
  in `AppShell` capped at `max-w-(--layout-container-reading)`. Add a sibling `loading.tsx`.
- **Discoverability is part of the work, not a follow-up.** There is no `/settings` index and
  no sub-nav (`sidenav.tsx:131`), and `DESIGN.md` forbids adding nav rows. The route must be
  linked from an existing settings page — pick one and link from exactly one place.
- **The reconnect payload.** `POST …/reconnect` takes a `CalendarReconnectIn`
  (`personalization/api.py:833`). Read its schema before designing the form; a reconnect
  that needs a fresh address is a different control from one that does not.
- **Disconnect is destructive and purges events.** The confirmation must say so plainly.
  Reuse the two-step in-place pattern from `personal-event-form.tsx`'s `DangerZone` rather
  than inventing a third confirmation idiom.
- **Apple and Outlook are "Pro — Phase 2" in the mockup.** Render what the API reports;
  do not hard-code three provider rows if the API returns one connection.

## Dependencies

- (none)
