---
id: notice-composition-and-email
title: Four subjects the PRD already wrote — the state-change email
intent: event-state-sync
complexity: medium
mode: confirm
status: completed
depends_on:
  - state-change-notice-model
created: 2026-11-04
run_id: run-eventpulse24-025
completed_at: 2026-11-10T08:43:52.084Z
---

# Work Item: Four subjects the PRD already wrote — the state-change email

## Description

FR-54 fixes the copy, which is unusual and makes this item narrow. The subjects are given verbatim:

- `EventPulse24: [event name] was cancelled.` — all future reminders suppressed
- `EventPulse24: [event name] was moved to [new date].` — reminders re-scheduled to the new time
- `EventPulse24: [event name] moved to [new location].` — map pin updated
- `EventPulse24: [event name] is sold out.` — Detail shows the badge and **removes the "Save Reminder" CTA**

This item renders those into the existing email machinery and nothing more. The entity, the stream, the cap and the mute are `state-change-notice-model`'s; the decision to send is `propagation-consumer`'s.

## Acceptance Criteria

- [ ] A template per change kind, using the PRD's subjects **exactly** — a test asserts the literal strings, so a well-meaning rewrite fails rather than ships.
- [ ] Templates follow the existing `delivery/services/email_templates.py` conventions, including the plain-text alternative.
- [ ] The body states **what changed and what it means for the user's reminders** — "your reminders have been rescheduled" / "your reminders have been cancelled" — because the reminder consequence is the reason the email is correctness-critical rather than informational.
- [ ] A link to the event's Detail screen, where the banner and the mute control live.
- [ ] **`reinstated` has copy.** It is the seventh kind, it re-mints reminders, and the PRD names no subject for it. This item writes one in the same register and records that it is ours, not the PRD's.
- [ ] `detail_changed` either has copy or is explicitly **not notified** — FR-53 is clear that not every change deserves a notification ("would be engagement-trap"), and a venue detail edit is the likeliest candidate for silence.
- [ ] **No unsubscribe URL** on a transactional send, and no footer implying one exists.
- [ ] The event name is rendered safely for an untrusted ingested string — no injection into the subject line, no unescaped HTML in the body.
- [ ] A missing or empty event name degrades to something legible rather than `EventPulse24: was cancelled.`
- [ ] Tests: one per kind asserting the subject; the escaping case; the empty-name case; a muted event producing no send.

## Technical Notes

`apps/delivery/services/email_templates.py` and `delivery_messages.py` hold the existing reminder and Pulse Ping templates — the house voice is established there and should not be re-derived. `EmailPort.send` enforces the AD-20 stream rules, including its refusal of a bulk send with no unsubscribe URL; a transactional send must not be made to look bulk.

The "moved to [new location]" case needs the venue, which lives in `catalog`. The notice carries what it needs from the propagation moment rather than reading `catalog` at render time, for the same reason `SAVED_EVENT` holds a snapshot — but the display name resolving through `catalog` at read time is the established pattern for saved events, so the design of `state-change-notice-model` decides which applies and this item follows it.
