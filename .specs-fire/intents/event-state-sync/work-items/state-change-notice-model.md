---
id: state-change-notice-model
title: One calm notice, once, and a way to silence it — the state-change notice
intent: event-state-sync
complexity: high
mode: validate
status: in_progress
depends_on: []
created: 2026-11-04
---

# Work Item: One calm notice, once, and a way to silence it — the state-change notice

## Description

FR-54 asks for "a single, calm in-app + email notification", "one-time per event", "never repeats", and "at most one state-change notification per event per day". FR-55 adds that a user can mute them for a specific event from the Detail Screen. Nothing of this exists.

`NotificationSettings` (`apps/delivery/services/notification_preferences.py:50`) is a frozen dataclass of exactly two things: `quiet_hours` and `default_reminder_slots`. There is no notice entity, no mute, and no per-event preference of any kind.

The notice is also two deliveries from one record: an email, and the in-app surfaces decided during capture — a dismissible strip on the digest home and a banner on the affected Detail screen. Both read the same row, or they will drift.

**This item needs a design doc (Checkpoint 1) before any code.** It introduces an entity, chooses an AD-20 stream, and defines a `due_at` rule that deliberately departs from AD-7.

## Acceptance Criteria

- [ ] A **notice entity** in `personal`, owned by `delivery` (AD-16), recording the event, the user, the change kind, the version it was raised for, and whether it has been seen.
- [ ] **One notice per event per user, never repeated.** A second change of the same kind does not raise a second notice; the design states what a *different* kind does.
- [ ] **At most one notice per event per day**, enforced in the write path and tested at the boundary.
- [ ] The email goes on the **transactional** stream. `ScheduledSend.stream` has no default by AD-20 (`models.py:316-318`), so the choice is explicit, and the item records why transactional is right: a one-time correction about a record the user themselves created is not a broadcast.
- [ ] **No RFC 8058 unsubscribe URL**, and none implied — `EmailPort.send` refuses a bulk send without one, and this is not a bulk send. The per-event mute is the opt-out.
- [ ] **Quiet Hours apply (AD-7), with one exception**: when deferral would push the notice past the event's own start, it sends immediately. Both branches tested, including an event starting *inside* the quiet window.
- [ ] A **per-event mute**, `delivery`-owned, settable and clearable. A muted event raises no notice and sends no email; its **reminders and digest placement are untouched**.
- [ ] **No global off switch.** Recorded as a decision: FR-54's notices are the mechanism that keeps reminders correct, so a global mute would let a user silently opt into wrong reminders.
- [ ] A notice is **raised by propagation, not by the sweep** — it is a consequence of a catalog change reaching a user, not of a send going out.
- [ ] Tests: the one-per-day cap at the boundary; a muted event producing no notice while its reminders still fire; the Quiet Hours exception on both sides of "would arrive after the event starts"; a repeated propagation raising exactly one notice.

## Technical Notes

**Design-doc decisions (Checkpoint 1):**

- **One entity or two.** A notice row plus a `ScheduledSend` for its email, or the `ScheduledSend` alone with the in-app surfaces reading it. The second is fewer tables; the first survives the email being suppressed by a mute while the in-app banner still shows. The design picks and justifies.
- **"One-time per event" versus "one per day".** FR-54 says both, and they are different rules. An event cancelled, reinstated and cancelled again in a week is the case that separates them. The design states the composed rule precisely.
- **What "seen" means.** Dismissing the digest strip, opening the Detail screen, or both. This is what makes "never repeats" true, and it is a product decision with a visible consequence.
- **The quiet-hours exception's exact predicate.** "Would arrive after the event starts" needs the event's start in the user's zone, the window end, and a margin — a notice landing ninety seconds before the doors open is technically in time and practically useless. The design names the margin or argues there is none.
- **Where the mute lives.** Beside `NotificationPreference` (one row per user) or as its own per-(user, event) table. The former does not fit a per-event fact.

**Reuse, do not reinvent:** the quiet-hours arithmetic is `domain/quiet_hours.py` via `NotificationSettings.quiet_hours`; AD-7's send-key rules are in `apps/delivery/send_keys.py`; the audit shape is `delivery/services/audit.py`.
