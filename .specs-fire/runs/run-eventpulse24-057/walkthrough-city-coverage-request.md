---
run: run-eventpulse24-057
work_item: city-coverage-request
intent: city-picker-and-auto-collection
generated: 2026-11-21
mode: confirm
---

# Implementation Walkthrough: The coverage request, one per city

## Summary

Item 9 gave Browse four honest states and left a **slot** in the no-sources one: a
`coverageRequest` prop that rendered nothing, so the state offered the reader nothing it
could not do.

**That was deliberate.** A slot that renders nothing is honest; a slot with a button behind
it and no endpoint is a lie. So the slot waited.

**This item fills it.** A reader whose city has no sources is now offered one way out — ask
us to go and cover it — and the ask becomes a row, a count, an audit entry, and a button
that replaces itself with a confirmation.

**One request per city, always.** The database refuses the second row, and a second press
lands on the count.

## The one problem the item really was

**Where does a request for a *city* live, when the reader asking for it is a *person*?**

The request is about a place — editorial reads a queue of cities nobody covers us. But it is
*raised* by a reader. So the row could go on either side of the AD-3 wall, and both
placements are defensible until you ask what the row is actually about.

| Placement | Why not |
|---|---|
| `personal` — a `CoverageRequest` per user | **The item's whole point is "one request per city".** A per-user row would make the uniqueness constraint `(user, city)` — a *different* guarantee. The editorial queue would then aggregate across readers to discover that forty people asked for Chittagong, **and that aggregation is the thing being stored.** It would also put a **user id beside a city**, which is the pairing AD-13 is careful about. |
| **`catalog`, next to the Source Registry** | **The row is about a city, not about a person.** A `City` FK and a counter. No user id, no location beyond the city the reader already asked about. |

**The row is on the `catalog` side**, in `apps.ingestion` — the Source Registry's home and
the app that owns the catalog schema (AD-16).

## The structure

```text
backend/apps/ingestion/models.py                            MODIFIED
└── CityCoverageRequest
    ├── city            FK → City, PROTECT, related_name="coverage_requests"
    ├── request_count   PositiveIntegerField(default=1)
    ├── created_at      auto_now_add  — when it was FIRST raised
    ├── updated_at      auto_now
    └── Meta
        ├── UniqueConstraint(["city"], "city_coverage_request_city_uq")   ← the guarantee
        └── CheckConstraint(request_count >= 1, "city_coverage_request_count_ck")

backend/apps/ingestion/services/coverage_requests.py        NEW
├── request_coverage(city=..., actor=...)   the command: throttle → resolve → upsert → audit
├── read_coverage_request(city=...)         the read: is this city already asked for?
├── throttle_key(user_id)                   "coverage_request:{user_id}"
└── CoverageRequestOutcome                  frozen dataclass — plain data for the wire

backend/apps/ingestion/coverage_api.py                      NEW
└── POST /api/catalog/coverage-requests    auth=current_user, on the router

backend/apps/ingestion/schemas.py                           NEW
└── CoverageRequestIn  { city }            — a city and nothing else
└── CoverageRequestOut { city, recorded, request_count, created }

backend/apps/ingestion/admin.py                             MODIFIED
└── CityCoverageRequestAdmin    ReadOnlyAdmin — editorial READS the queue

backend/shared/constants.py                                  MODIFIED
└── COVERAGE_REQUEST_LIMIT = 5, COVERAGE_REQUEST_WINDOW_SECONDS = 24h

backend/config/api.py                                        MODIFIED
└── api.add_router("/catalog", coverage_router)

frontend/components/browse/coverage-request-control.tsx      NEW
└── idle → busy → recorded | failed

frontend/components/browse/browse-states.tsx                 MODIFIED
└── BrowseCollecting gains the same coverageRequest slot as BrowseNoSources

frontend/app/browse/page.tsx                                 MODIFIED
└── the control is built once, guarded by hasNoSources

frontend/tests/browse-coverage-request.test.tsx               NEW  (24 tests)
frontend/tests/browse-states.test.tsx                        MODIFIED (the partition)
```

## The rules the surfaces hold

