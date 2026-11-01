---
id: delivery-and-reminders
title: Delivery, Reminders & Pulse Ping
status: completed
created: 2026-10-31
completed_at: 2026-11-01T08:46:47.709Z
---

# Intent: Delivery, Reminders & Pulse Ping

## Goal

Make the product **send**. Today EventPulse24 composes a Pulse Digest every morning and leaves it in a database row — the user sees it only if they think to open the site. This intent builds the delivery layer the whole architecture was shaped around: `SCHEDULED_SEND`, the due-index sweep, Quiet Hours, and the two surfaces that let a user say when and how often to hear from us.

It closes **FR-9** (multi-tier reminder picker), **FR-10** (Pulse Ping — one daily notification), **FR-11** (email multi-tier reminders) and **FR-12** (Quiet Hours), and it finishes **FR-20**, whose default reminder plan has been a module constant with no way for a user to change it.

The codebase names this intent by hand. `worker/tasks.py:221`, in `schedule_digests`' own docstring:

> **It sends nothing** — the send is the delivery intent's job.

## Users

- **The user who asked for 8am** (UJ-1, UJ-3), who chose a delivery time during onboarding and has never once been written to at that time. The digest exists; it has never arrived.
- **The user who saved an event and set reminders** (Flow: Detail → Edit reminders), who picks 1d + 1hr and is owed two emails — and today gets a `ReminderPlan` row that nothing reads.
- **The user who sleeps**, who needs 10pm–8am to mean something before they will trust a daily sender at all.
- **The user whose event moved**, whose reminders must follow the new date and must not fire for the old one. `propagate_state_change` already runs and has had nothing to call.

## Problem

- **Nothing in the system has ever sent an email.** `ports/email.py` defines `EmailPort`, `Stream.TRANSACTIONAL` and `Stream.BULK`, and `adapters/email/{smtp,memory}.py` implement them. Grep finds **no caller anywhere**. The port has been built and left unwired since the scaffold.
- **`SCHEDULED_SEND` does not exist.** AD-7 is written around it — the due-index sweep, the five send-key shapes, "the schedule is never in the broker" — and the table appears in the repository **only inside docstrings**. No model, no migration, no code.
- **The Reminder Plan is write-only.** `apps/delivery/models.py` has `ReminderPlan` with its 0–4 slot bound, and `services/reminder_plans.py` is 321 lines of working command surface. `apps/delivery/api.py` is **three lines** — an empty `Router()` with no endpoints. A user has no way to see or set a plan, and nothing turns a plan into a send.
- **Quiet Hours is not implemented at all.** `domain/` holds `conflict.py`, `ranking.py`, `event_fit.py` and six more; there is no `quiet_hours.py`, though ARCHITECTURE-SPINE.md line 71 lists "quiet-hours due-time shifting" among the things that belong there. A grep for `quiet_hours` finds one comment.
- **There is no settings surface.** The frontend has ten routes and none of them is under `/settings`. Delivery time is set once, in onboarding step 3, and can never be changed again. Quiet hours has nowhere to be set. The sidenav's Settings slot has no destination.
- **FR-20 is a constant, not a preference.** `attach_default_plan` reads `shared.constants.DEFAULT_REMINDER_PLAN` — the literal `(ONE_DAY, ONE_HOUR)`. The UX spec's `/settings/reminders` is a *Default Reminder Plan editor*; the default has to become the user's.

## Success Criteria

### The schedule — `SCHEDULED_SEND` and the sweep (AD-7)

