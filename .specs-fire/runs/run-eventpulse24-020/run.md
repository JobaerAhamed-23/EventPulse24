---
id: run-eventpulse24-020
scope: wide
work_items:
  - id: account-auth-core
    intent: onboarding-and-account
    mode: validate
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: calendar-connection-model
    intent: onboarding-and-account
    mode: validate
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: ics-calendar-adapter
    intent: onboarding-and-account
    mode: validate
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: calendar-sync-and-polling
    intent: onboarding-and-account
    mode: validate
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: auth-api-and-session-seam
    intent: onboarding-and-account
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: onboarding-state-and-interests
    intent: onboarding-and-account
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: calendar-connect-api
    intent: onboarding-and-account
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: event-fit
    intent: onboarding-and-account
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: pulse-preview-api-and-geo
    intent: onboarding-and-account
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: frontend-auth-surfaces
    intent: onboarding-and-account
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: frontend-onboarding-flow
    intent: onboarding-and-account
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: frontend-pulse-preview
    intent: onboarding-and-account
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
  - id: e2e-proof-and-contract-tests
    intent: onboarding-and-account
    mode: confirm
    status: completed
    current_phase: review
    checkpoint_state: approved
    current_checkpoint: plan
current_item: null
status: completed
started: 2026-10-29T06:25:40.374Z
completed: 2026-10-30T11:16:02.872Z
---

# Run: run-eventpulse24-020

## Scope
wide (13 work items)

## Work Items
1. **account-auth-core** (validate) — completed
2. **calendar-connection-model** (validate) — completed
3. **ics-calendar-adapter** (validate) — completed
4. **calendar-sync-and-polling** (validate) — completed
5. **auth-api-and-session-seam** (confirm) — completed
6. **onboarding-state-and-interests** (confirm) — completed
7. **calendar-connect-api** (confirm) — completed
8. **event-fit** (confirm) — completed
9. **pulse-preview-api-and-geo** (confirm) — completed
10. **frontend-auth-surfaces** (confirm) — completed
11. **frontend-onboarding-flow** (confirm) — completed
12. **frontend-pulse-preview** (confirm) — completed
13. **e2e-proof-and-contract-tests** (confirm) — completed


## Current Item
(all completed)

## Files Created
- `backend/ports/fetch_policy.py`: The test-only loopback allowance, gated on the settings module name AND an active test runner
- `backend/tests/fixture_ics_server.py`: The switchable TLS ICS server, shared by the e2e proof and the adapter tests
- `backend/tests/e2e/test_onboarding_and_calendar_proof.py`: The fifteen-step end-to-end scenario and the four-layer credential-leak sweep
- `backend/tests/e2e/test_loopback_allowance.py`: The proof that the loopback allowance cannot be reached outside a test
- `backend/tests/e2e/test_fixture_ics_server.py`: The fixture server own proof, over real TLS through the real client
- `backend/tests/architecture/test_write_ownership.py`: AD-16: only the owning app writes each table

## Files Modified
- `backend/ports/fetch.py`: The credential flag on the fetch port: the caller that holds a credential says so
- `backend/adapters/crawl/http.py`: The URL-logging suppression for a credential fetch, and the refusal of a non-verifying SSL context
- `backend/adapters/crawl/fake.py`: Accepts the credential keyword (a production break the review found)
- `backend/adapters/calendar/ics.py`: Passes credential=True; reads allowed_ports from the shared setting
- `backend/apps/personalization/services/calendar_connections.py`: The pre-flight consults the same deny-policy helper
- `backend/config/settings_test.py`: The test-only allowance settings
- `backend/tests/conftest.py`: The shared fixture_server fixture
- `backend/tests/adapters/test_crawl_http.py`: The credential and SSL-context tests, against a real socket
- `backend/tests/adapters/test_calendar_ics.py`: The assertion that the adapter passes credential=True
- `backend/tests/adapters/calendar_fakes.py`: Records the credential flag
- `backend/tests/ingestion/pipeline_support.py`: Accepts the credential keyword
- `backend/tests/architecture/test_preview_anonymity.py`: The AD-3/AD-16 invariants
- `backend/pyproject.toml`: The import contracts for the new port

## Decisions
(none)


## Summary

- Work items completed: 13
- Files created: 6
- Files modified: 13
- Tests added: 141
- Coverage: 99.05%
- Completed: 2026-10-30T11:16:02.872Z
