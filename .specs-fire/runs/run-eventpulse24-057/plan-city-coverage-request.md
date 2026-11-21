---
run: run-eventpulse24-057
work_item: city-coverage-request
intent: city-picker-and-auto-collection
generated: 2026-11-21
---

# Plan: The coverage request, one per city

## Context

Run `run-eventpulse24-057`, intent `city-picker-and-auto-collection`, work item 10 of 11.

Item 9 (`browse-collecting-states`) gave Browse four honest states and left a **slot** in the
no-sources one: `BrowseNoSources` accepts a `coverageRequest?: ReactNode` prop and renders it
inside `<div data-browse-coverage-request>`. The slot is empty today, so it offers the reader
nothing it cannot do.

**This item fills that slot.** It is the fallback for the cities automatic collection cannot
reach: a control that records *"please go cover this city"*, **once per city**.

Nothing in this area exists yet — there is no model, no endpoint and no button. This is new
work, not a surface being kept.

## The one problem the item really was

**Where does a request for a *city* live, when the reader asking for it is a *person*?**

The request is about a place — editorial reads a queue of cities nobody covers us. But it is
*raised* by a reader. So the row could go on either side of the AD-3 wall, and both placements
are defensible until you ask what the row is actually about.

| Placement | Why not |
|---|---|
| `personal` (a `CoverageRequest` per user) | **The item's whole point is "one request per city".** A per-user row would be one row per reader per city, and the uniqueness constraint would be on `(user, city)` — which is a different guarantee. The editorial queue would then have to aggregate across users to find out that forty people asked for Chittagong, and the count that aggregation produces is the thing being stored. |
| **`catalog`, next to the Source Registry** | **The row is about a city, not about a person.** It holds a `City` foreign key and a counter. It carries no user id and no location beyond the city the reader already asked about. |

**Decision: the row is on the `catalog` side**, in `apps.ingestion` — the Source Registry's
home, and the app that owns the catalog schema (AD-16). Its Technical Notes say exactly this:
*"keep it on the `catalog` side with the rest of the Source Registry's editorial surface, and
keep user ids out of it."*

## The decisions already made

### 1. A counter column, not a per-user join table

The Technical Notes say: *"Prefer the counter unless there is a stated need for the per-user
answer, and record the decision."*

**There is no stated need, and there is no reader who could act on it.** "Did *this* user ask?"
has no use: the reader's own state is in their own browser's answer to the request, and the
editorial queue asks a different question — *how many people want this city covered?* A
per-user join table would also put a **user id beside a city** — the exact pairing AD-13 is
careful about — and the item's own AC says *"the request stores the city, which is the point of
the row, but no per-user location is written into any audit `details` or log line."*

**So: `request_count`, a `PositiveIntegerField`, and no user id anywhere on the row.**

### 2. The uniqueness is a named `UniqueConstraint`, not a `OneToOneField`

`CityProvisioning` uses a `OneToOneField` and inherits an auto-named unique index
(`ingestion_citycoveragerequest_city_id_<hash>_uniq`). **An auto-named constraint cannot be
asserted by name**, and the AC demands *"a test asserts the unique constraint actually rejects
a duplicate at the database level"*. A named constraint is assertable, and the repo already has
the `violates("…")` helper that reads `excinfo.value.__cause__.diag.constraint_name`.

So: a `ForeignKey(City, PROTECT, related_name="coverage_requests")` plus an explicit
`models.UniqueConstraint(fields=["city"], name="city_coverage_request_city_uq")`.

**`PROTECT`, not `CASCADE`.** A city is never deleted, and a cascading delete would mean a
coverage request could vanish without anybody deciding to — the same argument
`CityProvisioning` makes.

### 3. The endpoint lives on an `apps.ingestion` router

`apps.ingestion/api.py` exists but is a three-line stub, unregistered. Two options:

