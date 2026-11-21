---
run: run-eventpulse24-057
work_item: city-provisioning-service
intent: city-picker-and-auto-collection
generated: 2026-11-21
status: complete
---

# Code Review: The city provisioning service

## Files Reviewed

| File | Change |
|------|--------|
| `backend/apps/ingestion/services/city_provisioning.py` | NEW — `provision_city`, `provision_city_on_commit`, `ProvisioningOutcome` |
| `backend/apps/ingestion/models.py` | MODIFIED — `CityProvisioning` added after `City` |
| `backend/apps/ingestion/migrations/0015_cityprovisioning.py` | NEW — `CreateModel` |
| `backend/apps/personalization/services/digest_preferences.py` | MODIFIED — the trigger, in `set_home_city` |
| `backend/tests/ingestion/test_city_provisioning.py` | NEW — 235 tests, whole-dataset |
| `backend/tests/ingestion/test_models.py` | MODIFIED — three model enumerations |
| `backend/tests/wall/test_schema_placement.py` | MODIFIED — the catalog table set |
| `backend/tests/architecture/test_write_ownership.py` | MODIFIED — `TABLE_OWNERS` |
| `backend/tests/personalization/test_digest_recompose_triggers.py` | MODIFIED — the callback assertion |

## Project Tooling

| Tool | Result |
|------|--------|
| `ruff check` | All checks passed |
| `ruff format --check` | Clean (only the pre-existing `tests/shared/test_retention_published.py` drift; the repo root was not formatted) |
| `lint-imports` | 21 contracts kept, 0 broken |
| `pytest` (full) | **8905 passed, 0 failed** (8664 at item 6) |
| Coverage | `city_provisioning.py` **100%**; `domain/` 100%; overall 97.45% |
| `makemigrations --check` | No changes detected |

## Findings

### 1. [Correctness] A city with no provider was recorded with no reason — FIXED

**File**: `apps/ingestion/services/city_provisioning.py`, `_provision_choice`

The `no_providers` branch read `error_code=skipped[0] if skipped else ""`. For a city no
enabled template covers, `resolve()` returns an **empty tuple** — so `_registerable` had
nothing to skip, `skipped` was empty, and the row was written with a **blank reason**.

So the surface would have been told "this city has no providers" and not why. Two facts
were being collapsed into one:

- **No template serves this city.** A fact about the *city*: no provider covers
  Bangladesh, and the fix is a new template.
- **The templates that do serve it need a credential we have not been given.** A fact
  about *this installation*: the provider serves the city, and we have not been given a
  key. The fix is a secret.

An operator needs to tell those apart, and only one of them is a code change. The service
now records `NO_TEMPLATE_COVERS_THIS_CITY` for the first and `no_credential:<SETTING>` for
the second, and `test_a_city_no_template_covers_says_so` holds the distinction.

**Found by the test that asserted the reason was non-empty** — the assertion was written
because "says why" is the requirement, and the blank string is what it caught.

**Risk**: none now. The status is unchanged; only the reason was blank.

### 2. [Correctness] The foreign key cascaded, and the guard was right — FIXED

**File**: `apps/ingestion/models.py`, `CityProvisioning.city`

`test_every_ingestion_foreign_key_is_protect` failed: the model was written with
`on_delete=models.CASCADE` where the guard demands `PROTECT`.

**The guard is right and the model's reasoning was wrong.** The reasoning was "a `City` is
never deleted anyway, so the rule is academic" — and that is true *today*, because
`Venue` and `EventFit` both `PROTECT` it. But a cascading delete means a city could one
day lose its provisioning record **without anybody deciding to**, and that record is the
sentence the surface reads about a city. The model now uses `PROTECT`, and the docstring
says why in terms of the decision rather than the accident.

**Risk**: none. `City` is already protected from every path that could delete it.

### 3. [Design] The service took a `country_code` the caller could get wrong — FIXED

**File**: `apps/ingestion/services/city_provisioning.py`, `provision_city`

The first draft took `country_code` as a parameter, on the reasoning that the catalog row
already carries it and the caller has it too. **That reasoning was the bug**: a country
supplied from the caller is a **second source of truth**, and a country that disagrees
with the catalog row mints a **second `City` for the same place** — the exact split
`domain.cities` exists to prevent, and it would happen silently.

The parameter is gone. The service reads the country from the catalog row it has already
resolved, and the trigger passes only the name. **One source of truth, and it is the
catalog.**

This also makes the service callable from the places the plan named — a management
command, a retry — all of which hold a city *string*.

