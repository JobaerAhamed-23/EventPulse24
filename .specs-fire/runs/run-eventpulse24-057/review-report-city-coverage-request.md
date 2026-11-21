---
run: run-eventpulse24-057
work_item: city-coverage-request
intent: city-picker-and-auto-collection
generated: 2026-11-21
status: passed
---

# Review Report: The coverage request, one per city

## What this item adds

The fallback for the cities automatic collection cannot reach. A reader whose city has no
sources is offered one way out — ask us to go and cover it — and this is where that ask
becomes a row, a count, an audit entry, and a button.

| Piece | Where | What it is |
|-------|-------|-----------|
| `CityCoverageRequest` | `apps/ingestion/models.py` | The row: a city FK, a count, two timestamps, one named constraint |
| `services/coverage_requests.py` | `apps/ingestion/services/` | The command and the read |
| `coverage_api.py` | `apps/ingestion/` | `POST /api/catalog/coverage-requests` |
| `schemas.py` | `apps/ingestion/` | The wire shapes |
| `coverage-request-control.tsx` | `frontend/components/browse/` | The button |

## The findings

### 1. The row is on the `catalog` side, and it is the right side

The row is about a *place*. It holds a `City` foreign key and a counter, and **no user id
anywhere**. The editorial question is *"how many people want this city covered?"* — and the
answer to that is a number.

The alternative (a per-user row on the `personal` side) would have made the uniqueness
constraint `(user, city)`, which is **a different guarantee** — one row per reader per
city, not one row per city. The editorial queue would then have to aggregate across
readers to find out that forty people asked for Chittagong, and **that aggregation is the
thing being stored**. It would also have put a **user id beside a city**, which is the
pairing AD-13 is careful about.

**A row that cannot answer the question it exists for is the wrong shape**, and the
counter is the shape that answers it.

### 2. The request never mints a city — and this was the hardest decision in the item

The plan walked through three answers before settling on the third, and the reasoning is
worth keeping because the first two are the tempting ones.

**The tempting answer 1: refuse an unknown city.** But the item is *"the fallback for the
cities automatic collection cannot reach"* — and a city nobody has ever mentioned is
*precisely* the city that needs covering. Refusing it would refuse the case the item
exists for.

**The tempting answer 2: mint the `City` row**, the way item 7's `provision_city` does.
But `provision_city` also registers sources and writes a `CityProvisioning` row — a
coverage request is *a reader asking us to do the work*, **not the work**. Conflating the
two would let a button on a page create sources.

**The answer this item settled on: the request always names a city that exists.**

Re-read the item: the cities automatic collection cannot reach are cities whose
provisioning says `no_providers`, `failed`, `yielded_nothing` or `paused`. **Those are
cities we already know about** — provisioning wrote their `City` row. So the request's
subject is always a city we have already tried to cover and failed to.

**And a city we have never heard of is a *pick*, not a request** — and a pick provisions
the city immediately, which is a *better* answer than queueing it. So the endpoint refuses
with the project's own `UnknownHomeCityError` (422, `unknown_home_city`), and the reader is
sent to the picker.

**This is the same trap `city_status_read.py` documented in item 9, in the opposite
direction**: there, a read that minted would have put a place in the registry nobody chose;
here, a request that minted would put a place in the registry nobody *provisioned*. The
`City` table is a registry of places — but a place enters it when somebody picks it or a
venue names it, and **a button on an empty state is neither.**

### 3. The uniqueness is a *named* constraint, and that is not decoration

`CityProvisioning` uses a `OneToOneField` and inherits an auto-named unique index. **An
auto-named constraint cannot be asserted by name**, and the AC demands *"a test asserts the
unique constraint actually rejects a duplicate at the database level."*

So the model carries an explicit `models.UniqueConstraint(fields=["city"],
name="city_coverage_request_city_uq")`, and the test uses the repo's `violates()` helper,
which reads `excinfo.value.__cause__.diag.constraint_name`. **The constraint is the
guarantee, not a promise the service makes** — a second writer that did not know about the
first is stopped by PostgreSQL rather than by a code path somebody has to remember to
write.

**`PROTECT`, not `CASCADE`.** A city is never deleted, and a cascading delete would mean a
coverage request could vanish without anybody deciding to.

### 4. The throttle runs *before* the idempotence shortcut

