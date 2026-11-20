---
id: run-eventpulse24-045
scope: single
work_items:
  - id: email-change-on-the-profile-screen
    intent: account-profile-expansion
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
status: completed
started: 2026-11-19T11:17:34.206Z
completed: 2026-11-19T11:56:00.199Z
---

# Run: run-eventpulse24-045

## Scope
single (1 work item)

## Work Items
1. **email-change-on-the-profile-screen** (confirm) — completed


## Current Item
(all completed)

## Files Created
- `frontend/components/settings/email-change.tsx`: The island: three states, resend, cancel
- `frontend/app/confirm-email/page.tsx`: Where the mail link lands
- `frontend/components/auth/confirm-email-form.tsx`: Spends the token with a POST

## Files Modified
- `backend/apps/identity/services/email_change.py`: cancel_email_change
- `backend/apps/identity/api.py`: DELETE /profile/email; me carries the pending expiry
- `backend/apps/identity/schemas.py`: EmailChangeCancelOut; pending_email_expires_at
- `frontend/app/settings/profile/page.tsx`: The island, under the name

## Decisions
- **Resend**: No endpoint; post the address again (The token is never stored, so a resend must mint a new link, and the request command already revokes the old row)
- **Cancel**: Revoke, not delete, and idempotent (The row is the history a takeover investigation wants; the caller wanted no pending change either way)
- **The expiry**: The server sends the moment (A duration in the frontend keeps claiming 24 hours after the constant changes)


## Summary

- Work items completed: 1
- Files created: 3
- Files modified: 4
- Tests added: 30
- Coverage: 0%
- Completed: 2026-11-19T11:56:00.199Z
