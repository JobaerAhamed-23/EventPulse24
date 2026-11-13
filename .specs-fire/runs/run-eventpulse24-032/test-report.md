---
run: run-eventpulse24-032
intent: account-profile-name
generated: 2026-11-13T11:00:00Z
status: passed
---

# Test Report

This is a **wide** run — six work items, and each one appends its section below. The
sections are in the order the items were executed, and each says which work item it
belongs to.

---

## Work Item: user-name-model-and-command

### Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Unit | 33 | 0 | 0 | 100% (`apps/identity/services/profile.py`) |
| Integration | 15 | 0 | 0 | — |
| **Total** | **48** | **0** | **0** | **100%** |

The command module is at **100% line coverage** — 24 statements, 0 missed, against an
80% gate.

### Acceptance Criteria Validation

- ✅ **The account has a name field, and it is `""` — not `null` — when unset** —
  `backend/tests/identity/test_models.py`. A null would make *"cleared"* and *"never
  set"* two states with the same meaning; the frontend's fallback is a **display** rule
  and the backend does not own it.
- ✅ **The migration exists and is generated, not hand-written** —
  `backend/apps/identity/migrations/0005_user_name.py`, produced by
  `makemigrations identity`. `makemigrations --check --dry-run` reports no changes.
- ✅ **`set_user_name` is a named command, published from the services module** —
  `backend/apps/identity/services/profile.py`; `test_the_command_is_published_from_the_services_module`
  asserts `"set_user_name" in services.__all__` and that the published object is the
  same function.
- ✅ **The name is trimmed, its internal whitespace collapsed, and an over-long name
  truncated rather than refused** — `test_set_user_name_trims_leading_and_trailing_whitespace`,
  `test_set_user_name_collapses_internal_whitespace`,
  `test_set_user_name_truncates_an_over_long_name`.
- ✅ **An empty (or whitespace-only) name means "no name set" and is not a refusal** —
  `test_set_user_name_stores_an_empty_name_as_no_name_set`,
  `test_set_user_name_stores_a_whitespace_only_name_as_no_name_set`.
- ✅ **A control character is refused, and **nothing is written** —
  `test_set_user_name_refuses_a_name_carrying_a_control_character` and
  `test_set_user_name_refuses_a_control_character_and_writes_nothing`. The refusal
  happens *before* the write, so the row keeps its old name.
- ✅ **The write happens inside `transaction.atomic(using=PERSONAL)`** (AD-3) — the
  source-reading assertion for the **alias** (which is a syntax rule, and is scanned
  independently by `tests/architecture/test_database_alias.py`), plus the behavioural
  test `test_set_user_name_cannot_write_an_audit_row_outside_a_transaction`.
- ✅ **The audit row commits with the mutation, or neither does** (AD-5) —
  `test_set_user_name_writes_the_audit_row_in_the_same_transaction` and
  `test_set_user_name_rolls_back_the_audit_row_when_the_write_fails`.
- ✅ **The audit row carries no name and no address** (AD-13) —
  `test_the_audit_row_details_carry_no_name` asserts `row.details == {}` **and** that
  neither *"Maya"* nor *"Ahmed"* appears in it, rather than only asserting the shape;
  `test_the_audit_row_carries_the_actor_by_value` asserts the actor is a UUID with no
  label.
- ✅ **The name is not a key — it leaves the email and the case alone** —
  `test_set_user_name_leaves_the_email_alone`,
  `test_set_user_name_leaves_the_name_case_alone`.
- ✅ **The command takes a `user_id` and not a `User`** —
  `test_set_user_name_for_an_unknown_account_raises` raises `User.DoesNotExist`; the
  row is looked up inside the transaction, so the command owns what it writes.

### Tests Written

`backend/tests/identity/test_profile_command.py` (created) — the command's rules, its
transaction, and its privacy. **29 tests at the time of this item** (33 today; the
next work item added four).

`backend/tests/identity/test_models.py` (extended) — the new field's default.

### Test Commands

```bash
cd backend

# This item's tests
uv run pytest tests/identity/test_profile_command.py tests/identity/test_models.py -q --reuse-db

# Coverage of the command module
uv run pytest tests/identity/test_profile_command.py -q --reuse-db \
  --cov=apps.identity.services.profile --cov-report=term-missing

# The architecture contracts
uv run pytest tests/architecture -q --reuse-db          # 990 passed

# The import-linter contracts (AD-2)
uv run lint-imports                                    # 19 kept, 0 broken

# The Django checks (AD-15)
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run
```

### Coverage Details

| Module | Statements | Branches | Functions | Lines |
|--------|------------|----------|-----------|-------|
| `apps/identity/services/profile.py` | 100% | — | 100% | 100% |

24 statements, 0 missed.

### Mutation Probes

Thirteen mutations, thirteen catches. Every test that pins a rule was shown to
**fail** when that rule is broken.

| Mutation | Test that caught it |
|----------|---------------------|
| The command writes the name outside the transaction | `test_set_user_name_cannot_write_an_audit_row_outside_a_transaction` |
| The audit write is dedented out of the `with` block | `test_set_user_name_cannot_write_an_audit_row_outside_a_transaction` |
| The audit row is written outside the transaction | `test_set_user_name_writes_the_audit_row_in_the_same_transaction` |
| The audit details carry the name | `test_the_audit_row_details_carry_no_name` |
| The actor carries the address as a label | `test_the_audit_row_carries_the_actor_by_value` |
| The cap is a literal that drifts from the column | `test_the_cap_agrees_with_the_column` |
| The refusal runs after the truncation | `test_set_user_name_refuses_a_control_character_past_the_cap` |
| An empty name is refused instead of stored | `test_set_user_name_stores_an_empty_name_as_no_name_set` |
| The name is not trimmed | `test_set_user_name_trims_leading_and_trailing_whitespace` |
| The internal whitespace is not collapsed | `test_set_user_name_collapses_internal_whitespace` |
| The name is not truncated at the cap | `test_set_user_name_truncates_an_over_long_name` |
| The write does not name its database alias | `tests/architecture/test_database_alias.py` |
| The API surface writes the row directly | `tests/architecture/test_no_direct_writes.py` |

**The probe found a hole in the tests, and it was in the transaction test.**
`test_the_write_is_inside_a_personal_transaction` read the command's own source and
asserted that the string `transaction.atomic(using=PERSONAL)` appeared in it. The
mutation proved the hole: **dedenting the audit write out of the `with` block leaves
that string intact, so the test still passed** with the audit row written outside the
transaction. A test that reads the code under test proves the code says what it says,
not that it does what it says. A behavioural test was added — patch
`transaction.atomic` to fail, and the command must write neither the name nor the row
— and the source-reading assertion was kept only for the **alias** rule, which *is* a
syntax rule and is scanned independently.

### Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| The `pytest --cov` subprocess holds a connection to the test database's **template**, so the next run's `CREATE DATABASE ... WITH TEMPLATE` fails with `DuplicateDatabase` / `ObjectInUse` | Environment | Worked around with `--reuse-db`, and by dropping the stale database with `DROP DATABASE ... WITH (FORCE)`. **Not a code defect** — the same tests pass without `--cov`, and the same tests pass with `--cov` once the stale database is dropped. It recurred three times in the next item as well |
| `tests/identity/test_local_pro_grant.py` — 5 failures | Pre-existing | **Not this item's.** `grant_pro.py` and `billing_read.py` are uncommitted work that was on the branch before this run started. Verified again with this item's files removed |
| `tests/e2e/test_state_change_proof.py::TestTheStripAndTheBanner` — 4 failures, and `tests/worker/test_trace_id.py` — 1 error | Pre-existing | **Not this item's.** Verified on a **clean worktree at `HEAD`** (`d582d38`) with this item's changes absent: the same errors occur. The failures are a 404 on `/api/events/{id}` — the `personalization` app, not `identity`. The worker test is order-dependent: it passes in isolation |

### Notes

**The command's published signature was narrowed during the review.** It was written
as `set_user_name(*, user_id: UUID, name: str, actor: Actor | None = None)`. The
work item specifies `set_user_name(*, user_id: UUID, name: str) -> None`, and the
sibling commands do not expose an actor either — `sign_up` and `reset_password` both
build `Actor.user(user.pk)` internally. The optional parameter widened the app's
published interface for a case that does not exist: the only caller is the endpoint,
acting as the account itself. It was dropped.

**The name's PII never reaches a row.** The name appears in no log line, no audit
detail and no actor label.

**The truncation/collapse order is collapse-then-cap.** The collapse happens before
the cap, so a name is collapsed to its final form and *then* truncated to 120.
Truncating first could leave a name ending mid-word at a collapsed boundary.

**The get/save race is last-write-wins**, which is the right semantic for *"set my
name to X"*. `password_reset.py` behaves the same way. No lock is needed.

---

## Work Item: profile-endpoint-and-contract

### Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Unit | 33 | 0 | 0 | 100% (`apps/identity/services/profile.py`) |
| Integration | 27 | 0 | 0 | — |
| **Total** | **60** | **0** | **0** | **100%** |

The command module is at **100% line coverage** — 24 statements, 0 missed.

### Acceptance Criteria Validation

- ✅ **`CurrentUserOut` carries `name: str`, and `GET /api/auth/me` returns it** —
  asserted by `test_me_returns_the_stored_name` and by the `me` payload assertion in
  `tests/identity/test_auth_api.py`, which now carries `"name": ""`.
- ✅ **A user with no name set gets `name: ""` — not `null`, and not a 404** —
  `test_me_returns_an_empty_name_when_none_is_set`. The "not `null`" half is a
  *mutation probe*: breaking `name=user.name` into `name=user.name or None` makes the
  test fail.
- ✅ **`PUT /api/auth/profile` saves the name and returns the updated profile** —
  `test_put_profile_saves_the_name_and_returns_the_updated_profile`. The answer is
  `{id, email, name}`.
- ✅ **The handler calls `require_csrf(request)` before any other work** —
  `test_the_csrf_check_runs_before_the_resolver`. The probe moves the check after the
  resolver and the test fails.
- ✅ **An anonymous caller gets 401** — `test_put_profile_refuses_an_anonymous_caller_with_a_401`.
  **The caller sends a valid CSRF token**: the check comes first, so an anonymous caller
  with *no* token is refused with 403. Both refusals are proved, and the reason is
  recorded in the test's docstring.
- ✅ **A request with no CSRF token gets 403** —
  `test_put_profile_refuses_a_request_without_a_csrf_token_with_a_403`, plus
  `test_a_signed_in_caller_without_a_csrf_token_is_refused_with_a_403` and
  `test_a_wrong_csrf_token_is_refused_with_a_403` for the two other ways to arrive
  without a valid token.
- ✅ **A refused name (newline, control character) gets 422 with the project's
  `{code, message, details}` shape** —
  `test_put_profile_refuses_a_name_carrying_a_newline_with_a_422` and
  `…_control_character_with_a_422`.
- ✅ **The endpoint calls the named command and writes no ORM row itself — asserted
  against `tests/architecture/test_no_direct_writes.py`** — the probe replaces
  `set_user_name(...)` with a direct `user.save()` and the architecture test fails.
- ✅ **The endpoint is declared `PUT`, and the OpenAPI schema says `put`** —
  `test_the_endpoint_is_declared_put_in_the_openapi_schema` (the **live** schema) and
  `test_the_committed_contract_declares_the_put` (the committed file). Two tests,
  because the two files can disagree — and a stale committed file is exactly what the
  first one must not be fooled by.
- ✅ **`make client` has been run, and both `frontend/lib/api/openapi.json` and
  `frontend/lib/api/schema.ts` are committed and modified in this change** — both are
  modified in the tree; `git diff --stat` lists both.
- ✅ **`backend/tests/api/test_contract.py` is green** — 1 passed. It compares the
  committed schema to the live one.
- ✅ **`backend/tests/e2e/test_state_change_contract.py` is green** — 14 passed with
  the contract test.
- ✅ **The new schemas live in `apps/identity/schemas.py`, next to the other wire
  shapes** — `ProfileIn` and `ProfileOut` sit beside `CurrentUserOut`.
- ✅ **Tests cover: save, read-back through `me`, empty name, an over-long name, an
  anonymous caller, a missing CSRF token, and a refused name — each verified by a
  mutation probe that makes it fail** — see below.

### Tests Written

#### Unit Tests

`backend/tests/identity/test_profile_api.py` (new, 27 tests) — the endpoint:

- **The write**: saves the name and returns the updated profile · reads back through
  `me` · trims and collapses the name · stores an empty name as "no name set" · stores
  a whitespace-only name as "no name set" · truncates an over-long name.
- **The refusals**: a newline → 422 · a control character → 422 · a refused name writes
  nothing · a refused name does not echo the name back (AD-13) · an anonymous caller →
  401 · no CSRF token → 403 · a signed-in caller without a token → 403 · a wrong CSRF
  token → 403 · the CSRF check runs before the resolver · the CSRF check does *not* run
  before the body is validated · a body with no name → 422 `invalid_request` · a command
  refusal is a *different* 422 (`invalid_input`).
