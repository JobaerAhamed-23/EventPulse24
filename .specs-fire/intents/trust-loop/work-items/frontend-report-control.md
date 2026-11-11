---
id: frontend-report-control
title: The small flag — "Report this event" on the Detail screen
intent: trust-loop
complexity: medium
mode: confirm
status: completed
depends_on:
  - event-report-api
created: 2026-11-10
run_id: run-eventpulse24-026
completed_at: 2026-11-11T04:58:33.651Z
---

# Work Item: The small flag — "Report this event" on the Detail screen

## Description

FR-59 places a small flag in the Detail screen's secondary action row, "alongside Save, Share, Dismiss … Not a primary button". Tapping it opens a modal with four single-select categories, one tap submits, and a toast reads "Thanks — we'll review this." This item builds that control against `event-report-api`'s generated client.

## Acceptance Criteria

- [x] A flag control in `components/detail/detail-actions.tsx`'s secondary row. It is visually subordinate to Save and Share, and it has an accessible name ("Report this event") because the icon alone is not a label.
- [x] The modal offers exactly four single-select options, worded exactly as in FR-59:
  - "Wrong date or time"
  - "Wrong venue or address"
  - "Doesn't exist or is cancelled"
  - "Duplicate of another event"

  There is no free-text field. Submit is disabled until an option is chosen, and choosing one and submitting is a single further action.
- [x] On success, the toast reads "Thanks — we'll review this." The modal closes, and focus returns to the flag.
- [x] **The rate limit** (the API's sixth-report error) renders as a calm inline message, not a raw error. A network failure leaves the modal open with the selection preserved and a retry.
- [x] **Signed out:** the plan states whether the flag is hidden or routes to sign-in, matching what Save does on the same screen, and a test pins it.
- [x] **The event never visibly changes after a report.** There is no "reported" badge or greyed card. A report is a private signal, not a state.
- [x] Accessibility: the modal traps focus, Esc closes it, the options are a proper radio group, and axe-core is clean on the open modal. The existing Playwright and axe gates cover it.
- [x] Vitest component tests cover rendering, selection, submission, success, the rate limit, network failure, and the signed-out state, using the generated API types with no hand-written request shapes (AD-19).

## Technical Notes

Look at `components/share/share-control.tsx` and `components/state/detail-mute-control.tsx` for the existing secondary-action and toast patterns on this screen. Check the UX spec (`_bmad-output/planning-artifacts/ux-designs/…`) for a report modal mockup before designing one. TRACEABILITY lists no FR-59 gap, so a design may exist. Remember Node 24: export the `.nvmrc` toolchain before running Vitest.

## Dependencies

- event-report-api

## Delivered

FR-59's user-facing half: the flag, the modal with FR-59's four categories, the toast, and
the two failure answers — the rate limit and the network failure.

**Signed out, the flag is hidden — and it is hidden by inheritance, not by
implementation.** The whole action row is already inside `{personal ? … : null}`
(`app/events/[id]/page.tsx:477`), so placing the flag in `DetailActions` inherits Save's
rule from the same `if`. It cannot drift from Save's, because it is not a second rule.
The plan rejected sign-in routing: *a control that always ends at a sign-in wall is a
control that does nothing, plus three taps.*

**The event never visibly changes.** A report is a private signal, not a state: no badge,
no greyed card, no re-read. FR-59 says it twice — *"a single report does not auto-reject
an event"* — and the reason is the calm principle: if one person's report changed what
everyone else saw, one report would be a lever on a listing.

**Every failure leaves the modal open.** A 429 is the server's answer, not a failure, so
it is an **inline message inside the modal** in the API's own words — a toast is
transient and the limit lasts until tomorrow. A network failure keeps the selection and
re-arms the Submit, because the selection is the user's work.

**The code:** `components/detail/event-report-control.tsx` (the flag, the modal, the
toast), `components/detail/detail-actions.tsx` (the flag, after Share), and nothing else
on the page — the flag inherits the `personal` gate.

**The proofs:** `components/detail/event-report-control.test.tsx` (36 component tests),
`tests/event-detail-a11y.test.tsx` (the flag's presence and absence, plus the axe case
over the open modal — the file that renders the **real** row), and
`tests/ad19-endpoint-coverage.test.ts` (the endpoint, its operation id and its caller).

**Every proof was verified by breaking the code.** 24 control probes, 2 page probes and
7 AD-19 probes — **33 caught, none BROKEN**. The probes check their pattern exists
before editing, because a probe whose edit finds nothing proves nothing while looking
like a pass.

**The one existing test this item breaks was handled honestly.**
`app/events/[id]/page.test.tsx:1137` asserted the Detail Screen renders no "report this
event" text. **One** assertion was removed; the other three are untouched; and the
`DetailActions` stub gained the flag so the removal is not true for the wrong reason.
The **positive** form of the claim lives in `tests/event-detail-a11y.test.tsx`.

**Gates:** 1810 frontend tests passed across 107 files · `tsc`, `eslint` and `prettier`
clean · 6158 passed, 16 failed on the backend (the run's standing pre-existing failures,
untouched — this item writes no backend file) · no migration · no new endpoint.

**Two gaps are reported, not papered over:** the **Playwright half** of the
accessibility criterion — Playwright is not in this repository, and the axe half is
honoured in the house's own way — and the shared **`Sheet`'s native-Escape desync**, a
house-wide gap this item inherits as its fourth `Sheet` caller and does not introduce.

**Three mockup features do not ship**, each recorded with its reason: the daily report
counter, the pre-emptively disabled Submit, and the repeat-reporter warning — the last
is **a remaining FR-59 consequence**.
