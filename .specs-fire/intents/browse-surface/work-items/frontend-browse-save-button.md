---
id: frontend-browse-save-button
title: The Inline Save Button — State Machine, Quota Wall and the Two Refusals
intent: browse-surface
complexity: medium
mode: confirm
status: completed
depends_on:
  - frontend-browse-shell-and-grid
created: 2026-11-12
run_id: run-eventpulse24-029
completed_at: 2026-11-12T12:43:02.350Z
---

# Work Item: The Inline Save Button — State Machine, Quota Wall and the Two Refusals

## Description

`Component.Button.Save.Inline` — the one element Browse cards add to the digest card
anatomy, and the surface's only affordance. The card body is not a button; Save is.

The spec gives it an explicit state machine and two named failure modes, and the backend
already distinguishes exactly those two. This item wires one to the other and makes the
refusals calm: an inline line under the button, never a modal, never a toast.

`save_cap.py` puts it plainly: *"A cap that interrupts with a modal is a cap that trains
people to dismiss prompts."*

## Acceptance Criteria

- [ ] State machine runs `idle → saving → saved → idle`. Labels: "Save", "Saving…" in
      ink-muted, "Saved ✓" in `color.signal.success`
- [ ] `saved` persists at least 1500ms before another interaction is accepted, so a fast
      double-tap cannot flicker the label
- [ ] From `saved`, a second tap un-saves with **no destructive confirmation** — the morph is
      the confirmation
- [ ] A successful save calls the existing `POST
      /api/personal/saved-events/{catalog_event_id}`; un-save calls its `DELETE`. **No new
      save endpoint is added**
- [ ] A 409 with code `save_cap_reached` renders inline under the button: "You've used your 1
      free save today. Upgrade for unlimited." with a `Text.Meta` "Upgrade" link
- [ ] A 409 with code `scheduling_conflict` renders inline under the button: "Conflicts with
      your saved dinner. Open Detail to resolve." with a `Text.Meta` "Open" link to the
      event detail
- [ ] **Neither refusal opens a modal or raises a toast** — asserted by a test, because this
      is the specific thing the design forbids
- [ ] When the quota is spent, every Save button on the page renders muted "1 of 1 used
      today", visible but disabled, carrying `title="Upgrade for unlimited saves"`; tapping
      does nothing
- [ ] A **Pro** user never sees the quota state, never sees the muted label, and can save
      repeatedly — asserted by a test that would fail if the entitlement check were dropped
- [ ] Each button is a real `<button>` with `aria-label="Save {event name} to my Pulse"`,
      while the visible label stays "Save"
- [ ] The morph to "Saved ✓" is announced via `aria-live="polite"` on the button, without
      moving focus
- [ ] Focus ring is 2px `color.accent.terracotta` at AA contrast; `Enter` and `Space` both
      trigger the machine
- [ ] Under `prefers-reduced-motion: reduce`, the 240ms morph collapses to an instant label
      swap
- [ ] The card's initial state comes from the API's `is_saved`, so an already-saved event
      renders "Saved ✓" on first paint rather than flashing "Save"

## Technical Notes

**The backend is already correct and already distinguishes the two cases.** Verified at
capture: `apps/personalization/api.py:360` documents the endpoint's two 409s — *"The two
409s are told apart by `code`: `scheduling_conflict` for a clash, `save_cap_reached` for the
cap."* Branch on `code`, not on a string match of the message.

`Esc` cancelling an in-flight save is in the spec (§384). The spec also says *"server-side
rollback is the responsibility of the save endpoint"* — check whether that rollback actually
exists before claiming the cancel works. If it does not, say so and scope the cancel to the
client-side label reset rather than implying a guarantee the server does not make.

The save is idempotent server-side, so a duplicate request is safe; this is a reason not to
over-engineer the in-flight guard.

## Dependencies

- frontend-browse-shell-and-grid
