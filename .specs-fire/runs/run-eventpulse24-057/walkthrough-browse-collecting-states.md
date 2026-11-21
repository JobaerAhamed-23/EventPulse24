---
run: run-eventpulse24-057
work_item: browse-collecting-states
intent: city-picker-and-auto-collection
generated: 2026-11-21
mode: confirm
---

# Implementation Walkthrough: The four honest states

## Summary

Item 8 gave every city a status that says something true about our collection of it. **Nothing
read it.** The status was written on the row, updated by the probation, and reached no reader.

So every city with no events said the same thing: **"Nothing nearby tonight. Try a wider
city?"**

**That sentence is the honest answer to exactly one of the four situations a city can be in.**
For the other three it is a lie. A collecting city is not empty — we are working on it, and
the reader is waiting. A city whose sources failed is not quiet — we have nothing to collect
from, and there is a way out. A reader with no city at all is not in a city.

**This item reads the status and gives each situation its own surface.** Three treatments, two
families within them, and a status vocabulary held exactly to the backend's.

## The one problem the item really was

**How does the provisioning status reach the payload without breaking the wall?**

The status lives on `catalog.ingestion_cityprovisioning`. The surfaces that need it live in
other apps. AD-3 says they may not import `apps.ingestion.models`, and the import-linter
enforces it.

**Three ways that look reasonable and are not:**

| Option | Why not |
|---|---|
| Import the models | Breaks AD-3. The contract is real. |
| Denormalise a `city_status` column onto `DigestPreference` | A **second writer of one fact** (AD-16). It goes stale the moment the probation moves a city to `live`, and nothing would ever notice. |
| A second endpoint | **Two answers that can contradict** — "collecting" above a listing that exists. |
| **A service handing over a frozen dataclass** | **The sanctioned seam, and the precedent is everywhere.** |

**The contract protects the models module, not the app.** Its own name says it: *"only
`apps.ingestion` imports `apps.ingestion.models` (**others call its services**)"*. And
`catalog_read`, `preview_read` and `city_read` are all services that hand over plain data —
`browse_read.py` already imported `catalog_read`.

## Structure Overview

```text
backend/apps/ingestion/services/city_status_read.py        NEW
├── CityCollectionStatus      frozen dataclass — a status and a source count, no model
└── read_city_collection_status(city=...)   one query, never a write

backend/apps/personalization/services/browse_read.py        MODIFIED
└── carries city_collection_status on BrowsePage

backend/apps/personalization/schemas.py + api.py            MODIFIED
└── BrowseOut.city_collection_status

backend/apps/ingestion/services/city_read.py                MODIFIED
└── carries city_collection_status on CityPage

backend/apps/catalog/schemas.py                              MODIFIED
└── CityPageOut.city_collection_status

frontend/components/browse/browse-states.tsx                MODIFIED
├── BrowseCollecting   the collecting state — its own <h1>, role="status"
└── BrowseNoSources    the no-sources state — its own <h1>, the coverage-request slot

frontend/app/browse/page.tsx                                 MODIFIED
└── the five-way branch: noCity | collecting | noSources | quiet | ordinary

frontend/components/city-page/city-page.tsx                  MODIFIED
└── collectionNote(city, status) — one added sentence, in the sparse state only
```

## The rules the surfaces hold

| Rule | Why it is a rule |
|---|---|
| **The branch order is load-bearing.** `city_missing` first, then `collecting`, then the no-sources family, then quiet. | A collecting city has no cards *by definition* — it has not published anything yet — and must not fall through to the quiet state. **That fall-through is the bug this item fixes.** |
| **A reader with no city is never told collection is under way.** | A user with no city has no collection to report, and telling them we are collecting for them would be a claim about a city they do not have. |
| **A covered city that is simply quiet is never told its sources failed.** | The quiet state says *your city has nothing on*; the no-sources state says *we have no sources for your city*. Different facts, different sentences. |
| **The four no-sources statuses share one sentence.** | `no_providers`, `failed`, `yielded_nothing` and `paused` are four facts about *why there are no sources*. The reader has no way to act on the difference. The distinction is in the payload, and the payload is what the editorial surface reads. |
| **The threshold and the status are different questions.** | The threshold asks whether the city has earned a page; the status asks whether our collection is working. **The threshold decides whether the page shows a listing; the status only ever *adds* a sentence to the sparse state.** The "coming soon" copy is never removed. |
| **A published city says nothing about its collection.** | Our collection's state does not un-publish a city that has earned a listing, and degrading a city that has events would throw away real events. |
| **A read must not mint.** | `resolve_city` *creates* a `City`. Using it in a read would put a place into the registry that no reader chose — every reader who opened Browse for an unprovisioned city would create the row that says we are collecting it. |

## The three treatments, and the two families within them

```text
collecting ──────────── its own treatment
                          "Events in Brooklyn. We're collecting events for Brooklyn."

quiet ───────┐
             ├── share the quiet treatment
noCity ──────┘   "Nothing nearby tonight. Try a wider city?"  +  Change city

noSources ──┐
paused ─────┤
noProviders ┼── share the no-sources treatment
failed ─────┘   "We couldn't find any event sources for Brooklyn."
```

