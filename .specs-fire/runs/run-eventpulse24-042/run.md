---
id: run-eventpulse24-042
scope: single
work_items:
  - id: pending-email-model-and-commands
    intent: account-profile-expansion
    mode: validate
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
status: completed
started: 2026-11-19T09:20:50.140Z
completed: 2026-11-19T09:52:31.876Z
---

# Run: run-eventpulse24-042

## Scope
single (1 work item)

## Work Items
1. **pending-email-model-and-commands** (validate) — completed


## Current Item
(all completed)

## Files Created
- `backend/apps/identity/services/tokens.py`: The shared token digest, mint and outstanding-row scan
- `backend/apps/identity/services/email_change.py`: request_email_change and confirm_email_change
- `backend/apps/identity/migrations/0006_pending_email_change.py`: PendingEmailChange
- `backend/tests/identity/test_email_change.py`: 20 tests over both commands

## Files Modified
- `backend/apps/identity/models.py`: PendingEmailChange
- `backend/apps/identity/services/password_reset.py`: Uses the extracted scan; hash_token re-exported
- `backend/apps/identity/services/throttle.py`: email_change limits
- `backend/apps/identity/services/__init__.py`: Exports both commands
- `backend/shared/constants.py`: 24h lifetime and throttle limits
- `backend/domain/errors.py`: InvalidEmailChangeTokenError
- `backend/tests/architecture/test_write_ownership.py`: Claims identity_pendingemailchange for identity

## Decisions
- **Sessions on confirm**: Not ended (Djangos session auth hash is an HMAC over the password field, so an email change invalidates nothing; ending sessions would sign out the victim rather than an attacker)
- **The request/confirm race**: Lost at user_email_uq (A pre-check narrows the window and cannot close it; the constraint is the only arbiter)
- **Taken address**: Silence, and no mail (Any difference makes the endpoint an account-existence oracle)
- **Token lifetime**: 24 hours (A reset is someone locked out now; an email change is someone who may read the new mailbox later)


## Summary

- Work items completed: 1
- Files created: 4
- Files modified: 7
- Tests added: 20
- Coverage: 0%
- Completed: 2026-11-19T09:52:31.876Z
