---
run: run-eventpulse24-057
work_item: city-provider-templates
intent: city-picker-and-auto-collection
mode: confirm
checkpoint: plan-approval
status: approved
approved_at: 2026-11-20
---

# Implementation Plan: City-parameterized provider templates

## What this item is

The registry that makes "pick a city, get sources" possible: for a `CityChoice`, which
providers exist, what URLs they answer at, and in what order they should be tried.

`domain/city_providers.py` is **pure data and pure functions**. No network, no database, no
Django. That is the point of the item: *which providers exist for which cities* is a
code-reviewed fact, not a runtime surprise.

## The three risks the item flagged, all now resolved

**1. Ticketmaster's `city` parameter exists.** Verified live during item 3 against the
official Discovery v2 Event Search parameter table: `city`, array type, "Filter by city",
alongside `countryCode`, `stateCode`, `marketId`, `dmaId`, `radius`/`unit`. The fallback
the item feared (`countryCode` plus client-side filtering) is **not** needed. The item's
"verify it before building on it" instruction is satisfied by item 3's verification, and
the URL template below uses `city=` directly.

`latlong` is deprecated in favour of `geoPoint`, so **no template uses it**.

**2. The API key is not in the URL template.** Item 3 built the mechanism:
`Source.url` holds the key-less URL, `provider_keys.authorized_url()` adds `apikey=` for
the one fetch and marks it `credential=True`, and `strip_key()` removes it again before
anything stores it. So the template emits a **key-less** URL. The key never enters
`domain/`, and `domain/` cannot import `settings` anyway — AD-2's `domain-pure` contract
forbids it.

**3. The `api` parser now exists.** The item's AC says the API tier is inert until
`api-source-parser` lands. It landed (`2a0a647`): `PARSERS["api"]` → `parse_api` →
`READERS["app.ticketmaster.com"]` → `ticketmaster.read`. So the AC's own test — *every
method the registry can emit has a registered parser* — now has something to assert
against, and it is not vacuous.

## The one open call, decided here: Eventbrite's Terms

The item says: *"Either settle that question in this item or ship the template disabled
behind configuration — do not quietly promote a source the codebase has already flagged."*

**The template ships disabled, and the reason is a fact about the codebase, not a hedge.**

`seed_dhaka_live.py` — the command that proves the Eventbrite URL shape works — says in its
own docstring:

> Eventbrite's own Terms separately restrict automated access and point at their API, so
> this is a local-development source, not a production one.

So the codebase has *already* decided this, in the place where the evidence was gathered.
Re-deciding it here, without new evidence, would be a second opinion on a settled fact.

How "disabled" is expressed matters. The options were: (a) omit the Eventbrite template
entirely; (b) ship it in the registry behind a flag; (c) ship it enabled.

- (a) drops the only JSON-LD template whose URL shape is **proven by running code**. The
  AC asks for "a JSON-LD city-directory template", and the Eventbrite directory page is
  the one we have actually fetched and parsed.
- (c) promotes a source the codebase has flagged, which the item explicitly forbids.
- (b) is right, but the flag must be **code, not configuration**: `domain/` may not read
  `settings` (AD-2 `domain-pure` forbids `shared`; `domain` is stdlib-only per
  `tests/architecture/test_stdlib_only.py`). A module-level constant in `domain` is
  stdlib-compatible and code-reviewed, which is exactly what "ship it disabled behind
  configuration" asks for in a stdlib-only layer.

**So: the Eventbrite JSON-LD template ships in the registry, `DISABLED = True`, and
`resolve()` skips a disabled template.** The URL builder and the template function are
still there, still tested, and become live when someone flips one constant after a Terms
review — which is a legal decision, and legal decisions belong to people, not to a merge.

A disabled template is **not** a template that emits `crawl`, and it does not produce a
`SourceSpec` — `resolve()` returns nothing for it, so a disabled template can never be
registered. That is what makes "disabled" safe rather than merely quiet.

### What the JSON-LD template's URL is

The Eventbrite directory shape, proven by `seed_dhaka_live.py`:

```
https://www.eventbrite.com/d/bangladesh--dhaka/events/
```

That is `{country_slug}--{city_slug}`, where the city slug is the **provider's own**
slugging — *not* `domain.cities.mint_city_slug()`, which mints our FR-27 URL segment and
must not be re-pointed at a third party's URL scheme. The item says this outright, so the
template gets its own slug function, in the template, local to it.

