---
run: run-eventpulse24-057
work_item: city-provider-templates
intent: city-picker-and-auto-collection
generated: 2026-11-20
mode: confirm
---

# Implementation Walkthrough: City-parameterized provider templates

## Summary

`domain/city_providers.py` is the registry that makes "pick a city, get sources" possible.
For a `CityChoice`, it answers two questions: **which providers exist for this city**, and
**what URL does each answer at**.

It is **pure** — no network, no database, no Django. That is the point of the item:
*which providers exist for which cities* is a **code-reviewed fact**, not a runtime
surprise. The whole registry can be evaluated in a test, over every city, with no side
effects at all.

## The three risks the item flagged, all resolved before planning

**1. Ticketmaster's `city` parameter exists.** Verified live during item 3 against the
official Discovery v2 Event Search parameter table: `city`, array type, "Filter by city",
alongside `countryCode`, `stateCode`, `marketId`, `dmaId`, `radius`/`unit`. The fallback the
item feared — `countryCode` plus client-side filtering — is **not** needed, and the
template uses `city=` directly. `latlong` is deprecated in favour of `geoPoint`, so **no
template uses it**.

**2. The API key is not in the URL template.** Item 3 built the mechanism:
`Source.url` holds the key-less URL, `provider_keys.authorized_url()` adds `apikey=` for
the one fetch and marks it `credential=True`, and `strip_key()` removes it before anything
stores it. The template emits a **key-less** URL. `domain/` could not hold a key anyway —
it is stdlib-only and cannot read `settings`.

**3. The `api` parser now exists.** Item 3 landed
`PARSERS["api"] → parse_api → READERS["app.ticketmaster.com"] → ticketmaster.read`. The
AC's own test — *every method the registry can emit has a registered parser* — now has a
real answer to give.

## Structure Overview

```text
backend/domain/city_providers.py
├── SourceSpec            frozen — a proposed Source row
├── ProviderTemplate      frozen — one provider's rule for a city
├── ACQUISITION_METHODS   FR-17's order, as a tuple
├── TICKETMASTER_COUNTRIES  the countries Discovery actually serves
├── _ticketmaster_spec    CityChoice -> SourceSpec | None
├── _eventbrite_spec      CityChoice -> SourceSpec | None   (disabled)
├── PROVIDER_TEMPLATES    the ordered registry
└── resolve(city)         the specs, in template order
```

## The four rules the registry holds

| Rule | Why it is a fact, not a preference |
|---|---|
| **No template emits `crawl`** | FR-17 gates crawling behind an approved ToS review, and nothing automatic can grant one. A `crawl` source would be refused by `ensure_can_ingest` — forever, and silently |
| **Every emitted method has a parser** | A source whose method `parse()` answers `unsupported_method` for is a source that never ingests |
| **No URL carries an API key** | A key in a URL is a credential. `Source.url` is a column read by the admin, and `register_source` writes its fields into an audit row kept for 24 months |
| **A disabled template produces nothing** | "Disabled" has to mean "cannot be registered", not merely "is quiet" |

The fourth is the one the tests work hardest on. A disabled template that only *hid* itself
would be settled by whoever was paying attention, so `test_a_disabled_template_emits_nothing_through_resolve`
computes the spec the disabled template **would** have built and asserts it is absent from
`resolve()`'s answer — **both halves**, with a separate test asserting `resolve()` still
returns something for a covered city, so an empty tuple cannot pass for the right reason.

## Architecture

### The vocabularies are restated, and a test holds them to the model's

