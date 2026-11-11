---
id: per-day-quiet-hours-domain-and-model
title: Seven windows instead of one — reshaping quiet hours without breaking
  Free users
intent: pro-tier-and-monetization
complexity: high
mode: validate
status: in_progress
depends_on:
  - subscription-model-and-entitlement
created: 2026-11-11
---

# Work Item: Seven windows instead of one — reshaping quiet hours without breaking Free users

## Description

FR-51 gives a Pro user *"7 distinct Quiet Hours windows (one per weekday)"*. Quiet hours are
structurally single-window today, in two places at once:

- `domain/quiet_hours.QuietHours` is a frozen pair of `start` / `end` local wall clocks, with
  `covers()`, `crosses_midnight` and `disabled` built on that pair.
- `NotificationPreference` stores one column pair (`quiet_hours_start`, `quiet_hours_end`),
  guarded by `notification_preference_quiet_hours_pair_ck`, which asserts both are null or
  both are set — *"A null pair means 'no quiet hours', and it is the only spelling of that."*

Both change shape, there is a live constraint and live user data in the way, and
`shift_to_sendable` is on the delivery path where getting it wrong means sending at 3am. That
is why this item is `validate`.

## Acceptance Criteria

- [ ] A Pro user holds **seven distinct windows, one per weekday**. A Free user keeps exactly
      one window, with today's behaviour unchanged.
- [ ] **The wall-clock invariant survives.** Windows stay local wall-clock values re-read
      against the zone on every due-time computation, preserving what
      `domain/quiet_hours.py` documents: *"'10pm' means 10pm wherever the user is, and
      survives both travel and DST."* No window stores an instant, and no window stores its
      own zone.
- [ ] **The existing single-window spelling of "off" is preserved.** Whatever the new shape,
      there is still exactly one way to say "no quiet hours", and `start == end` is still
      refused by the command with `InvalidQuietHoursWindowError` while `domain.quiet_hours`
      stays total and treats it as disabled.
- [ ] `shift_to_sendable` defers a send to the end of **the window that actually covers the
      instant**, including the case where a window crossing midnight runs into the *next
      day's* window — which must defer to the later end, not the earlier one.
- [ ] **The migration invents nothing.** A user with one window keeps one window. No
      migration fabricates seven copies of an existing window, and no Free user's delivery
      time moves as a result of this item.
- [ ] A **lapsed Pro user's seven windows are not deleted** (the brief's never-delete
      constraint). What the delivery path does with them while the user is Free is decided by
      the design doc and stated explicitly — it must not be left implicit.
- [ ] Tests cover: a weeknight and a weekend window behaving differently for the same user; a
      window crossing midnight into the next day's window; DST transitions in both directions
      with the window unchanged; the disabled spelling; a Free user's behaviour byte-for-byte
      unchanged; and the migration being a no-op for existing rows.

## Technical Notes

High complexity, so this item gets a design doc. The design must decide:

- **The storage shape.** Widening `NotificationPreference` to seven column pairs keeps it one
  row and one check constraint, at the cost of fourteen columns and a much longer constraint.
  A child table is cleaner and naturally handles "this user has one window" versus "seven",
  but adds a join on the delivery path and its own retention category. The existing
  `notification_preference_quiet_hours_pair_ck` has to be rewritten or replaced either way.
- **The domain shape.** Does `QuietHours` stay a single window with a new weekly collection
  wrapping it, or does it become a weekly type? The former keeps `covers()` and
  `crosses_midnight` untouched and is the smaller change; verify against every current caller
  before choosing.
- **Midnight-crossing across weekdays.** A Friday 22:00–08:00 window covers Saturday morning.
  Is that Friday's window or Saturday's? This is the single likeliest source of a 3am send,
  and the design must state the rule and the test that proves it.
- **What a lapsed Pro user's delivery path does** with seven stored windows.

Read every caller of `QuietHours` and `shift_to_sendable` before designing — the delivery
path is the one place in this intent where a mistake reaches a user as a notification at the
wrong hour.

## Dependencies

- subscription-model-and-entitlement
