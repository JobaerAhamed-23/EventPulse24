---
run: run-eventpulse24-057
work_item: city-provider-templates
intent: city-picker-and-auto-collection
generated: 2026-11-20
status: passed
---

# Test Report: City-parameterized provider templates

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Registry (new) | 45 | 0 | 0 | 100% |
| Backend suite (full) | 8664 | 0 | 0 | 97.45% |
| **Total** | **8664** | **0** | **0** | **97.45%** |

`domain/` at **100%**. `domain/city_providers.py` at **100%** — every line, including the
branches a disabled template never takes. `lint-imports` 21 contracts kept, 0 broken.
Overall coverage 97.45%, up from 97.44%.

## Acceptance Criteria Validation

- ✅ **`domain/city_providers.py` defines a frozen `SourceSpec(name, source_type, url,
  acquisition_method, tz_coverage)` and an ordered tuple of templates** —
  `SourceSpec` and `ProviderTemplate` are both `@dataclass(frozen=True)`, asserted by
  `test_a_source_spec_is_frozen` and `test_a_provider_template_is_frozen` (a frozen
  dataclass raises `FrozenInstanceError`, not a bare `Exception`). The ordered tuple is
  `PROVIDER_TEMPLATES`.
- ✅ **Each template is a pure function `CityChoice -> SourceSpec | None`. `None` means
  "this provider cannot serve this city" and is a normal answer** — `build` is typed
  `Callable[[CityChoice], SourceSpec | None]`; `None` is returned for a city outside
  Ticketmaster's countries (`test_a_city_outside_the_set_is_declined_rather_than_given_an_empty_source`)
  and `resolve()` skips it.
- ✅ **Templates are ordered by FR-17 priority: `api` before `jsonld`/`rss`/`ics`** —
  `test_the_templates_are_ordered_by_the_method_priority` asserts the emitted methods'
  ranks are non-increasing over `ACQUISITION_METHODS`, which is FR-17's order as a tuple;
  `test_the_api_tier_comes_first` pins the head of the registry; and
  `test_resolve_returns_the_specs_in_template_order` asserts `resolve()`'s **output** order
  too, not only the declaration.
- ✅ **No template may emit `acquisition_method="crawl"` — asserted by a test over the whole
  registry** — **two** assertions: `test_no_template_declares_crawl` (on the declarations,
  so a template that never fires for a catalog city still cannot say `crawl`) and
  `test_no_emitted_spec_carries_crawl` (on every spec the cross-product produces).
- ✅ **A Ticketmaster Discovery API template is included, restricted to the countries it
  actually covers, returning `None` elsewhere** —
  `test_the_template_answers_exactly_for_the_countries_it_names` asserts over **every**
  catalog city that a spec is returned **iff** the row's country is in
  `TICKETMASTER_COUNTRIES`. `test_every_country_in_the_set_is_a_country_the_catalog_has`
  holds the set against the catalog, so a constant naming a country with no city cannot
  drift.
- ✅ **Any template emitting `acquisition_method="api"` is covered by a parser in
  `PARSERS`** — `test_every_method_the_registry_can_emit_has_a_parser` and
  `test_every_emitted_specs_method_has_a_parser`. **`api` is no longer inert**: item 3
  landed `PARSERS["api"] → parse_api → READERS["app.ticketmaster.com"] → ticketmaster.read`,
  so the assertion has a real answer to give and a future template cannot emit a method
  `parse()` would refuse.
- ✅ **A JSON-LD city-directory template is included, built from `country_slug` and a city
  slug** — the Eventbrite template, `https://www.eventbrite.com/d/{country_slug}--{city_slug}/events/`,
  the shape `seed_dhaka_live.py` fetches and parses. **It ships disabled** (see below).