| Rule | Why it is a rule |
|------|------------------|
| **One row per city, enforced by the database.** | The constraint is *named* so a test can assert it. A service that "handles" a duplicate is a promise; a constraint is a fact. |
| **A second request increments the count; it does not create a second row.** | Two readers asking for one city is two people wanting it covered — the number editorial prioritises on. |
| **The request never mints a city.** | A request is about a city we already know about and have failed to cover. A city we have never heard of is a *pick*, and a pick provisions (item 7). |
| **The throttle is checked before the idempotence shortcut.** | A repeat still spends an attempt. A limit a repeat could slip past is not a limit. |
| **The row carries no user id; the audit `details` carry the city *id* and the count.** | AD-13. The city name is a location; the id is not. |
| **The command logs nothing at all.** | There is nothing to leak, because there is no log line. |
| **The control appears in the no-sources family only.** | The slot is on every state that could hold it, and the page passes the control into the no-sources branch and nowhere else. |
| **After a successful request the button is *replaced*, not disabled.** | A disabled button still looks like something you could do. |
| **The admin is read-only.** | Editorial *reads* the queue; readers *create* the rows. |

## The key decisions

**1. A counter, not a per-user join table.** The item says to prefer the counter and record
the decision. **There is no stated need for the per-user answer, and no reader who could
act on it** — "did *this* user ask?" has no use; the editorial queue asks a different
question. A join table would also put a user id beside a city.

**2. A named `UniqueConstraint`, not a `OneToOneField`.** An auto-named constraint cannot
be asserted by name, and the AC demands a database-level test. The repo's `violates()`
helper reads `excinfo.value.__cause__.diag.constraint_name`, so the test asserts *that*
constraint refused — not merely that *something* refused.

**3. The row is on the `catalog` side.** It is about a place, and `apps.ingestion` owns the
catalog schema (AD-16).

**4. The endpoint is on an `apps.ingestion` router, mounted at `/api/catalog`.** The surface
says `/api/catalog` for a catalog row, and `apps.identity.api_auth` is the published seam
for "who is asking". **The `/catalog` prefix is the public catalog's, and AD-12 says the
public catalog is session-free — so the module says why this one is not: it is a write, and
every write on this surface is a signed-in act.** The auth is on the *router*, so the
reader's id comes from the session and never from a payload.

**5. The request never mints a city.** This is the decision the item turned on.

A request is for a city we have already tried to cover and failed to — one with a
provisioning row saying `no_providers`, `failed`, `yielded_nothing` or `paused`. **Those
are cities we already know about**, because provisioning wrote their `City` row.

**A city we have never heard of is a *pick*, not a request** — and a pick provisions the
city immediately, which is a *better* answer than queueing it. So the endpoint refuses with
the project's own `UnknownHomeCityError` (422, `unknown_home_city`), and the reader is sent
to the picker.

**6. The throttle runs before the idempotence shortcut.** The `event_reports.py` rule, for
the same reason. The key is `coverage_request:{user_id}`; the limit is **5 per reader per
day**, the same number as a report's, because the shape of the abuse is the same.

**7. The count goes up on a repeat; the row does not change shape.** The increment is
`F("request_count") + 1` — an atomic database update, not a read-modify-write in Python,
which would lose a concurrent increment.

**8. The control's placement is structural.** The node is built once at the page level and
guarded by `hasNoSources`; every state that could hold it has the slot. **"Only there" is
a fact about where the page places the node**, not a condition inside the control that a
later edit could widen.

## What the mutation check found

**32 mutations, 32 caught, 0 survived.** Two of this item's nine survived on the first run,
and **both pointed at a real gap rather than a weak test.**

**"The one-row guarantee is removed from the schema" survived.** The mutation changed the
*model's declared* constraint from `["city"]` to `["city", "request_count"]` and the suite
stayed green. **The model's declaration and the database's constraint are two different
things** — the migration built the database's, and it had already run. And the existing
test asserted only the constraint's *name*, which a `(city, request_count)` constraint would
have carried unchanged.

**The missing test, now written: `test_the_constraint_covers_the_city_alone`** — it asserts
`list(constraint.fields) == ["city"]`. A constraint on `(city, request_count)` would permit
a second row for the same city at a different count. **That is not "one row per city", and
the difference is invisible to a name assertion.**

**"The control is offered in the collecting state as well" survived.** The mutation removed
the page's `hasNoSources` guard and the suite stayed green — **because the control was only
*placed* in the no-sources branch, so removing the guard changed a value nobody rendered.**
The mutation was inert.

**The fix was structural, and it is a better design.** The control is now built **once at
the page level**, and **`BrowseCollecting` gained the same `coverageRequest` slot**
`BrowseNoSources` has — so the absence is a decision rather than an accident.** Every state
that could hold the control has the slot; the page passes the control into the no-sources
branch and nowhere else. With that, removing the guard genuinely widens the control's
reach, and the partition test catches it.