## The shape of the module

```python
@dataclass(frozen=True)
class SourceSpec:
    name: str
    source_type: str
    url: str
    acquisition_method: str
    tz_coverage: str
```

Field names and vocabularies are taken from `apps.ingestion.models.Source`, because a
`SourceSpec` is a **proposed Source**, and the registry's own cleaner
(`clean_source_input`) validates those exact field names and values:

- `source_type` — `Source.SourceType`: venue / promoter / ticketing / community /
  government / media / other
- `acquisition_method` — `AcquisitionMethod`: api / partnership / jsonld / rss / ics /
  email_ics / crawl
- `tz_coverage` — `Source.TzCoverage`: full / partial / none

**`domain/` cannot import `apps.ingestion.models`** (AD-3 `models-ingestion`), so the
vocabularies are **restated as plain constants** in `domain/city_providers.py`, and a test
asserts each constant is a member of the model's vocabulary. That is the same pattern the
codebase already uses for the catalog's `country_code` values, and it is the only way a
stdlib-only module can stay honest about an `apps/` vocabulary it may not import.

The test is the guard that matters: if `AcquisitionMethod` gains a value, the registry
cannot drift from it silently.

### Templates

```python
@dataclass(frozen=True)
class ProviderTemplate:
    key: str
    method: str            # the acquisition_method every spec it emits carries
    build: Callable[[CityChoice], SourceSpec | None]
    enabled: bool = True
```

An ordered tuple, `TEMPLATES`, in FR-17's priority order:

| # | Template | Method | Enabled |
|---|---|---|---|
| 1 | Ticketmaster Discovery | `api` | yes |
| 2 | Eventbrite city directory | `jsonld` | **no** (Terms) |

`build` returns `None` when the provider cannot serve that city. That is a **normal
answer**, and the AC says so.

### Ticketmaster's country restriction

"A Ticketmaster Discovery API template is included, restricted to the countries it
actually covers, returning `None` elsewhere rather than minting a source that will always
be empty."

**The set is a module constant, `TICKETMASTER_COUNTRIES`, and it is the honest one.**

The official Discovery v2 page states its coverage as *"New Zealand, United Kingdom,
Ireland, other European countries, and more. More events and more countries are added on
continuous basis."* That is a **moving target**, stated in prose, not a list — so it cannot
be a fact this codebase holds. What the codebase can hold is a list that is **true today**
and **reviewable when it changes**.

So the set names the countries Ticketmaster operates in that the **catalog actually has
cities in**, and it is deliberately **not** the full global footprint:

| | Countries |
|---|---|
| North America | US, CA, MX |
| Oceania | AU, NZ |
| Western Europe | GB, IE, NL, BE, DE, ES, PT, FR, IT, AT, CH, DK, SE, NO, FI |

That is 19 of the catalog's 95 countries. A city in the other 76 gets **no Ticketmaster
source** — and that is the AC's own point: *"returning `None` elsewhere rather than minting
a source that will always be empty."* A source for a city Ticketmaster does not serve is a
source that will be fetched, found empty, and then judged a failure of *our* collection
rather than a fact about the provider.

**The test asserts the set against the catalog, both ways:**

- every country in `TICKETMASTER_COUNTRIES` is a country the **catalog actually has** —
  a set naming a country with no city in the catalog is a constant that has drifted;
- for every catalog city, the template returns a spec **iff** its country is in the set.

The second assertion is the "restricted to the countries it actually covers" AC, checked
over the whole dataset rather than a sample.

**The set is code, so widening it is a reviewed commit** — which is the right ceremony for
"we now know Ticketmaster serves Brazil". It is not a config value, because a config value
is a fact nobody reads.


### `resolve(city)`

```python
def resolve(city: CityChoice) -> tuple[SourceSpec, ...]:
    """The specs for `city`, in template order, skipping the templates that decline."""
```

- skips `None`s;
- skips **disabled** templates;
- returns an **empty tuple** for a city no template covers — a normal outcome, not an
  error. (Item 7 turns that into a `no_providers` status.)

## URL construction

The URL is built by string formatting over the catalog's columns, and **the query string
is built with `urlencode`** so a city with a space or an accent is encoded rather than
spliced raw into a URL.

The Ticketmaster template:

```
https://app.ticketmaster.com/discovery/v2/events.json?city={city}&countryCode={cc}
```

