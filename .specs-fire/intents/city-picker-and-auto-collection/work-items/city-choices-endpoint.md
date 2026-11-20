---
id: city-choices-endpoint
title: The picker's choices endpoint
intent: city-picker-and-auto-collection
complexity: medium
mode: confirm
status: pending
depends_on: [city-catalog-dataset]
created: 2026-11-20
---

# Work Item: The picker's choices endpoint

## Description

A public endpoint serving the curated catalog as picker choices — `{ value, label }` pairs,
alphabetical, stable. This is what the city `<select>` reads instead of
`GET /api/public/preview/cities`.

`list_supported_cities()` is **not** deleted. It answers a different and still-live
question — "which cities can the preview actually serve right now?" — and the Pulse Preview
still needs it. What changes is that it stops being mistaken for the picker's source.

## Acceptance Criteria

- [ ] A public endpoint returns the catalog as an ordered list of `{ value, label }`.
- [ ] `value` is the catalog's `name` (the string that will be stored); `label` is the disambiguated display form.
- [ ] The order is alphabetical by label under `str.casefold`, computed in Python — never a database `ORDER BY`, for the locale-collation reason `list_supported_cities` already documents.
- [ ] The response is identical for every caller and reads no session and no `personal` schema (AD-12), so it is cacheable.
- [ ] `list_supported_cities()` is unchanged in behaviour, and its docstring is amended to say it is the preview's coverage answer and not the picker's source.
- [ ] `home-city.tsx`'s docstring claim that the choices come from `preview/cities` is corrected in the item that rewires it, not left stale here.
- [ ] An architecture test asserts the endpoint touches no `personal` model.

## Technical Notes

The catalog is static, so this endpoint can be served without a database query at all. Do
not add a database read to make it feel symmetrical with the preview endpoint.

Put it alongside the existing public preview endpoints in `apps/catalog`, which is already
the home for anonymous surfaces under AD-12.

## Dependencies

- city-catalog-dataset