A third mutation was simply too weak — the original "the request mints a city" mutation
minted and *then raised*, so the transaction rolled back. It now mints without raising, and
is caught by three tests.

## The rules held

| Rule | Where it is held |
|------|------------------|
| **AD-13** — no PII in the audit sink or the log | The model's fields (no user field); the audit `details` (the city *id*, never the name); **no log line at all** (`caplog.records == []`). The city *name* is in the response, over the reader's own session — a different audience. |
| **AD-5** — the surface never writes through the ORM | `coverage_api.py` is in the surface list and the architecture test parses it and finds no ORM call. The audit row is written in the command's own transaction, so it rolls back with the row. |
| **AD-16** — one writer per fact | `ingestion_citycoveragerequest` → `ingestion`. |
| **AD-3** — the models wall | The endpoint is *inside* `apps.ingestion`, which may import its own models. The wire shapes cross as a service handing over plain data. |
| **AD-12** — the public catalog is session-free | The `/catalog` mount carries `auth=current_user`, and the module says why it is not the public catalog. |
| **AD-2** — `domain/` is pure | `normalize_city` is used, not reimplemented. |
| **AD-19** — the frontend reaches the backend only through the generated client | The control's body is typed by `components["schemas"]["CoverageRequestIn"]`, and `make client` regenerated the contract. |

## Verification

```bash
# backend
uv run --directory backend ruff check apps/ingestion shared config tests/ingestion tests/api tests/architecture tests/wall
#   → All checks passed!
uv run --directory backend ruff format --check apps/ingestion shared config tests/ingestion tests/api tests/architecture tests/wall
#   → 226 files already formatted
uv run --directory backend lint-imports
#   → Contracts: 21 kept, 0 broken.
uv run --directory backend python manage.py makemigrations --check --dry-run
#   → No changes detected
uv run --directory backend pytest -q
#   → 9091 passed, 1 warning in 331.33s

# frontend
pnpm typecheck        # → clean
pnpm lint             # → 0 errors, 2 pre-existing warnings (unrelated files)
pnpm test             # → 184 files, 2952 tests passed

# the contract
make client           # → openapi.json + schema.ts regenerated

# the mutation check
uv run --directory backend python ../.specs-fire/runs/run-eventpulse24-057/mutation/mutation_probe.py
#   → All 32 mutations were caught.
```

**`ruff format` was scoped to the directories being worked in** — never from the repo root,
which would drag the pre-existing drift in `backend/tests/shared/test_retention_published.py`
into the diff.

**`pnpm format:check` reports 45 files unformatted — one *fewer* than the 46 the branch
started with**, because this item's `browse-states.test.tsx` was in the pre-existing
unformatted set and was formatted here. The pre-existing drift is not this item's to fix.

## The risks

**The one risk worth naming** is the refusal of an unknown city. It is the right answer *as
the item is written* — "the cities automatic collection cannot reach" are cities that
already have a provisioning row — and it is consistent with item 7's
pick-provisions-immediately. **But it is the one place where the contract depends on a
reading of the item's wording**, and a reader who reads "ask us to cover a city we have not
covered" as including cities we have never heard of would expect a 201. **The answer would
then be a mint — through item 7's service, not a bare insert** — and the endpoint's
contract would change from "refuse" to "provision-later". That is a bigger design than this
item, and the refusal is the honest one until someone says otherwise.

**The second risk is the throttle's shared store.** `InMemoryThrottleAdapter` built without
a clock is a **process-wide shared store**, and every test in a file that shares an actor
id shares a throttle key. The first run of the service test file had 19 failures for
exactly this reason. The autouse fixture that monkeypatches `service.get_throttle_port`
with a fresh clocked adapter is load-bearing, and **a future test file that forgets it will
fail in a confusing way.** It is the same pattern `tests/personalization/test_event_reports.py`
uses, and the fixture's docstring says so.

## What this unblocks

**Item 11 (`home-city-dropdown-catalog`)** rewires the picker to the catalog and removes the
`GET /api/public/cities` declaration item 9 had to add to `DECLARED_UNCALLED`.

**And this item closes the loop item 9 opened.** The slot that was deliberately empty now
carries a control, so **Browse's no-sources state is the one empty state with a way out** —
and a state with no way out is a dead end, which is a lie about the product.