`domain` may not import `apps.ingestion.models` (AD-3's `models-ingestion` contract), and
is stdlib-only besides. So `SOURCE_TYPES`, `ACQUISITION_METHODS` and `TZ_COVERAGES` are
plain constants here.

Restating a vocabulary is a place two truths could grow apart, so
`tests/domain/test_city_providers.py` asserts each constant is a member of the model's
vocabulary — if `AcquisitionMethod` gains a value, this registry cannot drift from it
silently. **The test is the guard; the constants are the copy.**

### `ACQUISITION_METHODS` is a tuple, not a set

The first draft declared it a `frozenset`. The "templates are ordered by FR-17 priority"
test ranks by `enumerate` over the vocabulary — and a set has no order, so the test was
ranking by **hash order** and failing.

That is the bug the shape was hiding. `AcquisitionMethod`'s own docstring says "FR-17
priority order, highest first", and `ensure_can_ingest` refuses a crawl source without an
approved ToS review. **The tier order is a fact this module rests on**, and a set throws
it away. It is a tuple now, with `ACQUISITION_METHOD_SET` as the set view for membership
questions — two names on purpose, because they answer two different questions.

### The field names are the registry's own

`Source.url`, `Source.source_type`, `Source.acquisition_method`, `Source.tz_coverage` — so
a `SourceSpec` is a `Source` row that has not been written yet, and
`clean_source_input` validates it under exactly the rules the row will meet. No
translation layer in between.

### The module is pure, and two independent guards say so

`lint-imports`'s `domain-pure` contract forbids `django`, `ninja`, `pydantic` and
`shared` from `domain/`; `tests/architecture/test_stdlib_only.py` parameterises over
**every file in `domain/`** and checks its imports. The module imports only
`collections.abc`, `dataclasses`, `urllib.parse` and `domain.city_catalog`.

## The finding: two Portlands, one URL

**The whole-cross-product test found a real defect in the template as first written.**

Eventbrite's URL shape has one city segment and a separate country segment:
`/d/{country_slug}--{city_slug}/events/`. The slug dropped the region's qualifier — the
shape has nowhere to put it — and the catalog holds **two Portlands**:

```
Portland, ME  ─┐
                ├─→  https://www.eventbrite.com/d/united-states--portland/events/
Portland, OR  ─┘
```

`register_source` refuses a duplicate URL, so the second Portland would have been
**refused rather than served**, and the reader in Maine would have been shown Oregon's
events.

**The fix:** the region's own qualifier goes into the city segment — "portland-or" and
"portland-me". A city with no qualifier keeps its plain name, which is the shape
`seed_dhaka_live.py` proves ("bangladesh--dhaka").

The mutation check confirms the fix is load-bearing: dropping the qualifier again fails 4
tests, including `test_two_portlands_do_not_collide`.

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| **The Eventbrite template** | **In the registry, `enabled=False`** | **Your checkpoint call.** `seed_dhaka_live.py` already says Eventbrite's Terms "restrict automated access and point at their API" — the codebase has decided this in the place the evidence was gathered. Omitting it would drop the only JSON-LD shape *proven by running code*; enabling it would promote a source the codebase has flagged. Disabled keeps the shape and the tests, and makes the source live on one constant after a person's review |
| **"Disabled" means** | Cannot be registered, not merely quiet | A disabled template that only hid itself would be settled by whoever was paying attention. So `resolve()` skips it whole, and the test asserts the *would-have* spec is absent — both halves |
| **The vocabularies** | Restated as constants, with a drift test | **Your checkpoint call.** `domain` may not import `apps.ingestion.models`, and is stdlib-only besides. The restatement is guarded, so the two truths cannot drift apart silently |
| **`ACQUISITION_METHODS`** | A tuple, not a set | FR-17's order *is* the meaning, and `ensure_can_ingest` refuses a crawl source without an approved ToS review. A set throws the order away |
| **Ticketmaster's country set** | 19 countries, as a module constant | The official page states coverage in prose — "New Zealand, United Kingdom, Ireland, other European countries, and more" — and says more are added continuously. **No fixed list of theirs is a fact we could hold.** What we hold is the list that is true today for countries the catalog has cities in, and widening it is a reviewed commit: the right ceremony for "we now know Ticketmaster serves Brazil" |
| **The page size** | `size=100`, Discovery's documented maximum | The default is 20, and a source that only ever sees the first 20 goes stale silently. **`size` is per page, not a total** — paging is a fetch-layer concern, so the template asks for the fullest first page and stops |
| **The city slug** | The provider's own, not `mint_city_slug` | The item says so outright: `mint_city_slug` mints *our* FR-27 URL segment and must not be re-pointed at a third party's scheme |
| **`tz_coverage`** | `full` for Discovery, `none` for the Eventbrite page | A claim the provider supports. Discovery states a zone on every event; the directory page states none anywhere, so every one of its events leans on its venue |

## What the mutation check found

Eight mutations, all reverted, all caught:

| Mutation | Result |
|---|---|
| A template emits `crawl` | 5 failed |
| A template emits `partnership` — a method with no parser | 4 failed |
| **The API key baked into the template URL** | **1 failed** — the trap the item's technical note warned about, put back |
| The country restriction removed | 4 failed |
| The disabled template enabled | 6 failed |
| The templates reordered (`jsonld` first) | 4 failed |
| The region qualifier dropped (the Portland collision) | 4 failed |
| The query string-spliced instead of `urlencode`d | 2 failed |

Four other failures during the work were **wrong test assumptions about the catalog**, not
defects in the module: there is no "New York City" row (it is "New York, NY"), Bangladesh
is not in Ticketmaster's countries, and there are two Portlands rather than one.

## Verification

```bash
uv run --directory backend pytest tests/domain/test_city_providers.py -q   # 45 passed
make test-backend                                                            # 8664 passed
make coverage-backend                                                        # 97.45%, domain/ 100%
make lint-imports                                                            # 21 kept, 0 broken
```

`domain/city_providers.py` is at **100%** — every line, including the branches a disabled
template never takes.

## What This Unblocks

`city-provisioning-service` (item 7) is next, and it consumes this registry directly:
`provision_city(city)` walks `city_providers.resolve()`, registers one `Source` per spec
through the existing `source_registry.register_source()`, and records what happened. The
AC it inherits from here:

- **a city no template covers mints the `City` row and records `no_providers`** — that is
  `resolve()`'s empty tuple, and it is a normal answer, not an error;
- **a source is only registered for a method that has a registered parser** — this
  registry's own AC already guarantees it, over every city and every template;
- **each registered source carries `city` = the catalog name and `city_tz` = the catalog
  zone** — the catalog name is `CityChoice.name`, and item 2's `source-city-timezone`
  already put the zone on the row.

Two things item 7 must know from here:

1. **A spec's URL is key-less**, and it stays that way — item 7 registers it as-is, and
   the key is added at fetch time.
2. **The Eventbrite template contributes nothing today.** So a city outside Ticketmaster's
   19 countries resolves to **no sources at all**, which item 7 records as `no_providers`.
   That is honest — a source for a city no provider serves would be fetched, found empty,
   and read as a failure of our collection rather than a fact about the provider.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-057*
