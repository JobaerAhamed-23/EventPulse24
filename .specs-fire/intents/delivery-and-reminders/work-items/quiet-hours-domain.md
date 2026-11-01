---
id: quiet-hours-domain
title: Quiet Hours — a pure shift, computed once
intent: delivery-and-reminders
complexity: medium
mode: confirm
status: completed
depends_on: []
created: 2026-10-31
run_id: run-eventpulse24-023
completed_at: 2026-10-31T12:56:50.446Z
---

# Work Item: Quiet Hours — a pure shift, computed once

## Description

`domain/quiet_hours.py`: given an instant, a window and an IANA zone, return the instant the send should actually happen — the original if it falls outside the window, the window's end if it falls inside.

ARCHITECTURE-SPINE.md line 71 lists "quiet-hours due-time shifting (AD-7)" among the things that belong in `domain` — "the algorithmic core that must be testable without a database". There is no `quiet_hours.py` today; a grep for the term finds a single comment. This is the file that line was written for, and it sits beside `conflict.py`, `ranking.py` and `event_fit.py` with the same shape: no Django import, no I/O, no clock of its own.

The subtle part is **not** the comparison — it is that the window is a pair of local wall clocks and the instant is UTC, so the two can only be compared after the instant is rendered into the user's zone. The default window **10pm–8am crosses midnight**, which makes "inside the window" a disjunction rather than a range, and DST makes the window's end an instant that does not always exist or is sometimes ambiguous. `domain/timezones.py` already solves that class of problem for the project and is reused, never re-derived (AD-16).

## Acceptance Criteria

- [ ] A pure function takes `(instant_utc, window_start_local, window_end_local, tz)` and returns the effective instant. **No database, no Django, no `datetime.now()`** — the module imports nothing the other `domain` modules do not.
- [ ] An instant **outside** the window is returned **unchanged and identical** — not re-derived, not rounded, not re-zoned.
- [ ] An instant **inside** the window returns the **window's end**, in the user's zone, on the correct day.
- [ ] **A midnight-crossing window is the normal case.** For 22:00–08:00: 23:30 shifts to 08:00 **the next morning**; 02:00 shifts to 08:00 **the same morning**; 12:00 is untouched. Each is its own test.
- [ ] A **non-crossing** window (e.g. 13:00–14:00) works by the same code path, with no second branch for it.
- [ ] A window where start == end means **no quiet hours** and never shifts. A window covering the full day is rejected by the caller, not silently turned into "defer forever" — the domain states which it does and a test pins it.
- [ ] **DST is handled through `domain/timezones.py`.** A window end that falls in a spring-forward gap resolves to a real instant; one in a fall-back overlap resolves deterministically, and the choice is documented in the docstring.
- [ ] Shifting is **idempotent**: shifting an already-shifted instant returns it unchanged, because the window's end is outside the window.
- [ ] The boundaries are pinned: an instant exactly at the window start is inside, one exactly at the end is outside, and the docstring says so in words.
- [ ] Tests cover every case above with no database and no mocking of time.

## Technical Notes

Reuse `shared.constants` for the default window rather than adding a literal here — the default is `22:00–08:00` per EXPERIENCE.md §2 and the PRD glossary, and the constant belongs beside `DEFAULT_REMINDER_PLAN`.

This module is the *only* place the shift is computed. AD-7 is explicit that Quiet Hours is applied when `due_at` is **computed or recomputed**, never as a skip at send time — so the sweep must never import this module to re-check a row. If it ever needs to, that is a bug in the minting path.

## Dependencies

(none)
