---
run: run-eventpulse24-057
work_item: stored-city-is-the-picked-city
intent: city-picker-and-auto-collection
generated: 2026-11-20
mode: validate
---

# Implementation Walkthrough: The stored city is the picked city

## Summary

Before this item, `resolve_home_city()` asked the Pulse Preview **"which cities can you
show cards for right now?"** and, if the answer was no, quietly replaced the reader's city
with `PREVIEW_FALLBACK_CITY` and filed the row as `city_source="fallback"`. A reader in
Berlin picked Berlin; the server answered "New York City" and said nothing.

Now the question is **"is this a city a person may pick?"**, answered by
`domain.city_catalog` — the curated list item 1 built and item 4 published. A city in the
catalog is stored **exactly as picked**, in the catalog's spelling, with
`city_source="choice"`. A city outside it is **refused**, loudly, with the rejected value
in `details` — and nothing is written.

The guarantee this item exists to deliver is the intent's own first one:

> The stored city is the picked city. Never silently rewritten to anything else.

## The branch is on `source`, not on the city

The single most important decision in the item. Three writers write a city, and they are
not alike:

| Writer | A city outside the catalog | Why |
|---|---|---|
| `choice` — a reader picked it | **refused** (422) | The reader sent a value the picker should not have offered. Silently substituting another one is the bug this item ends. A loud refusal lets the client re-select |
| `geo` — an edge guessed it | **falls back** to `PREVIEW_FALLBACK_CITY`, `source="fallback"` | Nobody chose it. Refusing would turn an edge's guess into a 4xx on a path the reader never asked for |
| `seed` — the local dev seed wrote it | **stored verbatim** | There is no reader in the story at all. The seed authors a fictional city for a walk-through |

The tempting simplification is to refuse any city the catalog does not hold. That is
wrong for the two non-choice writers, and the tests for each say why:

- `test_a_geo_city_outside_the_catalog_still_falls_back`
- `test_a_seed_city_is_stored_verbatim`

## Structure Overview

```text
backend/
├── domain/
│   ├── errors.py                    NEW — UnknownHomeCityError(ValidationError)
│   └── city_catalog.py              +1 row — "Montgomery"
├── apps/personalization/
│   ├── models.py                    CitySource gained SEED
│   ├── migrations/0018_…            NEW — AlterField, moves no rows
│   ├── services/
│   │   ├── digest_preferences.py    the rewrite; _canonical deleted
│   │   └── onboarding.py            set_digest_preference(city_source=…)
│   ├── api.py, schemas.py           descriptions that promised the rewrite
└── apps/identity/api.py, schemas.py the same, on the sign-up path
```

## Architecture

### The module now imports `domain`, not `apps.ingestion`

`digest_preferences.py` used to reach into `apps.ingestion.services.preview_read` for
`list_supported_cities()`. It now imports `domain.city_catalog`.

That is the point of the item, not a side effect. The place that decides **which city a
reader may have** must not depend on the **preview's coverage answer** — that is what made
the picker a mirror of the catalog in the first place. `domain.city_catalog` is a `domain`
module (pure stdlib), and AD-2 points inward: `apps` may import `domain`. The
`models-ingestion` contract protects the *models* module, not the services, so
`lint-imports` confirms **21 contracts kept, 0 broken**.

### The refusal lives in the service, not at the API edge

`resolve_home_city()` raises, because the service knows **which caller it is serving** —
and because the rule is about the value, not about HTTP. The API edge maps
`ValidationError` to **422** through the project's existing `STATUS_BY_ERROR` walk, so no
error-handler wiring changed and no new mapping was added.

The raise happens **before** `transaction.atomic` opens, so a refusal writes nothing —
no `DigestPreference` row, no audit row, no recomposition.

### The refusal is a `ValidationError` in `domain/errors.py`

```python
class UnknownHomeCityError(ValidationError):
    code = "unknown_home_city"
    default_message = "We don't have that city yet. Pick one from the list."
```

`domain` is where the project's error vocabulary lives, and `ValidationError` already
means 422. Two audiences, two places: the **message** is calm prose for a person and does
not quote the value; the **value** is in `details["rejected_city"]`, machine-readable data
for the client that sent it and needs to know which value was refused. Echoing a value
back to its own sender is not disclosure — AD-13's concern is the audit log and the log
sink, which stay silent, and that is asserted separately with **both halves** so an empty
`details` cannot pass for the right reason.

