---
id: city-provisioning-service
title: Provisioning a city on first pick
intent: city-picker-and-auto-collection
complexity: high
mode: validate
status: pending
depends_on: [city-catalog-dataset, city-provider-templates, source-city-timezone, api-source-parser]
created: 2026-11-20
---

# Work Item: Provisioning a city on first pick

## Description

The service that turns a pick into collection: mint the `City` row, walk the provider
templates, register a `Source` per spec with the city's zone on it, and record what
happened so the surface can tell the truth about it.

After this, the existing scheduler does the rest for free — a source with
`last_attempted_at IS NULL` is due immediately, so `claim_due_sources` takes it on the next
60-second tick.

## Acceptance Criteria

- [ ] A `CityProvisioning` record exists, keyed uniquely on the city, with a status of `collecting` | `live` | `no_providers` | `yielded_nothing` | `paused`.
- [ ] `provision_city(city)` mints the `City` row via the existing `resolve_city()` when none exists, so the city has a slug and an FR-27 page before any event arrives.
- [ ] It registers one `Source` per spec from `city_providers.resolve()`, through the existing `source_registry.register_source()` — not by direct ORM writes, so FR-13's audit and FR-17's guards both apply.
- [ ] Each registered source carries `city` = the catalog name and `city_tz` = the catalog zone.
- [ ] A source is only registered for a method that has a registered parser. Registering a method `parse()` would answer `unsupported_method` for is a defect, and a test asserts it cannot happen.
- [ ] A city no template covers mints the `City` row and records `no_providers`, registering nothing. This is a normal outcome, not an error.
- [ ] Provisioning is **idempotent**: a second pick of an already-provisioned city registers nothing further and leaves its status untouched.
- [ ] Provisioning is **concurrency-safe**: two users picking the same city at the same moment produce one set of sources, not two. Use the same advisory-lock discipline `digest_preferences` already uses rather than relying on the unique constraint to raise.
- [ ] Provisioning is triggered on commit of a successful home-city set, never inline in the request's critical path — a slow registry write must not fail the user's save.
- [ ] A failure to provision does **not** roll back the stored city. The pick is kept; the status reflects the failure.
- [ ] Audit rows are written for the provisioning and for each registered source. AD-13: the city name stays out of `details`.
- [ ] `ingestion` remains the sole writer of `Source` and `City` (AD-16); `personalization` reaches this through a published interface, not by importing `apps.ingestion.models`.

## Technical Notes

The trigger belongs next to `enqueue_digest_composition_on_commit(user_id)` in
`set_home_city` — the same `on_commit` discipline, for the same reason: the row must be
committed before the worker reads it.

The AD-3 wall is the design constraint here. `personalization` may import
`apps.ingestion.services.*` (it already imports `catalog_read` in three places) but not
`apps.ingestion.models`. So the provisioning entry point is a service function and the
`CityProvisioning` model lives in `ingestion`.

Note that `_venue_for` falls back to `run.source.city` when a candidate names no venue
city, so setting `Source.city` to the catalog name also gives the pipeline the right city
string for fingerprinting and for `EventFit`. That is deliberate and worth a test.

## Dependencies

- city-catalog-dataset
- city-provider-templates
- source-city-timezone
- api-source-parser
