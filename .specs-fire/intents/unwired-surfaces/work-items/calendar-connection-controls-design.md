---
id: calendar-connection-controls-design
work_item: calendar-connection-controls
intent: unwired-surfaces
run_id: run-eventpulse24-031
status: approved
created: 2026-11-13
---

# Design: Disconnect and Reconnect

Approved under the run's standing approval (no checkpoint). Decisions are recorded here
rather than asked.

## The surface

A new route, **`/settings/calendars`**, following the five-step settings house pattern
(`force-dynamic`, session read + `homeRoute` redirect, `SettingsStates` for not-signed-in,
`SettingsStates` for unavailable, page in `AppShell` capped at
`max-w-(--layout-container-reading)`), with a sibling `loading.tsx`.

`settings-desktop.html` §`#calendar-sync` names the section "Calendar sync" and gives each
connected row a status line and a ghost **Disconnect** button. That is what this builds.

**Discoverability**: linked from `/settings/quiet-hours`, which is already the page that
carries a cross-link to `/settings/digest` (`:174`). One link, one place to keep in sync,
no nav row — the `DESIGN.md` rule holds.

## What the API gives, and what it withholds

`CalendarConnectionOut` carries `id`, `provider`, `status`, `display_label`,
`last_synced_at`, `next_sync_at`, `sync_in_progress`, `last_error_kind`. It carries **no
address and no fingerprint**, deliberately: *"a digest in a response body is one more thing
to leak in a screenshot"* (`schemas.py:1154`). `last_error_kind` is a slug, never a message
and never a URL, because *"an `httpx` exception message contains the full request URL, which
**is** the credential"* (AD-13).

So the UI **cannot** render the address even by accident — there is nothing to render. The
test asserting the address never appears is therefore a regression guard on the client's own
reconnect form, which does handle one.

## The two controls

**Disconnect** — `DELETE /api/personal/calendars/{id}`, two-step in place, reusing the
`DangerZone` idiom from `personal-event-form.tsx` rather than a third confirmation style.
The confirmation states what is lost: that connection's imported events are purged
(`calendar-sync-and-polling.md:42`). It does **not** claim the user's own events are
touched, because they are not.

**Reconnect** — `POST /api/personal/calendars/{id}/reconnect`, offered **only** when
`status === "needs_reconnect"`. `CalendarReconnectIn` takes `address` and `display_label`:
*"The provider revoked the old secret, so the address the user pastes now is a new one."*
So reconnect is a form, not a button — the same shape as the onboarding connect form, and
the address is cleared from state immediately after the request, as `calendar-step.tsx:208`
already does.

## Decisions taken without asking

1. **Provider rows are rendered from the API, not hard-coded.** The mockup shows Google,
   Apple and Outlook with the latter two as "Pro — Phase 2". The API returns the user's
   actual connections; inventing two disabled rows for providers the backend may not offer
   would be a UI claiming a roadmap.
2. **`sync_in_progress` and `next_sync_at` are shown, `last_error_kind` is translated.** A
   slug like `revoked` is not a sentence; the UI maps the slugs it knows and falls back to a
   neutral line for one it does not, rather than printing a slug at a person.
3. **No "Connect a calendar" control here.** Connecting lives in onboarding
   (`calendar-step.tsx`). Adding a second connect surface is its own work item; this one
   closes the two endpoints that have no caller. Stated so it is not mistaken for an
   oversight.

## Tests

| # | Test | Probe |
|---|---|---|
| 1 | disconnect calls `DELETE` with the connection id | send a different id |
| 2 | disconnect asks first — no request on the first press | fire immediately |
| 3 | the confirmation says the imported events are purged | soften the copy |
| 4 | reconnect is offered for `needs_reconnect` | offer it always |
| 5 | reconnect is **not** offered for an active connection | same probe, inverse assertion |
| 6 | reconnect posts the pasted address | post an empty body |
| 7 | the address is cleared from state after the request | keep it |
| 8 | no connections → an honest empty state, not an error | render `SettingsStates` |
| 9 | a refused disconnect reports and keeps the row | swallow the error |
| 10 | the address never appears in the DOM after submit | leave it in a value |
