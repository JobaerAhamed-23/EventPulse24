---
run: run-eventpulse24-057
work_item: city-coverage-request
intent: city-picker-and-auto-collection
generated: 2026-11-21
status: passed
---

# Test Report: The coverage request, one per city

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| `test_coverage_requests.py` (new) | 30 | 0 | 0 | 100% |
| `test_coverage_request_api.py` (new) | 12 | 0 | 0 | 100% |
| `browse-coverage-request.test.tsx` (new) | 24 | 0 | 0 | — |
| `browse-states.test.tsx` (extended) | 36 | 0 | 0 | — |
| Backend suite (full) | 9091 | 0 | 0 | — |
| Frontend suite (full) | 2952 | 0 | 0 | — |

`apps/ingestion/services/coverage_requests.py` and `apps/ingestion/coverage_api.py` at
**100%** — every statement, including the "this name normalises to nothing" guards on both
the command and the read. `lint-imports` **21 contracts kept, 0 broken**.
`makemigrations --check` reports **no changes**.

**The mutation probe: 32 mutations, 32 caught, 0 survived.**

## Acceptance Criteria Validation

### The row

- ✅ **One request per city, enforced by the database** —
  `test_coverage_requests.py` → `TestTheDatabaseRefusesADuplicate` →
  `test_a_second_row_for_the_same_city_is_refused` asserts the *database* refuses the
  duplicate **and names the constraint** (`city_coverage_request_city_uq`) via the repo's
  `violates()` helper, which reads `excinfo.value.__cause__.diag.constraint_name`.
  **This is the AC's headline test.**
- ✅ **The constraint is named, so a test can assert *that* constraint refused** —
  `test_the_constraint_is_named`, plus `test_the_constraint_covers_the_city_alone`, which
  pins the *fields* (see "What the mutation check found", below — the fields assertion
  exists because of a surviving mutation).
- ✅ **One per city, not one per table** — `test_two_cities_may_each_have_a_request`.
- ✅ **The row is about a place, not a person** —
  `TestNothingAboutTheReaderReachesTheRow` → `test_the_row_carries_no_user_field` asserts
  the *model's own fields* — no `user`, no `user_id`, no `requesting_user`. The model's own
  field list is the check, so there is no way to add a user field without this test
  noticing.

### The request

- ✅ **A request creates one row** — `TestTheRequestIsRecorded` →
  `test_a_request_creates_one_row`.
- ✅ **A second request does not create a second row, and the count goes up** —
  `test_a_second_request_does_not_create_a_second_row` asserts one row, `created is False`,
  and `request_count == 2`. **The count is where the second reader lands.**
- ✅ **The count moves up with every reader** — `test_the_count_moves_up_with_every_reader`
  (three requests → 3).
- ✅ **The request is found by the catalog's canonical name** —
  `test_the_request_is_found_by_the_catalogs_own_name`.
- ✅ **And by the identity key too** — `test_the_request_is_found_by_the_identity_key_too`:
  a city a *venue* minted under its own spelling (`"Portland, Oregon"`) is found by the
  catalog's name, and the two spellings of one place are one city.
- ✅ **`created_at` does not move on a later request** —
  `test_the_first_raised_time_does_not_move`: the timestamp answers "when did somebody
  *first* tell us about this city", and the editorial queue sorts on the first one.
- ✅ **The read finds the request, and finds nothing for a city never asked for** —
  `test_the_read_finds_the_request`, `test_the_read_finds_nothing_for_a_city_that_was_never_asked_for`,
  plus `test_the_read_finds_nothing_for_an_empty_city` and
  `test_the_read_finds_nothing_for_a_name_that_normalises_to_nothing`.

### A request never mints

- ✅ **A request for an unknown city is refused, and mints nothing** —
  `TestTheRequestNeverMints` → `test_a_request_for_an_unknown_city_is_refused` asserts
  `UnknownHomeCityError` **and** that the `City` count is unchanged.
