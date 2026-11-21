---
run: run-eventpulse24-057
work_item: city-provisioning-service
intent: city-picker-and-auto-collection
generated: 2026-11-21
status: passed
---

# Test Report: The city provisioning service

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Provisioning service (new) | 235 | 0 | 0 | 100% |
| Backend suite (full) | 8905 | 0 | 0 | 97.45% |
| **Total** | **8905** | **0** | **0** | **97.45%** |

`apps/ingestion/services/city_provisioning.py` at **100%** — every statement, including
the two "cannot happen" guards. `domain/` still at **100%**. `lint-imports` 21 contracts
kept, 0 broken. Overall coverage 97.45%, unchanged from item 6 — the new service is fully
covered and the new model adds no uncovered statements.

## Acceptance Criteria Validation

- ✅ **A reader's pick provisions the city's sources** —
  `test_a_pick_triggers_the_provisioning` patches the service's own entry point and
  asserts the stored city reaches it; `test_a_pick_that_provisions_really_registers_the_sources`
  runs the whole path with **no seam monkeypatched** and asserts the `Source` row and the
  `CityProvisioning` row are there afterwards.
- ✅ **The provisioning happens after the pick is committed, never inline** —
  `test_the_provisioning_does_not_run_inside_the_callers_transaction` asserts the service
  has not run *inside* the caller's `atomic()` block; `test_the_provisioning_runs_after_the_commit`
  asserts it has run after it; `test_a_rollback_leaves_nothing_provisioned` and
  `test_a_rollback_leaves_no_source` assert a rolled-back pick provisions nothing.
- ✅ **A failure in the provisioning does not roll back the stored city** —
  `test_the_callback_is_registered_robustly` asserts `robust=True` on the callback, and
  `test_a_failure_does_not_reach_the_caller` runs a callback that raises and asserts the
  exception never reaches the caller.
- ✅ **The provisioning is idempotent — a second pick registers nothing more** —
  `test_a_second_pick_registers_nothing_more`, `test_a_second_pick_leaves_one_provisioning_row`,
  `test_a_second_pick_returns_the_existing_row`, `test_a_second_pick_writes_no_second_audit_row`,
  and `test_provisioning_a_city_twice_does_not_raise_a_duplicate_error` (the registry's own
  duplicate-URL refusal must not be reached).
- ✅ **A city the catalog does not hold provisions nothing at all** — six tests, one per
  thing that must not happen: no `City` row, no source, no provisioning row, no audit row,
  and an outcome that says `provisioned is False`. `test_a_city_outside_the_catalog_is_not_even_looked_up_by_its_own_text`
  adds the near-miss case — "Portland" is not the catalog's name for either Portland, so it
  is refused rather than silently resolved to the nearest row.
- ✅ **A source is never registered for a provider this deployment cannot authenticate** —
  `test_an_api_source_is_not_registered_without_its_key`, `test_the_reason_is_recorded`
  (the reason is `no_credential:TICKETMASTER_API_KEY`), and `test_with_the_key_the_source_is_registered`
  for the other half. `test_the_registered_url_never_carries_the_key` asserts the key is
  not in the stored URL — the key is added at fetch time and never stored.
- ✅ **The provisioning records what it did, so the surface can tell the truth** —
  `test_the_provisioning_row_says_collecting` (not `live` — the city has no events until
  a source has answered), `test_the_provisioning_row_counts_the_sources_it_registered`,
  `test_the_provisioning_row_carries_no_error`, `test_the_provisioning_row_holds_the_city_and_not_its_name`.
- ✅ **The city's timezone is on the source** — `test_the_source_carries_the_catalogs_timezone`.
  This is the last link in FR-60's chain: without it a brand-new city rejects every
  date-only time as `tz_unresolvable` and publishes nothing, forever.
- ✅ **The city's name is the catalog's own, verbatim** —
  `test_the_source_carries_the_catalogs_name_verbatim`.
- ✅ **AD-13: the provisioning's audit row carries the city id, never the city name** —
  `test_the_audit_row_carries_the_city_id_and_not_the_city_name` asserts `"Portland"` is
  nowhere in the details; `test_the_audit_row_is_written_by_a_system_actor` asserts the
  actor is the system, not the reader.