- ✅ **Every emitted `url` is well-formed and <= 2048 characters — asserted across the full
  cross-product of catalog x templates, not a sample** — `test_every_emitted_url_is_an_https_url_with_a_host`,
  `test_every_emitted_url_is_within_the_length_bound` (2048, the `Source.url` column's
  `max_length`), `test_every_emitted_url_has_no_credentials_in_it`, all over the **332
  pairs** (166 cities × 2 templates).
- ✅ **`resolve(city)` returns the specs for a city in template order, skipping `None`s, and
  returns an empty tuple for a city no template covers** —
  `test_resolve_returns_an_empty_tuple_for_a_city_no_template_covers` (a city outside
  Ticketmaster's countries, with the JSON-LD template disabled),
  `test_resolve_skips_a_disabled_template`, `test_resolve_is_pure`.
- ✅ **Stdlib only. No network, no database, no Django** — the module imports only
  `collections.abc`, `dataclasses`, `urllib.parse` and `domain.city_catalog`. Two
  independent guards hold it: `lint-imports`'s `domain-pure` contract (forbids `django`,
  `ninja`, `pydantic`, `shared`) and `tests/architecture/test_stdlib_only.py`, which
  parameterises over every file in `domain/`.

## The decisions taken at the checkpoint

| Decision | Chosen | Where it is tested |
|---|---|---|
| **The Eventbrite template** | **Ships in the registry, `enabled=False`** | `test_a_disabled_template_is_marked_disabled`, `test_a_disabled_template_emits_nothing_through_resolve`, `test_a_disabled_template_cannot_reach_resolve_at_all` |
| **The vocabularies** | Restated as constants in `domain/`, with a drift test | `test_every_source_type_is_in_the_models_vocabulary`, `test_every_acquisition_method_is_in_the_models_vocabulary`, `test_every_tz_coverage_is_in_the_models_vocabulary` |

## What "disabled" means, and why it had to be more than quiet

A disabled template that only *hid* itself would be settled by whoever was paying
attention. So "disabled" is asserted to mean **cannot be registered**:

- `test_a_disabled_template_emits_nothing_through_resolve` asserts, for **every catalog
  city**, that the spec the disabled template *would* have built is absent from
  `resolve()`'s answer — and the assertion is **both halves**: the "would have" spec is
  computed, and `resolve()` is separately asserted to return something for a city the
  enabled template covers (`test_resolve_still_returns_something_for_a_city_the_enabled_template_covers`),
  so an empty tuple cannot pass for the right reason.
- `test_a_disabled_template_cannot_reach_resolve_at_all` — even for a city Ticketmaster
  declines, the template is skipped whole.
- `test_the_disabled_template_still_builds_a_spec_when_asked_directly` — the URL shape is
  **kept and tested**, because that is what a person flips the constant for.

## The finding the work surfaced: two Portlands, one URL

**The cross-product test found a real defect in the template as first written.**

Eventbrite's URL shape has one city segment and a separate country segment:
`/d/{country_slug}--{city_slug}/events/`. The catalog holds **two Portlands** —
"Portland, ME" and "Portland, OR" — and the slug was built by dropping the region
qualifier, which the shape has nowhere to put. So both rows minted the **same URL**:

```
https://www.eventbrite.com/d/united-states--portland/events/
```

`register_source` refuses a duplicate URL (`SourceAlreadyRegisteredError`), so the second
Portland would have been **refused rather than served** — and the reader in Maine would
have been shown Oregon's events. That is the exact failure the item's AC warns about:
"minting a source that will always be empty", one level up.

**The fix:** the region's own qualifier goes into the city segment — "portland-or" and
"portland-me". A city with no qualifier keeps its plain name, which is the shape
`seed_dhaka_live.py` proves ("bangladesh--dhaka").

Three tests now hold it: `test_two_cities_never_get_the_same_url` (over every emitted
spec, not a sample), `test_two_portlands_do_not_collide`, and
`test_the_city_slug_is_the_providers_own_not_ours`.