- ✅ **A refused request writes nothing** — `test_a_refused_request_writes_nothing`: no row,
  no count, no audit row.
- ✅ **An empty city is refused** — `test_an_empty_city_is_refused`.
- ✅ **A name that normalises to nothing is refused** —
  `test_a_name_that_normalises_to_nothing_is_refused`: `"!!!"` has no identity key, and a
  lookup with an empty key would match *every* city whose `normalized_key` is empty.

### AD-13

- ✅ **No city name in the audit `details`** —
  `test_the_audit_details_carry_the_city_id_and_the_count` asserts the details are
  **exactly** `{"city_id": str(city.id), "request_count": 1}`; plus
  `test_the_audit_details_carry_no_city_name`.
- ✅ **No user id in the audit `details`** — `test_the_audit_details_carry_no_user_id`.
- ✅ **The command writes no log line at all** — `test_the_command_writes_no_log_line`
  asserts `caplog.records == []`. **There is nothing to leak, because there is no log
  line** — and this is the assertion that would notice the day somebody added a
  `logger.info`.

### The audit

- ✅ **One audit row per request, with the right action and target** —
  `TestTheAuditRow` → `test_a_request_writes_one_audit_row` asserts the action is
  `city.coverage_requested` and the target type is `CityCoverageRequest`.
- ✅ **Every ask is audited, not only the first** — `test_a_repeat_writes_another_audit_row`:
  the row did not change shape, but somebody asked again, and the audit trail is how
  editorial would see a city being asked for more and more.
- ✅ **The audit row and the request roll back together** (AD-5) —
  `test_the_audit_row_and_the_request_roll_back_together`: a command that failed must
  leave no audit row, or the log would claim something that did not happen.

### The throttle

- ✅ **Five per reader, and the sixth is refused** — `TestTheThrottle` →
  `test_the_limit_is_five_per_reader`.
- ✅ **A refused request writes nothing** — `test_a_refused_request_writes_nothing`: one
  row, count 5.
- ✅ **The throttle is checked *before* the idempotence shortcut** —
  `test_the_throttle_is_checked_before_the_idempotence_shortcut`. **The first request spent
  attempt one**, so four more fit inside the limit and the *fifth* repeat is the one
  refused. If the throttle ran *after* the shortcut, every repeat would have been free
  and the reader would never have been refused at all.
- ✅ **The throttle key is the reader's own, and opaque** —
  `test_the_throttle_key_is_the_readers_own`.

### The endpoint

- ✅ **An anonymous request is refused** — `test_a_signed_out_request_is_refused`: 401/403,
  and no row.
- ✅ **A signed-in reader is accepted** — `test_a_signed_in_reader_is_accepted`: 201 with the
  exact body.
- ✅ **The request is recorded** — `test_the_request_is_recorded`.
- ✅ **The answer carries the catalog's name, not the caller's** —
  `test_the_response_carries_the_city_as_the_catalog_names_it`.
- ✅ **A second press is a second success, not a conflict** — `test_a_second_press_is_a_second_success`:
  201 again, `request_count == 2`, `created is False`, and still one row. **The client must
  not see a 409.**
- ✅ **A city we do not have is a 422** — `test_a_city_we_do_not_have_is_refused`: the code is
  `unknown_home_city`, and no `City` and no request row is written.
- ✅ **An empty city, and a missing city, are refused** —
  `test_an_empty_city_is_refused`, `test_a_missing_city_is_refused`.
- ✅ **The body carries no user id, and the body's user id is ignored** —
  `test_a_body_with_a_user_id_does_not_change_who_is_asking`: the body carries somebody
  else's id and the ask is still the signed-in reader's.
- ✅ **The audit row attributes the ask to the session** —
  `test_the_audit_row_attributes_the_ask_to_the_session`: `actor_id` is the session's
  reader, and not the body's.
- ✅ **Past the limit is a 429 with the wait** — `test_the_sixth_request_answers_429`: the
  code is `rate_limited` and `retry_after_seconds > 0`.
