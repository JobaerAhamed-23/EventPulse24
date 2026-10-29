---
id: onboarding-state-and-interests
title: Onboarding State, Interests & Digest Preferences
intent: onboarding-and-account
complexity: medium
mode: confirm
status: pending
depends_on:
  - auth-api-and-session-seam
created: 2026-10-29
---

# Work Item: Onboarding State, Interests & Digest Preferences

## Description

Gives the 3-step onboarding flow (FR-1) its server-side state.

- **Interests.** The 10 interest chips from `onboarding-step2-desktop.html` become one fixed constant in `shared/`. A user's picks (at most 3) are stored as `INTEREST` rows owned by `personalization` (AD-16).
- **Digest delivery time and timezone** (step 3) are stored as the user's preference. The Pulse Digest and Pulse Ping intents are the first to use them.
- **Onboarding progress** records which step the user is on. A user who leaves mid-step is **resumed at the same step on return within 7 days** (FR-1).

Nothing in this intent reads the interests for ranking. They are stored for the Pulse Digest intent.

## Acceptance Criteria

- [ ] `INTEREST_CHIPS` is one constant in `shared/constants.py` holding the 10 chips with stable keys and display labels: Tech & meetups, Sports & fitness, Arts & culture, Family & kids, Community & volunteering, Outdoors & nature, Classes & workshops, Markets & fairs, Talks & lectures, Government & civic. The frontend gets the list from the API, not a second copy.
- [ ] An `Interest` model in `personal` holds the user by value (no FK to `User`, OQ-8) and a chip key. One user can't hold the same chip twice (DB constraint).
- [ ] Setting interests **replaces** the user's set. More than 3 picks, or an unknown key, is refused with a calm message. Zero picks is valid, which is how the step is skipped.
- [ ] **Digest preferences** hold a delivery time (local wall-clock time) and an IANA timezone. A non-IANA or ambiguous zone is refused, using the same validator personal events use. A user who skips step 3 gets a documented default, held as a named constant.
- [ ] **Onboarding progress** records the current step (1–3) and when the user last advanced, completed or skipped.
  - Returning **within 7 days** resumes at the stored step. After 7 days, onboarding restarts at step 1. The window is a named constant, and a test pins it with a fixed clock.
  - Completing step 3, or choosing "skip all", marks onboarding complete, and a completed user is never sent back into it.
- [ ] **At most 3 steps.** The step model has exactly 3 steps, and a test fails if a 4th is added (FR-1: "exceeds 3 steps … violates FR-1").
- [ ] **Every step can be skipped.** No step requires input (FR-1). A test advances through all three with empty input.
- [ ] API endpoints under `/api/personal/onboarding` (or a coherent prefix chosen in the plan) to read progress, advance or skip a step, set interests, and set digest preferences, plus `GET` for the chip list. All are authed and scoped to the session user.
- [ ] `GET /api/auth/me` gains the onboarding status, read through `personalization`'s published interface.
- [ ] Every new model declares a retention category, and `make lint-imports` and `manage.py check` pass.
- [ ] Client regenerated (`make client`).
- [ ] Tests cover the 3-pick limit, replace semantics, an unknown key, the IANA refusal, the resume within and beyond 7 days, skip-all, complete is terminal, and the 3-step cap.

## Technical Notes

**Where digest preferences live.** AD-16's table assigns `PREFERENCE_GRAPH` to `personalization`, and `delivery` owns `SCHEDULED_SEND`, which will *consume* the delivery time. Storing the preference in `personalization` keeps `delivery` a reader. Decide in the plan whether it is a small dedicated model or part of a future `PREFERENCE_GRAPH`. Do not create `PREFERENCE_GRAPH` speculatively.

Calendar connect (step 1) is driven by its own API (`calendar-connect-api`). Onboarding progress only records that step 1 was passed. It does not own the connection.

## Dependencies

- auth-api-and-session-seam