**The mutation check proves the fix is load-bearing** — dropping the region qualifier
again fails 4 tests, including the two Portlands'.

## Mutation Check

Every whole-dataset invariant was mutated and the mutation reverted. **The rule that a
test must be able to fail.**

| Mutation | Result |
|---|---|
| A template emits `crawl` | **5 failed** |
| A template emits `partnership` — a method with no parser | **4 failed** |
| The API key is baked into the template URL | **1 failed** — `test_no_emitted_url_carries_an_api_key` |
| The country restriction removed (every city gets a Ticketmaster source) | **4 failed** |
| The disabled template is enabled | **6 failed** |
| The templates reordered (`jsonld` first) | **4 failed** |
| The region qualifier dropped from the Eventbrite slug (the Portland collision) | **4 failed** |
| The query built by string splicing instead of `urlencode` | **2 failed** |

The third is the one that matters most: it is the trap the item's technical note warned
about ("no API key in a URL template"), put back, and the test catches it.

## Tests Written

**`tests/domain/test_city_providers.py` (new, 45 tests)** — the item's own proof.

*The rules the registry exists to hold (9)*: no template declares `crawl`; no emitted spec
carries `crawl`; every method the registry can emit has a parser; every emitted spec's
method has a parser; no emitted URL carries an API key; no template mentions a key
parameter — **checked on the template as well as the spec**, because a disabled template
that baked in a key would still have the secret in the repository and would ship it the
day it is enabled.

*The URLs (8)*: https with a host; within 2048 characters; no userinfo credentials; the
query built by encoding, not splicing; a comma percent-encoded; an accented city reaches
the URL intact; the city and the country in the URL are the row's own; the API URL points
at exactly `app.ticketmaster.com`; two cities never get the same URL.

*Ticketmaster's country restriction (3)*: every country in the set is a country the
catalog has; the template answers exactly for the countries it names, over every city; a
city outside the set is declined.

*FR-17's order (3)*: the templates are ordered by the method priority; the API tier comes
first; `resolve()` returns the specs in template order.

*`resolve` (5)*: an empty tuple for a city no template covers; a disabled template is
skipped; a covered city returns its spec; `resolve()` is pure.

*Disabled templates (5)*: the template is in the registry; it is marked disabled; it emits
nothing through `resolve()`, both halves; it cannot reach `resolve()` at all; it still
builds a spec when asked directly.

*The Eventbrite URL shape (4)*: the country-slug/double-dash/city-slug shape; the city's
own slugging, with the region carried; two Portlands do not collide; a space is folded.

*The vocabularies (4)*: each of the three constants is a member of the model's vocabulary;
every emitted spec's values are in the vocabularies.

*The module itself (6)*: a spec is frozen; a template is frozen; the registry is not
empty; the template keys are unique; every template declares a method in the vocabulary;
the public types are what they claim to be.

## Test Commands

```bash
uv run --directory backend pytest tests/domain/test_city_providers.py -q
make test-backend && make coverage-backend
make lint-imports
```

## Issues Found

One, and it was a real defect rather than a test artefact — **the two Portlands minting
one URL**, described above. It was found by the whole-cross-product test, not by the suite
going green, and it is fixed with the region's qualifier carried in the city segment.

The other four failures during the work were **wrong test assumptions about the catalog**,
not defects in the module: the catalog has no "New York City" row (it is "New York, NY"),
Bangladesh is not in Ticketmaster's countries, and there are two Portlands rather than
one. Each was corrected against the catalog's actual contents.

## Ready for Completion

- [x] All tests passing (8664, zero failures)
- [x] Coverage met (100% on `domain/city_providers.py`, 100% on `domain/`, 97.45% overall)
- [x] All 10 acceptance criteria validated
- [x] Every whole-dataset invariant mutation-checked (8 mutations, all caught)
- [x] `lint-imports` 21 contracts kept, 0 broken
- [x] The module is stdlib-only, checked by two independent guards

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-057*
