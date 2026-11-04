---
id: event-state-sync
title: Event State Sync — Propagation, Notices & Conflict Re-evaluation
status: in_progress
created: 2026-11-04
---

# Intent: Event State Sync — Propagation, Notices & Conflict Re-evaluation

## Goal

Close **AD-17**. Every intent since `event-catalog-ingestion` has written the producer half of event-state propagation and then stopped at the wall: `ingestion` appends a versioned `EventStateChange`, the outbox enqueues it, the reconciler re-offers it — and the consumer that carries it into `personal` does not exist. `worker/tasks.py:159` is a placeholder that logs and deliberately leaves `propagated_at` NULL.

This intent builds the consumer, and the two things that depend on it: **FR-54**'s one-time state-change notice, and **FR-55**'s conflict re-evaluation. It also implements AD-17's **sweep guard**, which was specified and never built, and gives the **Pulse Card** the state treatment the Detail Screen already has.

It closes **FR-53** (state polling), **FR-54** (user-facing state-change notifications) and **FR-55** (conflict resolution on state change). FR-54 and FR-55 appear in **zero** of the eight preceding intent briefs — they are the only MVP requirements no intent has ever named.

This is the first intent whose primary deliverable is **correctness of something already shipped** rather than a new capability.

## Users

- **The user who saved an event that was cancelled.** Today they are told nothing, their reminders still fire, and their Timeline still shows the event. The system knows — `EventStateChange` has the row — and cannot reach them.
- **The user whose saved event moved.** `SavedEvent.start_utc` is a snapshot "thereafter updated only by AD-17 propagation" (`apps/personalization/models.py:278`). With no propagation, the snapshot is frozen at save time, so the Timeline, conflict detection and every reminder read a time the catalog has already corrected.
- **The user with a newly-created overlap** they did not cause. A postponement can push a saved event onto one they already had; nothing re-runs `detect_conflicts` after a catalog change.
- **The operator**, who currently has an unbounded, permanently-growing backlog of unpropagated rows and no signal that anything is wrong — the reconciler is working exactly as designed and will never drain.

## Problem

- **The consumer is an empty stub, and it is honest about it.** `worker/tasks.py:159-167`:
  > *"AD-17 placeholder consumer: no propagation into `personal` exists yet (FR-53-55). It deliberately leaves `propagated_at` NULL: marking the row would claim a propagation that never happened, and the real consumer would then skip it. The reconciler keeps re-offering it until that consumer arrives."*

  With `OUTBOX_RECONCILE_AFTER = timedelta(minutes=5)` and `OUTBOX_RECONCILE_EVERY_MINUTES = 5` (`shared/constants.py:79-81`), every state change ever recorded is re-enqueued every five minutes, forever. The backlog is monotonic.

- **`delivery` built its half and left it with no caller.** `apps/delivery/services/scheduled_sends.py:51`:
  > *"`propagate_state_change` is deliberately not wired to this module yet… the `personalization` half — the `SAVED_EVENT` snapshot and the conflict re-evaluation — **belongs to the FR-53/54 intent**. `apply_lifecycle_change` is built, published and tested here, ready for that intent to call."*

  `LIFECYCLE_SEND_BEHAVIOUR` (`shared/constants.py:903-911`) already maps all seven kinds, **including `reinstated → REMINT`**. The behaviour table is complete; nothing invokes it.

- **AD-17's sweep guard was never built — a second, independent correctness gap.** The Spine requires that after claiming a row the sweep read the Event's current `event_version` and, if the catalog's is newer, move the row to `held_for_propagation` rather than send it. `apps/delivery/services/delivery_sweep.py` contains **no version check at all**, and `ScheduledSend.Status` (`apps/delivery/models.py:286-297`) is only `pending/sent/cancelled/failed` — there is no held state to move it to. The sweep will send a reminder for an event that already moved, which is precisely the race AD-17 exists to prevent.

- **The Pulse Card has no state treatment, though the Detail Screen does.** `public-pages-and-seo` built status rendering on the public page (`frontend/components/public-event/public-event-page.tsx:192, 293-294`) and the authenticated detail screen (`frontend/app/events/[id]/page.tsx:402-407`). `frontend/components/digest/pulse-card.tsx` reads neither `is_sold_out` nor `status`. FR-53's testable consequence — *"A sold-out event is marked with a 'Sold Out' tag on the Pulse Card and Detail Screen"* — is therefore half-met.

- **Conflict re-evaluation has its function and no trigger.** `detect_conflicts` and `record_detected_conflicts` exist (`apps/personalization/services/conflicts.py:160, 229`), and AD-21 requires the overlap function run "on save, on Personal Event create, edit or import, **and on AD-17 propagation** — never at render". The propagation trigger is the missing one.

