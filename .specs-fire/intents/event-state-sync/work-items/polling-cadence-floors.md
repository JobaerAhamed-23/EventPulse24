---
id: polling-cadence-floors
title: Four hours for the sources that matter — FR-53's detection floors
intent: event-state-sync
complexity: medium
mode: confirm
status: in_progress
depends_on: []
created: 2026-11-04
---

# Work Item: Four hours for the sources that matter — FR-53's detection floors

## Description

FR-53: *"The system re-ingests high-priority sources at least every 4 hours. Lower-priority sources at least daily."* Its testable consequences turn that into detection guarantees — a cancelled event found within 4h (high-priority) or 24h (lower), and a postponed event's new time in the user's saved snapshot within 4h.

The machinery exists. `Source.ingestion_cadence` is a per-source `DurationField` (`apps/ingestion/models.py:89`), and `schedule_sources` / `ingest_source` already claim and run due sources on the tick. What does not exist is **priority**: there is no field, no derivation, and therefore no floor anyone can enforce. A source can be created with a seven-day cadence and nothing objects.

Webhooks — FR-53's near-real-time half — are **out of scope for this intent**, decided during capture: no Eventbrite, Meetup or Luma adapter exists, `event-catalog-ingestion` put official-API and partnership sources out of scope, and OQ-5 (the real source list and its ToS reviews) is still open. FR-53 names polling "the fallback"; this item ships the fallback.

## Acceptance Criteria

- [ ] A **priority notion on `Source`** — a field, or a documented derivation from what is already there. If derived, the derivation is in one named place and not re-expressed per caller.
- [ ] **Enforced ceilings**: a high-priority source's `ingestion_cadence` may not exceed 4 hours, a lower-priority source's may not exceed 24. Enforced where the value is written, so an out-of-range cadence is rejected rather than discovered later.
- [ ] Existing `Source` rows are **backfilled** with a priority and brought within their ceiling by a migration, not by hand.
- [ ] The scheduler honours the cadence it is given — asserted by a test, since the guarantee is only as good as the claim loop.
- [ ] A **test that can fail on the FR-53 consequence itself**: given a source at its ceiling, a cancellation introduced upstream is detected within the stated window. Not a test that the constant equals four.
- [ ] A source that is failing or rate-limited **does not silently stop meeting its floor** without surfacing — a cadence guarantee nobody is checking is worse than no guarantee, because the product promises on it.
- [ ] The constants live in `shared/constants.py` beside the other cadences, each with the comment the file's conventions require.

## Technical Notes

`shared/constants.py` already holds `CALENDAR_POLL_INTERVAL` with an explicit note that it is provisional and that "nothing else may hold an interval of its own" — the same discipline applies here, and these constants should read as siblings of it.

Priority is the only real decision. `Source` already carries `acquisition_method`, `tos_status`, `status` and `freshness_ttl_hours`; whether priority is a new field or a function of those is worth settling against FR-13's source registry, which is the surface where an operator would set it — and which is itself unbuilt, so this item should not assume a UI exists.

**Scope guard:** this item adds no adapters, no webhook ingress, and no new sources. It makes the existing polling meet a stated floor.
