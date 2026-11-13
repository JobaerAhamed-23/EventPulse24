---
id: unwired-surfaces
title: The Controls That Were Never Wired — Endpoints Without Callers, Features Without Surfaces
status: pending
created: 2026-11-13
---

# Intent: The Controls That Were Never Wired

## Goal

Close every gap between **what the backend can do** and **what a user can reach**, found by
a method-level audit of all 70 endpoints in the generated schema against every call site in
`frontend/app`, `frontend/components` and `frontend/lib` (2026-11-13).

**56 endpoints are called from the UI. 14 are not.** Seven of those fourteen are correctly
uncalled. **Five are gaps.** Three further gaps do not show up in an endpoint diff at all —
a half-wired endpoint, a feature unbuilt on both sides, and a screen that renders nowhere.

## Users

- **A Pro subscriber who paid for Saved Collections.** They can create a collection, rename
  it, reorder it and delete it. They cannot put a saved event *into* one.
  `PUT /api/personal/collections/{id}/events/{saved_event_id}` exists, is tested, and has
  no caller — while `collection-manager.tsx:396` tells them "Nothing in here yet. Add saves
  to it from your saved events," and `SavedEventRow` (`saved-events-section.tsx:86`) renders
  no control of any kind. FR-49 is sold, billed for, and unreachable.
- **A user who connected a calendar and wants it gone.** Onboarding promises it twice —
  "You can disconnect anytime" (`onboarding-flow.tsx:76`) and "read-only · disconnect any
  time in Settings" (`calendar-step.tsx:436`). There is no settings screen for calendars.
  `DELETE /api/personal/calendars/{connection_id}` has no caller. The promise is false.
- **A user whose calendar connection has gone stale.** `calendar-step.tsx:146` already
  detects `status === "needs_reconnect"`. `POST /api/personal/calendars/{id}/reconnect`
  exists. Nothing offers the fix.
- **A user reading "3 people like you saved this".** FR-24 counts a neighbour who **saved
  _or_ opened**; `neighbor_count.py:157-169` unions `SavedEvent` with `EventDetailOpen`.
  Nothing has ever written an `EventDetailOpen` row from the UI, so the second half of the
  rule contributes zero and every neighbour count in the product is systematically low.
- **A user who set reminders on a personal event.** They can't. `ReminderPicker` is mounted
  once, at `app/events/[id]/reminders/page.tsx:93`, hard-coded `targetKind="saved_event"`.
  The backend accepts `personal_event` (`delivery/api.py:81`) and FR-20 has its own mockup.
- **A user who keeps seeing events they don't want.** FR-25 ("Less like this") is MVP scope
  and is built nowhere — no endpoint, no UI, no swipe. `detail-actions.tsx:7` says so:
  *"there is no dismissal endpoint in this codebase — a 'Dismiss' button here would be a
  control that silently does nothing."*

## Problem

### The audit, stated as a table

Verified at capture (2026-11-13) by extracting every `(method, path)` from
`frontend/lib/api/schema.ts` and every `api.{GET,POST,PUT,PATCH,DELETE}("…")` call site,
test files excluded.

| Endpoint | Status | Why |
|---|---|---|
| `POST /api/events/{id}/opened` | **GAP** | FR-24's second neighbour signal, never fired |
| `DELETE /api/personal/calendars/{id}` | **GAP** | Disconnect, promised in onboarding copy |
| `POST /api/personal/calendars/{id}/reconnect` | **GAP** | Reconnect, already detected and unofferable |
| `PUT /api/personal/collections/{id}/events/{saved_event_id}` | **GAP** | FR-49 assign — collections cannot be filled |
| `PUT /api/reminders/{target_kind}/{target_id}` | **HALF** | Called, but only ever with `saved_event` |
| `GET`/`POST /api/email/unsubscribe`, `GET /api/email/click` | correct | RFC 8058 one-click; the provider has no session |
| `GET /api/exports/{id}`, `/{id}/{fmt}` | correct | The export arrives by email — `download-my-data.tsx:6` is explicit |
| `POST /api/webhooks/billing` | correct | Stripe calls it |
| `GET /api/catalog/events`, `/events/{id}` | correct | Anonymous public API; the UI uses `/personal/browse` and `by-slug` |
| `POST /api/personal/onboarding/step`, `/step/skip` | correct | Called via a variable path, `onboarding-flow.tsx:202` |

### Two of these were deferrals that were never scheduled

Not oversights — decisions, recorded and then lost:

- **The detail-open signal.** `frontend-event-detail.md:48`: *"The `opened` signal is not
  fired… That belongs to the delivery intent."* The delivery intent never took it.
  `tests/ad19-endpoint-coverage.test.ts:225` records the consequence honestly: *"The
  endpoint's presence is asserted; the caller is not asserted to exist, because it does
  not."*
- **The calendar controls.** `calendar-connect-api.md:20`: the HTTP surface is what
  *"onboarding step 1 (and, later, Settings → Sources)"* uses. "Later" never arrived.

### Three gaps an endpoint diff cannot see

1. **The personal-events list renders nowhere.** Every one of the six mounts of
   `PersonalEventsPanel` passes `sheetsOnly` — `add-event-button.tsx:91`,
   `detail-actions.tsx:407`, `sidenav.tsx:152`, `bottom-tab-nav.tsx:123`,
   `conflicts-panel.tsx:134`, `timeline-panel.tsx:73`. Its `events` prop is passed by
   nothing but tests. The heading, the "Add event" button, `PersonalEventRow`, the empty
   state and the visible `message` line are dead in the app and alive in the test suite —
   which is how they went unnoticed.
