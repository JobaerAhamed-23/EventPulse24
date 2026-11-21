---
id: city-coverage-request
title: The coverage request, one per city
intent: city-picker-and-auto-collection
complexity: medium
mode: confirm
status: completed
depends_on:
  - city-provisioning-service
created: 2026-11-20
run_id: run-eventpulse24-057
completed_at: 2026-11-21T03:36:14.946Z
---

# Work Item: The coverage request, one per city

## Description

The fallback for the cities automatic collection cannot reach: a control that records
"please go cover this city", once per city.

**This does not exist anywhere in the codebase today** — there is no coverage-request
model, endpoint or button. It is new work, not a surface being kept.

It appears only where it is the real way out: the `no_sources`, `yielded_nothing` and
`paused` states. It is deliberately absent from the collecting state, where the system is
already doing the thing the button would ask for, and from the quiet state, where the city
is covered and simply has nothing on tonight.

## Acceptance Criteria

- [ ] A `CityCoverageRequest` record exists with a **database unique constraint on the city** — "one request per city" is enforced, not merely intended.
- [ ] A second request for the same city succeeds idempotently and does not create a second row, whoever sends it.
- [ ] The row records when it was first raised and how many users have asked, so editorial can prioritise.
- [ ] The endpoint requires an authenticated user and is rate-limited.
- [ ] The control renders in the `no_sources`, `yielded_nothing` and `paused` states only, and is absent from `collecting` and from the quiet `live` state.
- [ ] After a successful request the control reports that it was recorded and does not invite a second press.
- [ ] AD-13 holds: the request stores the city, which is the point of the row, but **no per-user location is written into any audit `details` or log line**.
- [ ] The row is reachable by editorial — admin registration or an equivalent read.
- [ ] A test asserts the unique constraint actually rejects a duplicate at the database level, not only in the service.

## Technical Notes

Where the count is stored needs a decision: a counter column on the row is cheap but
cannot answer "did *this* user ask?", while a per-user join table can but puts a user id
beside a city, which is exactly the pairing AD-13 is careful about. Prefer the counter
unless there is a stated need for the per-user answer, and record the decision.

This row is about a city, not about a person — keep it on the `catalog` side with the rest
of the Source Registry's editorial surface, and keep user ids out of it.

## Dependencies

- city-provisioning-service