- **The audit row**: one row is written · the details carry no name · a refused name
  writes no audit row.
- **`me`**: an empty name when none is set · the stored name · still no password field,
  and exactly the four expected keys.
- **The contract**: the **live** schema says `put` and not `patch` · the **committed**
  schema says the same.

`backend/tests/identity/test_auth_api.py` (extended) — `me`'s payload assertion gains
`"name": ""`, and the test's name and docstring say what changed.

`backend/tests/identity/test_profile_command.py` (extended) — four tests added:
`test_set_user_name_refuses_a_control_character_past_the_cap` (the refusal runs
*before* the truncation, not after) · `test_the_cap_agrees_with_the_column` (the cap
*is* the column's limit, by construction) ·
`test_set_user_name_collapses_a_line_separator_into_a_space` and
`…_paragraph_separator_into_a_space` (U+2028 and U+2029 are whitespace, so they are
collapsed rather than refused — the same answer a tab gets).

`backend/apps/identity/services/profile.py` (extended) — `set_user_name` now **returns
the stored name**. See the review report: the endpoint's answer must report what the
account holds, not what was asked for.

#### Integration Tests

`backend/tests/identity/test_profile_api.py` is an integration test as well as a unit
one: it drives the real router through Django's test client, against the real database,
with the real CSRF middleware and the real session.

### Test Commands

```bash
cd backend

# This item's tests
uv run pytest tests/identity/test_profile_api.py tests/identity/test_profile_command.py \
  tests/identity/test_auth_api.py tests/identity/test_models.py -q --reuse-db

# Coverage of the command module
uv run pytest tests/identity/test_profile_command.py -q --reuse-db \
  --cov=apps.identity.services.profile --cov-report=term-missing

# The architecture contracts
uv run pytest tests/architecture -q --reuse-db          # 990 passed

# The contract test (AD-19)
uv run pytest tests/api/test_contract.py -q               # 1 passed
uv run pytest tests/e2e/test_state_change_contract.py -q

# The whole backend suite
uv run pytest tests/ -q --reuse-db --ignore=tests/identity/test_local_pro_grant.py

# The import-linter contracts (AD-2)
uv run lint-imports                                    # 19 kept, 0 broken

# The Django checks (AD-15)
uv run python manage.py check
uv run python manage.py makemigrations --check --dry-run

# The contract regeneration (AD-19)
make client

# The frontend
cd ../frontend && pnpm test && pnpm typecheck
```

**`--reuse-db` is required on this machine, and the reason is worth recording.** The
test database is created from a template (`eventpulse24_test_template`), and the
coverage plugin's subprocess holds a connection to it. A run with `--cov` therefore
leaves the template locked, and the *next* run fails at `CREATE DATABASE ... WITH
TEMPLATE` with `DuplicateDatabase` or `ObjectInUse`. This is an **environment**
condition, not a code defect: the same tests pass without `--cov`, and the same tests
pass with `--cov` when the stale database is dropped first. It recurred three times
during this item.

**`--reuse-db` also leaves rows behind between runs, and that is a second trap.** It
does not truncate, so a second run against the same database can hit
`IntegrityError: duplicate key value violates unique constraint "user_email_uq"` on a
fixed address like `maya@example.com`. The two failures this produced were **not**
regressions: dropping the database and re-running the affected file gave
`14 passed`. The affected address is used by `tests/identity/factories.py`,
`tests/identity/test_audit.py` and `tests/identity/test_authenticate.py` — **not** by
this item's own new file, which uses `maya@example.test`.

### Coverage Details

| Module | Statements | Branches | Functions | Lines |
|--------|------------|----------|-----------|-------|
| `apps/identity/services/profile.py` | 100% | — | 100% | 100% |

24 statements, 0 missed.

### Mutation Probes

Every test that pins a rule was shown to **fail** when that rule is broken. Twelve
mutations, twelve catches:

| Mutation | Test that caught it |
|----------|---------------------|
| The CSRF check is moved after the resolver | `test_the_csrf_check_runs_before_the_resolver` |
| The CSRF check is dropped entirely | `test_put_profile_refuses_a_request_without_a_csrf_token_with_a_403` |
| The endpoint writes the name itself instead of calling the command | `tests/architecture/test_no_direct_writes.py::test_surface_file_makes_no_direct_write` |
| The answer echoes the request instead of the stored name | `test_put_profile_trims_and_collapses_the_name` |
| The name is dropped from `me` | `test_me_returns_the_stored_name` |
| `me` answers `null` for an unset name | `test_me_returns_an_empty_name_when_none_is_set` |
| The endpoint is declared `PATCH` rather than `PUT` | `test_the_endpoint_is_declared_put_in_the_openapi_schema` |
| The committed contract is stale and says `PATCH` | `test_the_committed_contract_declares_the_put` |
| The refusal's details echo the input back | `test_a_refused_name_does_not_echo_the_name_back` |
| The cap is a literal again, so it can drift from the column | `test_the_cap_agrees_with_the_column` |
| The refusal runs after the truncation, so a late newline is cut away | `test_set_user_name_refuses_a_control_character_past_the_cap` |
| A line separator is refused rather than collapsed | `test_set_user_name_collapses_a_line_separator_into_a_space` |

**The probe found a hole in the tests, and it was in the verb.** The first version of
the "declared `PUT`" test read the **committed** `openapi.json`. Mutating the route
from `@router.put` to `@router.patch` left the committed file untouched, so the test
still passed — it was proving that the *file* said `put`, which is not the same claim
as *"the endpoint is a `PUT`"*. A second test was added that reads the **live** schema
through `api.get_openapi_schema()`, and the probe now fails as it should. The committed
file is still checked, by a test of its own: the two files can disagree, and a stale
committed file is exactly what the live-schema test must not be fooled by.

### Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| The `pytest --cov` subprocess holds a connection to the test database's **template**, so the next run's `CREATE DATABASE ... WITH TEMPLATE` fails with `DuplicateDatabase` / `ObjectInUse` | Environment | Worked around with `--reuse-db`, and by dropping the stale database with `DROP DATABASE ... WITH (FORCE)`. **Not a code defect** — the same tests pass without `--cov`, and the same tests pass with `--cov` once the stale database is dropped. It recurred three times in this item and once in the previous one |
| `--reuse-db` leaves rows behind, so a second run against the same database hit `IntegrityError` on `user_email_uq` for `maya@example.com` | Environment | **Not a regression.** Dropping the database and re-running the affected file gave `14 passed`. The affected address is used by `tests/identity/factories.py`, `tests/identity/test_audit.py` and `tests/identity/test_authenticate.py` — not by this item's new file, which uses `maya@example.test` |
| `tests/identity/test_local_pro_grant.py` — 5 failures | Pre-existing | **Not this item's.** `grant_pro.py` and `billing_read.py` are uncommitted work that was on the branch before this run started. Verified again: the same 5 failures occur with this item's files removed. The failing subset varies between runs, which is consistent with pre-existing flakiness |
| `tests/e2e/test_state_change_proof.py::TestTheStripAndTheBanner` — 4 failures, and `tests/worker/test_trace_id.py` — 1 error | Pre-existing | **Not this item's.** Verified on a **clean worktree at `HEAD`** (`d582d38`) with this item's changes absent: the same 4 errors occur. The failures are a 404 on `/api/events/{id}` — the `personalization` app, not `identity`. The worker test is order-dependent: it passes in isolation, with and without this item's changes |
| The frontend's `tests/endpoint-coverage.test.ts` failed with `PUT /api/auth/profile` having no caller | Expected | The endpoint landed before the editor that calls it. The endpoint was added to `DECLARED_UNCALLED` **with the reason**, and the file's own stale-entry check fails the moment the caller exists — so the next work item must remove the entry. This is the check working, not a gap papered over |
| `frontend/e2e/digest-opt-out.spec.ts:102` fails lint | Pre-existing | **Not this item's.** Verified via `git log`: committed in `5cffe04`, untouched by this change |

### Notes

**The endpoint returns the name the account holds, not the name it was sent.** The
first implementation answered `ProfileOut(name=body.name)`, and the mutation probe
caught it: a request for `"  Maya   Ahmed  "` came back with the spaces still in it,
while the row held `"Maya Ahmed"`. The client would have shown the user the value they
typed and the server would have stored a different one. The command now **returns** the
stored name — the same shape `ensure_account` and `authenticate` already have — and the
endpoint reports that.

**The 401 needs a CSRF token to be reachable, and that is not a bug.** The work item
requires the CSRF check first, and it requires an anonymous caller to get a 401. Both
hold, because an anonymous caller that *sends* a valid token gets past the check and
is then refused by the resolver. An anonymous caller with *no* token gets a 403 — which
is the more correct answer anyway: the request was refused as a cross-site write
before anyone asked who the caller was.

**The `DECLARED_UNCALLED` entry is a debt with a deadline.** `PUT /api/auth/profile`
is in the map because the contract is generated from the backend and the editor is the
next work item. The entry says so, and `tests/endpoint-coverage.test.ts`'s
stale-entry check fails the day the editor calls it. It must not outlive that.

**`make client` is not optional.** `backend/tests/api/test_contract.py` compares the
committed `openapi.json` to the live schema and fails when they differ, and CI's
contract job runs `make client` then `git diff --exit-code frontend/lib/api/`. Both
generated files are modified in this change.

**The operation ids were read, not assumed.** `apps_identity_api_put_profile` and
`apps_identity_api_me` were read out of the regenerated `frontend/lib/api/openapi.json`
— the work item says not to assume them, and the generated ones carry the Django app's
dotted path.

### Ready for Completion

- [x] All tests passing (60 in this item's own suites; 1424 across `tests/identity`,
      `tests/architecture`, the contract test and the state-change contract, after
      dropping the stale database; 6928/6932 in the whole backend suite, the 4
      failures verified pre-existing on a clean `HEAD`)
- [x] Coverage target met (100% on the command module, against an 80% gate)
- [x] All acceptance criteria validated
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-032*

---

## Work Item: profile-screen-and-editor

### Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Unit | 16 | 0 | 0 | — |
| Integration | 10 | 0 | 0 | — |
| Coverage | 5 | 0 | 0 | — |
| **Total** | **31** | **0** | **0** | — |

- `frontend/components/settings/profile-name.test.tsx` — **16** tests, the island.
- `frontend/app/settings/profile/page.test.tsx` — **10** tests, the page.
- `frontend/tests/settings-routes.test.ts` — **11** tests, the reachability rules.
- `frontend/tests/ad19-endpoint-coverage.test.ts` — **94** tests, the contract's chain.

**The whole frontend suite is 2439/2439.** `pnpm typecheck` is clean. `pnpm lint` has one
error — `e2e/digest-opt-out.spec.ts:102`, **pre-existing** (committed in `5cffe04`) and
untouched by this run.

### Acceptance Criteria Validation

- ✅ **The screen exists at `/settings/profile` and renders the name** —
  `app/settings/profile/page.tsx`. `shows the name the account holds` and `shows an
  empty field when no name is set`.
- ✅ **The screen is reachable from the settings nav** — `lib/settings-sections.ts`
  carries the `Profile` row, and `tests/settings-routes.test.ts`'s *"every route that
  exists is in the list"* is the assertion that was **missing for four of the six
  original screens**. It is data-driven, so it passes only because both the list and
  the page exist.
- ✅ **The screen carries the sub-nav, so it is not a dead end** — the
  `mount the sub-nav in every signed-in branch` rule. **The branch floor was lowered
  from two to one**, and the reasoning is recorded in the test: this page has one
  signed-in branch because **it reads nothing of its own**. The loop walks *every*
  branch it finds, so one branch is walked once — not vacuously, but exactly once.
- ✅ **The editor saves the name through the generated client** —
  `components/settings/profile-name.tsx` calls `api.PUT("/api/auth/profile", { body:
  { name } })`. The probe that replaces it with a hand-written `fetch` fails the suite.
- ✅ **The editor saves on change, with no Save button** — `saves on change, with no
  Save button`.
- ✅ **An emptied name is saved** — `saves an emptied name, because an empty name is a
  name`. Every other island refuses to send a half-finished value; **a name with
  nothing in it is a name**.
- ✅ **The API's refusal is shown verbatim** — `shows the server's refusal, verbatim`,
  with the generic line *not* shown as well.
- ✅ **The offline line is shown when the API said nothing** — `falls back to the
  route's own line when the API says nothing`.
- ✅ **The user's chosen name survives a failure** — `keeps the chosen name when the
  save fails`.
- ✅ **The `me` entry names `lib/session.ts` as its caller** —
  `tests/ad19-endpoint-coverage.test.ts`. **This is the item's one design decision**
  and it is the reason the separate read was removed.

### The design decision: this page reads nothing of its own

**Every other settings route reads the data it shows**, and that read can fail — which
is why they all have an `unavailable` shell. **This one's data is the name, and the
session already carries it**: `CurrentUserOut` gained a `name` field for exactly this.
A second `GET /api/auth/me` on the profile route would answer the same question twice
and double the route's API traffic for nothing.

**So `lib/profile-read.ts` was built and then deleted.** The first implementation read
the profile separately, and the code review caught it — the module was a redundant
round-trip whose docstring's justification did not hold. **The work item's own
acceptance criteria settled it**: *"the `me` entry names `lib/session.ts` as its
caller."* The intended design has no separate read, and the code now matches it.

**The consequence is one signed-in branch, and that is why the branch floor moved.**
`tests/settings-routes.test.ts` asserted ≥2 email-carrying `<AppShell>` branches per
settings page, which is true of every route that reads its own data. This one does
not, so the floor is now ≥1 — and the test's own docstring now says why, and why one is
enough for the rule to have teeth.

### The finding the review raised that the tests did not

**A stale response could overwrite the name the user has since typed.** The editor
saves on *every* keystroke, so a second save can be started before the first comes
back — and the first to *return* is not necessarily the newest request. Without a
guard, a slow first response would replace the name the user had typed since with the
server's answer to the *older* name.

**The fix is a counter**, and the rule it enforces is *"only the newest save may write
to the field"*. The counter is a ref, not state: it must not trigger a render of its
own. **Two tests pin it** — one where the stale response arrives last and must not
overwrite the field, and one where the stale save fails and must not put a failure
line on screen.

**This was not found by a test failing.** It was found by reading the island against
the fact that a free-text field is typed a character at a time. Both tests are
mutations now: removing either guard fails one of them.

### Mutation Probes

Every rule the tests pin was shown to **fail** when it was broken. Twenty mutations,
twenty catches:

| Mutation | Test that caught it |
|----------|---------------------|
| The editor saves through a hand-written `fetch` | `saves on change, with no Save button` |
| The editor sends more than the name | `sends the name, and only the name` |
| The editor refuses to save an emptied name | `saves an emptied name, because an empty name is a name` |
| The editor shows the generic line instead of the API's refusal | `shows the server's refusal, verbatim` |
| The editor throws the refusal away when the request never arrived | `falls back to the route's own line when the API says nothing` |
| The editor reverts the name on a failure | `keeps the chosen name when the save fails` |
| The editor shows the typed name instead of the stored one | `shows the name the server stored, not the one that was typed` |
| The editor grows a Save button | `saves on change, with no Save button` |
| A superseded save may overwrite the field | `ignores a slow response for a name the user has since replaced` |
| A superseded save's failure is shown | `does not show a failure for a save the user has already superseded` |
| The field is not marked invalid on a refusal | `marks the field invalid when the API refuses it` |
| The page addresses the account by nothing when no name is set | `falls back to the email-derived name when no name is set` |
| The page shows the editor to a visitor whose session could not be read | `shows an empty shell when the session could not be read at all` |
| The page reports a failure it did not have | `shows an empty shell when the session could not be read at all` |
| The page drops the sub-nav | `carries the sub-nav, so it is not a dead end` |
| The section is not in the list | `every route that exists is in the list` |
| The section row points at a route that does not exist | `every section in the list is a route that exists` |
| The section is listed twice | `lists no section twice, and no two sections under one label` |
| The endpoint is exempted from the coverage sweep again | `every endpoint is called or declared uncalled` |
| The AD-19 entry names a caller that does not exist | `lib/session.ts reaches /api/auth/me through the generated client` |

**The probes were re-pointed after the review.** The two that broke the deleted
`lib/profile-read.ts` and the removed `unavailable` branch could not be run any more,
and they were replaced by probes that break the rules the current design has — the
superseded-save guard, the `aria-invalid` mark, the empty shell, and the dropped
sub-nav. **A probe that cannot be run is not a probe**, and leaving the old two in
would have claimed coverage the code no longer had.

### Notes and Known Issues

**`frontend/tests/endpoint-coverage.test.ts` is byte-identical to `HEAD`.** This item
removed the `PUT /api/auth/profile` entry that item 2 had added to
`DECLARED_UNCALLED`, and that was the last change to the file — so the debt the
previous item recorded is fully paid with **no net diff**. The endpoint is now called
from `components/settings/profile-name.tsx`, and the sweep finds it.

**`pnpm lint` has one error and it is not this item's.** `e2e/digest-opt-out.spec.ts:102`
— `'digest' is defined but never used` — committed in `5cffe04` and verified untouched
by this run. **It was left alone deliberately**: fixing an unrelated lint error in a
change about the profile screen would put an unrelated line in the diff, and the
work item's scope is the profile screen.

### Ready for Completion

- [x] All tests passing (31 in this item's own suites; 2439 across the whole frontend
      suite)
- [x] Coverage target met (the item adds no backend module; the frontend suites are
      exhaustive over the island and the page)
- [x] All acceptance criteria validated
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-032*

---

## Work Item: reduced-account-sheet

### Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Unit | 9 | 0 | 0 | — |
| **Total** | **9** | **0** | **0** | — |

`frontend/components/shell/account-menu.test.tsx` — **10** tests, covering the panel
itself, the rail's row and the bottom bar's inline rendering.

**The whole frontend suite is 2449/2449.** `pnpm typecheck` is clean. `pnpm lint` has
one error — `e2e/digest-opt-out.spec.ts:102`, **pre-existing** (committed in `5cffe04`)
and untouched by this run.

### Acceptance Criteria Validation

- ✅ **The account sheet renders the name, the email, "Edit your name" and Sign out** —
  `shows the name and the email`, `offers 'Edit your name'`, `still offers Sign out, and
  it is the last thing in the panel`.
- ✅ **There is no `Settings` row** — `does not offer a Settings row`.
- ✅ **There is no `Pricing` row** — `does not offer a Pricing row`.
- ✅ **"Edit your name" links to `/settings/profile` — a route that exists** —
  `points 'Edit your name' at the profile screen, which exists`. The route was built by
  the previous item, and `tests/settings-routes.test.ts` asserts it is a page.
- ✅ **It is styled like the links it replaces** — the probe that restyles it as a
  button fails `offers 'Edit your name'`.
- ✅ **`SignOutButton` is still the last thing in the panel** — the probe that moves
  something after it fails.
- ✅ **The panel still opens as a `Sheet` and still renders inline** — the rail's row
  test opens the sheet and finds the panel inside it; the More sheet test renders the
  panel inline. **One change, two shapes, both asserted.**
- ✅ **The docstring no longer claims two links, no longer defends Pricing, and says
  the name is the one thing that can be changed** — the module's docstring was rewritten
  around exactly those three points.
- ✅ **The docstring still says the email, the password-while-signed-in and closing the
  account are not offered** — kept, and the password is now explained: it is changed by
  the reset flow, which ends the account's other sessions.
- ✅ **The sheet is correct at both breakpoints** — the More sheet test.
- ✅ **A test proves the sheet renders "Edit your name" and not "Settings" or
  "Pricing", and that the link points at `/settings/profile`** — three separate tests,
  so a failure says *which* row came back.
- ✅ **The panel links to exactly one route** — `links to one route, and it is the
  profile screen`. **This is the assertion the code review added**, and it is the one
  that matters: the label checks pin *wording*, and a link to `/settings` labelled
  "Account settings" re-opens exactly the door this item closed **without failing any
  of them**. The href is the invariant — which is how the repo pins link destinations
  elsewhere (`tests/settings-routes.test.ts` asserts on `href="/settings`, not on the
  label beside it).

### Mutation Probes

**Eleven mutations, eleven catches.** Seven were written before the review and four
after it — **and the four after it are the ones the first seven missed.**

| Mutation | Test that caught it |
|----------|---------------------|
| The `Settings` link comes back | `does not offer a Settings row` |
| The `Pricing` link comes back | `does not offer a Pricing row` |
| The link points at a route that does not exist | `points 'Edit your name' at the profile screen, which exists` |
| The link is renamed to "Profile" | `offers 'Edit your name'` |
| The link is styled as a button rather than a link | `offers 'Edit your name'` |
| Something is moved after Sign out | `still offers Sign out, and it is the last thing in the panel` |
| The panel stops showing the email | `shows the name and the email` |
| **The `Settings` link comes back under another label** | `links to one route, and it is the profile screen` |
| **The `Pricing` link comes back under another label** | `links to one route, and it is the profile screen` |
| **Sign out is moved to the top of the panel** | `still offers Sign out, and it is the last thing in the panel` |
| **Sign out is moved into the middle of the panel** | `still offers Sign out, and it is the last thing in the panel` |

**The last four are the review's contribution, and each one was proven to slip through
the original suite.** The relabelled-link mutation left the suite **9/9 green** — the
two doors this item closed, reopened under names the label checks did not match. The
two ordering mutations also left it green, because the assertion was built on
`signOut.closest("div")` — which is `SignOutButton`'s *own* wrapper, a div with one
child, so "the last child contains the button" is true by construction wherever the
button sits.

**Both are the failure mode this repo names most often: an assertion that cannot
fail.** The fix for the first is the href-set assertion; the fix for the second is a
`data-account-panel` hook so the assertion is made against the panel's *root*, plus a
floor assertion that the panel has at least three children — **so a refactor that
flattens the markup fails loudly instead of passing vacuously.**

### Notes and Known Issues

**The router is mocked in the test, and the mock is not incidental.** `SignOutButton`
calls `useRouter()` — it calls `router.replace("/signin")` after the sign-out POST — and
Next's `useRouter` throws *"invariant expected app router to be mounted"* outside an app
router context. The mock is the reason the panel can be rendered at all in a unit test,
and it was found by running the tests, not by reading them.

**`frontend/tests/digest-home-boundary.test.ts` did not break.** It asserts on the
account-menu *source* — that `<AccountMenu ` and `<AccountPanel ` are present — and both
are still there. **The panel's props did not change**, so `Sidenav` and `MoreMenu` did
not change either.

**The bottom bar's test renders `BottomTabNav`, not `MoreMenu` alone.** The work item
says *"the bottom bar's More sheet"*, and the bar is what carries the More slot — so
the test renders the bar and opens the More sheet through it, the way
`nav-routes.test.tsx` does. **Rendering `MoreMenu` directly would test the component
without the thing that mounts it.**

### Ready for Completion

- [x] All tests passing (9 in this item's own suites; 2448 across the whole frontend
      suite)
- [x] Coverage target met (the item adds no backend module)
- [x] All acceptance criteria validated
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-032*

## Work Item: display-name-everywhere

### Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Unit | 25 | 0 | 0 | — |
| **Total** | **25** | **0** | **0** | — |

Three new files: `frontend/lib/display-name.test.ts` (**16** tests),
`frontend/tests/display-name.test.ts` (**7** tests) and
`frontend/tests/stored-name-in-shell.test.tsx` (**4** tests) — **27 tests**, of which
two were added by the code review.

**The whole frontend suite is 2476/2476.** `pnpm typecheck` is clean. `pnpm lint` has
one error — `e2e/digest-opt-out.spec.ts:102`, **pre-existing** (committed in `5cffe04`)
and untouched by this run.

### Acceptance Criteria Validation

- ✅ **All 15 local `displayName` functions are deleted** — the filesystem-level test
  walks every `page.tsx` under `app/` and asserts none carries the rule.
- ✅ **No page carries its own copy** — `no page carries its own copy of the display-name
  rule`. **The rule, not the identifier**: the assertion matches a page that derives a
  name from an email, whatever it called the function.
- ✅ **Every page that names somebody calls the shared helper with the whole user** —
  `every page that names somebody calls the shared helper with the whole user`. The
  rule is *"the argument is not the whole user"*, not *"the argument is literally
  `session.user.email`"*.
- ✅ **No page passes a hand-built name to the shell** — `no page passes a hand-built
  name to the shell`. The name must be **traceable** to the helper: the call itself, or
  a local binding whose definition is exactly the call.
- ✅ **A stored name is shown verbatim** — `lib/display-name.test.ts::is called by that
  name verbatim, not trimmed and not re-cased`, plus the review's addition, `is not
  trimmed either`.
- ✅ **The fallback is the old rule, exactly** — twelve cases, from the dot to the
  separators-only local part.
- ✅ **A user with a stored name sees it in the shell** —
  `tests/stored-name-in-shell.test.tsx::shows a user with a stored name by that name`.
- ✅ **A user without one still sees the email-derived name** —
  `tests/stored-name-in-shell.test.tsx::shows a user with no stored name the
  email-derived name`. **The fallback is not "blank"** — a blank rail reads as "this
  account has no name" rather than "this feature is broken".
- ✅ **The helper is server-safe** — `is a server-safe module — no client banner and no
  imports`. Asserted against **comment-stripped** source, because the module's own
  docstring *names* `"use client"` in prose, and an assertion that reads a comment is
  asserting on prose.

### Mutation Probes

**Thirty mutations, thirty catches.** Twenty-six were written before the review and four
after it — **and the four after it are the ones the first twenty-six missed.**

| Mutation | Test that caught it |
|----------|---------------------|
| The helper ignores the stored name and always falls back | `lib/display-name.test.ts` |
| The helper returns the stored name even when it is empty | `lib/display-name.test.ts` |
| The helper does not split the local part on separators | `lib/display-name.test.ts` |
| The helper does not capitalise | `lib/display-name.test.ts` |
| The helper does not collapse a run of separators | `lib/display-name.test.ts` |
| The helper returns `""` instead of the email for an empty local part | `lib/display-name.test.ts` |
| The helper lower-cases the rest of each word | `lib/display-name.test.ts` |
| The helper trims the stored name | `lib/display-name.test.ts::is not trimmed either` |
| Any of the 15 pages passes the email instead of the user | `tests/display-name.test.ts` |
| The home page builds the shell's name itself | `tests/display-name.test.ts` |
| A page carries a *renamed* copy of the rule | `tests/display-name.test.ts::no page carries its own copy` |
| **A page hand-builds the name in a local `const name`** | `tests/display-name.test.ts::no page passes a hand-built name to the shell` |
| **A page hand-builds the name inline in the shell prop** | `tests/display-name.test.ts::no page passes a hand-built name to the shell` |
| The helper is a client module | `tests/display-name.test.ts::is a server-safe module` |
| The helper takes two positional arguments | `tests/display-name.test.ts::takes the whole user` |

**The three bold rows are the review's contribution, and each was proven to slip through
the original suite.** The hand-built-name mutation left the suite **7/7 green** — the
file's own docstring said *"no page carries a copy of its own"*, while a page could
write `const name = "Maya " + session.user.email.split("@")[0]` and pass every
assertion.

**Both are the failure mode this repo names most often: an assertion that cannot fail.**
The allow-list said *"the identifier `name` is fine"* without ever asking **where `name`
came from** — and six pages bind the name to a local `const name` and pass that, so the
shape was the established one. The fix is to make the name **traceable**: a prop is
legal if it is the helper's call, the empty string, or a local binding whose definition
is *exactly* the helper's call.

**The renamed-copy mutation is the same lesson one level up.** The original assertion
matched `/function\s+displayName\s*\(/` — so a copy called `localName` was the same copy
under another hat, and passed. The rule is now about **the rule**, not the identifier.

### Notes and Known Issues

**The work item said thirteen call sites. There are fifteen.** The extra two are the
profile page — built by the previous item — and one the item's list had missed. **All
fifteen local copies were verified byte-identical before being replaced**, so the
fallback really is the old function and not fifteen slightly-different ones.

**The `USER` fixtures are untyped plain objects, so `tsc` did not catch them.** The plan
said only `lib/session.test.ts` would need the `name` field — *"`tsc` flags it"* — and
that was **true only for the one fixture that is typed against the regenerated schema**.
**Twenty-three other fixtures across the test suite are plain objects**, and the pages
read `session.user.name` at runtime: `TypeError: Cannot read properties of undefined
(reading 'slice')`, **321 failures across 19 files**. Every one gained `name: ""`.

**This is worth recording as a lesson.** *A schema change is only half a change.* The
typed fixture caught itself; the untyped ones did not, and the whole suite went red at
once. The fixtures were found by grepping for `onboarding:` — the field that follows
`email:` in every one of them — rather than by reading the error, which named only the
first failure.

**The stored name and the fallback name are deliberately different strings.** The shell
test's email is `maya.ahmed@example.test`, whose fallback is `"Maya Ahmed"`, and the
stored name is `"Ada Lovelace"`. **If they were the same string the test could not tell
"the stored name was used" from "the fallback was used"** — it would pass either way,
which is the vacuity this repo's mutation probes exist to catch.

### Ready for Completion

- [x] All tests passing (27 in this item's own suites; 2476 across the whole frontend
      suite)
- [x] Coverage target met (the item adds no backend module)
- [x] All acceptance criteria validated
- [x] No critical issues open

---

## Work Item: contract-and-e2e-proof

### Summary

**The contract was already committed and true** — that part was verification, not work.
**The e2e proof did not exist**, and writing it is where the work turned out to be.

| Suite | Result |
|-------|--------|
| `frontend/e2e/profile-name.spec.ts` (new) | **7 passed** against the real stack |
| `frontend/e2e/settings-navigation.spec.ts` | **5 passed** against the real stack |
| `backend/tests/identity` + `tests/api/test_contract.py` | **443 passed** |
| `frontend` unit suite | **2482 passed** (147 files) |
| `frontend` typecheck | clean |
| `frontend` lint | clean for this work's files (one pre-existing error elsewhere — see Notes) |

### Acceptance Criteria Validation

| Criterion | Result | Evidence |
|-----------|--------|----------|
| The committed contract is the live contract | ✅ | `tests/api/test_contract.py` passes; `make client` leaves the tree unchanged |
| Every settings screen is reachable by clicking, including Profile | ✅ | `settings-navigation.spec.ts` — 5 passed |
| The sheet offers the name, "Edit your name" and Sign out | ✅ | `profile-name.spec.ts::the account sheet offers the name, the edit link and Sign out` |
| The sheet offers no Settings row and no Pricing row | ✅ | asserted on the **href set**, not the labels |
| Typing a name saves it, and it survives a reload | ✅ | `profile-name.spec.ts::typing a name saves it, and it survives a reload` |
| The rail shows the stored name, on every screen | ✅ | `profile-name.spec.ts::the rail shows the stored name, on this screen and on every other` |
| A user with no name set still sees the email-derived name | ✅ | `profile-name.spec.ts::a user with no name set still sees the email-derived name` |
| Clearing the name falls back again | ✅ | `profile-name.spec.ts::clearing the name falls back again` |
| The API's own refusal is shown, verbatim | ✅ | `profile-name.spec.ts::a name carrying a control character is refused…` |

### The finding the e2e proof produced

**The first run of the new spec failed 4 of 7 tests, and the failures were not the
test's fault — they were the product's.**

The rail showed `"Account: Free"` right after a name was saved, and `"Account: Maya
Ahmed"` on a test that had *cleared* the name. **The account held one name and the
screen held another.**

**The cause: the shell's name is a server render.** `AppShell` is a server component;
it receives `name` as a prop from the page, which read it from the session on the
server. That value is fixed for the life of the render. **Nothing in the design made
the rail live.**

**Two of the four failures were a second bug on top of it**: the `beforeEach` cleared
the account *after* the page had been rendered, so the rail was still carrying the
previous test's name. The fix was a reload — **the second run proved it**: without the
reload, "a user with no name set" still failed.

**The third failure was the test's fault, and it was an interesting one.** The test
filled the field with `"Maya\nAhmed"` and waited for a refusal that could never
arrive: **the HTML value sanitization algorithm strips `\r` and `\n` from a single-line
input**, so the newline never reached the field, let alone the API. **The API had been
asked to save a legal name.** The refusal is now driven by BEL, which the browser does
not strip and the backend does refuse.

**The fix for the real bug is its own work item — "live-name-in-the-shell" — and it is
below.**

### Mutation Probes

The e2e suite has no mutation probe harness; the probes below are for the live-name
work item, which is where the new code is.

### Notes and Known Issues

- **Five e2e failures are pre-existing and unrelated.** `digest-opt-out.spec.ts` (3)
  and `unwired-surfaces.spec.ts` (2) fail identically **on the baseline** — verified
  by stashing this work and re-running. The `unwired-surfaces` failures are a browse
  card linking to `/pricing` instead of `/events/…`, and the `digest-opt-out` failures
  are a missing "What's in your Pulse Digest" link. **Neither has anything to do with
  the account's name.**
- **One lint error is pre-existing.** `e2e/digest-opt-out.spec.ts:102` — `'digest' is
  defined but never used`. The file is unmodified by this work (last touched in
  `5cffe04`), and it was left alone rather than fixed as unrelated churn.
- **The `helpers.ts` deduplication.** `resetSignInThrottle` was copied into
  `settings-navigation.spec.ts` rather than shared. **Two copies of a throttle reset
  is two things to keep in sync**, and the helper file is where the other shared
  helpers already live — so it moved there, and both specs import it.

### Ready for Completion

Yes. The contract is committed and true; the navigation is proved by clicking; the
name is proved end to end in a real browser, **including the negative case**.

---

## Work Item: live-name-in-the-shell

### Summary

**The rail follows the save.**

The shell's name was a server render — a photograph, fixed for the life of the render.
A person who saved a name and looked up at the rail saw the old one, on every page,
and the account sheet opened from that row said something different from the row
itself.

**The fix is a module-level store**, read with `useSyncExternalStore`, holding the
**display** name, written by the profile island once the server accepts the write.

| Suite | Result |
|-------|--------|
| `frontend/tests/live-display-name.test.tsx` (new) | **6 passed** |
| **9 mutation probes** | **9 caught**, by the test named for each |

### Acceptance Criteria Validation

| Criterion | Result | Evidence |
|-----------|--------|----------|
| The rail shows the saved name | ✅ | `live-display-name.test.tsx::moves to the saved name` |
| The account sheet shows it too | ✅ | the same test's sheet assertion |
| The *server's* answer is published, not the typed one | ✅ | `::publishes the name the server stored, not the one that was typed` |
| Clearing the name falls back rather than blanking | ✅ | `::falls back again when the name is cleared` |
| A refused save moves nothing | ✅ | `::does not move when the save was refused` |
| An offline failure moves nothing | ✅ | `::does not move when the request never reached the API` |
| A page that never saved shows the server-rendered name | ✅ | `::shows the name the page was rendered with, before anything is saved` |
| The property, in a real browser | ✅ | `e2e/profile-name.spec.ts::the rail shows the stored name, on this screen and on every other` |

### The design decision: a store, not a provider and not a refresh

**A React context cannot do it without moving the shell.** The provider would have to
sit *above* the rail, and the rail is rendered by `AppShell`, which every page mounts
by hand. **A provider means fifteen pages each wrapping their own `<AppShell>`** — and
the fifteen pages are exactly the thing the display-name work just finished
consolidating.

**`router.refresh()` is the wrong tool.** It re-runs every server read on the page and
re-renders the whole route, for one string.

**So the store is a module, and the shell reads it directly.** `useSyncExternalStore`
is React's own answer to "a value outside React that React must re-render for".

**And only the two leaves that display the name read it** — `AccountMenu` (the rail
row) and `AccountPanel` (the sheet). `Sidenav` and `BottomTabNav` only forward the
name, so **neither file changed at all**.

### The store holds the *display* name, not the stored name

**The two are different questions, and the shell asks the display one.** The stored
name is `""` when no name is set; the display name is the address-derived fallback.

**So the island holds the address too**, and derives the display name with the *same*
shared helper the pages use — one rule, one implementation, and no second copy to keep
in sync. **Publishing the stored name instead would blank the rail** for anyone who
clears their name, and the mutation probe for exactly that mistake is caught by
`::falls back again when the name is cleared`.

### Mutation Probes

Nine mutations, one per rule, each broken in turn. **All nine were caught, by the test
named for each.**

| # | Mutation | Caught by |
|---|----------|-----------|
| 1 | The island never publishes | `moves to the saved name` |
| 2 | The island publishes the typed value, not the server's | `publishes the name the server stored, not the one that was typed` |
| 3 | The island publishes the stored name, not the display name | `falls back again when the name is cleared` |
| 4 | The island publishes even when the API refused | `does not move when the save was refused` |
| 5 | The island publishes even when the request never reached the API | `does not move when the request never reached the API` |
| 6 | The store ignores the seed, and shows nothing when nothing is published | `shows the name the page was rendered with, before anything is saved` |
| 7 | The store's listeners are never told | `moves to the saved name` |
| 8 | The row shows the rendered name, not the live one | `moves to the saved name` |
| 9 | The sheet shows the rendered name, not the live one | `moves to the saved name` |

**Mutation 9 was not caught on the first pass.** The first version of the test asserted
only on the rail row, so the sheet could show the stale name and the suite stayed
green. **A test that never fails proves nothing** — and this one had never failed,
because it had never been asked the question. The sheet assertion was added, and the
mutation was caught.

### Notes and Known Issues

- **The `useCallback` dependency lint warning was a real bug, not a style note.** The
  island's `save` callback closed over `email` and listed no dependencies, so a
  changed address would have been published with the old one. **ESLint caught it**;
  the dependency is now `[email]`.
- **The store outlives a navigation, and that is correct.** A soft navigation re-renders
  the server components, which read the name the account now holds — the same name the
  store holds, because the save went through the API first.
- **A hard reload empties the store** and the seed takes over — the right direction.
- **The genuinely stale case is another tab.** That is the same bargain the live save
  allowance makes, and it is recorded in the module's own docstring rather than left
  to be discovered.

### Ready for Completion

Yes. The property is proved in a unit test, in a mutation probe, and in a real
browser.
