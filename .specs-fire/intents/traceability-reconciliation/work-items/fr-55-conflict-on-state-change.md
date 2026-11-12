---
id: fr-55-conflict-on-state-change
title: FR-55 — design the cancelled-event conflict path, and prove nothing
  auto-cancels
intent: traceability-reconciliation
complexity: medium
mode: confirm
status: completed
depends_on: []
created: 2026-11-12
run_id: run-eventpulse24-028
completed_at: 2026-11-12T05:59:35.275Z
---

# Work Item: FR-55 — design the cancelled-event conflict path, and prove nothing auto-cancels

## Description

FR-55 has **nothing tagged anywhere** — not a mockup, not a DESIGN.md component, not an
EXPERIENCE.md flow. The matrix found only overlap with FR-58's conflict UI, *"with no
documented acknowledgment it also serves this trigger"*.

That phrase is the whole problem. FR-58's conflict prompt fires when the **user** creates a
conflicting event — the user is present, acting, and can choose. FR-55 fires when an
**event changes underneath the user**: a cancel, a postpone, a move. Same visual conflict,
entirely different moment. Reusing FR-58's UI may well be right, but nobody has written down
that it was a decision rather than an accident, and the states differ — a cancelled event's
conflict should *clear*, not prompt.

The backend is well-developed and already separates the concepts precisely.
`detail_read.py:112–115` insists the notice and the mute are *"two independent facts"* and
that *"a client must not read 'muted' as 'there is nothing to say'"*. The frontend has
`components/state/detail-notice-banner.tsx`, `detail-mute-control.tsx`, `notice-strip.tsx`
and `event-state-badge.tsx`.

## Acceptance Criteria

- [ ] A mockup exists, self-tagged `FR-55`, showing all three triggers the PRD names —
      **cancelled with no conflict**, **cancelled conflicting with a personal event**,
      **postponed conflicting with another saved event** — plus the per-event mute control.
- [ ] The design **states explicitly** whether FR-55 reuses FR-58's conflict surface, and why.
      If it reuses it, FR-58's existing mockups gain an `FR-55` tag acknowledging the second
      trigger. The matrix's complaint is the absence of that acknowledgment, so writing it
      down is the deliverable.
- [ ] The calm *"this overlaps with [other event]"* message on the Detail Screen is specified
      as copy, per the PRD's third consequence and EXPERIENCE.md §3's voice rules.
- [ ] A test: cancelled event, no saved personal event — user notified, event leaves the digest.
- [ ] A test: cancelled event conflicting with a personal event — user notified **and the
      personal event survives untouched**. The PRD says *no auto-cancel*; assert the personal
      event still exists and is unmodified, which is the consequence a cleanup path would
      quietly violate.
- [ ] A test: postponed event conflicting with another saved event — user notified, overlap
      message present on the Detail Screen.
- [ ] A test: per-event mute silences state-change notices **for that event only**, leaving
      other events' notices and the user's global preferences untouched.
- [ ] A test asserts a muted event still carries its notice fact in the API response — per
      `schemas.py:982` and `detail_read.py:114`, mute and notice are independent, and
      collapsing them is the specific bug those comments exist to prevent.
- [ ] Auto-rebook and alternative suggestions stay out (Phase 3).
- [ ] Tests name `FR-55`.

## Technical Notes

AD-21 governs this and should be read first. It states that when propagation removes an
overlap — a cancel, or a postpone past the partner — *"the pair closes as
`cleared_by_state_change`, which is not a user resolution"*, and that a resolved pair is
immutable and never re-prompted. That distinction belongs in the design: a conflict that
disappears because the event was cancelled must not look like a conflict the user resolved,
and must not re-prompt.

`services/conflict_resolutions.py` and `migrations/0012_conflictpair_conflict_pair_resolution_kind_ck`
are the backend home. The check constraint on `resolution_kind` is worth reading — it likely
already encodes `cleared_by_state_change` as distinct from a user choice, in which case the
test is asserting an invariant the database already holds, which is the cheap kind.

`components/detail/detail-conflict.test.tsx` exists. Check what it already covers before
writing new frontend tests.