`event_reports.py` states the rule and the reason: *"a client hammering the same report is
still spending attempts, and a limit a repeat could slip past is not a limit."* **The same
rule, for the same reason.** A reader pressing the button forty times is spending forty
attempts.

The test spells the arithmetic out, because it is easy to get wrong: **the first request
spent attempt one**, so four more fit inside the limit of five, and the *fifth* repeat is
the one refused. A test that expected the sixth call to fail would be asserting the wrong
number and would still pass — for the wrong reason.

### 5. AD-13, in three claims that must not be collapsed

| Claim | Where it holds |
|-------|----------------|
| The **row** carries no user id and no per-user location | The model has no user field — the *model's own fields* are the assertion, so there is no way to add one without the test noticing |
| The **audit `details`** carry no city name and no user id | `{"city_id": str(city.id), "request_count": n}` — the city *id*, never the name |
| The **audit row's** `actor_id` is the reader who asked | The codebase's own mechanism for recording who did a thing without pairing them with a place in the payload |

**And nothing is logged at all.** The service writes no log line, so there is no city name
to leak into one. The test asserts `caplog.records == []` — **the assertion that would
notice the day somebody added a `logger.info`.**

**The city *name* is not forbidden everywhere.** It is in the *response*, over the
reader's own session: the reader asked about a city, and the server answering the person
who just sent it is not a leak. It is forbidden in the *audit row* and the *log sink*, which
are the audiences that outlive the session.

### 6. The endpoint's home, and why it carries `auth=`

The endpoint is on a **new `apps.ingestion` router**, mounted at `/api/catalog`.

**The `/catalog` prefix is the public catalog's**, and AD-12 says the *public* catalog is
session-free — so this one needed a comment saying why it is not: **it is a write, and
every write on this surface is a signed-in act.** The auth lives on the **router**, not on
the operation, so the reader's id comes from the session and never from a payload.

**And it is an `apps.ingestion` router rather than a `personalization` one**, because the
row is a catalog row: a `personalization` router hosting a `catalog` row would misfile the
surface and put the path under `/api/personal` for a thing that is not personal.

### 7. The control replaces the button, and the reason is not fussiness

**After a successful request the button is *replaced* by the confirmation, not disabled in
place.** A disabled "Ask us to cover this city" reads as a **broken control** — it looks
like something the reader could still do and cannot. The confirmation takes its place.

**And a failure never leaves a confirmation behind.** The confirmation is set only on a
2xx — the server's own answer — so a refused request cannot put "we'll go and look" on the
screen, which would be a claim about the world that nothing supports (AD-10).

**The failure line is the server's own sentence**, not a paraphrase: `lib/api-errors.ts`
exists so the frontend quotes the API verbatim. The one message the frontend owns is the
offline one, because in that case the API never spoke.

### 8. The control's placement is structural, and the mutation check made it so

**The control appears in the no-sources family and nowhere else** — and "only there" is
enforced by *where the page places the node*, not by a condition inside the control that a
later edit could widen.

**This took a second pass.** The first implementation passed the control into the
no-sources branch and nothing else, which reads correctly but has a hole: a mutation that
removed the page's guard would have changed a value **nobody rendered**. The control is now
built **once at the page level**, and **every state that could hold the control has the
slot** — `BrowseNoSources` and `BrowseCollecting` — **so the absence is a decision rather
than an accident.** Removing the guard now genuinely widens the control's reach, and the
partition test catches it.

### 9. The count is on the wire and not on the screen

The response carries `request_count` — how many readers have asked — and the control does
not show it. **A reader told "you are the 47th person to ask" is being told something about
a crowd**, and the product's voice is calm. The number is for editorial, and it is on the
wire for them.

## The security and architecture notes

### AD-13 — no PII in the audit sink or the log

- The row: no user field, no per-user location. **The model's own fields are the check.**
- The audit `details`: `{"city_id", "request_count"}` — the id, never the name.
- The log: nothing at all. `caplog.records == []`.
- The response: the city name, over the reader's own session. **A different audience.**

### AD-5 — the surface never writes through the ORM

`apps/ingestion/coverage_api.py` is in the surface list, and
`tests/architecture/test_no_direct_writes.py` asserts it makes no direct write — **it
parses the file and finds no ORM call.** The endpoint parses the body, calls the published
command, and projects the command's plain data back.

