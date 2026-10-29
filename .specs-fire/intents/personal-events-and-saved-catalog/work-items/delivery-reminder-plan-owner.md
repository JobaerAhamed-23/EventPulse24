---
id: delivery-reminder-plan-owner
title: Delivery Reminder Plan Owner
intent: personal-events-and-saved-catalog
complexity: medium
mode: confirm
status: completed
depends_on:
  - repo-hygiene-cleanup
created: 2026-10-29
run_id: run-eventpulse24-019
completed_at: 2026-10-29T03:28:59.656Z
---

# Work Item: Delivery Reminder Plan Owner

## Description

AD-16 assigns `REMINDER_PLAN` to `delivery`, not to `personalization`. FR-20 then requires that a newly created personal event inherits a default plan of **1d + 1hr**.

The Spine settles exactly how the two modules meet:

> `delivery` owns `REMINDER_PLAN`. `personalization` calls `delivery`'s published service to attach the default plan when it creates a `PERSONAL_EVENT` (FR-20). Chosen because PRD **SM-5 targets >80%** of saved cards getting a customized plan — plan edits are the frequent path, personal-event creation the rare one — so the boundary crossing sits on the rare path, and "edit the plan, reschedule its sends" stays inside the module AD-17 already makes the sole rewriter of `SCHEDULED_SEND`.

The `delivery` app currently has an empty `models.py` and an empty `api.py`. This work item builds the **minimum** `delivery` that can legitimately own `REMINDER_PLAN`: the model, its retention category, and the published service that `personalization` will call.

It deliberately builds **nothing else**. Scheduled sends, quiet hours, the FR-9 multi-tier picker and the email adapters are a later intent. Building them here would drag AD-7's sweep, AD-20's mail streams and FR-9–FR-12 into this intent for no benefit.

## Acceptance Criteria

- [ ] `REMINDER_PLAN` is a model in `apps/delivery/models.py`, owned by `delivery` alone. `delivery` writes it; `personalization` never does.
- [ ] The plan holds up to 4 reminder slots, each identified by its own id, drawn from the `ReminderSlot` enum that **already exists** in `shared/constants.py` (`5d`, `2d`, `1d`, `1hr`) plus one custom slot. The enum is reused, never redeclared.
- [ ] `REMINDER_SLOT_OFFSET` — also already in `shared/constants.py` — is the single source for slot → offset arithmetic.
- [ ] The default plan is `DEFAULT_REMINDER_PLAN = (ReminderSlot.ONE_DAY, ReminderSlot.ONE_HOUR)`, which **already exists** in `shared/constants.py`. It is used, never re-declared. AD-16's rule is explicit: "FR-9 and FR-20 both hardcode the default plan as **1d + 1hr**. It is one named constant in `shared/`, beside the confidence thresholds — never two literals that can drift apart."
- [ ] A **published service** is exposed for `personalization` to call, with a signature that makes the ownership visible: it takes the event reference and the actor, and it writes the plan. `personalization` calls it; it does not touch `apps.delivery.models` directly.
- [ ] The `import-linter` contract `models-delivery` (already declared: only `apps.delivery` may import `apps.delivery.models`) keeps passing. `make lint-imports` is green.
- [ ] The plan is attached to **both** a `PERSONAL_EVENT` and a `SAVED_EVENT` (the PRD's Glossary says an Event is "1-to-1-or-0 ReminderPlan", and FR-9's picker applies to public events the user saved). The attachment mechanism for a saved public event must not require a FK across the AD-3 wall.
- [ ] The user can **remove all reminders**. An empty plan is a valid state, not an error.
- [ ] `Pulse Ping` is **not** part of any reminder plan (PRD Glossary). The model has no slot that could express it.
- [ ] The plan declares a retention category (`RetentionCategory.ACCOUNT_CONTENT` — it is user-derived content tied to the account).
- [ ] No `SCHEDULED_SEND` table, no Celery task, no beat entry, no email adapter is created. This work item is the owner, not the scheduler.
- [ ] Tests cover: attaching the default plan on personal event creation; the default being exactly `(1d, 1hr)`; removing all reminders leaving an empty plan; and `personalization` being unable to write the table directly (asserted structurally, or by a test that the import contract would catch it).

## Technical Notes

The `import-linter` contract `models-delivery` is already declared in `backend/pyproject.toml`:

```toml
[[tool.importlinter.contracts]]
id = "models-delivery"
name = "AD-2 only apps.delivery imports apps.delivery.models (others call its services)"
type = "protected"
protected_modules = ["apps.delivery.models"]
allowed_importers = ["apps.delivery"]
```

So `personalization` calling `delivery`'s service — not importing its models — is already enforced by the build. This is the mechanism that makes AD-16's boundary real rather than aspirational.

Follow `apps/ingestion/services/` as the reference for what a "published service" looks like in this codebase: a module under `apps/<app>/services/`, plain data in and out, no `request` object, and `now` passed explicitly rather than read from the clock.

`shared/constants.py` already contains everything this work item needs:

```python
class ReminderSlot(StrEnum):
    FIVE_DAYS = "5d"
    TWO_DAYS = "2d"
    ONE_DAY = "1d"
    ONE_HOUR = "1hr"

REMINDER_SLOT_OFFSET = { ... }

DEFAULT_REMINDER_PLAN = (ReminderSlot.ONE_DAY, ReminderSlot.ONE_HOUR)
```

Read that file before writing anything. The scaffold anticipated this intent, and re-declaring any of those names is the specific drift AD-16 warns about.

The ADR about the AD-3 wall matters for the attachment mechanism. A `REMINDER_PLAN` belonging to a `SAVED_EVENT` cannot FK to the `catalog` event. The plan should reference the *personal-side* record it belongs to, and the snapshot of the catalog event's time lives on the `SAVED_EVENT` row. The plan's slot offsets are relative offsets before the event start, so the plan itself needs no absolute time — which is what makes it portable across a postponed event.

## Dependencies

- repo-hygiene-cleanup