- ✅ **The throttled request is not recorded** — `test_the_throttled_request_is_not_recorded`:
  the count is exactly the limit.

### The control

- ✅ **It renders a button named for the ask** — `browse-coverage-request.test.tsx` →
  `the idle state` → `offers a button named for the ask`, `shows the words, not a glyph`.
- ✅ **It posts the city to the endpoint, through the generated client** —
  `the request` → `posts the city to the coverage-request endpoint`, `goes through the
  generated client`, `carries no user id`.
- ✅ **The busy state disables the button and says so** — `the busy state`: `disabled`,
  `aria-busy="true"`, **a quiet dot and not a spinner** (`EXPERIENCE.md`: a spinner is a
  visual urgency badge), and **it cannot be pressed twice**.
- ✅ **After a success the button is *replaced*, not disabled** — `the recorded state` →
  `replaces the button rather than disabling it` asserts `queryByRole("button")` is null.
  **A disabled "Ask us to cover this city" reads as a broken control.**
- ✅ **The confirmation announces itself politely** — `announces itself politely`.
- ✅ **The count is not shown** — `does not show the count`: a reader told "you are the 47th
  person to ask" is being told something about a crowd.
- ✅ **A failure shows the server's own sentence** — `the failed state` → `shows the
  server's own sentence` asserts the API's verbatim words.
- ✅ **A failure announces itself as an alert** — `announces itself as an alert`.
- ✅ **A failure puts the button back** — `puts the button back`.
- ✅ **A failure shows no confirmation** — `shows no confirmation`: a refused request must
  not put "we'll go and look" on the screen, which would be a claim about the world that
  nothing supports.
- ✅ **It can be retried** — `can be retried`.
- ✅ **A network failure shows the offline sentence and no confirmation** —
  `a network failure`: three tests.

### The control appears only where it belongs

- ✅ **The no-sources family carries the control** — `browse-states.test.tsx` →
  `the no-sources state` → `offers the control itself — the way out of a dead end`; plus
  `offers the control, like every member of the family` on the paused, no-providers and
  failed states.
- ✅ **The collecting state, the quiet state and the no-city state do not** —
  `offers no coverage request — we are already doing the thing` (collecting),
  `carries no coverage request either` (quiet), `carries no coverage request` (no city).
- ✅ **The partition is asserted as a partition** —
  `the states do not collapse into one another` → `offers the coverage request in the
  no-sources family and nowhere else`: the four states that offer it, the three that do
  not, named explicitly.

## The mutation check

**32 mutations, 32 caught, 0 survived.** The probe is
`.specs-fire/runs/run-eventpulse24-057/mutation/mutation_probe.py`, and it covers every
item in this run.

### This item's nine

| # | Mutation | Caught by | Result |
|---|----------|-----------|--------|
| 1 | The one-row guarantee is removed from the schema | `test_the_constraint_covers_the_city_alone` | 1 failed |
| 2 | A repeat creates a second row instead of raising the count | the idempotence and count tests | 7 failed |
| 3 | The request mints a city it has never heard of | the "never mints" tests | 3 failed |
| 4 | The count does not move on a repeat | the count tests | 4 failed |
| 5 | The audit details carry the city name | the AD-13 tests | 2 failed |
| 6 | The throttle is checked after the idempotence shortcut | the throttle-ordering test | 3 failed |
| 7 | The endpoint drops its authentication | the 401 test | 1 failed |
| 8 | The control is offered in the collecting state as well | the partition test | 2 failed |
| 9 | The control stays visible after a successful request | the "replaced" test | 1 failed |
| 10 | A failed ask leaves a confirmation behind | the "shows no confirmation" test | 1 failed |

### What the mutation check found — two surviving mutations and the tests they cost

**A mutation that survived is a missing test.** Two of the nine survived on the first run,
and both pointed at a real gap.

**1. "The one-row guarantee is removed from the schema" survived.**

