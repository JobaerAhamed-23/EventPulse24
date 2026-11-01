---
id: email-templates-and-unsubscribe
title: The mail itself — three bodies and a one-click unsubscribe
intent: delivery-and-reminders
complexity: medium
mode: confirm
status: completed
depends_on:
  - scheduled-send-model
created: 2026-10-31
run_id: run-eventpulse24-023
completed_at: 2026-10-31T16:18:49.558Z
---

# Work Item: The mail itself — three bodies and a one-click unsubscribe

## Description

The rendered email bodies — a reminder, the daily digest, and a state-change notice — plus the RFC 8058 one-click unsubscribe that the bulk stream requires and that FR-11 scopes **per event**.

`EmailMessage` already carries `to`, `subject`, `text_body`, `html_body` and `unsubscribe_url`, and `EmailPort.send` already refuses a bulk send with no unsubscribe URL. Nothing renders anything into those fields yet.

The unsubscribe is the part with a real rule behind it. FR-11: "A reminder email contains 1-click unsubscribe for that event's reminders (**does not unsubscribe from Pulse Ping**)." So there are two scopes, not one, and the link has to carry which — signed, so that a link forwarded or scraped cannot unsubscribe someone else.

## Acceptance Criteria

- [ ] Three renderers producing `EmailMessage` values: **reminder**, **digest**, **state-change notice**. Each returns both `text_body` and `html_body`; neither is optional, because a text-only client is not an error state.
- [ ] Voice follows EXPERIENCE.md §3: calm, no exclamation marks, no emoji, no urgency. Subject lines are plain and say what the mail is.
- [ ] The digest body carries the **3 cards** the composition already produced, with the stripe-and-label pairing the UI uses — **colour is never the sole carrier of meaning**, in email as on the web.
- [ ] Every link into the app is **server-side click-trackable**, because SM-2 measures the digest CTA click and explicitly rejects open-pixel measurement as unreliable.
- [ ] **One-click unsubscribe, two scopes**: a reminder's link unsubscribes **that event's reminders only**; the digest's link unsubscribes the **Pulse Ping**. A reminder unsubscribe never touches the Ping, and a test asserts it.
- [ ] The unsubscribe link is a **signed token** naming user, scope and target. It cannot be forged, cannot be edited into another user's unsubscribe, and does not expire into uselessness. Reuse the project's existing signing helper rather than adding a scheme.
- [ ] An **unauthenticated `POST` endpoint** honours RFC 8058's one-click semantics — a `GET` from a link scanner must not unsubscribe anyone. Both behaviours are tested.
- [ ] Unsubscribing a scope **cancels that scope's pending sends** through the minting service, rather than leaving rows that are swallowed at send time.
- [ ] A confirmation page the link lands on, in the calm voice, saying exactly what was turned off and offering the inverse.
- [ ] The digest's `unsubscribe_url` is always populated — `EmailPort.send` raises otherwise, and a test asserts the bulk path never raises.
- [ ] **No email address reaches a log sink** from any renderer (AD-13).
- [ ] Rendering is pure and snapshot-tested: no clock, no database reads inside the renderer, so bodies are asserted without a network or a fixture user.

## Technical Notes

Keep the renderers free of model instances — pass frozen dataclasses in, the way `catalog_read.PublicEvent` already does for the catalog. That keeps the templates testable and keeps `delivery` from reaching across module walls to render a title.

The state-change notice body is written here but **not minted** by this intent — FR-53/54 is the next intent's work. Rendering it now costs little and means the following intent is an API and a trigger rather than a fresh template pass. Say so in the module docstring so it is not mistaken for dead code.

## Dependencies

- scheduled-send-model
