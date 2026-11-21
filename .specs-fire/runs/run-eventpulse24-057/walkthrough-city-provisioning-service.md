---
run: run-eventpulse24-057
work_item: city-provisioning-service
intent: city-picker-and-auto-collection
generated: 2026-11-21
mode: validate
---

# Implementation Walkthrough: The city provisioning service

## Summary

`apps/ingestion/services/city_provisioning.py` is the seam between **a reader's pick** and
**a collection**. A reader picks a city; this mints the `City` row, walks the provider
templates, registers a `Source` per spec, and records what happened — so the surface can
tell the truth about it.

**It does not fetch anything.** A registered source with `last_attempted_at IS NULL` is due
immediately, so the existing scheduler takes it on its next 60-second tick. Provisioning's
whole job is to make sure the source *exists* by then.

## The three risks the item flagged, all resolved before planning

**1. The pick is written in `personal`; the sources are written in `catalog`.** Django
will not enlist two databases in one `atomic()` block, so a transaction spanning both would
be a lie about what is atomic. The provisioning therefore runs **after the personal
transaction commits**, in its own catalog transaction — the same seam
`enqueue_digest_composition_on_commit` already uses.

**2. A failure in the provisioning must not cost the reader their city.** The `on_commit`
callback is registered `robust=True`, so a slow registry write, a dead connection or a
provider that 500s cannot roll back a pick that has already been stored. The failure
lands on the provisioning row's `last_error_code` instead — and the row's existence is
what distinguishes *a city that failed* from *a city that was never provisioned*.

**3. Two readers picking the same city must produce one set of sources.** The lock is on
the **city**, not on the user, and it is an **advisory** lock — a row lock can only lock a
row that exists, and the interesting case is precisely the one where it does not: a city
nobody has provisioned yet.

## Structure Overview

```text
backend/apps/ingestion/services/city_provisioning.py
├── ProvisioningOutcome    frozen — what happened, as plain data
├── _LOCK_PERSON           b"eventpulse24-cty" — the city's own key space
├── ACTOR_LABEL            "city_provisioning"
├── _city_lock_key(city)   blake2b(city_id, digest_size=8, person=…)
├── _lock_city(city)       SELECT pg_advisory_xact_lock(…)
├── _spec_needs_a_key(spec)    the settings attribute this spec's host needs
├── _has_its_key(spec)         whether this deployment can authenticate it
├── _registerable(specs)       the specs we can register, and why the rest were skipped
├── NO_TEMPLATE_COVERS_THIS_CITY
├── provision_city(city_name)          the entry point — the catalog is the gate
├── _provision_choice(choice, actor)   the work, under the lock
├── _write_row(...)                    the provisioning row and its audit row
├── provision_city_on_commit(city_name)   the seam the pick path uses
└── _provision_quietly(city_name)          a failure becomes a recorded failure
```

## The six rules the service holds

| Rule | Why it is a fact, not a preference |
|---|---|
| **The catalog is the gate** | A city the catalog does not hold has no `CityChoice`, so there is nothing to resolve. Minting a `City` for it would put a place into the registry that no reader chose |
| **Provisioning is idempotent** | A second pick registers nothing and leaves the status **untouched** — a city that has gone `live` must not be dragged back to `collecting` by a reader who picks it again |
| **A deployment cannot provision what it cannot authenticate** | A Ticketmaster source without a key would be picked up within a minute, fail with a 401, and burn a slot in the reliability score — for a source that was never going to work |
| **The lock is on the city** | Two readers picking Chittagong at the same moment must produce one set of sources, not two. And the lock's key space is **its own**, because a user id and a city id are both UUIDs |
| **The audit row carries the city id, never the city name** | AD-13: where a reader lives is weak location data about a real person, and a log that crosses into `catalog` is exactly where it must not reach |
| **The status is `collecting`, not `live`** | The city has no events until the scheduler has run and a source has answered. `live` is written by the ingest path |

The third rule has a shape worth naming: **the template stays pure.** `domain.city_providers`
describes what a provider *is*; this module describes what *this installation* can use. The
template never asks for a key — `domain` is stdlib-only and cannot read `settings` — and
the split is what lets the registry stay pure. The decision is driven by
`provider_keys.PROVIDER_KEYS`, so there is **one** table of "hosts that need a key" and
not a second list here.

## The one source of truth: the catalog

The service's public entry point takes **only a name**:

```python
provision_city(*, city_name: str, actor: Actor | None = None) -> ProvisioningOutcome
```

The country is read from the catalog row the service has already resolved. The first
draft took `country_code` as a parameter, on the reasoning that the catalog row carries it
and the caller has it too. **That reasoning was the bug**: a country supplied from the
caller is a **second source of truth**, and a country that disagrees with the catalog row
mints a **second `City` for the same place** — the exact split `domain.cities` exists to
prevent, and it would happen silently.

The parameter is gone. The trigger passes only the name, and the service is callable from
everywhere the plan named — a management command, a retry — all of which hold a city
*string*.

## Architecture

### AD-16 is respected by construction