**AD-5 also holds for the audit row:** `write_audit` hard-fails outside
`transaction.atomic(using=CATALOG)`, and the command's audit is written inside its own
transaction — so the audit row and the request roll back together. There is a test for
exactly that.

### AD-16 — one writer per fact

`tests/architecture/test_write_ownership.py` gained
`"ingestion_citycoveragerequest": "ingestion"`. The row's only writer is
`services/coverage_requests.py`.

### AD-3 — the models wall

**`apps.ingestion` may import its own models** — the one exception the `models-ingestion`
contract makes. The endpoint lives there *because* of that: a `personalization` router
could not import `apps.ingestion.models` to write a catalog row.

**The wire shapes cross the wall as a service handing over plain data**, which is the
sanctioned seam: `CoverageRequestOutcome` is a frozen dataclass with plain fields, and the
schema is built from it.

### AD-12 — the public catalog is session-free; this is not

The endpoint is on the `/catalog` prefix and it carries `auth=current_user`. **The comment
in the module says why**: the public catalog's answers are identical for every caller,
which is what makes them cacheable; **this is a write**, and every write on this surface is
a signed-in act.

### AD-2 — `domain/` is untouched

`normalize_city` is used, not reimplemented. The service adds no dependency the domain
does not allow.

### The import contracts

**21 kept, 0 broken.** No contract needed amending — the new module is inside
`apps.ingestion`, which already imports its own models.

## The findings that were *not* problems, and why

**The body's unknown fields are ignored, not rejected.** Ninja's schemas accept and drop
fields the schema does not declare. The first draft of the API test asserted a body
carrying a `user_id` is *refused* with a 422 — and it returned 201.

**That was the wrong test.** The property that matters is not "the body is rejected"; it
is **"the body's user id does not become the reader"**. So the test was rewritten to assert
the real guarantee: a body carrying somebody else's id is still **the signed-in reader's**
ask, and the audit row's `actor_id` is the session's reader and not the body's. **The
project's convention across every endpoint is that an unknown body field is ignored, and
the reader comes from the session regardless** — and inventing a stricter rule for one
endpoint would have been an inconsistency, not a safety measure.

**The throttle's shared store is a test-isolation trap.** `InMemoryThrottleAdapter` built
without a clock is a **process-wide shared store**. The first run of the service test file
had 19 failures, because every test used the same `ACTOR` id, so every test shared a
throttle key, and the limit was already spent by the third test. The fix is the pattern
`tests/personalization/test_event_reports.py` already uses: an autouse fixture that
monkeypatches `service.get_throttle_port` with a fresh clocked adapter. **The adapter is
swapped at the module that calls it** — not globally — which is why the fixture is in this
file and not in a shared conftest.

## The deliberately-not-changed list

| Not changed | Why |
|-------------|-----|
| `worker/tasks.py` | The request is a row, not a job. **Nothing needs to happen on a schedule** — the editorial queue reads it. |
| `apps/ingestion/api.py` | It is a three-line stub, unregistered. The new endpoint has its own module, and the stub is not this item's to retire. |
| `apps/personalization/` | The row is not personal. Nothing in `personalization` imports `ingestion`'s models (AD-3), and nothing needed to change. |
| `frontend/lib/browse-read.ts` | The read does not gain a "did this reader already ask" field — see below. |
| `domain/` | `normalize_city` is used as-is. |
| `shared/constants.py`'s other entries | Only `COVERAGE_REQUEST_LIMIT` and `COVERAGE_REQUEST_WINDOW_SECONDS` were added. |
| The item's own `work-item.md` | Read, not rewritten. |

**The control starts in `idle` on every page load**, and this is deliberate. The read that
would tell it otherwise does not exist — and building one would mean carrying "did this
reader already ask" in a per-user row, **which is exactly what decision 1 ruled out**. So
the control is `idle` on load and **the server is idempotent**: a reader who asks twice
gets the same answer twice, and the count is honest. The AC's *"does not invite a second
press"* is about **the response to a press**, not about the state on a later page load.

## The "only there" rule, one more time

The no-sources family is four statuses — `no_providers`, `failed`, `yielded_nothing`,
`paused` — and **from the reader's side they are one sentence**, so they share one
treatment and one way out. The distinction is not lost: it is in the payload, and it is
what the editorial surface reads.