| Option | Why not |
|---|---|
| Put the endpoint on the `personalization` router | It would have to call an `apps.ingestion` service (AD-3 forbids importing the models) — fine — but the *router* would then be a `personalization` router hosting a `catalog` row. The surface would be misfiled, and the endpoint's path would live under `/api/personal` for a thing that is not personal. |
| **A new `apps.ingestion` router, `auth=current_user`, mounted at `/catalog`** | **The row is a catalog row and the surface says so.** `apps.ingestion` may import its own models (the one exception the `models-ingestion` contract makes), and `apps.identity.api_auth` is explicitly *"the published interface other apps use to find out who is making a request"*. |

The mount is `/api/catalog/coverage-requests`. **The `/catalog` prefix is already the public
catalog's**, and AD-12 says the *public catalog* is session-free — so this one needs a comment
saying why it is not: it is a **write**, and every write on this surface is a signed-in act.

### 4. The throttle is checked **before** the idempotence shortcut

`event_reports.py` states the rule: *"The throttle is checked **before** the idempotence
shortcut, deliberately: a client hammering the same report is still spending attempts, and a
limit that a repeat could slip past is not a limit."*

**The same rule, for the same reason.** A reader pressing the button forty times is spending
forty attempts, and a limit a repeat could slip past is not a limit. The throttle key is
`coverage_request:{user_id}` — the `event_report:{user_id}` precedent, which the codebase
already accepts as AD-13-clean (a cache key is neither a catalog row nor an audit payload).

**The limit: 5 per user per day.** The same number as `EVENT_REPORT_DAILY_LIMIT`, because the
shape of the abuse is the same — one person, many presses.

### 5. The read that finds the city is a **read**

`resolve_city` **mints** a `City`. Using it here would put a place into the registry that no
reader chose — the same trap `city_status_read.py` documented in item 9.

**But there is a difference from item 9's read.** In item 9, the city was one the reader had
*already picked* (their stored preference), so the row was guaranteed to exist. Here, the
reader is asking us to cover a city we have never seen. **There may be no `City` row at all.**

**So the request names a city by its *stored* string, and the row it writes holds a `City` FK —
which means the city must exist.** What does a request for a city we have no `City` row for?

Two honest answers:

| Answer | What it means |
|---|---|
| **Refuse (422)** | "We don't have that city yet." The reader cannot ask about a city we have no row for — but that is *exactly* the case the item is for! A city nobody has ever mentioned is precisely the city that needs covering. |
| **Mint the `City` row** | The reader's pick is what puts a city on the map. This is item 7's `provision_city` doing its job. |

**The answer is: mint it, through item 7's own service, not through a bare insert.**

**But minting a `City` is `provision_city`'s job, and `provision_city` also registers sources
and writes a `CityProvisioning` row.** A coverage request is a *reader asking us to do the
work* — it is not the work. So the two must not be conflated.

**The resolution: the coverage request resolves the city through `resolve_city` (which mints
the `City` row if it is new), and does nothing else.** It does not register a source, does not
write a provisioning row, does not provision anything. The city's *collection* is a separate
decision that the editorial queue makes; the request is the queue's input.

Wait — but then the request *does* mint a `City` row, and the AC says the row is "one request
per city". Minting a `City` for a place the reader named is exactly what item 7 does for a
picked city, and the catalog's `City` table is a *registry of places*, not a registry of
readers' choices. A city a reader named is a place that exists.

**Hold on. There is a cleaner answer, and it is the one the item's own wording points at.**
Re-read: *"the fallback for the cities automatic collection cannot reach"* — the cities
automatic collection *cannot reach* are cities that **already have a provisioning row** whose
status is one of `no_providers` / `failed` / `yielded_nothing` / `paused`. **Those are cities
we already know about.** They have a `City` row, because provisioning wrote one.

