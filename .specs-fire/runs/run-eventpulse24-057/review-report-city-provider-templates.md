---
run: run-eventpulse24-057
work_item: city-provider-templates
intent: city-picker-and-auto-collection
generated: 2026-11-20
status: complete
---

# Code Review: City-parameterized provider templates

## Files Reviewed

| File | Change |
|------|--------|
| `backend/domain/city_providers.py` | NEW — `SourceSpec`, `ProviderTemplate`, `PROVIDER_TEMPLATES`, `resolve()` |
| `backend/tests/domain/test_city_providers.py` | NEW — 45 tests, whole-dataset |

Nothing else changed. This item is **additive on purpose**: a new provider is a new
template function and one entry in a tuple, and no other module has to know.

## Project Tooling

| Tool | Result |
|------|--------|
| `ruff check` | All checks passed |
| `ruff format --check` | Clean (both files formatted; the repo root was not touched) |
| `lint-imports` | 21 contracts kept, 0 broken |
| `pytest` (full) | **8664 passed, 0 failed** (8617 at HEAD) |
| Coverage | `domain/city_providers.py` **100%**; `domain/` 100%; overall 97.45% |

## Findings

### 1. [Correctness] Two Portlands minted one URL — FIXED

**File**: `domain/city_providers.py`, `_eventbrite_city_slug`

Eventbrite's URL shape has one city segment and a separate country segment:
`/d/{country_slug}--{city_slug}/events/`. The slug dropped the region's qualifier, and
the catalog holds **two Portlands** — "Portland, ME" and "Portland, OR". Both rows minted:

```
https://www.eventbrite.com/d/united-states--portland/events/
```

`register_source` refuses a duplicate URL (`SourceAlreadyRegisteredError`), so the second
Portland would have been **refused rather than served**, and the reader in Maine would
have been shown Oregon's events.

**The fix** carries the region's own qualifier into the city segment: "portland-or" and
"portland-me". A city with no qualifier keeps its plain name, which is the shape
`seed_dhaka_live.py` proves ("bangladesh--dhaka").

**Found by the whole-cross-product test**, not by the suite going green. The mutation check
confirms the fix is load-bearing: dropping the qualifier again fails 4 tests.

**Risk**: none now. The shape deviates from the single example the codebase has proven —
"bangladesh--dhaka" — but only for cities that *need* a qualifier, and the alternative was
a wrong city.

### 2. [Correctness] `ACQUISITION_METHODS` was a set, which threw away FR-17's order — FIXED

**File**: `domain/city_providers.py`

The first draft declared `ACQUISITION_METHODS = frozenset({...})`. A set has no order, so
the "templates are ordered by FR-17 priority" test — which ranks by `enumerate` over the
vocabulary — computed its ranks from **hash order**, and failed.

That is the bug the shape was hiding: `AcquisitionMethod`'s own docstring says "FR-17
priority order, highest first", and `ensure_can_ingest` refuses a crawl source without an
approved ToS review. **The tier order is a fact this module rests on**, and a set throws
it away.

Now a **tuple**, with `ACQUISITION_METHOD_SET` as the set view for membership tests. The
two are separate names on purpose: `ACQUISITION_METHODS` means *FR-17's order* and
`ACQUISITION_METHOD_SET` means *the membership question*.

**Risk**: none. The vocabulary's contents are unchanged.

### 3. [Testing] Three tests asserted catalog contents that were wrong — FIXED

**File**: `tests/domain/test_city_providers.py`

Three assumptions about the catalog did not survive contact with it:

- **"New York City"** — the catalog's row is **"New York, NY"**. (The fallback city,
  `PREVIEW_FALLBACK_CITY`, *is* "New York City" — which is why the mistake was easy to
  make.)
- **Bangladesh** — not in Ticketmaster's countries, so it has no API spec at all. The test
  that wanted "a city Ticketmaster serves" was picking the wrong city.
- **"Portland, OR"** — the catalog holds two Portlands, so `next(...)` on a name match
  picked Maine first. The test was checking a URL it had not pinned.

Each was corrected against the catalog's actual contents. **No module behaviour changed** —
these were wrong assertions, not defects.

The third one is worth naming: `test_two_cities_never_get_the_same_url` was written
*because* of finding 1, and it initially passed for the wrong reason (the two Portlands
were being compared by `next()` on an unpinned name). It now names both Portlands
explicitly.

### 4. [Testing] An accent-encoding test that could not fail — FIXED

**File**: `tests/domain/test_city_providers.py`

The first version of the encoding test looked for a spec whose URL contains "bogot", then
asserted `query["city"] == ["Bogotá"]`. Bogotá is **not** in Ticketmaster's countries, so
the spec it found was the *Eventbrite* URL — which has no query string at all — and the
assertion raised `KeyError` rather than testing anything.

Now two tests that can actually fail:
- `test_a_city_with_a_comma_is_percent_encoded` asserts `"%2C" in spec.url` for the API
  spec, where the comma really is in a query string.
- `test_an_accented_city_reaches_the_url_intact` asserts the accented name survives into
  the path segment, which is where it lands.

The mutation check confirms both: string-splicing the query instead of using `urlencode`
fails 2 tests.

### 5. [Testing] A blind `pytest.raises(Exception)` — FIXED

**File**: `tests/domain/test_city_providers.py`

