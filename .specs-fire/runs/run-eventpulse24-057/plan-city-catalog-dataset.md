---
run: run-eventpulse24-057
work_item: city-catalog-dataset
intent: city-picker-and-auto-collection
mode: confirm
checkpoint: plan-approval
approved_at: 2026-11-20
---

# Implementation Plan: The curated world-city catalog

## Approach

One new pure module, `domain/city_catalog.py`, holding a frozen tuple of `CityChoice`
rows and four lookup helpers. Stdlib only — no Django, no database, no I/O — so it sits
beside `domain/cities.py`, which it must agree with and whose `split_region` it reuses
rather than reimplementing.

**The dataset declares what `domain.cities.split_region()` will produce, and a test proves
it.** `split_region` treats a trailing alphabetic run of <= 3 characters as a region
qualifier, so "Portland, OR" keys as `("portland", "or")` and "Chittagong" as
`("chittagong", "")`. Rather than re-deriving the region downstream, each row *states*
its `(key, region)` and a whole-dataset test asserts the two agree. That makes a bad row
a test failure at commit time instead of a wrong city page in production.

**`name` is the stored value; `label` is derived, never stored.** `DigestPreference.city`
will hold "Portland, OR" — a string the existing catalog, `split_region` and
`venue_fingerprint` all already understand. The disambiguating display form
("Portland, Oregon", "Chittagong, Bangladesh") is computed for the picker and never
written anywhere. This is what keeps the user's §5 ("no country field on my preference")
true while still letting the dropdown disambiguate.

**Size and composition.** Roughly 150 cities across ~60 countries for the first cut:
every country's largest one or two cities, plus the US/CA/AU/BR cases that genuinely need
a region qualifier, plus the cities the catalog already ingests (Dhaka, Lisbon, Brooklyn)
so nothing regresses. Deliberately not thousands — the whole-dataset invariant tests are
the quality bar, and a hand-verified 150 that all pass is worth more than 5,000 that were
never read. Growing it is a one-line PR per city, which is the point of a checked-in list.

**`tz` is the load-bearing column** and the reason this item blocks `city-provisioning-
service`. It is what lets a brand-new city resolve date-only event times with no
registered venue. Every row's zone is asserted loadable via `zoneinfo` and canonical via
`domain.timezones.canonical_zone`.

**`country_slug` is for URL templating only** (`city-provider-templates` builds
`/d/bangladesh--chittagong/` from it). It is explicitly not an identity field and is not
part of the uniqueness invariant.

## Files to Create

| File | Purpose |
|------|---------|
| `backend/domain/city_catalog.py` | `CityChoice`, the `WORLD_CITIES` tuple, and the lookup helpers |
| `backend/tests/domain/test_city_catalog.py` | Whole-dataset invariants and lookup behaviour |

## Files to Modify

| File | Changes |
|------|---------|
| (none) | Nothing existing is touched. `domain/cities.py` is imported, not changed. |

## Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/domain/test_city_catalog.py` | tz loads + canonical (whole dataset); `split_region` round-trip (whole dataset); identity uniqueness; country-code shape; `lookup` hit/miss/case/spacing; `label` disambiguation; non-empty names; the same-named Portland pair resolving to two distinct identities |

`tests/domain/test_domain_is_django_free.py` and `test_domain_api.py` walk every module in
`domain`, so both pick up the new module with no change — the purity and API constraints
are enforced for free.

## Technical Details

**Public API**

```python
@dataclass(frozen=True)
class CityChoice:
    name: str           # the STORED value: "Portland, OR", "Chittagong"
    country_code: str   # ISO 3166-1 alpha-2, uppercase: "US", "BD"
    country_name: str   # for the label: "United States", "Bangladesh"
    country_slug: str   # for URL templates only: "united-states", "bangladesh"
    region: str         # what split_region() yields: "or", "" — lowercase
    region_name: str    # for the label: "Oregon", "" — display form
    tz: str             # IANA zone: "America/Los_Angeles", "Asia/Dhaka"

    @property
    def label(self) -> str: ...      # "Portland, Oregon" / "Chittagong, Bangladesh"
    @property
    def identity(self) -> CityIdentity: ...   # reuses domain.cities.CityIdentity

WORLD_CITIES: tuple[CityChoice, ...]
def lookup(name: str | None) -> CityChoice | None: ...
def choices() -> tuple[CityChoice, ...]:   # alphabetical by label, str.casefold
```

**Two name fields per qualifier, and why.** `region` must be exactly what `split_region`
emits (lowercase, <= 3 chars) because it feeds `City` identity; `region_name` is the
human form for the label. Deriving one from the other means a 50-state mapping table
inside `domain`, which is more surface than two columns. Same reasoning for
`country_code` / `country_name` / `country_slug`.

**`lookup` folds through `domain.cities.normalize_city`**, so "  portland, or " finds
"Portland, OR". It does **not** go through `canonical_spelling`/`CITY_ALIAS_GROUPS` —
that table answers "which spellings name the same place", a different question from
"which places may be picked", and routing through it would let an alias resolve to a
catalog row whose `tz` and `country` were never verified for that spelling.

**Index built once at import**, like `cities._ALIAS_INDEX`, so `lookup` is a dict hit
rather than a scan over the tuple.

**Every test asserts over `WORLD_CITIES` in full**, not a sampled subset — per the user's
standing rule that a test must be able to fail. A sampled invariant test passes while a
bad row sits three hundred lines down.

---
*Plan approved at checkpoint. Execution follows.*
