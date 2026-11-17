---
id: pulse-ping-control
title: Let a user turn the daily Pulse Ping off — FR-10
intent: traceability-gap-closure
complexity: medium
mode: confirm
status: completed
depends_on: []
created: 2026-11-17
run_id: run-eventpulse24-036
completed_at: 2026-11-17T15:19:19.989Z
---

# Work Item: Let a user turn the daily Pulse Ping off — FR-10

## Description

Onboarding tells every new user *"One calm Pulse Ping per day. It links to your brief. **You
can change this anytime** — and quiet hours come later in Settings."*
(`frontend/components/onboarding/onboarding-flow.tsx:86`).

They cannot. `NotificationSettingsIn` (`backend/apps/delivery/schemas.py:267`) carries
`quiet_hours`, `quiet_hours_overrides`, `default_reminder_slots` and `digest` — **no ping
field** — and `/settings/general` has no row for one. The only way to stop the ping is the
RFC 8058 one-click unsubscribe link inside a ping the user must first receive.

The storage already exists: `ping_unsubscribed` on `NotificationPreference`
(`migrations/0004_notificationpreference_ping_unsubscribed`), already honoured by the
suppression path and already written by the unsubscribe token endpoint. **This is wiring, not
new machinery** — expose the existing column through the settings API and give it a row.

## Acceptance Criteria

- [ ] `NotificationSettingsIn` gains an optional ping on/off field, following the schema's established patch semantics: an omitted field means "leave it alone".
- [ ] `GET /api/personal/notification-settings` returns the current ping state so the UI can render the switch in the right position on first paint.
- [ ] `PUT` persists it to the **existing** `ping_unsubscribed` column — no second column, no parallel preference.
- [ ] Turning the ping **off** cancels that scope's pending sends, exactly as the RFC 8058 unsubscribe path already does, so mail the user just turned off is not delivered afterwards.
- [ ] Turning it off leaves **every reminder plan alone** — the two scopes never touch, which is the rule the unsubscribe endpoint's own docstring states.
- [ ] A Settings row renders on `/settings/general` using the existing `SettingRow` + `SwitchControl` components, with inline save feedback via the existing `settings-inline-save` pattern.
- [ ] The row states what the ping is in one calm line; no new copy vocabulary is invented.
- [ ] Round-trip proven: toggle, reload the page, the state persists.
- [ ] The onboarding sentence at `onboarding-flow.tsx:86` is now true as written and is **left unchanged**.
- [ ] Backend and frontend suites pass; `make lint-backend` and `pnpm lint` clean for touched files.

## Technical Notes

**Reuse the components, do not add a pattern.** `/settings/general` already mounts
`DigestPersonalEvents`, `DigestDeliveryTime`, `DigestTimezone`, `QuietHoursWindow`,
`WeekdayQuietHours` and `DefaultReminderSlots`. `components/settings/switch-control.tsx` and
`setting-row.tsx` exist and carry the mockup's switch semantics (`36fcee4`). The new row is
one more of the same.

**Mind the polarity.** The column is `ping_unsubscribed` (true = off) and the UI switch reads
"Daily Pulse Ping: ON". Invert at one boundary only, name it clearly, and do not let a
double negative leak into the component.

**The actor comes from the session, never the payload** — `preferences_api.py` states this
rule at the top of the file (AD-12's personal-surface rule). The new field changes nothing
about scoping.

**Do not duplicate the suppression logic.** `worker/tasks.py:486` →
`pulse_ping.mint_ping_send` already decides whether a ping is minted or suppressed and why.
This item changes the *preference*; it must not add a second place that decides whether to
send.

## Dependencies

(none)