**Risk**: none. The country was already read from the catalog row; the parameter was
never used for anything else.

### 4. [Correctness] A `TypeError` in the idempotent branch — FIXED

**File**: `apps/ingestion/services/city_provisioning.py`, `_provision_choice`

The idempotency branch built `ProvisioningOutcome(..., last_error_code=existing.last_error_code)`,
but the dataclass's field is `error_code`. Every second pick raised a `TypeError` — so
"provisioning is idempotent" was not true at all; the second pick **crashed**.

Found by the second of the eight idempotency tests, on the first run.

**Risk**: none now. It is fixed and the mutation check confirms it: removing the
idempotency check fails 8 tests.

### 5. [Testing] Two mutations survived the first round — FIXED

**File**: `tests/ingestion/test_city_provisioning.py`

The mutation check is the run's rule: **a test must be able to fail.** Two mutations
survived the first pass, and both were gaps in the test file rather than in the service.

- **The parser filter.** `_registerable` refuses a spec whose method has no parser, but
  no test covered one — every enabled template's method has a parser, so removing the
  check changed nothing observable. Fixed by `TestASpecWithNoParserIsSkipped`, which
  patches the provider registry to emit a `crawl` spec: the method `parse()` refuses.
- **The advisory lock.** The tests patched `_lock_city` (the *wrapper*), so removing the
  SQL *inside* it was invisible — the wrapper was still called, and the order assertions
  still held. Fixed by `test_the_lock_is_actually_taken`, which watches the
  `pg_advisory_xact_lock` query go out on the wire, and `test_the_lock_key_is_the_citys_own`,
  which watches the key that goes with it.

**Risk**: none now. All 15 mutations are caught.

### 6. [Testing] The rollback assertions would have passed for the wrong reason — FIXED

**File**: `tests/ingestion/test_city_provisioning.py`, `TestTheAfterCommitSeam`

`pytest`'s `django_db` fixture wraps every test in a transaction that is rolled back, so
Django's `on_commit` callbacks **never fire on their own**. The first version of "the
provisioning runs after the commit" asserted the callback had run — and it had not, and
the assertion would have failed for a reason that had nothing to do with the service.

The fix has two halves, and the distinction matters:

- The repo's existing `on_commit` fixture (`test_digest_enqueue.py`'s pattern) — capture
  the callbacks and run them on demand — for the "did it run" assertions.
- **Django's own `django_capture_on_commit_callbacks`** for the **rollback** assertions,
  because Django's capture *discards* a rolled-back transaction's callbacks. A hand-run
  list would have run them anyway, and the test would have passed for the wrong reason
  again.

**Risk**: none now. The rollback tests now exercise Django's real semantics.

### 7. [Testing] A blind `pytest.raises(Exception)` — FIXED

**File**: `tests/ingestion/test_city_provisioning.py`

`B017` flagged the frozen-dataclass test. It now asserts `FrozenInstanceError`
specifically, which is what a frozen dataclass actually raises — a blind `Exception` would
have passed against any failure at all, including a `TypeError` from a typo in the test.

## Deliberately Not Changed

- **`register_source`'s audit row keeps the source's city.** The AD-13 rule this item
  settled is: *this item's* provisioning audit row carries the city id and never the city
  name. `register_source`'s own row keeps the source's city, because **a source's city is
  a public fact about a place** while a person's city is weak location data about a real
  person. That is the distinction the codebase already draws (`register_venue` writes
  `{"fields": fields}`; `_write_city_audit` writes `{"has_city": bool}`), and changing
  `register_source` is FR-13's contract, not this item's to change.
