---
id: e2e-proof-and-contract-tests
title: The Proof — Every Reconnected Surface, Walked End to End
intent: unwired-surfaces
complexity: medium
mode: confirm
status: in_progress
depends_on:
  - collection-assign-control
  - calendar-connection-controls
  - detail-open-signal
  - personal-event-reminder-plan
created: 2026-11-13
---

# Work Item: The Proof — Every Reconnected Surface, Walked End to End

## Description

This intent's whole subject is the gap between an endpoint that works and a user who can
reach it. **A unit test cannot prove that gap closed**, because every one of these endpoints
already had passing backend tests while being unreachable.

So the proof is an end-to-end walk against a running stack, through the UI, for each
reconnected surface — plus the contract check that the generated client still matches the
live API for any endpoint added by `less-like-this-adjustment` or
`settings-sources-surface`.

## Acceptance Criteria

- [ ] **Collections**: a Pro user saves an event, assigns it to a collection, sees it there,
      assigns it to a second collection, unassigns it from the first, and the **save still
      exists** afterwards
- [ ] **Collections tier gate**: a free user cannot assign, and can unassign
- [ ] **Calendar**: a connected calendar can be disconnected from Settings; the confirmation
      appears first; that connection's imported events are gone afterwards and a second
      connection's events remain
- [ ] **Calendar**: a connection in `needs_reconnect` offers reconnect; a healthy one does not
- [ ] **Detail open**: opening the signed-in Detail Screen writes an `EventDetailOpen` row;
      opening the public page does not; an anonymous visit does not
- [ ] **Neighbour count**: a second user opening the same event moves the neighbour count —
      the whole point of FR-24's union, proven through the UI rather than against the service
- [ ] **Personal-event reminders**: a plan can be set on a personal event and read back, and a
      saved event's plan is untouched
- [ ] **Contract**: `make client` produces no diff, and `git diff --exit-code frontend/lib/api/`
      passes
- [ ] **The walkthrough is run in a real browser** and anything broken is reported as found,
      not smoothed over
- [ ] Every assertion can fail — verified by mutation probes, not by inspection

## Technical Notes

- **Follow the existing e2e house pattern.** `frontend/e2e/` holds the current walkthroughs;
  `digest-opt-out.spec.ts` is the most recent and shows the shape, including the
  `runCompose` helper that shells into Django for a backend fact the UI cannot show.
- **The sign-in throttle will bite on the second run.** `AUTH_THROTTLE_SIGN_IN_IP` is ten an
  hour per IP and `AUTH_THROTTLE_SIGN_IN_ACCOUNT` five per account
  (`shared/constants.py:466-468`). `digest-opt-out.spec.ts` solves it with the product's own
  `reset_sign_in_throttle` — reuse that, do not invent a backdoor.
- **The neighbour-count assertion needs two users and k-anonymity.** `count_neighbors`
  buckets the result; check the bucket thresholds before asserting on a number, or the test
  will assert on a figure the product deliberately never shows.
- **`docker compose up -d --wait` first** — Postgres, Redis and Mailpit. `make up`.
- **A test that cannot fail is worse than no test here**, because this intent exists because
  green tests coexisted with unreachable features for weeks.

## Dependencies

- collection-assign-control
- calendar-connection-controls
- detail-open-signal
- personal-event-reminder-plan