`B017` flagged the two frozen-dataclass tests. They now assert
`FrozenInstanceError` specifically, which is what a frozen dataclass actually raises — a
blind `Exception` would have passed against any failure at all, including a `TypeError`
from a typo in the test.

### 6. [Design] The Eventbrite template ships disabled — as decided at the checkpoint

**File**: `domain/city_providers.py`, `PROVIDER_TEMPLATES`

The checkpoint's decision, and the review confirms it was implemented as agreed rather
than as described:

- the template **is** in the registry, so its URL shape and its tests survive;
- `enabled=False`, and `resolve()` **skips it whole** — it cannot yield a `SourceSpec` and
  therefore cannot be registered;
- the flag lives in **code**, not configuration, because `domain/` may not read `settings`
  (AD-2's `domain-pure` contract forbids `shared`; `tests/architecture/test_stdlib_only.py`
  parameterises over every file in `domain/`).

The alternative — omitting the template — would have dropped the only JSON-LD URL shape
**proven by code that actually ran and parsed it** (`seed_dhaka_live.py`), and left the
AC "a JSON-LD city-directory template is included" unmet.

## Deliberately Not Changed

- **`list_supported_cities()` and the preview's coverage answer** — untouched, and for the
  same reason item 5 left it alone: it answers the preview's question, which is still the
  right answer to its own question.
- **No key in any URL, ever.** Item 3 built the mechanism — `provider_keys.authorized_url`
  adds `apikey=` for the one fetch and marks it `credential=True`, `strip_key` removes it
  before anything stores it — and this module emits the **key-less** URL. The AC's own
  shape follows from that: `domain/` is stdlib-only and cannot read `settings` at all, so
  a template that needed the key could not have it.
- **No `latlong`, and no `geoPoint`.** `latlong` is deprecated in favour of `geoPoint`
  (item 3's verification), and neither is needed: the `city` parameter does the work.
- **No paging, no `dateTimeStart`/`dateTimeEnd`.** Discovery's paging is a fetch-layer
  concern, not a template's. The template asks for the fullest first page Discovery will
  give (`size=100`, its documented maximum) and stops there. **The number of pages is a
  real limitation**, and it is recorded in the module's own comment rather than left
  implicit: a source that only ever sees page one is a source that goes stale silently.
- **The vocabularies are restated, not imported.** `domain` may not import
  `apps.ingestion.models` (AD-3's `models-ingestion`), and is stdlib-only besides. The
  restatement is guarded by four tests that hold each copy to the model's — so the two
  truths cannot drift apart silently.
- **`mint_city_slug` is not used.** The item says so outright: it mints *our* FR-27 URL
  segment and must not be re-pointed at a third party's URL scheme. Each template brings
  its own slug, local to that provider's convention.

## Security

- **The API key never enters `domain/`, and never enters a URL.** The key is added at
  fetch time by a module that *can* read `settings`, and the URL the template emits is
  the one stored on the `Source` row and written into `register_source`'s audit row —
  which is kept for 24 months (AD-5). A key there would be a secret in the database and in
  the audit log. **Two tests hold this**: `test_no_emitted_url_carries_an_api_key` (on the
  emitted specs) and `test_no_template_mentions_a_key_parameter` (on the *template*, so a
  disabled template that baked one in would still be caught — and would still have the
  secret in the repository).
- **The host is exact, not a suffix.** `app.ticketmaster.com` is matched exactly, matching
  the parser's `READERS` and the key injector's `PROVIDER_KEYS`. A suffix match would
  hand `app.ticketmaster.com.evil.test` our key and a document the reader trusts.
  `test_the_api_url_points_at_the_ticketmaster_host` holds it.
- **No credentials in any URL.** `test_every_emitted_url_has_no_credentials_in_it` — a
  URL with a userinfo section is a URL with a password in it.
- **No network, no database, no Django.** The module's imports are `collections.abc`,
  `dataclasses`, `urllib.parse` and `domain.city_catalog`. Two independent guards hold it:
  `lint-imports`'s `domain-pure` contract and `tests/architecture/test_stdlib_only.py`,
  which parameterises over every file in `domain/`.

## Architecture

`domain/city_providers.py` imports `domain.city_catalog` — inward, `domain` to `domain`.
Nothing in `apps/` imports it yet; item 7 (`city-provisioning-service`) will, and it may
import `domain` freely.

**AD-16 is respected by construction.** The module produces *proposed* sources — a
`SourceSpec` is a `Source` row that has not been written — and `ingestion` remains the
sole writer of `Source`. Item 7 registers each spec through
`source_registry.register_source()`, so FR-13's audit and FR-17's guards both apply.

**The field names are the registry's own.** `Source.url`, `Source.source_type`,
`Source.acquisition_method`, `Source.tz_coverage` — so a spec is validated by
`clean_source_input` under exactly the rules the row will meet, with no translation layer
in between. `test_every_emitted_specs_values_are_in_the_vocabularies` is the check that
the vocabulary the spec names is one the model knows.

## Summary

| | Count |
|---|---|
| Fixed | 6 (two Portlands minting one URL; the vocabulary set throwing away FR-17's order; three tests asserting the wrong catalog contents; an accent test that could not fail; a blind `pytest.raises`) |
| Pending suggestions | 0 |

One of the six was a **real defect** in the module — the two Portlands. Three were wrong
test assumptions about the catalog. Two were test-quality faults. **The one that mattered
was found by the whole-cross-product test**, not by the suite going green.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-057*
