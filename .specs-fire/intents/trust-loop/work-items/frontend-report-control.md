---
id: frontend-report-control
title: The small flag — "Report this event" on the Detail screen
intent: trust-loop
complexity: medium
mode: confirm
status: pending
depends_on:
  - event-report-api
created: 2026-11-10
---

# Work Item: The small flag — "Report this event" on the Detail screen

## Description

FR-59 places a small flag in the Detail screen's secondary action row, "alongside Save, Share, Dismiss … Not a primary button". Tapping it opens a modal with four single-select categories, one tap submits, and a toast reads "Thanks — we'll review this." This item builds that control against `event-report-api`'s generated client.

## Acceptance Criteria

- [ ] A flag control in `components/detail/detail-actions.tsx`'s secondary row. It is visually subordinate to Save and Share, and it has an accessible name ("Report this event") because the icon alone is not a label.
- [ ] The modal offers exactly four single-select options, worded exactly as in FR-59:
  - "Wrong date or time"
  - "Wrong venue or address"
  - "Doesn't exist or is cancelled"
  - "Duplicate of another event"

  There is no free-text field. Submit is disabled until an option is chosen, and choosing one and submitting is a single further action.
- [ ] On success, the toast reads "Thanks — we'll review this." The modal closes, and focus returns to the flag.
- [ ] **The rate limit** (the API's sixth-report error) renders as a calm inline message, not a raw error. A network failure leaves the modal open with the selection preserved and a retry.
- [ ] **Signed out:** the plan states whether the flag is hidden or routes to sign-in, matching what Save does on the same screen, and a test pins it.
- [ ] **The event never visibly changes after a report.** There is no "reported" badge or greyed card. A report is a private signal, not a state.
- [ ] Accessibility: the modal traps focus, Esc closes it, the options are a proper radio group, and axe-core is clean on the open modal. The existing Playwright and axe gates cover it.
- [ ] Vitest component tests cover rendering, selection, submission, success, the rate limit, network failure, and the signed-out state, using the generated API types with no hand-written request shapes (AD-19).

## Technical Notes

Look at `components/share/share-control.tsx` and `components/state/detail-mute-control.tsx` for the existing secondary-action and toast patterns on this screen. Check the UX spec (`_bmad-output/planning-artifacts/ux-designs/…`) for a report modal mockup before designing one. TRACEABILITY lists no FR-59 gap, so a design may exist. Remember Node 24: export the `.nvmrc` toolchain before running Vitest.

## Dependencies

- event-report-api