- **There is no notification entity for a state change, and no mute.** `NotificationSettings` (`apps/delivery/services/notification_preferences.py:50`) holds `quiet_hours` and `default_reminder_slots` and nothing else. FR-55's per-event mute has no home. `ScheduledSend.stream` has **no default** by AD-20 (`apps/delivery/models.py:316-318`), so a notice must choose one deliberately.

## Success Criteria

### The propagation consumer (AD-17)

- `worker.tasks.propagate_state_change` replaces its placeholder with a real consumer that, for each affected user, applies the change in **one `personal` transaction keyed `(state_change_id, user_id)`**, and **only if** the change's `event_version` exceeds the version on that user's `SavedEvent`.
- It calls each owner's published service and writes nothing itself: **`delivery`**'s `apply_lifecycle_change` for `SCHEDULED_SEND`, **`personalization`** for the `SAVED_EVENT` snapshot and `CONFLICT_PAIR` re-evaluation. AD-16's write ownership is unbroken and the `import-linter` contracts stay green.
- `propagated_at` is set through `ingestion`'s `mark_propagated` **only once every affected user is done**, so a partial run is re-offered rather than lost.
- **No transaction spans both schemas** (AD-3). The sequence is ordered and idempotent instead.
- A **retried**, **partial** or **out-of-order** run neither double-applies nor lets an older change overwrite a newer one — pinned by tests, not by review.
- All seven kinds are handled per `LIFECYCLE_SEND_BEHAVIOUR`: `time_moved`/`postponed`/`reinstated` → re-mint, `cancelled`/`superseded` → cancel and close conflicts, `sold_out`/`detail_changed` → re-stamp and keep.

### The sweep guard (AD-17, previously unbuilt)

- A **new non-terminal `held_for_propagation` status** on `ScheduledSend`, added without disturbing `TERMINAL_STATUSES` — a held row is not terminal and is explicitly re-openable, which every other non-`pending` status is not.
- After claiming a row, the sweep reads the Event's current `event_version` through `ingestion`'s read interface as a **separate, non-transactional read** (the claim transaction stays `personal`-only), and holds rather than sends when the catalog's version is newer.
- Propagation **releases, rewrites or cancels** a held row. A held row is never stranded: a test proves one always reaches a terminal state or returns to `pending`.
- The accepted residual window from AD-17 — a change committing between the version read and the provider call — is **documented and tested as accepted**, not silently tolerated.

### State-change notices (FR-54)

- One notice per event per user, **never repeated**, on the **transactional** stream (AD-20), with the per-kind subjects the PRD fixes verbatim: cancelled, moved to a new date, moved to a new location, sold out.
- **At most one state-change notification per event per day**, enforced and tested.
- **Quiet Hours apply (AD-7), with one exception**: when deferral would push the notice past the event's own start, it sends immediately. A user never travels to a cancelled event because the system was being polite. Both branches are pinned by tests.
- The in-app half is a **dismissible strip on the digest home** listing unseen changes, plus a **persistent banner on the affected Event Detail screen**. Dismissal is what makes "one-time, never repeats" true.
- **No notifications inbox is built.** FR-10's design decision stands — `onboarding-skip-all-state-desktop.html` states the topbar Notifications button is removed because "per PRD FR-10 there is no in-app notifications inbox."
- **No push** (FR-54 defers it to Phase 2+).

### Conflict re-evaluation (FR-55)

- Propagation re-runs the **one overlap function** in `domain/conflict.py` (AD-21) via `detect_conflicts` / `record_detected_conflicts`. No second implementation, and no render-time detection.
- A **cancelled** public event **never auto-cancels a personal event** — the personal event is preserved and the user is notified.
- A new overlap created by a state change surfaces as a **calm, non-blocking "this overlaps with [other event]" message on the Detail Screen**, per the PRD's own wording. It is explicitly **not** FR-58's three-action forced prompt: that pattern is for a conflict the user is creating, and interrupting someone over a change a venue made is the wrong register.
- A **per-event mute**, set from the Detail Screen, suppresses that event's FR-54 notices and nothing else — reminders and the digest are untouched.
- This closes TRACEABILITY's FR-55 gap **by decision**, replacing an inferred-only overlap with FR-58 with an explicit, designed answer.

### Polling (FR-53)

- Re-ingest cadence meets FR-53's floors: **high-priority sources at least every 4 hours, lower-priority at least daily**, through the existing `schedule_sources` / `ingest_source` path.
- A cancelled event is detected within **4h** (high-priority) / **24h** (lower-priority); a postponed event's new time reaches the user's saved snapshot within **4h**.

### Frontend

- `pulse-card.tsx` gains sold-out / cancelled / postponed treatment matching `sold-out-card-state-desktop.html` (self-tagged `FR-53 FR-54`), reusing the **backend's vocabulary** — `Event.Status` is `scheduled`/`postponed`/`cancelled` — exactly as `public-event-page.tsx:279-280` already does.
- The Detail Screen's existing sold-out handling extends to carry the change banner and, when sold out, **removes the "Save Reminder" CTA** per FR-54.
- Colour is never the sole carrier of meaning (WCAG 1.4.1); the `axe-core` zero-serious-violations gate stays green on every touched surface.