- **No retry.** The `CityProvisioning` row's existence means "provisioned", whatever its
  status says. A reader's pick is not a retry request — they did not know anything failed,
  and a retry would be invisible to them. A retry belongs to a person or to the scheduler
  (item 8's probation job).
- **No `live` status from provisioning.** The city has no events until the scheduler has
  run and a source has answered, so `collecting` is the honest word. `live` is written by
  the ingest path, and `yielded_nothing` and `paused` by the probation job (item 8).
- **The `Source` rows are not deleted or paused by this service.** A registered source
  with `last_attempted_at IS NULL` is due immediately, so the existing scheduler takes it
  on its next 60-second tick. **Provisioning's whole job is to make sure the source
  exists by then** — it fetches nothing.
- **No `City` row is minted for a city the catalog does not hold.** The stored preference
  still says whatever the reader picked; it is simply not provisioned. Minting a `City`
  would put a place into the registry that no reader chose.
- **The template stays pure.** `domain.city_providers` describes what a provider *is*; this
  module describes what *this installation* can use. The template never asks for a key —
  `domain` cannot read `settings` — and the split is what lets the registry stay
  stdlib-only.

## Security

- **The API key never enters the registry, the database or the audit log.** A spec whose
  host needs a key this deployment has not been given is **skipped**, not registered — a
  Ticketmaster source without a key would be picked up by the scheduler within a minute,
  fail with a 401, and burn a slot in the reliability score for a source that was never
  going to work. The decision is driven by `provider_keys.PROVIDER_KEYS`, so there is
  **one** table of "hosts that need a key" and not a second list here.
- **The host is exact, never a suffix.** The same rule the parser and the key injector
  use, for the same reason: `app.ticketmaster.com.evil.test` must never be handed our
  key, and must never be *assumed* to need one.
  `test_a_host_that_only_ends_with_a_providers_host_needs_no_key` holds it.
- **The city's name never reaches the audit log or the logger.** The provisioning's audit
  row carries `city_id` and the status, never the name — AD-13's discipline, and the log
  sink is exactly the place a person's weak location data must not reach.
  `test_the_audit_row_carries_the_city_id_and_not_the_city_name` asserts `"Portland"` is
  nowhere in the details, and `_provision_quietly`'s warning carries no city name either.
- **The stored URL carries no key.** The key is added at fetch time by `provider_keys`,
  and `test_the_registered_url_never_carries_the_key` asserts the secret is not in the
  stored URL.

## Architecture

**AD-16 is respected by construction.** `ingestion` owns `SOURCE` and `CITY`, and this
module is inside `ingestion`, so it writes them. `personalization` reaches it through
`apps.ingestion.services.city_provisioning` — a published service — and never through
`apps.ingestion.models`. AD-3's `models-ingestion` contract is what proves that, and
`lint-imports` keeps it: **21 contracts kept, 0 broken**.

**The trigger imports the service lazily, inside the function.** `set_home_city` is on the
hot path of every reader's save, and the import is inside `_provision_city_on_commit` so
the module-level import graph of `personalization` does not gain an `ingestion` edge. (The
repo already imports `apps.ingestion.services.*` in sixteen places, so this is a matter of
keeping the *module-level* graph as it was, not of avoiding the dependency.)

**AD-11 holds.** The request handler validates, writes, and returns. The provisioning is
not in the handler — it is an `on_commit` callback, which is the same seam
`enqueue_digest_composition_on_commit` uses and the same shape AD-11's "validate, enqueue,
return" describes.

**The lock's key space is its own.** `_LOCK_PERSON = b"eventpulse24-cty"`, separate from
`digest_preferences`' `b"eventpulse24-onb"`. Both lock on a UUID, and a hash of one must
never be mistaken for a hash of the other — the two would then serialise against each
other for no reason, and a bug in one would look like a bug in the other.

**The lock is an advisory lock, and transaction-scoped.** A row lock can only lock a row
that exists, and the interesting case is precisely the one where it does not: a city
nobody has provisioned yet. Two concurrent provisioners would both find nothing to lock
and both register sources — and the loser would get a raw `IntegrityError` from the unique
constraint, which reaches the caller as a 500. `pg_advisory_xact_lock` is released at
commit, so a crashed worker cannot leave a city wedged.

**The model carries the guards the schema can hold.** `OneToOneField` on the city is the
idempotency guarantee *in the database*: a second provisioning of the same city cannot
create a second row, so "provisioning is idempotent" is a fact the schema holds rather
than a promise the service makes. A check constraint holds `status` non-empty.

## Summary

| | Count |
|---|---|
| Fixed | 7 (a blank reason on `no_providers`; a cascading FK the guard caught; a `country_code` parameter that could mint a second `City`; a `TypeError` in the idempotent branch; two surviving mutations; rollback assertions that could pass for the wrong reason; a blind `pytest.raises`) |
| Pending suggestions | 0 |

Three of the seven were **real defects** — the blank reason, the cascading FK, and the
`TypeError` in the idempotent branch. Two were **design corrections** the review made
before they could bite — the `country_code` parameter and the trust in the cascade. Two
were **test-quality faults** the mutation check surfaced. One was a lint.

**The one that mattered most was the `TypeError`.** "Provisioning is idempotent" was the
item's central promise, and it was false: the second pick of a city raised rather than
returning the existing row. It was caught by the second of the eight idempotency tests on
their first run — which is the whole argument for writing eight tests for one promise
rather than one.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-057*