**So the request always names a city that exists.** The endpoint resolves it by identity and
refuses a city we have never heard of — because a request for a city we have never heard of is
not a coverage request, it is a *pick*, and a pick is item 7's `POST /api/personal/...` and
provisions the city immediately.

**That is the cleanest resolution, and it makes the endpoint's contract honest:** *ask us to
cover a city we know about and have failed to cover.* A city we have never heard of is
handled better by picking it.

So: **resolve by identity, do not mint.** A city that does not exist is a **422** with the
project's own `UnknownHomeCityError` shape (the same code and message the picker's unknown
city gets), because it is the same fact: "we don't have that city yet".

**But `resolve_city` mints.** So the coverage service does its own lookup — the same shape
`city_status_read.py` uses — and refuses a city that is not there. **A request never mints a
city.**

### 6. What the counter means, and what a second request does

*"A second request for the same city succeeds idempotently and does not create a second row,
whoever sends it."*

**The row does not change shape; the count goes up.** The idempotence is about the *row* — one
row per city — not about the count. Two readers asking for Chittagong is **two people wanting
it covered**, and that is the number editorial prioritises on.

**So a second request increments `request_count` and returns the same row.** The response says
`recorded: true` and `request_count: n`, and the control says *"we've recorded it"* — the
reader does not learn the count, because a reader who learns "you are the 47th person to ask"
is being told something about a crowd, and the product's voice is calm.

**The increment is `F("request_count") + 1`**, an atomic database update — not a
read-modify-write in Python, which would lose a concurrent increment.

### 7. AD-13, precisely

Three separate claims to keep apart:

| Claim | Where it holds |
|---|---|
| The **row** carries no user id and no per-user location | The model has no user field. The only fields are the city FK, the count, and two timestamps. |
| The **audit `details`** carry no city name and no user id | `details={"city_id": str(city.id), "request_count": n}` — the city *id*, never the name. The name is a fact about a place, but it is also the value a reader's location would take, and the codebase's rule for a city-scoped command is the id (`city.provisioned`, `city.resumed`, `city.venue_resolved`). |
| The **audit row's** `actor_id` is the user who asked | This is the codebase's own mechanism for recording who did a thing without pairing them with a place in the payload — every admin action and every command writes it. It is not a `details` field and not a log line. |

**And nothing is logged.** The service writes no log line at all, so there is no city name to
leak into one.

### 8. The control

A client island in `frontend/components/browse/coverage-request-control.tsx`, passed into
`BrowseNoSources`'s `coverageRequest` slot from `app/browse/page.tsx`.

**It renders only in the no-sources family** — and it is passed *only* in that branch, so the
collecting state and the quiet state cannot show it even by accident. That is the AC's "only",
and it is enforced by the branch rather than by a condition inside the control.

**After a successful request the control reports that it was recorded and does not invite a
second press.** The button is replaced by the sentence — not disabled in place, because a
disabled button still looks like something you could do.

The failure line is the project's own: `role="alert"`, "Couldn't record that. Try again."

### 9. The state the control starts in

The reader may have asked before. **The control starts in `idle` every time the page loads**,
because the read that would tell it otherwise does not exist — and building one would mean
carrying "did this reader already ask" in a per-user row, which decision 1 ruled out.

**So the control is `idle` on load, and the server is idempotent.** A reader who asks twice
gets the same answer twice, and the count is honest. The AC says *"after a successful request
the control reports that it was recorded and does not invite a second press"* — which is about
**the response to a press**, not about the state on a later page load.

## Structure Overview

