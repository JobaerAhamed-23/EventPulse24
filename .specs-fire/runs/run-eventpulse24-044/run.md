---
id: run-eventpulse24-044
scope: single
work_items:
  - id: email-change-endpoints-and-contract
    intent: account-profile-expansion
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
status: completed
started: 2026-11-19T10:37:19.444Z
completed: 2026-11-19T11:15:48.309Z
---

# Run: run-eventpulse24-044

## Scope
single (1 work item)

## Work Items
1. **email-change-endpoints-and-contract** (confirm) — completed


## Current Item
(all completed)

## Files Created
- `backend/tests/identity/test_email_change_api.py`: 15 tests over both endpoints

## Files Modified
- `backend/apps/identity/api.py`: Two handlers; me reports a pending change
- `backend/apps/identity/schemas.py`: Four schemas; CurrentUserOut.pending_email
- `backend/tests/identity/conftest.py`: apps.identity.api added to the email consumers
- `backend/tests/identity/test_auth_api.py`: me field-set guard updated
- `backend/tests/identity/test_profile_api.py`: me key-set guard updated
- `frontend/lib/api/openapi.json`: Regenerated
- `frontend/lib/api/schema.ts`: Regenerated

## Decisions
- **CSRF on the anonymous confirm**: Required, as password_reset_confirm does (GET /api/auth/csrf issues the token for a caller with no session, so anonymous does not mean unprotected)
- **me reporting a pending change**: The address, not a boolean (A screen that cannot say which address a link went to is no use to someone who mistyped it)
- **Where the mails are sent**: At the edge, not in the command (The command stays testable with no email port; the cost is a third consumer in the email fixture)


## Summary

- Work items completed: 1
- Files created: 1
- Files modified: 7
- Tests added: 15
- Coverage: 0%
- Completed: 2026-11-19T11:15:48.309Z
