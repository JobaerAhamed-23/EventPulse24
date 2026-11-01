---
work_item: city-canonicalization
intent: public-pages-and-seo
created: 2026-11-01
mode: validate
checkpoint_1: approved
---

# Design: A city is one place — the canonical City noun and the venue backfill

## Summary

FR-27 needs one page per city. The database has no city — it has a free-text string copied onto `Venue.city` and again onto `EventFit.city`. This design introduces a canonical **`City`** row with a stable slug, a pure domain normalizer that maps a venue's free-text city onto it, and a backfill over existing venues.

Two questions were left open at planning (OQ-A, and the `EventFit` relation). Reading the module contracts answers both, and more narrowly than expected.

## Scope

**In Scope:**
- A `City` model in the catalog schema, with a stable slug and a display name
- `domain/cities.py` — a pure normalizer, no Django, no database
- `Venue.city_ref` and `EventFit.city_ref` foreign keys, added beside the existing strings
- City resolution at venue registration (`register_venue`)
- An idempotent backfill management command

**Out of Scope:**
- The city page read and its `>5 events` threshold (`city-page-read-api`)
- The city page itself (`frontend-city-page`)
- Any change to `venue_fingerprint` or venue identity — see Risk 1
- Merging or renaming cities by hand; an editorial surface for cities is a later intent
- Geocoding, region/country hierarchy, or "nearby city" logic

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| **OQ-A — which module owns `City`** | **`apps.ingestion`** | Not a judgment call: import-linter contract `models-catalog` protects `apps.catalog.models` to `apps.catalog` importers only, and `models-ingestion` does the same for ingestion. A `Venue → City` FK requires importing the model, so City must live where Venue lives. `apps/catalog/api.py`'s own docstring states the division: *"This module never imports `apps.ingestion.models` … the catalog is read-only here, and `ingestion` is the sole writer (AD-4, AD-16)."* |
| **The Spine says FR-26–28 belong to `catalog`** | No conflict | "catalog" in the Capability Map is the **bounded context / schema alias**, not the Django app. `DATABASE_ROUTING` maps `ingestion`, `catalog` **and** `editorial` all to the `CATALOG` alias. `apps.ingestion` writes that context; `apps.catalog` reads it. City is written, so it is ingestion's. |
| **`EventFit` relation** | **Add `city_ref` FK, keep the `city` string** | The string is documented as *"the venue's city, **as written on the Venue row**"* — that provenance is evidence and is kept. The FK makes the city page's lookup exact and indexable instead of `iexact` string matching, which cannot unify "Brooklyn" and "Brooklyn, NY" at all. |
| **`Venue` relation** | `city_ref` FK, nullable | A venue with an empty city resolves to no City, matching the rule `EventFit` already follows (no row rather than a guess). |
| **Where resolution happens** | At `register_venue` only | `venue_registry.py` documents that a venue's *"name, city and country make its identity fingerprint, so they are fixed once it is registered."* A venue's city never changes after creation, so resolution happens once and never needs re-running. |
| **Normalizer placement** | `domain/cities.py` | Beside `domain/dedup.py`, `domain/conflict.py`, `domain/event_fit.py`. Contract `domain-pure` forbids Django, pydantic and `shared` (except `constants`/`ids`) — so it is testable on its own, as the work item requires. |
| **Ambiguity policy** | Under-merge, never over-merge | A string the normalizer cannot resolve confidently becomes its own City. A wrong merge publishes one SEO page about two different places and is only discoverable by a human; an unmerged city is a missing page that a later rule fixes. |
| **Trailing region suffix** | **Kept, never dropped** *(revised during implementation)* | The plan's original rule — drop a final 2-letter token — would map `Portland, OR` and `Portland, ME` to one City. `domain/dedup.venue_fingerprint`'s own docstring names this hazard: *"The country keeps Portland, Oregon apart from Portland, Maine."* The region text is load-bearing in venue identity, and `country_code` cannot separate two same-country cities. A region is therefore kept as its own field and carried into the slug (`brooklyn-ny`). **Consequence, accepted:** `Brooklyn` and `Brooklyn, NY` remain two Cities; FR-27's `>5 events` threshold keeps the thin fragment from getting a page. |
| **City slug** | Minted once, never re-minted | Same discipline as `mint_slug` for events (`services/slugs.py`: *"minted once at creation and never changed, so a retitled Event keeps its URL"*). A city page URL must not move once indexed. |
| **Display name** | Stored, not derived | `Brooklyn`, not `brooklyn`. Derived title-casing mangles `NYC`, `São Paulo`, `'s-Hertogenbosch`. First writer wins; editorial correction is a later intent. |