**A reader whose city was paused by an editor still needs to be able to ask for it**, and
**a reader whose city failed to provision still needs a way to say "please try again for
my city"** — the failure was ours, not theirs.

**And the control is not offered in the collecting state** — asking us to collect a city we
are collecting is asking for what we are already doing — **nor in the quiet state** (a
covered city with nothing on tonight is a working collection on a Tuesday, and nothing about
it is broken) **nor for a reader with no city** (they have no collection to report on, and
the way out for them is the picker).

## What the mutation check found

**32 mutations, 32 caught, 0 survived.** Two of this item's nine survived on the first run,
and both pointed at a real gap rather than a weak test:

1. **"The one-row guarantee is removed from the schema"** — because the model's *declared*
   constraint and the database's are two different things (the migration built the
   database's), and the existing test asserted only the constraint's *name*. A constraint on
   `(city, request_count)` has the same name and would still permit a second row at a
   different count. **The missing test — `test_the_constraint_covers_the_city_alone` —
   asserts the fields.**

2. **"The control is offered in the collecting state as well"** — because the control was
   only *placed* in the no-sources branch, so removing the guard was an inert change.
   **The fix was structural**, and better: the control is built once at the page level, and
   every state that could hold it has the slot, so the absence is a decision.

The full detail is in `test-report-city-coverage-request.md`.

## The verdict

**The item's acceptance criteria are met, and the mutation check proves the tests can
fail.**

- The one row per city is **the database's** guarantee, and the test asserts it *by name
  and by fields*.
- A request never mints a city, and the test asserts the `City` count is unchanged.
- The count goes up on a repeat and the row does not change shape.
- The throttle is checked before the idempotence shortcut, and the test spells out the
  arithmetic.
- AD-13 holds in three separate claims, and the log claim is asserted by `caplog`.
- The endpoint's contract is 401/201/422/429, idempotent on a repeat, and it ignores a
  body-supplied user id.
- The control replaces its button on success, shows the server's own sentence on failure,
  and appears in the no-sources family and nowhere else.

**The one thing I would want a second pair of eyes on** is decision 2 — the refusal of an
unknown city. It is the right answer *as I read the item* ("the cities automatic collection
cannot reach" are cities we already have a provisioning row for), and it is consistent with
item 7's pick-provisions-immediately. **But it is the one place where this item's contract
depends on a reading of the item's wording**, and a reader who reads "ask us to cover a city
we have not covered" as including cities we have never heard of would expect a 201. **The
answer would then be a mint — through item 7's service, not a bare insert** — and the
endpoint's contract would change from "refuse" to "provision-later". That is a bigger
design than this item, and the refusal is the honest one until someone says otherwise.

## The files

| File | Change |
|------|--------|
| `backend/apps/ingestion/models.py` | `CityCoverageRequest` |
| `backend/apps/ingestion/migrations/0017_citycoveragerequest.py` | new |
| `backend/apps/ingestion/services/coverage_requests.py` | new — the command and the read |
| `backend/apps/ingestion/schemas.py` | new — the wire shapes |
| `backend/apps/ingestion/coverage_api.py` | new — the endpoint |
| `backend/apps/ingestion/admin.py` | `CityCoverageRequestAdmin` — read-only |
| `backend/shared/constants.py` | the limit and the window |
| `backend/config/api.py` | the router mount |
| `backend/tests/ingestion/test_coverage_requests.py` | new — 30 tests |
| `backend/tests/api/test_coverage_request_api.py` | new — 12 tests |
| `backend/tests/ingestion/test_models.py` | the model enumeration |
| `backend/tests/wall/test_schema_placement.py` | the table enumeration |
| `backend/tests/architecture/test_write_ownership.py` | the ownership entry |
| `backend/tests/architecture/test_no_direct_writes.py` | the surface list |
| `backend/tests/architecture/test_digest_composition_separation.py` | the request-module list |
| `frontend/components/browse/coverage-request-control.tsx` | new — the control |
| `frontend/components/browse/browse-states.tsx` | the slot on the collecting state |
| `frontend/app/browse/page.tsx` | the placement and the guard |
| `frontend/tests/browse-coverage-request.test.tsx` | new — 24 tests |
| `frontend/tests/browse-states.test.tsx` | the partition |
| `frontend/lib/api/openapi.json`, `schema.ts` | `make client` |