- ✅ **Two readers picking the same city produce one set of sources** —
  `test_the_lock_is_actually_taken` watches the `pg_advisory_xact_lock` query go out;
  `test_the_lock_key_is_the_citys_own` asserts two cities take two locks;
  `test_the_lock_key_space_is_not_the_one_the_personal_path_uses` asserts the city lock
  space is not the user lock space.

## The decisions taken at the checkpoint

| Decision | Chosen | Where it is tested |
|---|---|---|
| **The audit row's details** | City id; the source rows keep their own city | `test_the_audit_row_carries_the_city_id_and_not_the_city_name` |
| **A retry** | The row's existence means "provisioned", whatever its status | `test_a_failed_provisioning_is_not_retried_by_a_later_pick` |
| **A city the catalog does not hold** | Nothing happens at all | `TestTheCatalogIsTheGate` (6 tests) |

## The two-database problem, and the seam that solves it

**The pick is written in `personal`; the sources are written in `catalog`.** Django will not
enlist two databases in one `atomic()` block, so a transaction spanning both would be a lie
about what is atomic. The provisioning therefore runs **after the personal transaction
commits**, in its own catalog transaction — the same seam `enqueue_digest_composition_on_commit`
already uses.

**`robust=True` is what makes the pick safe.** A slow registry write, a dead connection, a
provider that 500s — none of them may cost the reader their city. The pick stands; the
provisioning row's `last_error_code` says what went wrong.

**One source of truth: the catalog.** The trigger passes only the *name*. The country is
read from the catalog row by the service, because a country supplied from the caller could
disagree with it — and a disagreement mints a **second `City` for the same place**, which is
the exact split `domain.cities` exists to prevent. The `country_code` parameter the service
originally carried was removed for this reason.

## The finding the work surfaced: a city with no provider had no reason recorded

**The `no_providers` status was being written with a blank reason.** `resolve()` returns an
empty tuple for a city no enabled template covers, so `_registerable` had nothing to skip
and `skipped[0]` was never reached — the row said "no providers" and *not why*.

**"No template serves this city" and "the providers that do serve it need a credential we
have not been given" are different facts**, and an operator needs to tell them apart: the
first needs a new template, the second needs a secret. The service now records
`NO_TEMPLATE_COVERS_THIS_CITY` for the first and `no_credential:<SETTING>` for the second,
and `test_a_city_no_template_covers_says_so` holds the first.

## A second finding: the architecture guard was right and the model was wrong

**`test_every_ingestion_foreign_key_is_protect` failed on the new model.** The guard says
every `ingestion` foreign key is `PROTECT`; the model was written with `CASCADE` on
`CityProvisioning.city`.

The guard is right, and the model's reason was wrong. A `City` is never deleted today
(`Venue` and `EventFit` already `PROTECT` it), so the rule is academic *now* — but a
cascading delete would mean a city could one day lose its provisioning record without
anybody deciding to, and that row is the sentence the surface reads about a city. The
model was changed to `PROTECT` and the docstring now says why.

## The guards that were updated, and why each is a real change

None of these were "the test needs relaxing". Each enumerates the models, and a new model
is a new thing to enumerate:

| Guard | What it now says |
|---|---|
| `test_ingestion_has_the_thirteen_designed_models` → **fourteen** | `CityProvisioning` is the fourteenth `ingestion` model |
| `test_every_ingestion_foreign_key_is_protect` | The new FK is `PROTECT` |
| `test_ingestion_retention_categories` | `CityProvisioning` is `SOURCE_REGISTRY` |
| `test_catalog_schema_holds_only_catalog_tables` | `ingestion_cityprovisioning` is a catalog table |
| `test_write_ownership`'s `TABLE_OWNERS` | `ingestion` owns `ingestion_cityprovisioning` |
| `test_the_callback_is_registered_on_the_personal_alias_and_robustly` | **Two** callbacks now, and *every* one must be on `PERSONAL` and robust |

The last one is the interesting one. Setting a home city now registers **two** `on_commit`
callbacks — the digest recomposition and the provisioning. The old assertion was
`== [(PERSONAL, True)]`, an exact-count assertion that would have failed on a *correct*
change. It now asserts that every callback is on `PERSONAL` and robust, so a future
callback registered without `robust=True` fails there rather than at a reader's expense.

## Mutation Check

Every whole-dataset invariant was mutated, the mutation reverted, and the suite re-run.
**The rule that a test must be able to fail.** 15 mutations, 15 caught.

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

**Two mutations survived the first round**, and both were real gaps in the test file
rather than in the service:

