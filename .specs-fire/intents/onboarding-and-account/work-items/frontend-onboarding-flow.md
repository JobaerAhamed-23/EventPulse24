---
id: frontend-onboarding-flow
title: Frontend Onboarding Flow (3 steps)
intent: onboarding-and-account
complexity: medium
mode: confirm
status: in_progress
depends_on:
  - onboarding-state-and-interests
  - calendar-connect-api
  - frontend-auth-surfaces
created: 2026-10-29
---

# Work Item: Frontend Onboarding Flow (3 steps)

## Description

Builds `/onboarding` from `onboarding-step1-desktop.html`, `onboarding-step2-desktop.html`, `onboarding-step3-desktop.html` and `onboarding-skip-all-state-desktop.html`. It has three steps, and every one can be skipped (FR-1):

1. **Calendar connect.** Google, Apple and Outlook appear at equal weight. Each has inline guidance on where to find its secret ICS/webcal address and a masked address input. After connecting, the step shows the imported events "without leaving the onboarding flow" (FR-3).
2. **Interest chips.** The 10 chips, up to 3 picks.
3. **Digest time and timezone.**

The flow ends on the signed-in placeholder home at `/`.

## Acceptance Criteria

- [ ] Each step implements its mockup exactly. The topbar is quiet, and Back, "Skip for now" and Continue live in the **footer**, never the topbar (`EXPERIENCE.md` topbar-quiet rule).
- [ ] **Step 1:**
  - The three providers are styled as the mockup and FR-3 require.
  - Choosing one reveals that provider's guidance (FR-50's per-provider instructions) and a **masked** address input. The input never echoes the address into the DOM after submission and never stores it in `localStorage`.
  - Connecting shows the sync state, then the imported events.
  - The Free-cap response shows the calm in-app upgrade message, with no modal.
  - "Connection failed. Skip for now?" is the error state (`EXPERIENCE.md` `/onboarding` table).
- [ ] **Step 2:** the chips come from the API. A 4th pick is prevented in the UI (and refused by the API anyway). Zero picks is a valid Continue.
- [ ] **Step 3:** delivery time and an IANA timezone picker, defaulting to the browser's zone. It reuses the timezone helpers in `frontend/lib/timezones.ts`.
- [ ] **Skip all** reaches the skip-all state from its mockup and then `/`. A user who skips everything still finishes onboarding (FR-1).
- [ ] **Resume.** Reloading or returning within 7 days opens the server-recorded step, never step 1 by default. A test mocks the progress API at step 2 and asserts step 2 renders.
- [ ] A completed user visiting `/onboarding` goes to `/`.
- [ ] The Personal tone (`color.warm.personal`) on imported-event previews is always paired with the visible "Personal" label (WCAG 1.4.1), as in the last intent's surfaces.
- [ ] Accessibility: the chips are toggle buttons with `aria-pressed`, the step progress is announced, and focus moves to the step heading on each step change.
- [ ] Generated client only, tokens and vanilla components only.
- [ ] Vitest tests cover each step's render and skip path, masking, the cap message, the 3-pick limit, resume-at-step, skip-all, and the completed redirect. `make lint-web` and `make test-web` pass.

## Technical Notes

The step-1 mockup may draw OAuth-style "Connect" buttons. Amendment A-9 and AD-18 make the MVP mechanism a pasted ICS address. Follow the amendment, and keep the mockup's layout and equal-weight styling. Where the two conflict, note it in the walkthrough rather than redesigning.

## Dependencies

- onboarding-state-and-interests
- calendar-connect-api
- frontend-auth-surfaces
