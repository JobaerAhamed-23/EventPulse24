---
id: calendar-sync-and-polling
title: Calendar Sync Services & Polling
intent: onboarding-and-account
complexity: high
mode: validate
status: pending
depends_on:
  - calendar-connection-model
  - ics-calendar-adapter
created: 2026-10-29
---

# Work Item: Calendar Sync Services & Polling

## Description

The `personalization` write side of calendar import consists of four commands:

- **connect**, which validates the address, enforces the Free cap, stores the connection and requests a first sync;
- **sync**, which fetches through the calendar port and reconciles the connection's imported `PERSONAL_EVENT`s;
- **reconnect**, which replaces the credential and returns the status to active;
- **disconnect**, which purges exactly that connection's events.

It also includes **polling**: due connections are synced on the provisional 1-hour interval, dispatched from the existing single 60s tick.

This is also where imported events meet **FR-58 conflict detection**. A conflict between an imported event and a saved or personal event must be detected the same way as any other, by the one function in `domain/conflict.py`. But FR-58's forced three-way prompt assumes a creation flow the user is in, and a background sync has none. The design doc must settle what happens.

## Acceptance Criteria

- [ ] **Connect** validates the address shape, refuses a duplicate of an already connected calendar, enforces `FREE_TIER_CALENDAR_PROVIDER_CAP`, and stores the connection. It **does not fetch inside the request** (AD-11); it enqueues the first sync. Exceeding the cap returns a typed error that the API turns into the calm upgrade message.
- [ ] **Sync** fetches through `CalendarPort`, then reconciles:
  - new UIDs become `PersonalEvent` rows;
  - changed UIDs update their row and bump `version`;
  - UIDs that disappeared from the feed are removed.
  
  Re-running a sync with an unchanged feed changes nothing, so it is idempotent. Every create, update and delete goes through the same command paths as user-created events, so conflict detection, the FR-20 reminder default via `delivery`, and audit all apply, unless the design doc decides that an import gets a different reminder default.
- [ ] A **revoked** fetch outcome (401, 403, 404 or 410) sets the connection to `needs_reconnect` and **keeps the already imported events**. It never silently deletes them. A **transient** failure leaves the status alone and retries at the next due time.
- [ ] **Reconnect** replaces the encrypted credential, sets the status to active and enqueues a sync.
- [ ] **Disconnect** deletes **exactly that connection's** imported events and their conflict pairs and reminder plans (each through its owner's interface), and removes or retires the connection. Another connection's events and user-created events are untouched (FR-50). A test with two connections proves this.
- [ ] **Polling** works from the tick:
  - The tick enqueues a dispatcher. The dispatcher claims connections whose next-due time has passed, in bounded batches, and enqueues one sync per claim. This mirrors `ingestion`'s `claim_due_sources`.
  - Two overlapping ticks never sync the same connection twice concurrently, because the claim is atomic and has a TTL.
  - **`beat_schedule` stays exactly one 60s tick**, and `backend/tests/worker/test_tick.py` passes unchanged.
- [ ] **Conflicts:** imported events are checked by `domain/conflict.py` (strictly more than 15 minutes) against the user's personal and saved events. The resulting `CONFLICT_PAIR` behaviour for a background import is exactly what the design doc decides, and it is pinned by tests. A conflict a user resolved with "Keep both" is not re-prompted on the next sync.
- [ ] Sync, connect and disconnect write `personalization` audit entries by actor (a system actor for polled syncs), with no event content and no URL.
- [ ] No event content (titles, locations, notes) and no URL reaches any log (AD-13). This is tested with log capture over a full sync.
- [ ] Tests cover connect enqueueing rather than fetching, the cap, the duplicate refusal, the three reconcile branches, idempotent re-sync, revoked keeping events, transient leaving the status alone, reconnect, the two-connection disconnect purge, the due-claim atomicity, and the conflict behaviour on import.

## Technical Notes

**Design doc required (validate).** It must settle at least:

- **FR-58 conflicts on background import.**
  - **Option A:** create an `active` `CONFLICT_PAIR` and show the amber indicator. The three-way prompt is presented the next time the user opens the app, through a pending-conflicts read.
  - **Option B:** record the pair and show only the indicator, never a forced prompt, because the user didn't create the event here.
  - Whichever is chosen, "Delete the new one" on an imported event raises a question: it would reappear on the next sync. Decide what that action means for an imported event, for example hiding the UID or relabelling the choice. Cite `EXPERIENCE.md` §`Sheet.ConflictResolution`.
- **Duplicate detection (FR-58's 80% token overlap) for imports.** Does it apply between an imported event and a user-created one? For example, a user typed "Dinner" and their calendar also has "Dinner".
- **The reminder default for imported events.** FR-20 says *new personal events* get 1d + 1hr. Does an imported meeting get two reminders automatically? This is a product question. Propose an answer, and the user decides at Checkpoint 1.
- **Reconcile on time change.** An imported event whose time moves is an edit. State how its conflict pairs and reminder sends are updated.
- **The first-sync timing** and what the onboarding step-1 UI shows while it runs. FR-3 says "see their personal events in the Calendar Connect step without leaving the onboarding flow", so the step needs a pollable sync status.

OQ-7 is still open. `CALENDAR_POLL_INTERVAL` is provisional. Record the interval in the run's walkthrough so it is easy to find when OQ-7 is resolved.

## Dependencies

- calendar-connection-model
- ics-calendar-adapter