- *The parser filter.* No test covered a spec whose method had no parser, so removing the
  check changed nothing observable. Fixed by `TestASpecWithNoParserIsSkipped`, which
  patches the provider registry to emit a `crawl` spec — the method `parse()` refuses.
- *The advisory lock.* The tests patched `_lock_city` (the wrapper), so removing the SQL
  **inside** it was invisible. Fixed by `test_the_lock_is_actually_taken`, which watches
  the `pg_advisory_xact_lock` query go out on the wire, and `test_the_lock_key_is_the_citys_own`,
  which watches the key that goes with it.

## Tests Written

**`tests/ingestion/test_city_provisioning.py` (new, 235 tests)** — the item's own proof.

*The catalog gate (7)*: an unknown city provisions nothing, mints no city row, registers
no source, writes no provisioning row, writes no audit row, and returns an outcome that
says so; plus a near-miss case, and a **whole-dataset** pass over **every** catalog city
asserting each one is accepted.

*The pick provisions (12)*: the city row, the sources, the catalog's timezone, the catalog's
name, the `collecting` status, the source count, the blank error, the city id and not the
name, the audit row's details, the system actor, the source's due-immediately state, and
its active status.

*No providers (5)*: the status, the absence of sources, the presence of a city row, the
presence of a provisioning row, and the recorded reason.

*A provider without a credential (5)*: the source is not registered, the reason is
recorded, the status is `no_providers`, the key makes the difference, and the key is
never in the stored URL.

*A spec with no parser (4)*: not registered, the reason recorded, the status, and the
other half — a method that *can* be parsed is registered.

*The idempotency (8)*: nothing more registered, one row, the status untouched, the same row
returned, one audit row, a failed provisioning not retried, a `no_providers` city staying
there.

*The lock (6)*: the key is stable, two cities take two keys, the key space is not the
personal path's, the key is not the bare uuid, the lock is taken before the row is read,
the lock is held through the registration, the lock is transaction-scoped, the SQL is
really issued, and two cities take two locks.

*The after-commit seam (6)*: not inline, after the commit, a rollback provisions nothing,
a rollback registers no source, the alias is `PERSONAL`, and the callback is robust.

*The pick path (4)*: the pick triggers the provisioning, a pick with no city provisions
nothing, a refused pick provisions nothing, and the whole path registers the sources with
nothing monkeypatched.

*Plain data (2)*: the outcome is frozen, and it does not expose the model.

*The guards that should never fire (4)*: a catalog row that names no city is refused; a
URL that cannot be parsed needs no key; a URL with no host needs no key; and a host that
only *ends with* a provider's host needs no key — the suffix trap.

## Test Commands

```bash
uv run --directory backend pytest tests/ingestion/test_city_provisioning.py -q
make test-backend && make coverage-backend
make lint-imports
```

## Issues Found

**Two, and both were real.**

1. **The `no_providers` status carried no reason.** A city no template covers got a
   provisioning row saying "no providers" and nothing else. Fixed with
   `NO_TEMPLATE_COVERS_THIS_CITY`, and the two facts are now told apart.
2. **The model's foreign key cascaded.** The architecture guard caught it, the guard was
   right, and the model was changed to `PROTECT`.

The other failures during the work were **wrong test assumptions** rather than defects:
the default deployment has no `TICKETMASTER_API_KEY` (so the "a pick provisions" tests
needed a deployment that does), and `pytest`'s `django_db` fixture wraps every test in a
transaction that is rolled back — so Django's `on_commit` callbacks never fire on their
own. The last one is the important trap: without `django_capture_on_commit_callbacks` the
"the provisioning runs after the commit" test would have **passed for the wrong reason**,
because the callback would never have run at all. The file now uses Django's own capture
for the rollback assertions — the one that *discards* a rolled-back transaction's
callbacks, which is the behaviour under test — and the repo's existing `on_commit` fixture
pattern for the rest.

## Ready for Completion

- [x] All tests passing (8905, zero failures)
- [x] Coverage met (100% on the new service, 100% on `domain/`, 97.45% overall)
- [x] All acceptance criteria validated
- [x] Every whole-dataset invariant mutation-checked (15 mutations, all caught)
- [x] `lint-imports` 21 contracts kept, 0 broken
- [x] The architecture guards updated, none relaxed
- [x] `makemigrations --check` reports no drift

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-057*
