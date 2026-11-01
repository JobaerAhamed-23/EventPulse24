---
id: notification-preferences
title: The notification preference — quiet hours and the user's own default plan
intent: delivery-and-reminders
complexity: medium
mode: confirm
status: completed
depends_on: []
created: 2026-10-31
run_id: run-eventpulse24-023
completed_at: 2026-10-31T13:15:40.916Z
---

# Work Item: The notification preference — quiet hours and the user's own default plan

## Description

A `NotificationPreference` model and its command service, **owned by `delivery`** (AD-16): one row per user holding the Quiet Hours window and the user's default Reminder Plan.

**This is a decision, taken with the user on 2026-10-31, not a default.** The alternative was three more columns on `personalization`'s `DigestPreference`, which already holds `delivery_time` and `timezone`. That model's own docstring invites the reconsideration — "the shape is reconsidered when a second, genuinely separate preference arrives" — and this is the arrival. The answer is a separate row, because `delivery` reads the window on the hot path of **every** `due_at` computation, and AD-16 makes write ownership total: a `delivery`-owned table that `delivery` reads directly beats a cross-module read through a published service on the path that runs most often.

The accepted cost is two preference rows per user and a settings surface that writes to two modules. That is recorded in the brief so a later reader does not "fix" it by merging the rows.

The second field is the point of FR-20. `attach_default_plan` currently reads the module constant `DEFAULT_REMINDER_PLAN` — the literal `(ONE_DAY, ONE_HOUR)` — and a user has no way to change what new saves get. `/settings/reminders` is specified as a *Default Reminder Plan editor*, so the default becomes the user's, with the constant surviving as the fallback.

## Acceptance Criteria

- [ ] `NotificationPreference` in `apps/delivery/models.py`, in the `personal` schema, with `retention_category` set and the user held **by value** (`user_id`, no FK to `User`) — the OQ-8 convention every other model in this project follows.
- [ ] One row per user, under a unique constraint, created lazily with defaults on first read so an account that predates this item is never missing one.
- [ ] **Quiet Hours**: `quiet_hours_start` and `quiet_hours_end` as local wall clocks (`TimeField`), defaulting to **22:00–08:00**. A null pair means "no quiet hours" and is a valid state.
- [ ] The window's **zone is not stored here.** The user has exactly one zone, on `DigestPreference`, and a second copy would drift. The service that computes `due_at` reads the zone from `personalization`'s published interface — the rare path, read once per computation batch, not per row.
- [ ] **Default reminder plan**: `default_reminder_slots` as a JSON array, under the same "at most 4" check constraint as `ReminderPlan` — expressed with `jsonb_array_length`, reusing `SLOTS_MAX`, never a second literal. An empty array is valid and means "new saves get no reminders".
- [ ] **`shared.constants.DEFAULT_REMINDER_PLAN` stays the fallback and is not duplicated** (AD-16). A user who has never opened `/settings/reminders` gets exactly today's behaviour.
- [ ] `attach_default_plan` in `services/reminder_plans.py` is changed to read the user's default and fall back to the constant. Its docstring, which today says "the default plan — 1d + 1hr (FR-20)", is updated to say where the default now comes from.
- [ ] A command service: read the preference, set the window, set the default plan. Every write goes through it and writes a `DeliveryAuditEntry` via `write_audit`, as the existing delivery services do.
- [ ] The window is **validated in the command, not by a check constraint** — a full-day window is rejected with a readable error, matching how `DigestPreference` validates its zone and city (the database cannot know what the domain considers a valid window).
- [ ] A published read for `personalization` and the API layer, returning a frozen dataclass and **never a model instance**, matching `catalog_read.PublicEvent`.
- [ ] Migration applies cleanly; a backfill is unnecessary by construction (lazy creation) and the docstring says why.
- [ ] Tests: defaults on first read; the unique constraint; the slot bound at 0, 4 and 5; a rejected full-day window; `attach_default_plan` honouring a user default and falling back to the constant; the audit entries.

## Technical Notes

Put the default window in `shared/constants.py` beside `DEFAULT_REMINDER_PLAN` and `DEFAULT_DIGEST_DELIVERY_TIME`, not in the model — `quiet-hours-domain` needs it too and must not import `delivery`.

The `jsonb_array_length` CHECK is not obvious and the existing `ReminderPlan` model explains why in a comment worth re-reading: Django's `__len` transform renders `(slots -> 'len') <= '4'`, which reads a key named "len", yields NULL for every array, and a CHECK that evaluates to NULL **passes**. Reuse `_SLOTS_LENGTH_AT_MOST_4`'s approach rather than rediscovering this.

## Dependencies

(none)
