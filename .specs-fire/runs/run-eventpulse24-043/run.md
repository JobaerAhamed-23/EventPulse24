---
id: run-eventpulse24-043
scope: single
work_items:
  - id: email-change-mails
    intent: account-profile-expansion
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
status: completed
started: 2026-11-19T10:15:44.126Z
completed: 2026-11-19T10:35:55.524Z
---

# Run: run-eventpulse24-043

## Scope
single (1 work item)

## Work Items
1. **email-change-mails** (confirm) — completed


## Current Item
(all completed)

## Files Created
- `backend/apps/identity/templates/identity/email_change_confirm.txt`: The confirmation mail body
- `backend/apps/identity/templates/identity/email_change_requested.txt`: The warning to the old address
- `backend/tests/identity/test_email_change_mails.py`: 13 tests over both renderers

## Files Modified
- `backend/apps/identity/services/emails.py`: Link, two renderers, stream; reset copy now follows its constant
- `backend/apps/identity/services/password_reset.py`: A reset revokes outstanding email changes
- `backend/apps/identity/templates/identity/password_reset.txt`: Expiry rendered from the constant
- `backend/tests/identity/test_email_change.py`: The remedy test

## Decisions
- **The warning mails remedy**: A password reset revokes pending email changes (confirm_email_change checks a token not a session, so without this the advice would do nothing)
- **Naming the new address in the warning**: Named (A warning that will not say what is changing is hard to act on, and the account holder can already see it on their profile)
- **Send failure**: Not retried (The row expires and the resend control is the remedy; retrying makes a provider outage a failed API call)


## Summary

- Work items completed: 1
- Files created: 3
- Files modified: 4
- Tests added: 14
- Coverage: 0%
- Completed: 2026-11-19T10:35:55.524Z