### `set_digest_preference` takes a `city_source`, defaulting to `SOURCE_CHOICE`

Every browser path that sets a city is a reader picking one, so the default is the common
case and the parameter is the exception. **Every existing caller is unchanged** — the
sign-up path, the API edge, the onboarding command. Only the seed names a different one,
and it names it explicitly.

## The migration touches no rows

`city_source` is a `CharField` with `choices`, and **Django does not enforce choices at the
database level**. So `0018_digestpreference_city_source_seed` is an `AlterField` on the
Python-side vocabulary and nothing else. Its docstring says exactly that, and says what the
reverse does.

The existing `city_source="fallback"` rows are **left alone** — the brief forbids
migrating them, and the reasoning holds: nulling them would push a surprise empty Browse
onto people who never asked for one, and `citySourceNote()` already labels them honestly.
They repick whenever they like, and now the pick sticks.

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `backend/tests/personalization/test_stored_city_is_the_picked_city.py` | 682 cases — the item's own proof, whole-dataset |
| `backend/tests/api/test_digest_preference_api.py` | 11 tests — the endpoint's HTTP shape over a real session |
| `backend/apps/personalization/migrations/0018_digestpreference_city_source_seed.py` | `AlterField`; moves no rows |
| `backend/tests/shared/test_city_catalog.py` | unchanged — the new catalog row passes it untouched |

### Modified

| File | Changes |
|------|---------|
| `backend/domain/errors.py` | `UnknownHomeCityError(ValidationError)` |
| `backend/domain/city_catalog.py` | One row: `("Montgomery", "", "", "America/Chicago")` |
| `backend/apps/personalization/services/digest_preferences.py` | The rule rewritten; `_canonical` deleted |
| `backend/apps/personalization/services/onboarding.py` | `set_digest_preference` takes a `city_source` |
| `backend/apps/personalization/models.py` | `CitySource.SEED` |
| `backend/apps/personalization/{api,schemas}.py` | Descriptions that promised the rewrite |
| `backend/apps/identity/{api,schemas}.py` | The same, on the sign-up path |
| `backend/config/management/commands/seed_browse_catalog.py` | The seed's city is now the server's own |
| `backend/tests/personalization/test_digest_preferences.py` | Rewritten — the old coverage-rule tests inverted |
| `backend/tests/personalization/test_onboarding_api.py` | 2 assertions — they asserted the rewrite |
| `backend/tests/personalization/test_digest_preference_model.py` | Vocabulary is five, not four |
| `backend/tests/config/test_seed_browse_catalog.py` | +1 — the seeded city is labelled `seed` |
| `frontend/lib/api/{openapi.json,schema.ts}` | Regenerated by `make client` — description-only |

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| **The refusal's status** | **422** (`ValidationError`) | **Your checkpoint call.** A bad value is a bad request, and `ValidationError` already maps there — so no error-handler wiring changed. 400 would have meant "the server could not parse it", which is not what happened |
| **Echo the refused city?** | In `details["rejected_city"]`, **not** in the message | **Your checkpoint call.** The client needs to know *which* value was refused to re-select it; the person reading the message does not need the string echoed at them. Two audiences, two places |
| **Migrate the `fallback` rows?** | **No** | The brief forbids it, and nulling them would push a surprise empty Browse onto people who never asked for one. `citySourceNote()` already labels them honestly, and now the pick sticks when they do repick |
| **Branch on `source` or on the city?** | On `source` | A choice outside the catalog is a client bug and deserves a loud 422. A geo guess outside the catalog is not the reader's fault and must not become a 4xx on a path they never asked for. Branching on the city alone would have refused both |
| **The seed's fictional city** | A third writer, `SOURCE_SEED`, stored verbatim | "Fixtureville" cannot go in the catalog — it is not a place a reader may choose, and putting it there would make the picker offer a city that does not exist, the exact thing the catalog exists to prevent. And bending it into a real city would make the seed's venues, events and accounts disagree, leaving the Browse surface the walk-through exists to show empty. The seed **is** the server choosing, with no reader in the story — the same exemption the fallback gets, for the same reason |
| **`_canonical`** | Deleted | It became dead code: once `resolve_home_city` returned `row.name` directly, nothing called it. The invariant it guarded — *a stored city is always a city the catalog holds, in the catalog's spelling* — is now enforced at the single point that stores a city, and pinned over the whole dataset |

