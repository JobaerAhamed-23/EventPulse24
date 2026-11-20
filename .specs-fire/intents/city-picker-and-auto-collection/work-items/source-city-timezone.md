---
id: source-city-timezone
title: A source carries its city's timezone
intent: city-picker-and-auto-collection
complexity: high
mode: validate
status: pending
depends_on: []
created: 2026-11-20
---

# Work Item: A source carries its city's timezone

## Description

Add one link to the timezone fallback chain: `venue_tz` -> `source.city_tz`.

`ingest_item._venue_for` never creates a venue (D5), so a city with no registered venues
resolves `venue=None` for every candidate, and `resolve_tz` rejects every naive or
date-only time as `TZ_UNRESOLVABLE`. Without this, a freshly provisioned city fetches
cleanly, parses cleanly, and publishes nothing, forever.

Strictly additive: an existing source has no `city_tz`, and its behaviour is byte-for-byte
what it is today.

## Acceptance Criteria

- [ ] `Source.city_tz` is added — a nullable/blank IANA zone name, validated through `domain.timezones.canonical_zone` on write.
- [ ] `resolve_tz` accepts a `city_tz` argument and uses it **only** when `source_zone` is absent and `venue_tz` is absent.
- [ ] A new confidence constant scores strictly **below** `TZ_SCORE_VENUE_REGISTRY` — a city zone is weaker evidence than a specific venue's address.
- [ ] The resulting resolution reports a `reason` that names the city-zone row distinctly, so review and audit can tell it from a venue-zone resolution.
- [ ] The DST fold/gap caps apply to a city-zone reading exactly as they do to a venue-zone reading.
- [ ] A date-only `startDate` with no venue and a `city_tz` resolves at the PARTIAL tier instead of rejecting — asserted by a test that fails without the change.
- [ ] A candidate with an explicit zone or instant ignores `city_tz` entirely — the precedence order is asserted, not assumed.
- [ ] A source with `city_tz` unset behaves identically to today — asserted against the existing rejection test.
- [ ] `ingest_item` passes `run.source.city_tz` through to `resolve_tz`.
- [ ] D5 is untouched: no code path in this item creates a `Venue`.
- [ ] Migration applies cleanly and is reversible.

## Technical Notes

Where the new score sits matters for publication. `tz_gate(confidence)` feeds
`combine_gates` and then `_PUBLICATION`, so a score chosen too low will route every
city-zone event to review and the city will look empty for a different reason. Pick it so a
city-zone resolution still publishes, and assert the resulting `publication_status` in a
test rather than inferring it.

Consider whether a city-zone resolution should set `tz_review_pending`. Argument for: it is
the weakest resolution the pipeline can make. Argument against: it would flag every event
in every newly provisioned city, which is a review queue nobody can clear. Decide
explicitly and record the decision in the design doc.

## Dependencies

(none)
