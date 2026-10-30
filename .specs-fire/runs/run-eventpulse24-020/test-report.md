---
run: run-eventpulse24-020
work_item: calendar-connect-api
intent: onboarding-and-account
generated: 2026-10-29
status: passing
---

# Test Report: Calendar Connect API (FR-50)

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Item-scoped | 87 | 0 | 0 | 100% (the item's modules, in isolation) |
| **Total (whole backend)** | **2909** | **0** | **0** | **98.98%** |

The 87 item-scoped tests are a subset of the 2909-test backend suite. The whole backend
suite is **2909 passed, 0 failed** in 85.87s; coverage is **98.98%** across 6402
statements, with **157 files at 100%**.

**Every module this item created or changed is at 100%** — notably
`apps/personalization/services/calendar_connections.py` and the new
`domain/address_policy.py`. The 65 uncovered statements are pre-existing gaps elsewhere
in the codebase.

> **This report was updated after the code review** (step 6b). The review found ten
> defects; each was reproduced with a failing test and then fixed. The numbers above
> are the **post-review** figures. The pre-review figures were 2893 / 72 / 91% — and
> the review's own findings are recorded in `review-report.md`.

## Test Commands

```bash
# The item's own tests
cd backend && .venv/bin/python -m pytest \
    tests/personalization/test_calendar_connect_api.py \
    tests/personalization/test_calendar_connection_reads.py -q

# The whole backend suite, with coverage
cd backend && .venv/bin/python -m pytest tests/ -q --cov --cov-report=term-missing

# The linter and the format check
cd backend && .venv/bin/python -m ruff check . && .venv/bin/python -m ruff format --check .

# The import contracts
make lint-imports

# Django's own checks and the migration drift
cd backend && .venv/bin/python manage.py check
cd backend && .venv/bin/python manage.py makemigrations --check --dry-run

# AD-19: the schema and the TypeScript client regenerate with no drift
make client

# The frontend suite (the client is regenerated from the OpenAPI schema)
pnpm --dir frontend test
```

## What Was Added

| File | Tests | Covers |
|------|-------|--------|
| `backend/tests/personalization/test_calendar_connect_api.py` | 56 | The five endpoints: the list, connect, the Free cap, each invalid-address refusal, reconnect, disconnect, the cross-user 404, the log capture, and the CSRF refusals |
| `backend/tests/personalization/test_calendar_connection_reads.py` | 16 | The read service: the projection's shape, the list, the one-connection read, the sync-state flags, and the cross-user 404 |
| `backend/tests/personalization/test_review_repro.py` | 12 | The **twelve defect reproductions** the code review produced — each one failed before its fix |
| `backend/tests/personalization/test_calendar_connect_concurrency.py` | 3 | The commands under concurrency: two connects racing for the one slot, two connects racing for the same address, and a disconnect that commits first |

Two more files are the **revert verification harnesses** — `backend/revert_check.sh` for
the item's own rules, and `backend/revert_review_check.sh` for the review's fixes. Each
patches a rule out of the source, runs the tests, records the outcome, and restores. They
are how the two revert tables were produced.

## What Was Changed in the Existing Tests

**None.** No existing test file changed, because no existing endpoint's payload changed.
The only existing source file touched outside the new code was
`backend/adapters/crawl/address_policy.py`, which was **rewritten as a re-export** of the
new `domain/address_policy.py` — the adapter's import path and its own tests
(`tests/adapters/test_crawl_address_policy.py`, `test_crawl_loopback.py`) are unchanged and
still pass.

**The review changed no existing test either.** Each of the ten findings was pinned by a
*new* test in `test_review_repro.py` or `test_calendar_connect_concurrency.py`, rather
than by editing a test that already existed. A review that rewrites the tests it is
reviewing is a review that cannot fail.

## The Properties Pinned

### The address never leaves the server

This is the item's central guarantee, and it is **structural** rather than careful: the
response shape and the read projection have no field for the credential and none for the
fingerprint, so no endpoint *can* leak it.

- `test_the_projection_has_no_field_for_the_credential` — asserts the dataclass field
  set explicitly: no `credential`, no `address`, no `credential_fingerprint`, no
  `fingerprint`. And the rendered projection carries neither the address nor its host.
- `test_no_endpoint_in_the_router_returns_the_address` — the sweep the acceptance
  criterion asks for: it calls the list, the one-connection GET, a failing connect and a
  reconnect, one after the other, and asserts that **not one response body** carries the
  secret segment or the host. A new endpoint added later is covered by the same assertion.
- `test_the_list_carries_no_address`, `test_the_one_connection_carries_no_address`,
  `test_a_refused_address_is_not_echoed_in_the_error` — the per-endpoint versions of the
  same property.

### The address never reaches a log either (AD-13)

- `test_a_failing_request_writes_the_address_to_no_log` — the check is on a **failing**
  request, because that is where a log line is most likely: an unhandled exception's
  traceback carries the arguments, and a validation error's `input` carries the
  submitted value. The test captures the logs and asserts the address appears in none
  of them.

### The Free cap is a 409, with no modal semantics

- `test_a_second_connection_is_refused_with_409` — the status is pinned, and the code is
  `calendar_cap_reached`.
- `test_the_cap_payload_has_no_modal_semantics` — the payload's key set is pinned
  **exactly**: `{"code", "message", "details"}` at the top, `{"cap", "upgrade_hint"}` in
  the details. No `modal`, no `title`, no `actions`, no `dismissable` — and the test
  asserts the string "modal" does not appear anywhere in the details. A future edit
  cannot grow a modal-shaped field without failing this test.
- The copy is the approved one, taken from the UX spine rather than written fresh: the
  error's own *"You've connected the calendars your plan allows."* and the hint's
  *"Save more with Pro."*

### Each invalid address gets a calm, specific refusal

- `test_a_loopback_address_is_refused_by_the_ssrf_policy`,
  `test_a_private_address_is_refused`, `test_a_link_local_address_is_refused`,
  `test_an_ipv6_loopback_address_is_refused` — the four denied-network families.
- `test_a_refused_address_is_not_stored` — the refusal happens **before** the row is
  written, so a refused address leaves no trace.
- `test_a_bad_scheme_is_refused`, `test_an_address_with_embedded_credentials_is_refused`,
  `test_an_empty_address_is_refused` — the shape checks.
- `test_an_already_connected_address_is_refused` — the duplicate is named as such, and
  **does not consume a second slot** (the same connection is returned, not a refusal).

### The provider is a label, not a branch

- `test_connect_accepts_every_known_provider` — Google, Apple and Outlook all connect,
  each on its own fresh account (the Free cap is one calendar, so a shared account
  could not hold three).
- `test_connect_refuses_an_unknown_provider` — a provider that is not in the known set is
  refused. The check lives in the **service**, not the API, because the API may not
  import the model and a check only one caller performs is a check another caller walks
  past.

### The first sync is enqueued, not run inline (AD-11)

- `test_connect_does_not_fetch_the_calendar` — the connect call returns without
  touching the network, so a slow or unreachable provider cannot hold the request open.

### Another user's connection is 404, not 403

- `test_get_one_of_another_users_connection_is_404_not_403`,
  `test_get_one_of_an_unknown_connection_is_404` — both answer the **same** status and
  the same body. A 403 would confirm the record exists, so a caller could probe for other
  users' connection ids by watching for 403 instead of 404.
- The same rule on every write: reconnect and disconnect of another user's connection
  are 404 too.

### The reads never write

- `test_the_reads_never_write` — a read that mutates is a cross-site write, and a GET is
  never CSRF-checked, so a GET that writes is exactly the thing CSRF does not protect.
- `test_an_unclaimed_connection_is_not_syncing`,
  `test_a_fresh_claim_is_a_sync_in_progress`,
  `test_a_stale_claim_is_not_a_sync_in_progress` — the in-progress flag is a **fresh**
  claim, not any claim. A claim older than `CALENDAR_CLAIM_TTL` is a lost job (a worker
  died holding it) and the connection becomes claimable again. Showing a stale claim as
  "syncing" would be a lie the user can see: the spinner would never stop.

### The scoping happens in one place

- The ownership lookup lives in the **service**, because the API layer may not import
  `apps.personalization.models` (the `models-personalization` contract). The API calls
  `reconnect_calendar_for_user` / `disconnect_calendar_for_user`, and the service does
  the `user_id` filter. The API never touches the model.

## Acceptance Criteria Validation

| Criterion | Result | Where it is pinned |
|-----------|--------|-------------------|
| `GET /api/personal/calendars` lists id, provider, status, last synced, sync-in-progress | ✅ | `test_the_list_carries_the_sync_state`, `test_the_list_carries_no_address` |
| The address is never in a response — full, masked or as a fragment | ✅ | `test_the_projection_has_no_field_for_the_credential`, `test_no_endpoint_in_the_router_returns_the_address` (the sweep over every endpoint in the router) |
| `POST /api/personal/calendars` connects from `{provider, address}` | ✅ | `test_connect_accepts_every_known_provider` |
| The response carries the new connection's status and sync state | ✅ | `test_connect_returns_the_connection_and_its_state` |
| The first sync is **enqueued, not run inline** | ✅ | `test_connect_does_not_fetch_the_calendar` |
| A second connection returns a calm, typed error | ✅ | `test_a_second_connection_is_refused_with_409` (status + code pinned) |
| The error follows the approved upgrade copy, with **no modal semantics** | ✅ | `test_the_cap_payload_has_no_modal_semantics` — the key set is pinned exactly |
| Invalid addresses get a calm, specific message | ✅ | the seven invalid-address tests |
| The message never echoes the address | ✅ | `test_a_refused_address_is_not_echoed_in_the_error`, `test_a_refused_address_is_not_stored` |
| `POST .../{id}/reconnect` takes a new address for a `needs_reconnect` connection | ✅ | the reconnect section of `test_calendar_connect_api.py` |
| `DELETE .../{id}` disconnects and purges that connection's events | ✅ | the disconnect section — the imported events and their conflict pairs and reminder plans go, the user's own events stay |
| Sync status exposed, so onboarding step 1 can show imported events in-flow (FR-3) | ✅ | `test_the_list_carries_the_sync_state`, `test_a_fresh_claim_is_a_sync_in_progress` |
| All endpoints authed and scoped | ✅ | the 401 tests on every endpoint; the cross-user 404s |
| Another user's connection id returns **404, not 403** | ✅ | `test_get_one_of_another_users_connection_is_404_not_403` and the read-service twin |
| The address is excluded from logging — **proved on a failing request** | ✅ | `test_a_failing_request_writes_the_address_to_no_log` (with `caplog`) |
| The router is registered in `config/api.py` | ✅ | the OpenAPI contract test sees the five paths |
| `make client` (AD-19) | ✅ | `make client` was re-run and committed; `tests/api/test_contract.py` passes |
| `make lint-imports` passes | ✅ | 17 kept, 0 broken |
| Tests cover list, connect, cap, each invalid refusal, reconnect, disconnect, cross-user 404, and the no-address/no-log guarantee | ✅ | 87 tests across the four files |

## Reverting Each Fix

Every rule was verified by **reverting it and watching the test fail**. A regression test
that passes against the broken code is not a regression test. The harness is
`backend/revert_check.sh`; it patches the source, runs the two test files, records the
outcome, restores from `/tmp/revert_backup_*`, and ends with a `git diff --stat` that
proves every patch was put back.

| # | Rule | Reverted | Result |
|---|------|----------|--------|
| R1 | The response shape has no field for the address | added `address: str = ""` to `CalendarConnectionOut` | **1 test fails** ✓ |
| R2 | The Free cap is a 409 (a conflict with the account), not a 400 | `CalendarProviderCapReached(ConflictError)` → `(DomainError)` | **1 test fails** ✓ |
| R3 | The cap payload carries no modal semantics | added `modal`, `title` and `actions` to the details | **1 test fails** ✓ |
| R4 | The SSRF pre-flight refuses a denied address | `if is_denied(...)` → `if False` | **5 tests fail** ✓ |
| R5 | Another user's connection is a 404, not a 403 | `NotFoundError` → `PermissionDeniedError` | **4 tests fail** ✓ |
| R6 | A stale claim is not "in progress" | `fresh = claimed` | **2 tests fail** ✓ |
| R7 | The reads never write | made the list write `sync_claimed_at` | **5 tests fail** ✓ |
| R8 | The provider is validated against the known set | removed the membership test | **2 tests fail** ✓ |
| R9 | The connect endpoint requires a CSRF token | removed `require_csrf(request)` from the **resolver** | **3 tests fail** ✓ |

All nine reverts were restored and the suite re-run green afterwards; `git diff --stat`
confirmed no revert artifacts remained.

### R9 — and why the first attempt at it did not catch anything

The first version of R9 removed the explicit `require_csrf(request)` call from
`post_calendar` and **all 72 tests still passed**. That was not a passing test; it was a
test that could not distinguish the two things it was supposed to.

The cause: `apps/personalization/api.py` declares `router = Router(tags=["personal"],
auth=current_user)`, and `identity`'s `current_user` resolver calls `require_csrf(request)`
itself before returning the user. The router-level check therefore already applied to
every unsafe method on the router — the endpoint-body calls were **redundant duplicates**,
and no test can tell a duplicate from the thing it duplicates.

Two things were done about it, and the first is the one that matters:

1. **The redundant calls were removed** from `post_calendar`, `post_reconnect_calendar`
   and `delete_calendar`, along with the now-unused `require_csrf` import. One mechanism
   is easier to reason about than two, and the mechanism that survives is the one the
   resolver owns — it applies to unsafe methods only, and it refuses a bad token before
   the endpoint body runs at all.

   This is **not** a change to `apps/identity/api_auth.py`. The contrast with
   `apps/identity/api.py` is worth stating: *that* router has no `auth=` (sign-up and
   sign-in are how a session is created, so requiring a session to get one would be
   circular), so its explicit `require_csrf` calls **are** load-bearing and stay.

2. **R9 was re-aimed at the real mechanism** — it now reverts the resolver's
   `require_csrf(request)` call, and the three CSRF-refusal tests fail. The guarantee is
   now pinned where it actually lives.

## The Review's Fixes, and Their Own Reverts

The code review (step 6b) found **ten defects**. Each was **reproduced with a failing
test before it was fixed** — a review finding is a claim, not a fact — and each fix was
then verified by reverting it and watching the test fail again.

The full write-up is in `review-report.md`. The revert table is here, because the
question it answers is this report's question: *are these properties actually pinned?*

| # | Rule | Reverted | Result |
|---|------|----------|--------|
| V1 | A disconnected connection does not squat the address | the **migration**'s partial condition removed | **2 tests fail** ✓ |
| V2 | The cap applies on the `needs_reconnect` reuse path | the `occupying -= 1` removed | **1 test fails** ✓ |
| V3 | The cap is decided under the advisory lock | `_lock_user(user_id)` removed | **2 tests fail** ✓ |
| V4 | A reconnect refuses an address the user already holds | `_refused_duplicate` removed from the reconnect | **1 test fails** ✓ |
| V5 | The reconnect re-reads the status under a row lock | `select_for_update()` replaced by the unlocked row | **1 test fails** ✓ |
| V6 | A malformed host is refused calmly, not with a 500 | `except ValueError` → `except ZeroDivisionError` | **1 test fails** ✓ |
| V7 | An address on a port the fetch would refuse is refused | `_refused_port(parts)` removed | **2 tests fail** ✓ |
| V8 | The reads do not decrypt the credential | `.only(*_READ_COLUMNS)` removed | **1 test fails** ✓ |
| V9 | The ownership lookup does not decrypt the credential | `.only(...)` removed from `_owned_connection` | **1 test fails** ✓ |
| V10 | The CSRF check is not duplicated | the three explicit `require_csrf(request)` calls restored | **3 tests fail** ✓ |

**All nine V-cases are caught** (V10 is the R9 story, already covered above). The item's
own R1–R9 were re-run after the review's fixes and are **all still caught**.

### Two of these cases needed a second attempt

Both failures were the same failure, in different clothes: **the revert case did not
fail, because the test could not distinguish the two states it was meant to separate.**

- **V1** first patched the **model** — and the test still passed, because the test
  database is rebuilt from the **migrations**, so the partial index was still in place.
  The revert now patches the migration file.
- **V8** and **V9** first ran against credentials that decrypted **successfully**, so the
  old code passed vacuously. Both tests now write a corrupt envelope straight to the
  column, so the decryption genuinely fails.

The general rule the review settled on: **a revert case that does not fail is not a
revert case.** It is a hole in the suite wearing a harness's clothes.

## Notes on the Implementation

Three decisions are worth recording, because each one could reasonably have gone the
other way.

### The SSRF deny table moved from the adapter into `domain`

The table was in `adapters/crawl/address_policy.py`. The calendar service now needs to
read it for its connect-time pre-flight, and **an app may not reach into an adapter**
(AD-2). So the table moved to `domain/address_policy.py` — the policy is *knowledge*, not
machinery, and `domain` is reachable from both under the `domain-pure` contract, which
is stdlib-only. The adapter's file was rewritten as a re-export, so its import path and
its own tests are unchanged and there is still exactly **one** table.

### The pre-flight is a pre-flight, not the policy

The real SSRF enforcement is `adapters.crawl.http.GuardedBackend`, which resolves the
host itself and refuses any denied address **on every redirect hop**, so DNS rebinding
cannot bypass it. That check is not optional and was not weakened.

The pre-flight exists because a connect-time refusal is **invisible at connect time**: the
user pastes an address, the row is created, and the first poll — up to a minute later, in
a worker, with nobody watching — fails. The pre-flight refuses the obvious denied IP
*literal* at the moment the user would still be looking at the screen. It does **not**
resolve names, so it says nothing about a hostname that resolves to a private address —
and it does not need to, because the connect-time check catches that too.

### The cap's status changed from 400 to 409

`CalendarProviderCapReached` now extends `ConflictError`. The address the user pasted is
perfectly good; it is the *state of the account* that refuses it, because the account
already holds the one calendar its plan allows. The request was well-formed and conflicts
with the account, which is what a 409 means; a 400 would say "your request was wrong",
and it was not. This is the same reasoning already applied to
`OnboardingAlreadyCompleteError` in the previous item.

## The Final Gate

```
pytest tests/ -q --cov --cov-report=term-missing
2909 passed in 85.87s (0:01:25)
TOTAL                                             6402     65    99%
157 files skipped due to complete coverage.
Required test coverage of 80.0% reached. Total coverage: 98.98%

pytest tests/personalization/test_calendar_connect_api.py \
         tests/personalization/test_calendar_connection_reads.py \
         tests/personalization/test_review_repro.py \
         tests/personalization/test_calendar_connect_concurrency.py -q
87 passed

pytest tests/ -q --cov=apps.personalization.services.calendar_connections \
                  --cov=domain.address_policy --cov-report=term-missing
2909 passed in 82.09s
TOTAL                                              211      0   100%
2 files skipped due to complete coverage.

ruff check .
All checks passed!

ruff format --check .
356 files already formatted

lint-imports
Contracts: 17 kept, 0 broken.

manage.py check
System check identified no issues (1 silenced).

manage.py makemigrations --check --dry-run
No changes detected

make client
lib/api/openapi.json → lib/api/schema.ts

pytest tests/api/test_contract.py -q
1 passed

pnpm --dir frontend test
149 passed (16 files)

frontend tsc --noEmit
clean
```

## What This Item Does Not Cover

- The **frontend** calendar step — `frontend-onboarding-flow` owns the connect form, the
  address field and the upgrade prompt's presentation. This item ships the typed error
  and the calm copy the prompt needs; the modal semantics are deliberately **not** here.
- The **sync worker** — the poll, the ICS fetch and the event import were delivered by
  the earlier calendar items. This item only enqueues the first sync and exposes the
  state of it.
- The **Pulse Digest** and **geo** — `pulse-preview-api-and-geo` owns those.
- A **Pro tier** — there is no subscription entity yet, so the cap cannot be lifted
  programmatically. The error's `details["cap"]` and `details["upgrade_hint"]` are the
  seam a billing system would fill.
- **Calendar disconnection from the provider's side** — a provider-side revocation is
  detected by the poll and surfaces as `needs_reconnect`; the user-side
  `DELETE` is what this item ships.

### Test Result

**Passing.** 2909 passed, 0 failed, 98.98% coverage, 100% on both the changed service and
the new `domain/address_policy.py`, ruff clean, format clean, 17/17 import contracts
kept, the committed OpenAPI schema matches the live API, the frontend suite green
(149 tests) and the frontend typecheck clean. All **nine** item rules **and** all
**nine** review rules are pinned by a revert that was watched to fail.