## Data Models Affected

### Creates

- **`City`** (`apps/ingestion/models.py`) — `UUIDv7Model`
  - `slug` — `SlugField(max_length=120)`, **unique**, the FR-27 URL segment, minted once
  - `name` — `CharField(max_length=100)`, display name
  - `country_code` — `CharField(max_length=2)`, so `Brooklyn, US` and a same-named city elsewhere stay distinct
  - `normalized_key` — `CharField(max_length=100)`, the normalizer's output (case/whitespace/punctuation/accent folded, region **not** stripped)
  - `region` — `CharField(max_length=16, blank=True)`, the trailing qualifier when one was written (`ny`, `or`); kept separate so it can never be silently discarded
  - **unique together: `(normalized_key, region, country_code)`** — the column resolution looks up
  - `created_at` / `updated_at`
  - `retention_category = RetentionCategory.SOURCE_REGISTRY` — required by system check `eventpulse.E003`; City holds no user-derived data

### Modifies

- **`Venue`** — adds `city_ref = FK(City, null=True, on_delete=PROTECT)`. The existing `city` CharField is **untouched** (it feeds `venue_fingerprint`).
- **`EventFit`** — adds `city_ref = FK(City, null=True, on_delete=PROTECT)` and an index on `(city_ref, score)`. The existing `city` CharField and `event_fit_city_score_idx` are **untouched**, so the live Pulse Preview read is unaffected.

## Technical Approach

### Architecture

```
  ingest / admin
        │
        ▼
  register_venue()  ──► domain/cities.normalize_city(name, cc)
  (the one creation      │  pure: case, whitespace, punctuation,
   point for Venue)      │        trailing region suffix
        │                ▼
        │          City.objects.get_or_create(normalized_key, country_code)
        ▼
  Venue.city_ref ──────────────┐
                               ▼
  write_event_fit()  ──►  EventFit.city_ref   (copied from the venue,
                               │               as EventFit.city already is)
                               ▼
                    city-page-read-api  (next work item)
```

### Database Changes

```sql
-- all in the CATALOG schema (DATABASE_ROUTING: ingestion -> catalog alias)
CREATE TABLE city (
  id uuid PRIMARY KEY,
  slug varchar(120) NOT NULL,
  name varchar(100) NOT NULL,
  country_code varchar(2) NOT NULL,
  normalized_key varchar(100) NOT NULL,
  region varchar(16) NOT NULL DEFAULT '',
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  CONSTRAINT city_slug_uq UNIQUE (slug),
  CONSTRAINT city_key_region_country_uq UNIQUE (normalized_key, region, country_code),
  CONSTRAINT city_name_nonempty_ck CHECK (name <> ''),
  CONSTRAINT city_key_nonempty_ck CHECK (normalized_key <> '')
);

ALTER TABLE venue     ADD COLUMN city_ref_id uuid NULL REFERENCES city(id);
ALTER TABLE event_fit ADD COLUMN city_ref_id uuid NULL REFERENCES city(id);
CREATE INDEX event_fit_city_ref_score_idx ON event_fit (city_ref_id, score);
```

Three migrations, in order: **(1)** create `City`; **(2)** add both nullable FKs and the index; **(3)** none — the backfill is a management command, not a data migration, so it is re-runnable and does not lock the table inside a deploy.

## Affected Files