- A `SCHEDULED_SEND` table in the `personal` schema, **owned by `delivery`** (AD-16), carrying a `(due_at, status)` index and the send key under a unique constraint.
- The **key is minted once at row creation and never derived from `due_at`**, in the shapes AD-7's table fixes. Quiet Hours, timezone, delivery-time and plan changes **rewrite `due_at` on `pending` rows only and never touch the key**, so no recompute can produce a second send.
- The worker sweeps due rows off the **existing 60s tick** (`config/celery.py` `TICK_SECONDS = 60.0` already satisfies AD-7's ≤60s rule — no new beat entry). Rows transition under `SELECT … FOR UPDATE SKIP LOCKED`, so adding worker replicas can never double-send.
- **A reminder is never a per-reminder Celery task.** Postgres rows are the only source of truth for what is due; a total Redis loss costs in-flight pipeline jobs and not one user's reminder.
- Delivery is at-least-once with dedupe at the send boundary: the send key is passed to the provider as its idempotency key, and a `sent` row is never rekeyed.

### Quiet Hours (FR-12)

- A pure `domain/quiet_hours.py` that shifts a due instant to the window end, with no database and no Django import — testable on its own, like `domain/conflict.py`.
- **Quiet Hours is applied when `due_at` is computed or recomputed, never as a skip at send time** (AD-7). A deferred send is silently moved — never dropped, never re-delivered the next day.
- Windows that **cross midnight** (the 10pm–8am default) are the normal case, not an edge case, and are evaluated on **wall-clock local time in the user's zone**, with DST handled by the same `domain/timezones.py` the rest of the project uses.
- A Pulse Ping that lands inside the window is deferred to the window end, with no notification stack and no next-day surprise.

### Reminders (FR-9, FR-11, FR-20)

- `GET` / `PUT` a per-event Reminder Plan through `delivery`'s own router, filling the empty `apps/delivery/api.py`. Saving a plan **mints, rewrites or cancels that event's pending sends in the same transaction**.
- A plan of **0 slots is a valid saved state**, not an error: "No reminders. You'll still see this event in Pulse Digest."
- Each slot produces **one transactional email** at its offset before the event start. A user with 5d/2d/1d/1hr gets four emails, one per slot.
- Reminder mail carries **RFC 8058 one-click unsubscribe scoped to that event's reminders**, which does **not** unsubscribe the user from the Pulse Ping.
- **The default plan becomes the user's**, editable at `/settings/reminders`. `attach_default_plan` reads it and falls back to `shared.constants.DEFAULT_REMINDER_PLAN` for a user who has never set one — so FR-20's default survives as the fallback rather than the only answer.

### The Pulse Ping (FR-10)

- **One email per user per day**, at their chosen local delivery time, carrying the digest. *Decided with the user 2026-10-31: in MVP the digest email **is** the Pulse Ping.* AD-7's separate `pulse_ping` key stays reserved for the Phase 2 push channel; MVP mints the `digest` key only.
- It goes on the **bulk** stream with an unsubscribe URL; reminders go on **transactional**. The two never share a stream (AD-20), and `EmailPort.send` already refuses a bulk send with no unsubscribe URL.
- **The suppression rule holds and is tested:** zero qualifying public events **and** zero personal events in the next 48 hours → **no Ping**. One or more personal events with zero public events → **Ping sent**, with a personal-only digest. Three qualifying events → exactly **one** Ping, never three.
- Suppression is counted, because SM-C1 targets a suppression rate **≥30%** and treats a *higher* number as better.

### Rescheduling and propagation (AD-17)

- When `propagate_state_change` moves an event, `delivery`'s published service **cancels the `pending` rows, bumps `event_version` and mints new ones**. The old key stays spent, so a `1d` reminder already sent for the old date does not block the `1d` reminder for the new one.
- A cancelled, rejected or superseded event cancels its pending sends. Un-saving an event or deleting a personal event cancels them too.
- Changing quiet hours, timezone or delivery time **rewrites `due_at` on pending rows in place** — no cancel, no re-mint, no new key.

### The surfaces

- **`/events/:id/reminders`** — the picker, as Amendment A-21 draws it: the A-8 shell, the crumb `Digest · {event} · Edit reminders`, four slot chips (5d/2d/1d/1hr), one custom slot, and the action bar. *Decided with the user 2026-10-31: a full route, not a sheet.* The IA table's 14 routes gain a 15th, recorded as an amendment note.
- Chip selection is **ink inversion, never terracotta** (`component.input.reminder.slot`). A chip whose delivery would land inside Quiet Hours **dims to 40% and shows "Will deliver at {end of quiet hours}."** — still selectable, and selecting it queues the deferred send.
- **`/settings/reminders`** — the Default Reminder Plan editor, with inline save and the locked failure line "Couldn't save. We'll try again on your next change."
- **`/settings/quiet-hours`** — the window editor, defaulting to **10pm–8am**, with the locked label "10pm–8am. Nothing during this window." Per-day-of-week windows are **Pro (FR-51) and out of scope**; Free sees the single window.
- Locked microcopy is used verbatim: "Remind me:", the two labels above, and the empty state "No reminders. You'll still see this event in Pulse Digest."
- The sidenav's **Settings** entry becomes a real link.

### Proof — tests that can fail

- Domain: Quiet Hours shifting, including a midnight-crossing window, a DST transition, a due time already outside the window, and a window that covers the whole day.
- Model: the send-key unique constraint; a recompute that rewrites `due_at` and leaves the key; the `(due_at, status)` index actually used by the sweep query.
- Sweep: two concurrent workers never double-send the same row; a crashed worker's row becomes claimable; an at-least-once retry dedupes at the boundary.
- Suppression: all four FR-10 consequences, each as its own test.
- Propagation: an event that moves cancels and re-mints; a `1d` already sent for the old date does not block the new one; a cancelled event sends nothing.
- Streams: a reminder is transactional, the digest is bulk, and a bulk send with no unsubscribe URL raises.
- Frontend: the picker's chip states including the 40% dimmed Quiet-Hours chip and its tooltip, 0-slot save, the custom slot, both settings forms, and every empty/loading/error state.
- An **end-to-end proof** in the style of earlier intents: set quiet hours, save an event with a plan whose slot falls inside the window, run the sweep against the fake email adapter, and assert the mail landed at the window end with the right stream and key.
- `make client` stays the contract: regenerated for the new endpoints, and CI's diff check passes.

## Constraints

- **Reuse, never rebuild.** `ports/email.py` and both adapters, `ReminderPlan` and `services/reminder_plans.py`, `shared.constants.ReminderSlot` / `REMINDER_SLOT_OFFSET` / `DEFAULT_REMINDER_PLAN`, the 60s tick, and the digest composition from run 021 all exist and are the starting point. AD-16 forbids a second declaration of any of them.
- **AD-7** governs the schedule: due-index sweep, key minted once, `SKIP LOCKED`, and the schedule never in the broker.
- **AD-16**: `delivery` owns `REMINDER_PLAN` and `SCHEDULED_SEND`. `personalization` reaches them only through `delivery`'s published services, as it already does for `attach_default_plan`.
- **AD-17**: propagation rewrites and cancels `SCHEDULED_SEND` through `delivery`'s published service, per user, versioned and idempotent.
- **AD-20**: transactional and bulk never share a stream, and `stream` has no default.
- **AD-19**: the frontend reaches the API only through the generated client; new endpoints go through `make client`.
- **AD-13**: email addresses never reach a log sink. Send logs carry the user id and the send key, never the recipient.
- **DESIGN.md and EXPERIENCE.md govern** the two settings routes and the picker, with `reminder-picker-desktop.html` and `settings-desktop.html` as visual references; where a mockup drifts from the spine, the spine wins.
- **Spacing stays on the DESIGN.md scale** — `tests/spacing-scale.test.ts` enforces it.
- **Works fully offline** with the fake adapters (`ADAPTER_MODE=fake`), as every previous intent. The memory email adapter is the test seam.

## Notes

**Decisions captured with the user (2026-10-31):**

1. **The digest email is the Pulse Ping** in MVP — one email per user per day, not two. The `pulse_ping` send key is reserved for the Phase 2 push channel and is not minted now.
2. **Quiet Hours lives in a new `delivery`-owned `NotificationPreference` model**, not on `personalization`'s `DigestPreference`. `delivery` reads its own table on the hot path, keeping AD-16 ownership clean. The cost — two preference rows per user, and a settings page that writes to two modules — was accepted deliberately. `DigestPreference`'s docstring anticipated this reconsideration; this is its answer.
3. **The reminder picker is a full route**, `/events/:id/reminders`, matching the A-21 mockup rather than the IA table's silence.
4. **Only `/settings/reminders` and `/settings/quiet-hours`** are in scope. `/settings/sources` (FR-13/16) and `/settings/privacy` (FR-22/52) stay with the intents that own their backends.

**Closed by decision 2 and the `/settings/reminders` editor:** the TRACEABILITY.md gap where **FR-20 is `PARTIAL — inferred only`**, with no design of its own. The default reminder plan stops being a module constant and becomes a stored user preference with a designed editor, which is what FR-20 always meant.

**Carried into the FR-53/54 intent by decision (2026-10-31):** wiring `worker/tasks.py`'s
`propagate_state_change` placeholder. AD-17 marks `propagated_at` only once every owner has
applied a change, and the `personalization` half — the `SAVED_EVENT` snapshot update and
conflict re-evaluation — belongs to that intent. The `delivery` half
(`apply_lifecycle_change`) is built, published and tested in this intent, ready to be called.

**Out of scope, later intents:** FR-51 per-day-of-week quiet hours (Pro), FR-53/54 state-change notices to users — which become cheap once this intent's send layer exists, and are the natural next intent — FR-25 "less like this", FR-59 report-event, FR-48/49/52 Pro tier and export, `/settings/sources`, `/settings/privacy`, `/browse`, and Phase 2 push on any channel.

**Retention follow-up (recorded 2026-10-31):** `SCHEDULED_SEND` carries `ACCOUNT_CONTENT` so a
long-lead pending reminder can never be purged before it fires. The consequence is that `sent`
rows outlive PRD §10.2's 90-day email-delivery-events policy. Closing that needs a status-aware
prune in the retention sweep, and belongs to whichever later item touches it.

**Watch for:** `DEFAULT_REMINDER_PLAN` currently has two readers once this ships — the user's stored default and the constant fallback. The constant must stay the fallback and must not be duplicated into `delivery` (AD-16).