```text
backend/apps/ingestion/models.py                            MODIFIED
└── CityCoverageRequest    the row: city FK, count, two timestamps, one named constraint

backend/apps/ingestion/migrations/0017_citycoveragerequest.py   NEW
└── CreateModel + the named unique constraint

backend/apps/ingestion/services/coverage_requests.py        NEW
├── request_coverage(city=..., actor=...)   the command: throttle, resolve, upsert, audit
├── read_coverage_request(city=...)         the read: is this city already asked for?
└── throttle_key(user_id)                   the throttle's key

backend/apps/ingestion/coverage_api.py                      NEW
└── the endpoint: POST /api/catalog/coverage-requests

backend/apps/ingestion/schemas.py                           NEW
└── CoverageRequestIn / CoverageRequestOut

backend/apps/ingestion/admin.py                             MODIFIED
└── CityCoverageRequestAdmin    read-only: editorial reads the queue

backend/shared/constants.py                                  MODIFIED
└── COVERAGE_REQUEST_LIMIT, COVERAGE_REQUEST_WINDOW_SECONDS

backend/config/api.py                                        MODIFIED
└── api.add_router("/catalog", coverage_router)

frontend/components/browse/coverage-request-control.tsx      NEW
└── the control: idle → busy → recorded | failed

frontend/app/browse/page.tsx                                 MODIFIED
└── passes the control into BrowseNoSources' slot

frontend/tests/browse-coverage-request.test.tsx               NEW
└── the control's own tests

frontend/tests/browse-states.test.tsx                        MODIFIED
└── the control appears in the no-sources family, and only there
```

## The rules the surfaces hold

| Rule | Why it is a rule |
|---|---|
| **One row per city, enforced by the database.** | The AC says so, and the constraint is *named* so a test can assert it. A service that "handles" a duplicate is a promise; a constraint is a fact. |
| **A second request increments the count; it does not create a second row.** | Two readers asking for one city is two people wanting it covered — the number editorial prioritises on. |
| **The request never mints a city.** | A request is about a city we already know about and have failed to cover. A city we have never heard of is a *pick*, and a pick provisions (item 7). Minting here would put places in the registry that no reader chose — the trap `city_status_read.py` documents. |
| **The throttle is checked before the idempotence shortcut.** | A repeat still spends an attempt. A limit a repeat could slip past is not a limit. |
| **The row carries no user id; the audit `details` carry the city *id* and the count.** | AD-13. The city name is a location; the id is not. |
| **The control appears in the no-sources family only.** | It is passed only in that branch, so it cannot appear elsewhere even by accident. |
| **After a successful request the button is *replaced*, not disabled.** | A disabled button still looks like something you could do. |
| **The admin is read-only.** | `CommandAdmin.save_model` raises `PermissionDenied`; a `ReadOnlyAdmin` cannot fabricate a request. Editorial *reads* the queue; readers *create* the rows. |

## The key decisions

1. **A counter, not a per-user join table** — the item says to prefer the counter, and there is
   no reader-facing need for the per-user answer. A join table would also put a user id beside
   a city.
2. **A named `UniqueConstraint`, not a `OneToOneField`** — an auto-named constraint cannot be
   asserted by name, and the AC demands a database-level test.
3. **The row is on the `catalog` side** — it is about a place, and `apps.ingestion` owns the
   catalog schema (AD-16).
4. **The endpoint is on an `apps.ingestion` router** — the surface says `/api/catalog`, and the
   row is a catalog row. `apps.identity.api_auth` is the published seam for "who is asking".
5. **The request never mints a city** — a request names a city we already have; an unknown one
   is a *pick*, and gets the project's existing unknown-city refusal.
6. **The throttle runs before the idempotence shortcut** — the `event_reports.py` rule, for the
   same reason.
7. **The count goes up on a repeat; the row does not change shape.**
8. **The control is passed only into `BrowseNoSources`** — the AC's "only", enforced by the
   branch rather than by a condition.

## The tests

### `backend/tests/ingestion/test_coverage_requests.py` (new)

- **The constraint, at the database level.** A second row for the same city is refused, and
  the refusal names `city_coverage_request_city_uq`. **The AC's headline test.**
- **The service is idempotent about the row.** A second request for the same city leaves one
  row and increments the count.
- **The service never mints.** A request for a city that does not exist is refused and writes
  no `City` row.