Wait — the country code is redundant when `city` is given, and adding a parameter that
might disagree with the city is a way to mint a source that answers about the wrong
place. But `countryCode` narrows the search in a way `city` alone does not, and the
country is a fact the catalog holds. Both come from the **same** `CityChoice` row, so
they cannot disagree. Kept, and the test asserts the two in the URL are the row's own
`country_code` and the row's own city.

**The `size` parameter.** Discovery v2 defaults to 20 events per page. A source that
only ever returns the first 20 is a source that goes stale silently. `size=100` is
Discovery's documented maximum per page — but it is a **per-page** size, and the number of
pages is a paging concern the fetch layer does not handle. So the template sets `size=100`
and nothing else: the first page is as full as Discovery will make it, and the paging
limit is a fact recorded in the item's own notes rather than a silent truncation.

**No `apikey` in the template.** Ever. That is item 3's whole mechanism.

## Tests

New file `backend/tests/domain/test_city_providers.py`.

Whole-dataset (parameterised over all 166 `WORLD_CITIES`):

1. `test_no_template_emits_crawl` — over the whole registry, no emitted spec has
   `acquisition_method="crawl"`. (The AC's own assertion.)
2. `test_every_method_the_registry_can_emit_has_a_parser` — every method any template can
   emit is in `PARSERS`.
3. `test_every_emitted_url_is_well_formed` — over the **full cross-product** of catalog ×
   templates (not a sample), the URL parses, has an `https` scheme and a host.
4. `test_every_emitted_url_is_within_the_length_bound` — over the same cross-product,
   `len(url) <= 2048` (the `Source.url` column's `max_length`).
5. `test_every_emitted_url_carries_no_api_key` — no emitted URL contains `apikey=`. The
   key is added at fetch time; a template that baked it in would put a credential in
   every audit row.
6. `test_the_ticketmaster_template_covers_exactly_the_countries_it_names` — the set is
   countries the catalog has; the template returns a spec iff the row's country is in it.
7. `test_resolve_returns_the_specs_in_template_order` — order is FR-17's.

Registry-level:

8. `test_the_templates_are_ordered_by_fr_17_priority` — the emitted methods are
   non-increasing in FR-17's rank (`api` before `jsonld`), asserted over the tuple.
9. `test_no_template_declares_crawl` — asserted on the template *declarations*, not only
   on what they emit, so a template that never fires for a catalog city still cannot say
   `crawl`.
10. `test_a_disabled_template_emits_nothing` — the Eventbrite template is disabled, and
    `resolve()` returns no spec for it for any city.
11. `test_resolve_returns_an_empty_tuple_for_a_city_no_template_covers` — a city outside
    the Ticketmaster countries, with the JSON-LD template disabled.
12. `test_resolve_skips_a_template_that_declines_the_city`.
13. `test_the_url_is_built_from_the_cities_own_columns` — the city's name and the
    country's code are in the URL, and a different city's row would give a different URL.

Vocabulary:

14. `test_every_source_type_is_in_the_models_vocabulary`.
15. `test_every_acquisition_method_is_in_the_models_vocabulary`.
16. `test_every_tz_coverage_is_in_the_models_vocabulary`.

## Files

**Created**

| File | Purpose |
|---|---|
| `backend/domain/city_providers.py` | `SourceSpec`, `ProviderTemplate`, `TEMPLATES`, `resolve()` |
| `backend/tests/domain/test_city_providers.py` | The whole-dataset proof |

**Modified:** none. This item is additive on purpose — nothing else needs to change for a
new provider to exist.

## Verification

```bash
uv run --directory backend pytest tests/domain/test_city_providers.py -q
make test-backend
make lint-imports
```

## The checkpoint

This is a **confirm**-mode item, so there is one checkpoint before implementation. **Both
calls were confirmed at the checkpoint:**

1. **Eventbrite ships disabled** — in the registry, not omitted; `resolve()` skips it;
   flipping one constant after a Terms review makes it live. ✅ confirmed
2. **The vocabularies are restated as constants in `domain/`**, with a test asserting each
   is a member of the model's vocabulary — because `domain` may not import
   `apps.ingestion.models`. ✅ confirmed
3. **Ticketmaster's country set** is a module constant naming the countries Discovery
   actually covers, with the catalog-city check above it. — a design detail, not a
   decision to ask about; the set and its reasoning are above.
