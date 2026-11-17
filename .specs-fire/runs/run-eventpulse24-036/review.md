---
run: run-eventpulse24-036
work_item: pulse-ping-control
intent: traceability-gap-closure
date: 2026-11-17
---

# Code Review: Let a user turn the daily Pulse Ping off — FR-10

## Checked and found sound

| Concern | Finding |
|---|---|
| Nested transactions | `unsubscribe_pulse_ping` / `resubscribe_pulse_ping` each open `atomic(using=PERSONAL)` inside `apply_settings_patch`'s outer one. Django makes the inner a savepoint; the whole patch still lands or rolls back together |
| Order inside the patch | The ping branch runs **before** `reschedule_pending_for_user`. Correct: the unsubscribe cancels the pending digests, and the rewrite only re-times rows that are still pending, so it cannot resurrect them |
| A patch that changes the ping *and* the schedule | The digest-schedule branch still runs; the rewrite recomputes from the new values. No interaction |
| Polarity | Inverted in exactly two places, both at a boundary: `preferences_read` (`pulse_ping=not preference.pulse_ping_unsubscribed`) and the branch in `apply_settings_patch`. Nothing above them sees a double negative |
| Audit action vocabulary | `write_audit(action: str)` is free-form — no registry to extend, so `resubscribe.pulse_ping` needs no companion change |
| Scope leakage | The resubscribe touches one column and writes one audit row. No reminder plan is read or written in either direction |
| Required field on the wire | `NotificationSettingsOut.pulse_ping` is non-optional; every consumer regenerated through `make client`, and the full frontend suite passes |
| `_to_settings` call sites | One, verified by grep — so adding a required dataclass field could not silently miss a constructor |

## Accepted, with the reason recorded

**`resubscribe_pulse_ping` returns an `UnsubscribeResult`.** A resubscribe returning an
"unsubscribe result" reads oddly. It is kept because the alternative — a second result type,
or renaming the dataclass — ripples through `unsubscribe_event_reminders` and the token
endpoint for a cosmetic gain. The field that matters (`changed`) means the same thing in
both directions, and `cancelled=0` is documented as deliberate rather than vestigial.

## Not changed, and why

**The two pre-existing `tests/delivery/test_preferences_api.py` failures.** They are real
(`ScheduledSend.DoesNotExist`) and they sit in this area, which is exactly why it is
tempting to fix them here — and exactly why not to. This run's diff should describe FR-10.
They want their own work item, and this is the second run to say so; worth raising as one.

## Verdict

**Approved.** No defects found in this pass. The one behavioural change to an existing test
is an invariant whose count follows its controls, documented in place.
