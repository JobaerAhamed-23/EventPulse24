---
id: home-city-dropdown-catalog
title: The dropdown reads the catalog
intent: city-picker-and-auto-collection
complexity: medium
mode: confirm
status: pending
depends_on: [city-choices-endpoint, stored-city-is-the-picked-city]
created: 2026-11-20
---

# Work Item: The dropdown reads the catalog

## Description

Point the city `<select>` at the curated catalog, show the disambiguating labels, and
correct the docstring that currently explains the component in terms of a rewrite that no
longer happens.

It stays a `<select>`. No free text.

## Acceptance Criteria

- [ ] `/settings/profile`'s city control reads the catalog choices endpoint instead of `GET /api/public/preview/cities`.
- [ ] Options render the disambiguating `label` and submit the catalog `value` — the user sees "Portland, Oregon" and the server stores "Portland, OR".
- [ ] Picking a city stores that city and the control shows it afterwards. A test asserts a city with no ingested events is picked and kept — it must fail against today's rewrite.
- [ ] The stored city remains in the options even when the catalog no longer offers it, so a select whose value is absent never renders blank. This behaviour exists today and must be preserved by test, not by accident.
- [ ] `citySourceNote()` still labels a `fallback` city honestly for the accounts that already carry one.
- [ ] The "Choose a city" placeholder still appears only when no city is set.
- [ ] The component's docstring is rewritten: the paragraph claiming the server "replaces a city it cannot serve with a fallback (FR-2), silently — so typing 'Chittagong' would appear to work and quietly store somewhere else" is **no longer true for a picked city** and must not be left standing as the stated reason for the control's shape.
- [ ] The list is long enough to need it, so the control remains usable at that length — keyboard type-ahead works and the option count does not break the layout.
- [ ] Browse's "Change city" links still land on this control.
- [ ] No country dropdown, no country field, no "cities near you" appears anywhere in this item.

## Technical Notes

The existing `options` line — `choices.includes(city ?? "") || city === null ? choices : [city, ...choices]` — is what satisfies the user's §3 ("my city stays mine") and already works. Keep it; the only change is where `choices` comes from and that options now carry a separate label.

A catalog of a few thousand entries in a native `<select>` is acceptable and keeps the
platform's own type-ahead and mobile picker. If the length proves unworkable, that is a
finding for a follow-up item, not a licence to turn this into a combobox — the user asked
twice for a dropdown and not a text box.

## Dependencies

- city-choices-endpoint
- stored-city-is-the-picked-city
