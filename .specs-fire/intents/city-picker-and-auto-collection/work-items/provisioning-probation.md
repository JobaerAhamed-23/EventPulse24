---
id: provisioning-probation
title: Probation for a city that yields nothing
intent: city-picker-and-auto-collection
complexity: medium
mode: confirm
status: in_progress
depends_on:
  - city-provisioning-service
created: 2026-11-20
---

# Work Item: Probation for a city that yields nothing

## Description

The honesty clock, and the cost ceiling.

After each ingest run of a provisioned source, update the city's provisioning status. A
city that publishes its first event becomes `live`. A city whose sources have run three
times without ever publishing anything has its sources paused and becomes
`yielded_nothing` — so the page stops saying "collecting" about something that is not
going to happen.

Three runs rather than one, because a 404 or a transient fetch failure must not condemn a
city permanently. At a 4-hour cadence that is roughly twelve hours of honest "we're
collecting" before the page admits defeat.

Without this, a thousand-city dropdown mints sources that fetch every four hours forever
for cities with one user and zero yield.

## Acceptance Criteria

- [ ] The first event published for a provisioned city moves its status to `live`.
- [ ] A provisioned source that completes a run having published nothing increments a zero-yield counter on that source.
- [ ] Any run that publishes an event resets that source's counter to zero.
- [ ] At three consecutive zero-yield runs, the source is paused via the existing `source_registry` pause command — audited, never deleted (FR-13).
- [ ] When **every** source for a city is paused or absent, the city's status becomes `yielded_nothing`.
- [ ] A city that reaches `live` and later goes quiet **stays `live`**. A quiet covered city is state B and must not be confused with state C — this is the distinction `browse-states.tsx` already insists on.
- [ ] A **fetch failure** is distinguished from a **successful empty fetch**. `ingest_source` already records `consecutive_failures` and `last_error_code`; a run that never reached the feed must not count toward the zero-yield probation.
- [ ] An editor pausing a source by hand produces `paused`, not `yielded_nothing` — the two have different causes and the surface says different things.
- [ ] Re-provisioning a `yielded_nothing` city (a later coverage decision, a new template) resumes rather than duplicating its sources.
- [ ] A test drives three zero-yield runs and asserts the pause and the status transition; it fails if the threshold is one.

## Technical Notes

`IngestReport.counts` already carries per-run outcome counts, and `ingest_source` already
separates `fetch_failed` / `parse_failed` / `not_modified` / `ok`. Build the probation on
those outcomes rather than on a fresh count of published rows — `not_modified` in
particular is a successful run that publishes nothing and must **not** count as a
zero-yield.

The counter belongs on `Source`, beside `consecutive_failures`, which it parallels exactly.
Do not reuse `consecutive_failures` itself: a source can fetch perfectly and publish
nothing, and conflating the two loses the distinction this item exists to preserve.

## Dependencies

- city-provisioning-service