2. **FR-25 is unbuilt end to end.** `less-like-this-mute-prompt-desktop.html` specifies it:
   dismissal, then a mute prompt *"after 3 clustered dismissals (embedding cosine ≥0.7)"*.
   No endpoint, no model, no UI, no swipe.
3. **Settings → Sources is unbuilt end to end.** `settings-sources-desktop.html` (Amendment
   A-18) specifies a grouped source list, reliability dots and a 3-state mute control
   (Mute / Show less / Default) plus "Restore all defaults". The **score itself is built** —
   `domain/reliability.py:148`, `SourceReliabilityScore` — but no endpoint exposes it and no
   endpoint stores a per-user source mute.

### Why this class of gap survived twelve intents

`TRACEABILITY.md` has **Section A — PRD ↔ Design** and **Section B — PRD ↔ Architecture**.
There is **no PRD ↔ implementation section**. `FULL` means *designed* and *architected*;
nothing in the matrix ever asks whether the code is wired to a user. FR-18 scored `FULL`
while its danger zone did not exist (built 2026-11-13, commit `2ba0073`), and FR-20, FR-24,
FR-49 and FR-50 carry `FULL` today under exactly the same rule. The matrix names the
problem itself: *"Whether FIRE work items should be traced against FRs is an open
question."*

## Success Criteria

- **Every endpoint in the generated schema is either called from the UI or listed, by path
  and method, with the reason it is not** — and that list is enforced by a test that fails
  when a new endpoint appears with neither a caller nor an entry
- **A Pro user can put a saved event into a collection, and take it out again** (FR-49)
- **A user can disconnect a calendar connection, and reconnect a stale one, from a settings
  screen** — and the onboarding copy that promises it points somewhere real (FR-50)
- **Opening a Detail Screen records the open**, fire-and-forget, never blocking the render,
  never fired for an anonymous visitor (FR-24)
- **A personal event can carry a reminder plan** through the same picker saved events use
  (FR-20)
- **The personal-events list is either given a surface or deleted** — a component that only
  its tests can render is not allowed to stay in either state by default
- **FR-25 and Settings → Sources are each either built or explicitly deferred in writing**,
  with the deferral recorded in the traceability matrix rather than in a code comment
- **Every test can fail** — no placeholder assertions, no `or`-fallbacks, each verified by a
  mutation probe
- **Each finished surface is demonstrated working** in a real browser against a running
  stack, with anything broken reported rather than smoothed over

## Constraints

- **The generated client is the contract** (AD-19). Frontend work calls through
  `lib/api/schema.ts`. Where a work item adds a backend endpoint, `make client` regenerates
  and `git diff --exit-code frontend/lib/api/` gates CI.
- **House style is binding** (`ARCHITECTURE-SPINE.md` Consistency Conventions): no component
  kit, no new hex values, no new spacing tokens, no `prefers-color-scheme` auto-switch, one
  240ms `motion.fadeIn`. Every visual comes from an existing token.
- **No new mockups.** `settings-desktop.html` (`#calendar-sync`), `collections-desktop.html`,
  `personal-event-reminders-desktop.html`, `settings-sources-desktop.html` and
  `less-like-this-mute-prompt-desktop.html` already specify these surfaces. Build from them.
- **The tier gate on collections is on `create` and `assign` only** —
  `collections-desktop.html:34` states it. Rename, reorder, delete and unassign stay open on
  every tier.
- **There is no `/settings` index and no settings sub-nav** (`sidenav.tsx:131`). New settings
  routes are reachable by prefix-match active state and must be linked from an existing
  settings page, not from the nav.
- **No PII in logs** (AD-13). Calendar work must not log or return the secret ICS address —
  `calendar-connect-api.md:35` already requires this of the API and it holds for the UI.
- **Never-delete constraint.** Disconnect purges that connection's imported events by
  design (`calendar-sync-and-polling.md:42`); unassigning a save from a collection must not
  delete the save (`collections_api.py:175`).

## Notes

Decisions taken at capture (2026-11-13):

- **Scope is "cover all"** — Jobaer's call, over starting with the worst gap alone. All
  eight gaps are in this intent.
- **Two items are large enough to be their own intents, and are flagged rather than
  hidden.** `less-like-this-adjustment` needs a dismissal model, a clustering rule
  (cosine ≥0.7 over three dismissals) and a new endpoint; `settings-sources-surface` needs
  two new endpoints over a score that exists but is unexposed. Both are `validate` mode and
  design-first. **If either design checkpoint shows the work is larger than the rest of this
  intent combined, it should be split out rather than forced through.**
- **The dead-list item is a decision, not a cleanup.** Deleting the list and giving it a
  route are both defensible; the item states the choice and does not pre-empt it.
- **The traceability item is the systemic fix.** Without a PRD ↔ implementation section, the
  next unwired control is found by the next audit instead of by CI.
- **FR-16's missing design citation is not in scope.** The matrix's own open item #1 says one
  line in `EXPERIENCE.md` or a tag in `settings-sources-desktop.html`'s header closes it —
  but editing a document to improve its own score is the matrix's problem to fix, not this
  intent's.

Out of scope, named so they are not lost:

- **`DigestPreference.share_precise_location`** — a privacy control with no UI, carried out
  of `digest-personal-events-control` and still unclaimed.
- **The two writers of `include_personal_events`** (`onboarding.py:370`,
  `digest_preferences.py:336`) — recorded by `run-eventpulse24-030`'s walkthrough.
- **Advancing past the digest step leaving a user with no schedule** (`onboarding.py:451`) —
  a product question, recorded by the same walkthrough.
