---
id: e2e-proof-and-contract-tests
title: End-to-End Proof & Contract Tests
intent: onboarding-and-account
complexity: medium
mode: confirm
status: completed
depends_on:
  - frontend-onboarding-flow
  - frontend-pulse-preview
created: 2026-10-29
run_id: run-eventpulse24-020
completed_at: 2026-10-30T11:16:02.872Z
---

# Work Item: End-to-End Proof & Contract Tests

## Description

Proves the intent works end to end against the local stack (Django, Next.js, Postgres, Redis, Mailpit), and pins the architecture invariants this intent adds. It follows the pattern of the earlier proof items (`run-eventpulse24-018` and the `e2e-proof-and-contract-tests` item of `personal-events-and-saved-catalog`).

## Acceptance Criteria

- [ ] A **recorded end-to-end scenario** runs and passes:
  - **Preview:** an anonymous visitor opens `/`, is sent to `/preview`, and sees up to 3 cards for the faked geo city, with Event Fit tags. "Don't use my location" switches to NYC.
  - **Soft wall:** the 3rd "Save to Pulse" routes to `/signup`.
  - **Onboarding:** after signing up, the user is on `/onboarding` step 1. They **skip all**, land on `/`, and their personal-events endpoints now work with the real session.
  - **Sign-out and sign-in:** sign out, then sign back in. `/` loads without going through onboarding again.
  - **Reset:** password reset sends one transactional mail to Mailpit. Using the link sets a new password, and **reusing the link fails**.
  - **Calendar import:** a second user connects a calendar pointed at a **local fixture ICS server**. Sync imports its events as `PersonalEvent`s linked to the connection, and an overlapping event creates the `CONFLICT_PAIR` behaviour the `calendar-sync-and-polling` design decided.
  - **Revoked feed:** the fixture server returns 410, the next poll marks the connection `needs_reconnect`, and the imported events remain.
  - **Disconnect:** disconnecting removes exactly that connection's events, and the user's own events remain.
  - **Free cap:** a second calendar connection is refused with the calm upgrade message.
- [ ] **Credential invariant:** across the whole scenario, the captured backend logs, the API responses and the frontend DOM snapshots never contain the fixture ICS URL, and the database column holds ciphertext.
- [ ] **AD-12 invariant:** `/api/public/preview` returns identical bodies with and without a session, and `/preview` renders the same for both.
- [ ] **AD-3 / AD-16:** no new FK crosses schemas. `identity` writes only `USER`, `personalization` writes `INTEREST` and `CALENDAR_CONNECTION` (plus its existing entities), and `ingestion` writes `EVENT_FIT`. This is asserted in `backend/tests/architecture/`.
- [ ] `beat_schedule` is still exactly one 60s tick, and `backend/tests/worker/test_tick.py` passes untouched.
- [ ] `make lint-imports` passes, including any contract amended by `ics-calendar-adapter`, with the amendment's reason recorded in the contract's description.
- [ ] `manage.py check` passes, including the retention category for every new model.
- [ ] **CI is green**, including the coverage gates (≥80% overall, 100% `domain/`). No skipped or quarantined tests are introduced.
- [ ] A **test report** records:
  - the scenario and its result;
  - the enumeration-safety and token-reuse checks;
  - the credential-leak sweep;
  - the coverage figures;
  - the provisional `CALENDAR_POLL_INTERVAL` with OQ-7 still open;
  - the known gaps carried forward: OIDC, `SUBSCRIPTION` / Pro cap, FR-1's first-digest proof (moved to the Pulse Digest intent), "Free" tags and reliability in Event Fit, and the PRD glossary amendment (OQ-6).

## Technical Notes

The fixture ICS server must be local and deterministic, with no live provider in CI. It needs switchable responses (200 with a body, 304, 410) so revocation can be triggered on demand. Because the SSRF policy denies loopback, the test configuration needs a deliberate, test-only allowance. Make it impossible to enable outside tests, and add a test proving that.

**What this item must not do.** It is a proof item. A bug found here is fixed in the work item that owns the code, or recorded as a known issue. It never expands this item's scope.

## Dependencies

- frontend-onboarding-flow
- frontend-pulse-preview
