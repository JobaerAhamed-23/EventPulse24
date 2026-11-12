---
id: fr-20-reminder-defaults
title: FR-20 — design the reminder default, and prove you can clear it
intent: traceability-reconciliation
complexity: medium
mode: confirm
status: completed
depends_on: []
created: 2026-11-12
run_id: run-eventpulse24-028
completed_at: 2026-11-12T05:25:37.921Z
---

# Work Item: FR-20 — design the reminder default, and prove you can clear it

## Description

FR-20 asks for one thing and its opposite: *"A new Personal Event has a Reminder Plan of
1d + 1hr by default"* and *"The user can remove all reminders."* The default is built —
`personal_events.py` imports `attach_default_plan` from `apps.delivery.services.reminder_plans`,
and `personal_events.py:285` is explicit that *"FR-20's default is a property of creation."*

What does not exist is any design. `reminder-picker-desktop.html` is self-tagged `FR-9`
(reminders on *saved public* events) and nothing else; DESIGN.md and EXPERIENCE.md never
mention FR-20. So the personal-event reminder default has been built from FR-9's UI by
adjacency — which is exactly what the matrix calls `PARTIAL (inferred only)`.

The consequence most likely to fail is the second one. "Remove all reminders" is a legitimate
empty state that a well-meaning validator, a `min_length`, or a re-apply-the-default-on-save
path will quietly forbid — and the user would then be unable to turn reminders off at all.

## Acceptance Criteria

- [ ] A mockup exists under `mockups/`, self-tagged `FR-20` in its own header comment, showing
      the Personal Event reminder state: the 1d + 1hr default as created, an edited plan, and
      **the deliberately empty plan**.
- [ ] A named section in DESIGN.md or EXPERIENCE.md cites `FR-20` directly and describes how
      the personal-event case differs from FR-9's, or states plainly that it reuses
      `Input.ReminderSlot` and why that is correct.
- [ ] A test asserts a newly created Personal Event has exactly the 1d + 1hr plan.
- [ ] **A test asserts a user can remove every reminder slot, that the resulting plan persists
      as empty, and that a subsequent edit or save does not silently re-apply the default.**
- [ ] A test asserts the empty plan produces no `ScheduledSend` rows — removing reminders
      actually stops reminders, rather than only hiding them in the UI.
- [ ] If any consequence fails, the code is fixed; the PRD wins.
- [ ] Tests name `FR-20` so the requirement is greppable from the test suite.

## Technical Notes

`apps/delivery/models.py:32` defines `_SLOT_COLUMNS = frozenset({"slots", "default_reminder_slots"})`
and `:39` distinguishes `NOTIFICATION_PREFERENCE.default_reminder_slots` ("what new plans
start as") from FR-9's per-event slots. Read that distinction before designing — the empty
state has to be empty on the *plan*, not on the preference, or clearing one event's reminders
would change the default for every future event.

`calendar_sync.py:19` says an imported calendar event gets *"the same FR-20 reminder default"*
as a manually created one. Worth a test: the default is a property of creation regardless of
which path created it.

Per the house style, the mockup carries no component kit, uses the CSS-custom-property
tokens, and ships `data-theme="dark"` on `<html>`.