**A collapse of the *groups* is the failure this item exists to catch. A collapse of a group
onto itself is the design** — and the AC says so explicitly for `paused` ("Paused renders the
same honest line as 'no sources'").

## The key decisions

1. **A service, not the models.** The wall holds because the seam is a service handing over a
   frozen dataclass, and the precedent already exists in `catalog_read`.
2. **A read, not a resolution.** The module's first line says it: *"This module reads and
   never writes."*
3. **One query.** The two city lookups were collapsed into one `Q(name=name) |
   Q(normalized_key=key)`, and the provisioning row is *joined* with
   `annotate(F("provisioning__status"))` rather than fetched after.
4. **The query-count guards were raised, with the reason written down.** Browse's from 1 to 2,
   the city page's from 3 to 4 — because the status is a separate fact from the pool and comes
   from a different table. **A raised bound with a reason is not a weakened test; a raised
   bound without one is.**
5. **A coverage-request *slot*, not a control.** Item 10 fills it. An empty slot is honest;
   a control that pretends to work is not.
6. **`live` is named in code.** Not because it needs a treatment of its own — it does not —
   but so the vocabulary test can check it and a reader of the file can see it is handled.

## What the mutation check found

**Eight mutations, eight caught.** The probe was **extended, not duplicated** — it is the
run's single mutation instrument — and **it now covers both halves of the application**: a
mutation in a Python file is caught by pytest and one in a React component by vitest, with the
runner chosen by the target's own path.

| # | Mutation | Caught by |
|---|---|---|
| 1 | the status is never read — every city is quiet | 4 tests |
| 2 | the status read mints a `City` | 1 test |
| 3 | the collecting state is folded into the quiet state | 7 tests |
| 4 | a live city with no cards is told its sources failed | 1 test |
| 5 | a user with no city is told collection is under way | 3 tests |
| 6 | the collecting state does not announce itself | 1 test |
| 7 | the city page's collection note is dropped | 3 tests |
| 8 | the frontend learns a status the backend does not have | the vocabulary test |

**The survivor was in the mutation, not in the test.** Mutation 5's first version replaced
`{noCity ? (` with `{false ? (`, on the theory that the no-city reader would then fall through
to the collecting state. **They did not** — the fall-through is `noCards`, and a no-city
reader has no cards, so they fell through to the *quiet* state, which is exactly what the
test asserts they get. The mutation survived because **it did not do what it said.**

It was rewritten to swap the branch's body for `<BrowseCollecting city={browse.city} />`,
which *is* the lie, and that one is caught by three tests.

**A mutation that survives is a missing test — or a mutation that does not do what it says.
Both are worth a run's attention, and this one was the latter.**

## The trap worth remembering

**The backend has six statuses and the plan named five.**

`CityProvisioning.Status` holds `collecting`, `live`, `no_providers`, `yielded_nothing`,
`paused` — and **`failed`**, which item 8's probation writes when provisioning itself errored.

**The vocabulary test caught it**, because the test reads the model's `Status.choices` out of
the Django source rather than a list written by hand. `failed` is a fact about *why there are
no sources*, so it joins the no-sources family on both surfaces.

**A hand-written list would have missed it**, and the surface would have said "Nothing nearby
tonight" about a city whose provisioning had failed — which is the exact lie this item exists
to remove.

**And the second trap is what the vocabulary test is really for.** A frontend status the
backend does not have is a sentence waiting to be wrong: the day the backend's spelling
changes, the string simply stops matching, and every city in that status falls back to the
quiet state — **silently**. Mutation #8 is that failure, and it is caught.

## Verification

```bash
# backend
uv run --directory backend ruff check apps/ingestion apps/personalization apps/catalog shared tests/ingestion tests/personalization tests/api
uv run --directory backend ruff format --check apps/ingestion apps/personalization apps/catalog tests/ingestion tests/personalization tests/api
uv run --directory backend lint-imports                    # 21 kept, 0 broken
uv run --directory backend python manage.py makemigrations --check --dry-run
uv run --directory backend pytest -q                        # 9036 passed, 0 failed

# frontend
pnpm typecheck                                             # clean
pnpm lint                                                  # 0 errors
pnpm test                                                   # 2922 passed, 0 failed

# the mutation check
uv run --directory backend python ../.specs-fire/runs/run-eventpulse24-057/mutation/mutation_probe.py
#   → All 22 mutations were caught.
```

`apps/ingestion/services/city_status_read.py` at **100%** coverage.

## What this unblocks

**Item 10 (`city-coverage-request`)** fills the `data-browse-coverage-request` slot that
`BrowseNoSources` now carries — in the no-sources family only.

**Item 11 (`home-city-dropdown-catalog`)** rewires the picker to the catalog, and removes the
`GET /api/public/cities` declaration this item had to add to `DECLARED_UNCALLED` — the one
pre-existing failure this item found, and the one that belongs to item 11.