`ingestion` owns `SOURCE` and `CITY`, and this module is inside `ingestion`, so it writes
them. `personalization` reaches it through `apps.ingestion.services.city_provisioning` —
a published service — and never through `apps.ingestion.models`. AD-3's `models-ingestion`
contract is what proves that, and `lint-imports` keeps it: **21 contracts kept, 0 broken**.

### The trigger imports the service lazily, inside the function

`set_home_city` is on the hot path of every reader's save, and the import is inside
`_provision_city_on_commit` so the module-level import graph of `personalization` does not
gain an `ingestion` edge. (The repo already imports `apps.ingestion.services.*` in
sixteen places, so this is a matter of keeping the *module-level* graph as it was, not of
avoiding the dependency.)

### AD-11 holds

The request handler validates, writes, and returns. The provisioning is not in the
handler — it is an `on_commit` callback, which is the same seam
`enqueue_digest_composition_on_commit` uses and the same shape AD-11's "validate, enqueue,
return" describes.

### The lock's key space is its own

`_LOCK_PERSON = b"eventpulse24-cty"`, separate from `digest_preferences`' `b"eventpulse24-onb"`.
Both lock on a UUID, and a hash of one must never be mistaken for a hash of the other —
the two would then serialise against each other for no reason, and a bug in one would look
like a bug in the other.

The lock is an **advisory lock, and transaction-scoped**. A row lock can only lock a row
that exists, and the interesting case is precisely the one where it does not: a city
nobody has provisioned yet. Two concurrent provisioners would both find nothing to lock
and both register sources — and the loser would get a raw `IntegrityError` from the unique
constraint, which reaches the caller as a 500. `pg_advisory_xact_lock` is released at
commit, so a crashed worker cannot leave a city wedged.

### The model carries the guards the schema can hold

`OneToOneField` on the city is the idempotency guarantee *in the database*: a second
provisioning of the same city cannot create a second row, so "provisioning is idempotent"
is a fact the schema holds rather than a promise the service makes. A check constraint
holds `status` non-empty.

## Two findings the work surfaced

### A city with no provider was recorded with no reason

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

### The foreign key cascaded, and the guard was right

`test_every_ingestion_foreign_key_is_protect` failed: the model was written with
`on_delete=models.CASCADE` where the guard demands `PROTECT`.

**The guard is right and the model's reasoning was wrong.** The reasoning was "a `City` is
never deleted anyway, so the rule is academic" — and that is true *today*, because `Venue`
and `EventFit` both `PROTECT` it. But a cascading delete means a city could one day lose
its provisioning record **without anybody deciding to**, and that record is the sentence
the surface reads about a city. The model now uses `PROTECT`, and the docstring says why
in terms of the decision rather than the accident.

## The `TypeError` that made the central promise false

The idempotency branch built `ProvisioningOutcome(..., last_error_code=existing.last_error_code)`,
but the dataclass's field is `error_code`. Every second pick raised a `TypeError` — so
"provisioning is idempotent" was not true at all; the second pick **crashed**.

