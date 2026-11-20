---
id: city-catalog-dataset
title: The curated world-city catalog
intent: city-picker-and-auto-collection
complexity: medium
mode: confirm
status: pending
depends_on: []
created: 2026-11-20
---

# Work Item: The curated world-city catalog

## Description

A checked-in, stdlib-only dataset of world cities — the list the picker offers, independent
of what has been ingested. One row per city, carrying everything downstream items need:
the name as it should be stored, the country, the trailing region qualifier where one is
needed to keep two same-named cities apart, and the IANA timezone.

The zone is the load-bearing column. It is what lets a brand-new city resolve date-only
event times without a registered venue, and it is a fact that does not go stale.

Lives in `domain/` because it is pure data with no database and no I/O, and because
`domain.cities` — which it must agree with — already lives there.

## Acceptance Criteria

- [ ] `domain/city_catalog.py` defines a frozen `CityChoice(name, country_code, country_slug, region, tz)` and a module-level tuple of them.
- [ ] The dataset covers a broad spread of countries and regions, well beyond the cities currently ingested, and includes at least one same-named pair (Portland, OR / Portland, ME) as a worked case.
- [ ] `name` is the string that will be stored on `DigestPreference` — "Portland, OR", not "Portland, Oregon".
- [ ] A `label` derivation produces the disambiguating display form ("Portland, Oregon", "Chittagong, Bangladesh") without that form ever being stored.
- [ ] `lookup(name)` returns the `CityChoice` for a stored city string, case- and spacing-insensitively, and `None` for a city not in the catalog.
- [ ] Every row's `tz` loads via `zoneinfo.ZoneInfo` and passes `domain.timezones.canonical_zone` — asserted by a test over the whole dataset, not a sample.
- [ ] Every row's `name` round-trips through `domain.cities.split_region()` to the `(key, region)` the row declares — asserted over the whole dataset.
- [ ] No two rows share a `(normalized_key, region, country_code)` identity — asserted over the whole dataset.
- [ ] Every row's `country_code` is two uppercase letters.
- [ ] Stdlib only. No Django import, no database access.

## Technical Notes

`domain.cities.split_region()` already treats a trailing alphabetic run of <= 3 characters
as a region qualifier, so "Portland, OR" keys as `("portland", "or")` and "Chittagong" as
`("chittagong", "")`. The catalog must not fight this — it declares what `split_region`
will produce, and a test proves the two agree. That is why `region` is a column rather
than something re-derived downstream.

`country_slug` ("bangladesh", "united-states") exists only for URL templating in
`city-provider-templates`; it is not an identity field.

Do not reuse `CITY_ALIAS_GROUPS` here. That table answers "which written forms name the
same place"; this one answers "which places may be picked". Keeping them separate is what
lets a catalog entry exist for a city the alias table has never heard of.

## Dependencies

(none)
