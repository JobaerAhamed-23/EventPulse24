---
run: run-eventpulse24-024
work_item: city-canonicalization
intent: public-pages-and-seo
mode: validate
checkpoint: plan
approved_at: pending
---

# Implementation Plan: A city is one place — the canonical City noun and the venue backfill

## Approach

Build inward-out, in the order the import contracts allow: the pure domain function first (it has no dependencies and is the only part with real logic), then the model and migrations, then the service seam, then the write-path hook, then the backfill.

**The normalizer reuses `domain.dedup.tokens`.** That function already folds case, strips punctuation and splits words across scripts, and it is proven in production by `venue_fingerprint` and `title_fingerprint`. `domain/cities.py` calls it **read-only** and adds exactly one rule on top: drop a trailing region or country token. Reusing it means city normalization and venue identity agree about what a word is, without `cities.py` being able to change what `dedup.py` computes — `domain/conflict.py` already imports `domain.dedup` the same way.

Everything lands beside existing code rather than replacing it: new columns are nullable and additive, the existing `city` strings and `event_fit_city_score_idx` are untouched, and the backfill is a command rather than a data migration so it is re-runnable and holds no lock during deploy.

## Files to Create

| File | Purpose |
|---|---|
| `backend/domain/cities.py` | `normalize_city()` and `mint_city_slug()` — pure, stdlib + `domain.dedup.tokens` |
| `backend/apps/ingestion/migrations/0005_city.py` | Create the `city` table with its constraints |
| `backend/apps/ingestion/migrations/0006_city_refs.py` | Nullable `city_ref` FKs on `venue` and `event_fit`, plus `(city_ref, score)` index |
| `backend/apps/ingestion/services/cities.py` | `resolve_city()` — the get-or-create seam over `(normalized_key, country_code)` |
| `backend/config/management/commands/backfill_cities.py` | Idempotent batched backfill (shape of `backfill_event_fit.py`) |
| `backend/tests/domain/test_cities.py` | Normalizer table; pure, no database |
| `backend/tests/ingestion/test_cities.py` | Resolution, backfill idempotence, **fingerprint invariance** |

## Files to Modify

| File | Changes |
|---|---|
| `backend/apps/ingestion/models.py` | Add `City`; add `city_ref` FK to `Venue` and to `EventFit` + index |
| `backend/apps/ingestion/services/venue_registry.py` | `register_venue` resolves a City; blank city → `None` |
| `backend/apps/ingestion/event_fit/writes.py` | Copy `city_ref` everywhere `city` is already copied |

## Tests

| Test File | Coverage |
|---|---|
| `backend/tests/domain/test_cities.py` | Case, whitespace, internal punctuation, trailing region suffix, non-Latin name, empty string, slug minting + collision disambiguation |
| `backend/tests/ingestion/test_cities.py` | Two spellings → one City; blank city → no City; `PROTECT` on delete; backfill idempotence; **every existing venue's `venue_fingerprint` byte-identical after backfill** |
| *(existing)* `backend/tests/ingestion/` preview suite | Must pass **unmodified** — the regression gate for `/preview` |
| *(existing)* `backend/tests/architecture/test_import_contracts.py` | `domain-pure` and `models-ingestion` still intact |

## Technical Details

**Build order** (each step leaves the tree green):

1. `domain/cities.py` + its unit tests — no Django, runs standalone.
2. `City` model + migration 0005. `manage.py check` must stay clean: `retention_category = SOURCE_REGISTRY` satisfies `eventpulse.E003`, and `UUIDv7Model` satisfies `E005`.
3. `city_ref` FKs + migration 0006. Both nullable, both `on_delete=PROTECT`. No `eventpulse.E002` risk — `ingestion` routes to the `CATALOG` alias and both ends are in it.
4. `services/cities.resolve_city()` — `get_or_create` on `(normalized_key, country_code)`, `using(CATALOG)`, inside the caller's transaction.
5. Hook into `register_venue`. **`Venue.city` is passed through unchanged**; only the new FK is set.
6. Copy `city_ref` in `event_fit/writes.py`.
7. `backfill_cities` command — batched, `Actor.system("city_backfill")`, resumable.

**The fingerprint-invariance test is the centrepiece.** It snapshots every existing venue's `venue_fingerprint`, runs the backfill, and asserts the set is byte-identical. If normalization ever leaks into venue identity, this test is what catches it — and it is written to fail if the invariant is removed.

**Slug collision.** `mint_city_slug` produces `slugify(name)`; on a unique-constraint trip the caller retries with a `-{country_code}` suffix, then a short id tail — the same escalation `mint_slug` uses for events (`services/slugs.py`, retry with a longer tail).

**Trailing region: kept, not dropped** *(revised at implementation — see the design doc's Key Decisions)*. The rule first planned here would have merged `Portland, OR` with `Portland, ME`, which is the over-merge the policy forbids and which `domain/dedup.venue_fingerprint`'s own docstring warns about. `normalize_city` therefore folds only case, whitespace, punctuation and accents. A trailing qualifier is **split off into its own `region` value**, part of the uniqueness key and carried into the slug (`brooklyn-ny`), so it can never be silently discarded. `Brooklyn` and `Brooklyn, NY` stay two Cities; FR-27's `>5 events` threshold keeps the thin one off the web.

## Based on Design Doc

Reference: `.specs-fire/intents/public-pages-and-seo/work-items/city-canonicalization-design.md`

---
*Plan approved at checkpoint. Execution follows.*