### Proof — tests that can fail

- The version gate **at the exact boundary**: a change at the stored version is a no-op; at version+1 it applies.
- An out-of-order run — an older postponement arriving after a newer cancellation — leaves the cancellation intact.
- A retried partial run completes without losing or duplicating a row, and `propagated_at` is set exactly once.
- A held send is released by propagation, and **no code path strands one**.
- `reinstated` re-mints from the surviving `ReminderPlan`, and the old spent key does not block the new send.
- The one-notice-per-event-per-day cap, and the Quiet Hours exception on **both** sides of "would arrive after the event starts".
- A cancelled public event leaves the conflicting personal event present and unmodified.
- A muted event produces no notice while its reminders still fire.
- `ingestion` still never writes to `personal`; the `import-linter` contracts and coverage gates stay green.

## Constraints

**Out of scope:**

- **Webhooks (the FR-53 near-real-time half).** No Eventbrite, Meetup or Luma adapter exists — `event-catalog-ingestion` shipped RSS/ICS only and put official-API and partnership adapters out of scope, and **OQ-5** (the real source list and its ToS reviews) is still open. FR-53 itself names polling "the fallback"; this intent ships the fallback and defers the subscription path to a later intent, once there are real sources to subscribe to.
- **Push notifications** (FR-54, Phase 2+).
- **Automatic rebooking and alternative suggestions** (FR-55, Phase 3).
- **State-change notices for unsaved events** — surfaced only on the public Event URL, which already renders status.
- **A notifications inbox** — FR-10 forbids it by design.
- **The editorial review queue (FR-57)**, which would introduce the editorial-lock that overrides automatic re-gating. Still open from `event-catalog-ingestion`.
- **Public-vs-public conflicts** (Phase 3, per AD-21).

**Still open:**

- **PRD amendment needed (FR-55):** the PRD's calm-message wording and TRACEABILITY's assumption that FR-58's modal covers FR-55 disagree. This intent follows the PRD text; the matrix entry should be updated from PARTIAL to FULL against the design this intent produces.
- **Architecture amendment needed (AD-17):** the "what each change does" rule names moved, cancelled/rejected/superseded, and sold-out/venue-detail. It does **not** name `reinstated`, although `shared/constants.py:906` already maps it to `REMINT` and the model comments it as D12. The Spine prose should be amended to match the code it already has.
- **`held_for_propagation` is a schema change to a hot table.** `ScheduledSend` is swept continuously; the migration and the status-set change need a design pass, not an autopilot edit.
- **Carried forward, unresolved:** OQ-5 (source list + ToS), OQ-7 (Google ICS cache freshness), the beachhead city, the 40-source / 15-per-city launch floor (FR-13), venue renames, and editorial vs. automatic re-gating.

**Decisions taken during capture (2026-11-04):**

1. **Polling only.** Webhooks deferred until real source adapters and their ToS reviews exist.
2. **In-app = dismissible digest strip + Detail banner.** No inbox; FR-10 stands.
3. **FR-55 is calm and non-blocking**, not FR-58's forced three-action prompt.
4. **The AD-17 sweep guard ships in this intent**, because the propagation consumer is what releases a held row — building one without the other leaves the race open.
5. **`reinstated` re-mints and notifies**, confirming the mapping `shared/constants.py:906` already encodes.
6. **The per-event mute is its own `delivery`-owned row**, with no global off switch — FR-54's notices are a correctness mechanism, and a global mute would let a user silently opt into wrong reminders.
7. **Notices go on the transactional stream**, with the per-event mute as the opt-out rather than an RFC 8058 unsubscribe.
8. **Quiet Hours apply, except when deferral would outlast the event's start.**

## Notes

The unusual property of this intent is that almost none of it is a new decision. AD-17 fixes the propagation mechanics, versioning and idempotency; FR-54 fixes the notice copy and the one-per-day rule; FR-55 fixes that a cancellation never auto-cancels a personal event; `LIFECYCLE_SEND_BEHAVIOUR` already encodes the per-kind behaviour table for all seven kinds. Three prior intents cut the seams on purpose and documented the cut.

What remained genuinely open were the eight questions above — and six of the eight exist only because a requirement and a design decision contradicted each other (FR-54's "in-app banner" against FR-10's "no inbox"; the PRD's calm FR-55 message against TRACEABILITY's assumption of FR-58's modal) or because the Spine's prose fell behind its own code (`reinstated`).

**Mockups available:** `sold-out-card-state-desktop.html` (self-tagged `FR-53 FR-54`), `conflict-prompt-desktop.html` and `conflict-indicator-card-state-desktop.html` (`FR-58`, the register this intent deliberately departs from), `event-detail-desktop.html` (`FR-24`).

**Work happens on branch `feature/event-state-sync`.**