The mutation changed the *model's declared* `UniqueConstraint` from `fields=["city"]` to
`fields=["city", "request_count"]` — and the suite stayed green. **The reason is that the
model's declaration and the database's constraint are two different things:** the migration
is what built the database's, and the migration had already run. So changing the
declaration changed nothing the database did.

And the existing test — `test_the_constraint_is_named` — asserted only that the *name* was
present. A constraint on `(city, request_count)` would have the **same name** and would
still be *called* `city_coverage_request_city_uq`, so the name assertion could not see the
difference. **The gap was that nothing asserted the constraint's fields.**

**The missing test, now written: `test_the_constraint_covers_the_city_alone`** — it asserts
`list(constraint.fields) == ["city"]`. A constraint on `(city, request_count)` would forbid
a second row for the same city *only when the count matched*, so it would permit a second
row for the same city at a different count. **That is not "one row per city"**, and the
difference between the two is invisible to a name assertion.

**2. "The control is offered in the collecting state as well" survived.**

The mutation removed the `hasNoSources` guard from the page's `coverageRequest` — and the
suite stayed green. **The reason is that the control was only *placed* in the no-sources
branch**, so removing the guard changed a value nobody rendered. The mutation was inert,
not the test weak.

**The fix was structural, and it is a better design.** The control is now built **once, at
the page level**, and the guard is the only thing deciding whether it is offered. And
`BrowseCollecting` was given the **same `coverageRequest` slot** `BrowseNoSources` has —
**so the absence is a decision rather than an accident.** Every state that could hold the
control has the slot; the page passes the control into the no-sources branch and nowhere
else. With that, removing the guard genuinely widens the control's reach, and the
partition test catches it.

**3. A third mutation was simply too weak.** "The request mints a city it has never heard
of" originally *minted and then raised* — so the transaction rolled back and the city was
never committed. The mutation now mints **without raising**, and is caught by three tests.

### The other 22

The other 22 are items 1–9's mutations, all still caught: the probation's threshold, its
yield set, its `not_modified` rule, its treatment of fetch failures, the `live` city's
terminality, the hand-pause marker, the resume path's backfill and its duplicate-avoidance
and its status reset, the counter's reset, the pause reason's audit shape, the city link's
audit shape, the probation's transaction boundary, and item 9's five frontend mutations and
the status read's mint.

## The tests written

### `backend/tests/ingestion/test_coverage_requests.py` — 30 tests

| Class | Tests | What it defends |
|-------|-------|-----------------|
| `TestTheDatabaseRefusesADuplicate` | 4 | The one-row guarantee, at the database level, by name and by fields |
| `TestTheRequestIsRecorded` | 11 | One row per city; the count; the lookup by name and by key; the timestamps; the read |
| `TestTheRequestNeverMints` | 4 | An unknown, empty or unnormalisable city is refused and writes nothing |
| `TestNothingAboutTheReaderReachesTheRow` | 5 | AD-13: no user field, no city name, no user id, no log line |
| `TestTheAuditRow` | 3 | One audit row per ask; the audit and the row roll back together |
| `TestTheThrottle` | 4 | Five per reader; the ordering against the idempotence shortcut; the key |

### `backend/tests/api/test_coverage_request_api.py` — 12 tests

The endpoint's contract: the statuses (401/201/422/429), the body, the idempotence, the
throttle, and the fact that the body's user id is ignored rather than obeyed.

### `frontend/tests/browse-coverage-request.test.tsx` — 24 tests

The control's four states (idle, busy, recorded, failed), the request, the confirmation,
the refusals, and the network failure.

### `frontend/tests/browse-states.test.tsx` — 6 tests added

The control appears in the no-sources family and nowhere else, asserted as a partition.

## The commands

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
#   → 9091 passed, 1 warning in 332.06s

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

**`pnpm format:check` reports 45 files unformatted — one *fewer* than the 46 the branch
started with**, because this item's `browse-states.test.tsx` was in the pre-existing
unformatted set and was formatted here. The pre-existing drift is not this item's to fix.
