---
id: run-eventpulse24-053
scope: wide
work_items:
  - id: account-deletion-and-avatar-removal
    intent: account-profile-expansion
    mode: validate
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: avatar-on-the-shell
    intent: account-profile-expansion
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: profile-screen-and-e2e
    intent: account-profile-expansion
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
status: completed
started: 2026-11-20T03:37:57.952Z
completed: 2026-11-20T06:43:49.702Z
---

# Run: run-eventpulse24-053

## Scope
wide (3 work items)

## Work Items
1. **account-deletion-and-avatar-removal** (validate) — completed
2. **avatar-on-the-shell** (confirm) — completed
3. **profile-screen-and-e2e** (confirm) — completed


## Current Item
(all completed)

## Files Created
- `frontend/e2e/profile-screen.spec.ts`: The click-through: the profile screen, reached by clicking, with all four controls used
- `frontend/e2e/fixtures/avatar.png`: A real one-pixel PNG, because the server identifies the format from the bytes
- `frontend/tests/profile-a11y.test.tsx`: The profile screen axe-core gate, over four different documents

## Files Modified
- `frontend/app/settings/profile/page.tsx`: The docstring rewritten around the design the code now has; the read question answered; the not-signed-in branch reason corrected
- `frontend/app/settings/profile/page.test.tsx`: 17 to 27 tests: the picture, the order, the read question
- `frontend/components/shell/avatar-disc.tsx`: data-avatar-disc on the wrapper, in both branches
- `frontend/e2e/helpers.ts`: Eight helpers: the rail, the sub-nav, the walk, the account row, the two discs, the picture removal, the email-change reset
- `frontend/e2e/settings-navigation.spec.ts`: Privacy added to the sections list
- `backend/apps/identity/services/throttle.py`: reset_email_change_throttle: the email-change window own reset, mirroring the sign-in one
- `backend/tests/identity/test_throttle.py`: 16 to 23 tests: the new reset

## Decisions
(none)


## Summary

- Work items completed: 3
- Files created: 3
- Files modified: 7
- Tests added: 41
- Coverage: 95%
- Completed: 2026-11-20T06:43:49.702Z