- **The count.** The first request is 1; the second is 2.
- **The timestamps.** `created_at` is when it was *first* raised and does not move; `updated_at`
  moves.
- **AD-13.** The audit `details` are exactly `{"city_id", "request_count"}` — no city name, no
  user id. The row has no user field.
- **The throttle.** The eleventh request in a window is refused; the throttle is checked
  *before* the idempotence shortcut, so a repeat still spends an attempt.
- **The audit row** is written in the same transaction as the row.

### `backend/tests/api/test_coverage_request_api.py` (new)

- The endpoint refuses an anonymous request (401).
- The endpoint accepts a signed-in reader (201).
- The endpoint is idempotent (a second press is 201, not 409 or 500).
- The endpoint refuses a city we do not have (422).
- The endpoint is rate-limited (429).
- The endpoint takes **no user id** in the body.

### `frontend/tests/browse-coverage-request.test.tsx` (new)

- The control renders a button when idle.
- Pressing it posts the city and reports that it was recorded.
- After the request the button is **gone**, not disabled.
- A failed request says so and offers the button again.
- The control is not offered in the collecting state or the quiet state.

### `frontend/tests/browse-states.test.tsx` (extended)

- The no-sources family carries the control.
- The collecting state and the quiet state do not.

### The mutation check

Every one of these must be caught:

1. The unique constraint is removed → the duplicate is no longer refused.
2. The service creates a second row instead of incrementing → the "one row" test fails.
3. The service mints a `City` → the "never mints" test fails.
4. The counter is not incremented → the count test fails.
5. The audit `details` carry the city name → the AD-13 test fails.
6. The throttle is checked *after* the idempotence shortcut → the throttle test fails.
7. The endpoint drops `auth=` → the 401 test fails.
8. The control is offered in the collecting state → the "only" test fails.
9. The control stays visible after a successful request → the "replaced" test fails.

## Verification

```bash
# backend
uv run --directory backend ruff check apps/ingestion shared tests/ingestion tests/api
uv run --directory backend ruff format --check apps/ingestion shared tests/ingestion tests/api
uv run --directory backend lint-imports                                    # 21 kept, 0 broken
uv run --directory backend python manage.py makemigrations --check --dry-run
uv run --directory backend pytest -q

# frontend
pnpm typecheck                                                          # clean
pnpm lint                                                               # 0 errors
pnpm test

# the contract
make client                                                             # openapi.json + schema.ts
```

**`make client` is required** — the endpoint changes the API surface, and
`tests/api/test_contract.py::test_committed_openapi_schema_matches_the_live_api` fails on
drift until the client is regenerated.

**`ruff format` is scoped to `apps/ingestion` and `tests/ingestion` only** — running it at the
repo root drags the pre-existing drift in `backend/tests/shared/test_retention_published.py`
into the diff.

## Artifacts

Per the run's practice, each work item owes four artifacts in
`.specs-fire/runs/run-eventpulse24-057/`:

- `plan-city-coverage-request.md` — this plan.
- `test-report-city-coverage-request.md` — the AC-by-AC validation, the mutation table, the
  tests-written breakdown, the commands.
- `review-report-city-coverage-request.md` — the findings, the security/architecture notes, the
  "deliberately not changed" list.
- `walkthrough-city-coverage-request.md` — the summary, the structure overview, the rules held,
  the key decisions, what the mutation check found, verification, and what it unblocks.

Then: advance the phase to `review`, run `complete-run.cjs … --complete-item
city-coverage-request`, update `run.md`, and commit.

## What this unblocks

**Item 11 (`home-city-dropdown-catalog`)** rewires the picker to the catalog, and removes the
`GET /api/public/cities` declaration item 9 had to add to `DECLARED_UNCALLED`.

**And this item closes the loop item 9 opened**: the slot that was deliberately empty now
carries a control, so Browse's no-sources state is the one empty state with a way out.