## What the mutation check found

Every whole-dataset invariant was mutated and the mutation reverted. The rule that a test
must be able to fail.

| Mutation | Result |
|---|---|
| `lookup` always misses | 520 failed across the three new files |
| `resolve_home_city` returns `""` instead of `row.name` | 513 failed |
| **The old silent rewrite restored** — a choice outside the catalog falls back | **23 failed, and every one is a refusal test** |
| `resolve_home_city` returns the **caller's** spelling instead of the catalog's | 170 failed, including `test_the_stored_city_is_always_a_city_the_catalog_holds` |

The third mutation is the important one: it is **the old bug, put back**, and 23 tests
catch it. The fourth is the replacement for the `_canonical` guard this item deleted.

Two findings came out of the work that the suite going green did **not** reveal:

1. **`_canonical` was dead code.** The coverage report surfaced it: `digest_preferences.py`
   was at 97% with exactly one uncovered line in the module — `_canonical`'s `return
   row.name`, the success path of a function nobody reaches. The `raise` branch was covered
   because the test called `_canonical` directly; the *useful* line was not.
2. **"Montgomery" was not in the curated catalog.** The project's own local seed city —
   named in `config/local_feeds.json` and filled with venues in
   `config/local_feeds.fixtures.json` — was **unpickable**. Under the old rule that was
   harmless (the city was stored as the fallback and the surface showed New York City).
   Under this item's rule it would be **refused**, and the picker would offer a city the
   server answers with a 422.

   It joins the catalog with **no region qualifier**, because the string the seed's venue
   and its source already use is plain `"Montgomery"`; a qualified `"Montgomery, AL"` would
   key as `("montgomery", "al")` and resolve to nothing — a *different* city. And
   `America/Chicago`, not the country's `America/New_York` default: Montgomery is in
   Central Time. The label is "Montgomery, United States", the same shape as "Brooklyn,
   United States".

**Every city the repository mentions is now in the catalog**, checked over every JSON file
under `backend/config/` and `backend/tests/fixtures/`.

## Two pre-existing tests asserted the rewrite

`test_putting_the_digest_preference_carries_the_city_and_the_opt_out` and
`test_omitting_the_city_does_not_clear_the_stored_one` both asserted that a **"Brooklyn"**
pick came back as `"New York City"` with `city_source="fallback"`.

"Brooklyn" **is** in the curated catalog, so the answer is now `"Brooklyn"` with
`city_source="choice"`. The old assertions were the bug, in test form — they are the
clearest statement of what this item removed.

## Verification

```bash
uv run --directory backend pytest \
  tests/personalization/test_stored_city_is_the_picked_city.py \
  tests/personalization/test_digest_preferences.py \
  tests/api/test_digest_preference_api.py \
  tests/config/test_seed_browse_catalog.py -q      # 785 passed
make test-backend                                    # 8617 passed
make coverage-backend                                # 97.44% overall, domain/ 100%
make lint-imports                                    # 21 contracts kept, 0 broken
make client && uv run --directory backend pytest tests/api/test_contract.py -q
pnpm --dir frontend typecheck                        # passes
```

`digest_preferences.py` is at **98%**, up from 94% at HEAD; the two lines still uncovered
are the pre-existing `get_delivery_settings_for` batched reader, which this item does not
touch.

## What This Unblocks

`home-city-dropdown-catalog` (item 8) is the one waiting on this. The `<select>` still
reads `preview/cities`, whose answers are the ones this item stopped trusting — and whose
docstring still claims the server rewrites a city silently. That item rewires the dropdown
to `/api/public/cities`, where every `value` is guaranteed to resolve through
`domain.city_catalog.lookup` — which is exactly what this item now refuses anything else
for.

The frontend needed **no change** for this item to be observable: `home-city.tsx` already
replaces its optimistic value with the server's answer and renders `response.error`
verbatim, so a 422 shows its message and reverts.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-057*