| File | Action | Purpose |
|---|---|---|
| `backend/domain/cities.py` | create | Pure normalizer + slug minting |
| `backend/apps/ingestion/models.py` | modify | `City`; `city_ref` on `Venue` and `EventFit` |
| `backend/apps/ingestion/migrations/00XX_city.py` | create | Create the table |
| `backend/apps/ingestion/migrations/00XX_city_refs.py` | create | Add FKs + index |
| `backend/apps/ingestion/services/cities.py` | create | `resolve_city()` — the get-or-create seam |
| `backend/apps/ingestion/services/venue_registry.py` | modify | Resolve a City in `register_venue` |
| `backend/apps/ingestion/event_fit/writes.py` | modify | Copy `city_ref` as `city` is already copied |
| `backend/config/management/commands/backfill_cities.py` | create | Idempotent backfill (shape of `backfill_event_fit.py`) |
| `backend/tests/domain/test_cities.py` | create | Normalizer table, pure |
| `backend/tests/ingestion/test_cities.py` | create | Resolution, backfill idempotence, fingerprint invariance |

## Risks & Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| **Normalization leaks into `venue_fingerprint`** | **Severe** — the fingerprint is computed from the raw city string and *is* venue identity (`domain/dedup.py`). Changing it would silently re-identify venues and corrupt event dedup across the whole catalog. | `domain/cities.py` is a **separate** function from `domain/dedup.venue_fingerprint`, and `Venue.city` is never rewritten. A test asserts every existing venue's fingerprint is byte-identical after the backfill. |
| **Over-merging two real places** | An SEO page conflates two cities; only a human notices | **Found and removed during implementation** — the original trailing-suffix rule merged Portland OR with Portland ME. The normalizer now folds only case, whitespace, punctuation and accents; the region is preserved as its own field and is part of the uniqueness key alongside `country_code`. No fuzzy or distance matching anywhere. |
| **Backfill partially applied** | Some venues resolved, some not; city pages show incomplete sets | The command is idempotent, batched and re-runnable, following `backfill_event_fit.py`. FKs are nullable, so a partial run is a valid intermediate state, not a broken one. |
| **Breaking the live Pulse Preview** | `/preview` is in production today | `EventFit.city`, `event_fit_city_score_idx` and `list_event_fit_for_city` are all left untouched. The existing preview tests must pass unmodified — treated as the gate, not as a nice-to-have. |
| **Slug collision between same-named cities** | Two Brooklyns fight for one URL | `slug` is globally unique; the minter appends a country/region disambiguator on collision rather than failing or overwriting. |
| **`on_delete=PROTECT` blocks a city delete** | Deliberate | A City with venues attached must not vanish under an indexed URL. Deletion is an editorial concern, out of scope here. |

## Implementation Checklist

- [ ] `domain/cities.py`: `normalize_city()` and `mint_city_slug()`, stdlib-only, no Django
- [ ] Unit-test the normalizer as a table: case, whitespace, internal punctuation, accents, non-Latin name, empty string
- [ ] **Test: `Portland, OR` and `Portland, ME` resolve to two different Cities**
- [ ] `City` model with `retention_category`, both unique constraints, both check constraints
- [ ] Migration 1: create `City`
- [ ] `city_ref` on `Venue` and `EventFit`, nullable, `PROTECT`; index `(city_ref, score)`
- [ ] Migration 2: add FKs + index
- [ ] `services/cities.resolve_city()` — get-or-create on `(normalized_key, country_code)`
- [ ] Hook resolution into `register_venue`; a blank city resolves to `None`, not a City
- [ ] Copy `city_ref` in `event_fit/writes.py` wherever `city` is already copied
- [ ] `backfill_cities` management command — batched, idempotent, system `Actor`
- [ ] Test: two venues spelled differently resolve to one City
- [ ] Test: backfill run twice changes nothing the second time
- [ ] **Test: every existing venue's `venue_fingerprint` is unchanged after backfill**
- [ ] Test: the existing Pulse Preview suite passes **unmodified**
- [ ] `lint-imports` clean — `domain-pure` and `models-ingestion` both intact
- [ ] `manage.py check` clean — no `eventpulse.E002`/`E003` errors

---
*Generated by specs.md - fabriqa.ai FIRE Flow | Checkpoint 1 approved: 2026-11-01*