Found by the second of the eight idempotency tests, on the first run. It was the most
important of the seven fixes the review made, because idempotency was the item's central
promise and the promise was false.

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| **The audit row's details** | City id; the source rows keep their own city | **Your checkpoint call.** A source's city is a public fact about a place; a person's city is weak location data about a real person. That is the distinction the codebase already draws — `register_source` writes `{"fields": fields}`, `_write_city_audit` writes `{"has_city": bool}` |
| **A retry** | No — the row's existence means "provisioned", whatever its status | **Your checkpoint call.** A reader's pick is not a retry request: they did not know anything failed, and a retry would be invisible to them. A retry belongs to a person or to the scheduler (item 8's probation job) |
| **A city the catalog does not hold** | Nothing happens at all | **Your checkpoint call.** The stored preference still says whatever the reader picked; it is simply not provisioned. Minting a `City` would put a place into the registry that no reader chose |
| **The trigger's arguments** | The name only, never the country | A country from the caller is a second source of truth, and a disagreement mints a **second `City` for the same place** — the split `domain.cities` exists to prevent, happening silently |
| **The lock** | `pg_advisory_xact_lock`, keyed on the city id, in its own key space | A row lock cannot lock a row that does not exist, and the interesting case is exactly that one. Transaction-scoped, so a crashed worker cannot wedge a city |
| **The credential filter** | Driven by `provider_keys.PROVIDER_KEYS`; exact hosts, never suffixes | One table of "hosts that need a key", not two. And `app.ticketmaster.com.evil.test` must never be handed our key, nor *assumed* to need one |
| **The status** | `collecting` | The city has no events until the scheduler has run and a source has answered. `live` is the ingest path's word; `yielded_nothing` and `paused` are item 8's |

## What the mutation check found

Fifteen mutations, all reverted, all caught:

| Mutation | Caught by |
|---|---|
| The catalog gate removed (an unknown city gets provisioned) | `test_a_city_outside_the_catalog_provisions_nothing` |
| The idempotency check removed | `test_a_second_pick_registers_nothing_more` |
| The credential filter removed | `test_an_api_source_is_not_registered_without_its_key` |
| The parser filter removed | `test_a_spec_with_no_parser_is_not_registered` |
| `city_tz` blanked on the source | `test_the_source_carries_the_catalogs_timezone` |
| The city's name lowercased on the source | `test_a_pick_registers_the_providers_sources` |
| `collecting` → `live` | `test_the_provisioning_row_says_collecting` |
| `no_providers` → `collecting` | `test_a_city_no_provider_covers_is_recorded_as_no_providers` |
| The source count inflated | `test_the_provisioning_row_counts_the_sources_it_registered` |
| The city name added to the audit details | `test_every_catalog_city_is_accepted[Dhaka]` |
| The audit action renamed | `test_the_audit_row_carries_the_city_id_and_not_the_city_name` |
| `robust=True` → `False` | `test_the_callback_is_registered_robustly` |
| The `on_commit` alias `PERSONAL` → `CATALOG` | `test_the_callback_is_registered_on_the_personal_alias` |
| **The advisory lock removed** | `test_the_lock_is_actually_taken` |
| **The lock key space changed** | `test_the_lock_key_space_is_not_the_one_the_personal_path_uses` |

**Two mutations survived the first round**, and both were gaps in the test file rather than
in the service:

- **The parser filter.** `_registerable` refuses a spec whose method has no parser, but
  no test covered one — every enabled template's method has a parser, so removing the
  check changed nothing observable. Fixed by `TestASpecWithNoParserIsSkipped`, which
  patches the provider registry to emit a `crawl` spec: the method `parse()` refuses.
- **The advisory lock.** The tests patched `_lock_city` (the *wrapper*), so removing the
  SQL *inside* it was invisible — the wrapper was still called, and the order assertions
  still held. Fixed by `test_the_lock_is_actually_taken`, which watches the
  `pg_advisory_xact_lock` query go out on the wire, and `test_the_lock_key_is_the_citys_own`,
  which watches the key that goes with it.

## The trap worth remembering: `on_commit` and pytest

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

## The guards that were updated, and why each is a real change

None of these were "the test needs relaxing". Each enumerates the models, and a new model
is a new thing to enumerate:

| Guard | What it now says |
|---|---|
| `test_ingestion_has_the_thirteen_designed_models` → **fourteen** | `CityProvisioning` is the fourteenth `ingestion` model |
| `test_every_ingestion_foreign_key_is_protect` | The new FK is `PROTECT` — the model changed to match the guard, not the other way round |
| `test_ingestion_retention_categories` | `CityProvisioning` is `SOURCE_REGISTRY` |
| `test_catalog_schema_holds_only_catalog_tables` | `ingestion_cityprovisioning` is a catalog table |
| `test_write_ownership`'s `TABLE_OWNERS` | `ingestion` owns `ingestion_cityprovisioning` |
| `test_the_callback_is_registered_on_the_personal_alias_and_robustly` | **Two** callbacks now, and *every* one must be on `PERSONAL` and robust |

The last one is the interesting one. Setting a home city now registers **two** `on_commit`
callbacks — the digest recomposition and the provisioning. The old assertion was
`== [(PERSONAL, True)]`, an exact-count assertion that would have failed on a *correct*
change. It now asserts that every callback is on `PERSONAL` and robust, so a future
callback registered without `robust=True` fails there rather than at a reader's expense.

## Verification

```bash
uv run --directory backend pytest tests/ingestion/test_city_provisioning.py -q  # 235 passed
make test-backend                                                            # 8905 passed
make coverage-backend                                                        # 97.45%, domain/ 100%
make lint-imports                                                            # 21 kept, 0 broken
uv run --directory backend python manage.py makemigrations ingestion --check --dry-run
```

`apps/ingestion/services/city_provisioning.py` is at **100%** — every statement, including
the two "cannot happen" guards. `domain/` still at **100%**. `ruff check` passes; the only
`ruff format --check` drift is the pre-existing `tests/shared/test_retention_published.py`.

## What This Unblocks

`provisioning-probation` (item 8) is next, and it **inherits three statuses** this item
deliberately did not write:

- **`live`** — written by the ingest path, when a source has actually answered. This item
  writes `collecting`, because the city has no events until the scheduler has run.
- **`yielded_nothing`** — a city whose sources answered and produced nothing. The
  probation job is the only thing that can know that.
- **`paused`** — a city whose sources keep failing. A reader's pick cannot pause a city
  they know nothing about, and a provisioning that failed is not the same as a city that
  is not producing.

**And it inherits the retry that a reader's pick deliberately is not.** The
`CityProvisioning` row's existence means "provisioned", whatever its status says, so
`test_a_failed_provisioning_is_not_retried_by_a_later_pick` holds that a later pick does
not retry. Item 8's probation job is the thing that may re-attempt — and it must do so
**without a reader knowing**, which is exactly why a pick is not a retry.

Item 8 also inherits the vocabulary this item established: `no_providers` with a **reason**
(`no_template_covers_this_city` vs `no_credential:<SETTING>`), and `last_error_code` as the
place a failure is recorded rather than raised.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-057*
