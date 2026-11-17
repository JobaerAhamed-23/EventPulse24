---
run: run-eventpulse24-036
work_item: pulse-ping-control
intent: traceability-gap-closure
mode: confirm
checkpoint: plan
approved_at: pending
---

# Implementation Plan: Let a user turn the daily Pulse Ping off — FR-10

## Approach

Expose the **existing** `pulse_ping_unsubscribed` column through the notification-settings
endpoint and give it a row on `/settings/general`, so the sentence onboarding already shows
every new user — *"One calm Pulse Ping per day… You can change this anytime"* — becomes true.

Three corrections to the work item, from reading the code:

**1. The column is `pulse_ping_unsubscribed`, not `ping_unsubscribed`.** The work item named
it after the migration file (`0004_notificationpreference_ping_unsubscribed`), and the field
inside that migration is `pulse_ping_unsubscribed`.

**2. There is no "turn it back on" anywhere, and that is the real work.** The work item
assumed this was pure wiring. `unsubscribe_pulse_ping` (`services/unsubscribes.py:185`)
exists, because the only existing caller is the RFC 8058 one-click link, which is one-way by
definition. Settings needs both directions, so a `resubscribe_pulse_ping` command has to be
written. That is why this is `medium` rather than `low`.

**3. The settings read does not carry the flag yet.** `NotificationSettings`
(`notification_preferences.py:51`) and `NotificationSettingsView` (`preferences_read.py:39`)
are both frozen dataclasses that stop at quiet hours, overrides and default slots. Both gain
the field, and `_to_settings` maps it — otherwise the switch cannot render in the right
position on first paint.

**The polarity is inverted in exactly one place.** The column stores
`pulse_ping_unsubscribed` (true = off) and every user-facing name says `pulse_ping` (true =
on). The wire, the view and the patch all speak "enabled"; the single inversion is the
branch inside `apply_settings_patch` that picks the unsubscribe command or the resubscribe
one. A double negative must not reach the component — a switch whose `true` means "off" is
how a settings screen ends up lying.

**Turning it off reuses `unsubscribe_pulse_ping` rather than writing the column directly**,
so the Settings path and the email path do the same three things: flip the flag, cancel that
scope's pending digest sends, and write the audit entry. Two code paths writing one column
is how they drift.

**Turning it back on does not resurrect the cancelled sends.** They were cancelled; the next
tick mints a fresh ping. Un-cancelling would deliver a digest for a day that has passed.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/tests/delivery/test_pulse_ping_control.py` | The command pair, the patch, the round trip |
| `frontend/components/settings/pulse-ping-switch.tsx` | The Settings row |
| `frontend/components/settings/pulse-ping-switch.test.tsx` | Its behaviour, including the failure revert |

## Files to Modify

| File | Changes |
|------|---------|
| `backend/apps/delivery/services/unsubscribes.py` | Add `resubscribe_pulse_ping`; export it |
| `backend/apps/delivery/services/__init__.py` | Export the new command |
| `backend/apps/delivery/services/notification_preferences.py` | `NotificationSettings.pulse_ping_unsubscribed`; map it in `_to_settings` |
| `backend/apps/delivery/services/preferences_read.py` | `NotificationSettingsView.pulse_ping`, read from the preference |
| `backend/apps/delivery/services/preferences.py` | `SettingsPatch.pulse_ping`; apply it in `apply_settings_patch` |
| `backend/apps/delivery/schemas.py` | `pulse_ping` on `NotificationSettingsIn` and `NotificationSettingsOut` |
| `backend/apps/delivery/preferences_api.py` | Map the field in `_patch_from`; document it |
| `frontend/app/settings/general/page.tsx` | Mount the row; pass the server's value |
| `frontend/lib/api/openapi.json`, `frontend/lib/api/schema.ts` | **Regenerated** by `make client` — never hand-edited (AD-19) |

## Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/delivery/test_pulse_ping_control.py` | off writes the column, cancels pending digests, writes the audit; off twice is a no-op; on clears the column; on does **not** resurrect cancelled sends; the patch leaves the field alone when omitted; `GET` reports the state; turning the ping off leaves every reminder plan untouched (FR-11's scope split) |
| `frontend/components/settings/pulse-ping-switch.test.tsx` | renders the server's state; optimistic flip; reverts and shows the failure line on a rejected save; the accessible name is stable across states |

## Technical Details

**The patch's "omitted means leave alone" rule.** `_patch_from` reads
`model_fields_set`, so `pulse_ping` absent → `None` → untouched. Unlike `quiet_hours`, `null`
is **not** a meaningful third value here: a ping is on or off. The field is
`bool | None` only to express presence.

**The frontend body is just the one key.** `PUT /notifications` is a true patch, so this row
sends `{"pulse_ping": false}` alone. That is a real difference from
`digest-personal-events.tsx`, which must resend the whole schedule because
`DigestPreferenceIn` requires `delivery_time` and `timezone` — worth noting so the new
component is not modelled on that constraint by accident.

**The control follows the house pattern, not a new one**: a `<button>` with `aria-pressed`
via `SwitchControl` + `SettingRow`, a stable accessible name, and the state in *words* for
sighted readers so colour is never the sole carrier (WCAG 1.4.1). Optimistic flip, with the
server's answer replacing the guess and a failure putting it back.

**No Pro gate.** The ping is every tier's.

## Verification

`make test-backend`, `make lint-backend`, `pnpm test`, `pnpm lint`, `pnpm typecheck`,
`pnpm format:check`, and `make client` to regenerate the contract.

**Out of scope, deliberately:** the two pre-existing failures in
`tests/delivery/test_preferences_api.py` are real (`ScheduledSend.DoesNotExist`, not an
environment problem) and live in this area, but they are not this work item. New tests go in
a new file so this run's additions are not entangled with them.

---
*Plan approved at checkpoint. Execution follows.*
