---
run: run-eventpulse24-057
work_item: provisioning-probation
intent: city-picker-and-auto-collection
generated: 2026-11-21
status: approved
---

# Review Report: The city probation

## Summary

Item 8 closes the gap item 7 left open: `CityProvisioning.Status` had five choices and
nothing in the codebase wrote three of them. Every provisioned city said `collecting` forever —
including a city whose only source fetches successfully every four hours and returns nothing.

The work adds a **zero-yield counter** on `Source`, moves it inside `ingest_source`'s own
transaction, and — after that transaction commits — runs a **probation** that pauses a source
which has yielded nothing three times running, and marks the city `yielded_nothing` when every
one of its sources is paused that way.

**14 mutations, 14 caught.** `city_probation.py` and `city_provisioning.py` at 100% coverage.
The backend suite: **9001 passed, 0 failed**.

## The findings

### 1. `not_modified` leaves the counter alone — and that was the hard call

The plan's table said a 304 **resets** the counter. The implementation says **leave**. The
change is deliberate, and the reason is worth recording because the plan's own reasoning was
self-contradicting.

The AC says a run "that never reached the feed must not count toward the zero-yield
probation". A 304 *did* reach the feed — it proves the feed is alive — so it is not a
zero-yield run. But it carries no information about whether the feed *has anything in it*, so
it is not evidence that the previous zero-yield runs were wrong.

**Leave** is the only effect that moves the counter only on evidence. Resetting would let a
source alternate "empty" / "304" / "empty" / "304" forever and never be condemned; incrementing
would count a run that produced nothing against a source that did. The mutation check caught
the reset version (mutation #3), so the distinction is now enforced by a test rather than by a
comment.

### 2. `unchanged` is the member of the yield set that matters

`YIELDED_COUNT_KEYS` has six members, and one of them carries the whole design: **`unchanged`**
— an event a source re-reports that is already in the catalogue, matched by content hash.

That is what a **healthy** source returns on every poll after the first. Without it in the
yield set, every healthy source would accrue a zero-yield run per poll and be **paused after
twelve hours of doing its job perfectly**. The counter would condemn the most reliable sources
in the registry.

The mutation check removes it (mutation #2) and two tests fail. This is the single most
consequential line in the item.

### 3. The pause reason is a column, not audit history

The probation needs to know "is this source paused, and by whom, **right now**". The audit log
is for accountability; a column is for state. And `IngestionAuditEntry` is retained 24 months —
beyond that the answer disappears, and a paused source would silently become a hand-pause.

**The audit `details` stay exactly `{"from", "to"}`.** `tests/ingestion/test_source_registry.py:621`
asserts exact equality on `(action, details)`, and every other status change in the registry has
that shape. The reason lives on the row. The mutation check writes the reason into the audit
details (mutation #11) and two tests fail.

**An empty reason means "we do not know",** and the city reads it as a hand-pause — the
conservative reading, because "somebody paused this" is a stronger claim than "the probation
paused this", and only the probation's own pauses should produce `yielded_nothing`.

### 4. `live` is terminal

A city that has published once stays `live` forever, even if its sources later go quiet.

This is the difference between **state B** (covered, quiet) and **state C** (never produced
anything). `browse-states.tsx` already insists on the distinction, and collapsing them would
lose information the surface has decided to show. A drought can pause a `live` city's *source*;
it cannot un-publish the city.

The mutation check lets the probation overwrite a `live` city (mutation #5) and two tests fail.

### 5. `city_ref` is a link, not a text join

`Source.city` is a plain string — "a venue names a city the way it is written". The probation
needs "every source for a city", and a text join would miss rows (and would miss a row whose
city was written "Portland, Oregon" against a catalog row of "Portland, OR").

So `Source.city_ref` is a nullable `PROTECT` FK to `City`, mirroring `Venue.city_ref`, which
already exists for exactly this reason. The provisioning service hands the registry the row it
already resolved; **the registry never resolves a name**, because that would be a second
source of truth about which city a source belongs to — and a disagreement would mint a second
`City` for the same place.

`register_source` refuses a name or an id with a `TypeError`. The link is **not** in the audit
details (mutation #12 proves the tests notice), so every `register_source` audit row keeps the
same shape.

### 6. Two transactions, never nested

The counter moves **inside** `ingest_source._close`'s existing transaction — it is the run's
own fact, and it belongs with the run's audit row.

The city-wide consequence runs **after the commit**, in its own transaction. Running it inside
would hold the source's row lock while reaching for the city's other sources and the
provisioning row — and two concurrent runs of two different sources of the same city would
each hold their own lock while reaching for the other, and **deadlock**.

`pause_source` opens its own atomic block and writes its own audit row; `_probate_city_status`
opens another. Nesting them would invert the lock order against a concurrent hand-pause.

### 7. The migration test fixture, and a deferred foreign key

The `constraint_dropped()` fixture in `tests/ingestion/test_migrations.py` could not re-add the
cadence ceiling constraint once `Source` had a `PROTECT` foreign key:

```
django.db.utils.OperationalError: cannot ALTER TABLE "ingestion_source"
because it has pending trigger events
```

**The mechanism.** Django creates `PROTECT` foreign keys `DEFERRABLE INITIALLY DEFERRED`, so
the row the test inserted queues a deferred FK trigger event that is only evaluated at commit.
PostgreSQL refuses to `ALTER TABLE` a relation with pending trigger events.

**The fix** is one line in the fixture: `SET CONSTRAINTS ALL IMMEDIATE` before the
`ALTER TABLE`, which evaluates the pending events inside the test's transaction without
committing it.

**Why this is a fixture change and not a design change.** The fixture simulates the
*pre-migration* database — it drops a constraint to build a state that the migration can then
be tested against. The new foreign key has nothing to do with the cadence ceiling, and the
`PROTECT` choice is right by default (a city is never deleted; `Venue` and `EventFit` already
protect it). The guard `test_every_ingestion_foreign_key_is_protect` was **not** relaxed.

**How it was proved.** The change was stashed (`git stash push -u`), the tests re-run, and the
stash restored: the same 12 tests passed before the change and failed after it. The regression
was mine, and it was located before the fix was written.

### 8. A mutation that survived found a missing test

Mutation #13 — "the probation runs inside the ingest transaction" — **survived** the first
run of the check. The try/except around `probate_after_run` was load-bearing and *nothing
tested it*.

That is the whole point of the exercise: **a mutation that survives is a missing test.** Two
tests were added (`test_a_probation_failure_does_not_fail_a_successful_ingest` and
`test_a_probation_failure_still_records_the_run`) and the mutation is now caught.

The rule it defends: the run's outcome is already recorded; the probation is a consequence. The
city is one step behind until the next run, which is a smaller harm than a failed ingest — the
events are in the catalogue either way, and a failed run would say the fetch did not work when
it did.

### 9. The module-level cycle, and the lazy import that avoids it

`city_probation` imports `source_registry` at module level (for `pause_source`).
`source_registry` needs `city_probation` (for the re-probation after a status change). A
module-level import back would be a cycle.

The established pattern in this repo is a lazy import inside the function — see
`digest_preferences.set_home_city`. `source_registry._reprobate_city` uses it, with the reason
written down.

`ingest_source` imports `city_probation` at module level with no cycle.

### 10. The resume path resumes; it does not duplicate

`register_source` **raises** `SourceAlreadyRegisteredError` on a duplicate URL and never
updates an existing row. So the resume path looks the source up **first**, via
`find_source_by_url`, which canonicalises the URL the same way `register_source` does.

Then: a paused source is **resumed**; a missing source is **registered**; a source with no
`city_ref` gets it **backfilled** (without the backfill the probation would never see it
again, and the city could never yield nothing a second time); the counter is reset; and the
city goes back to `collecting`.

**Only `yielded_nothing` re-opens.** A `live` city stays `live` — item 7's contract, and the
mutation check proves it. A `paused` city stays `paused`: **an editor's pause is not undone by
a reader picking the city.**

## The security and architecture notes

| Rule | How it holds |
|---|---|
| **AD-13** (no PII in logs or audit details) | The probation's audit row carries `city_id` and the status — **never the city's name**. The log line says *that* the probation failed and nothing about which city. Two tests assert `"Portland"` is nowhere in the details. |
| **AD-16** (total write ownership) | `ingestion` owns `SOURCE`, `CITY` and `CITY_PROVISIONING`, and the probation is inside `ingestion`. The `test_write_ownership.py` comment was updated — the `ingestion_cityprovisioning` entry's owner is unchanged, but its comment ("written only by `services/city_provisioning.py`") was false and now names both services. |
| **AD-3** (`models-ingestion`) | `personalization` never imports `apps.ingestion.models`. The probation reads no personal schema. `lint-imports`: 21 contracts kept, 0 broken. |
| **AD-2** (layers point inward) | `domain/` is untouched and still pure stdlib. The classification logic is in `apps/ingestion`, not in `domain` — because it reads a model's status vocabulary, which `domain` cannot. |
| **AD-11** (handler = validate/enqueue/return) | No API surface changed. **No `make client` was needed**, and `tests/api/test_contract.py` is unaffected. |
| **FR-13** (sources are paused, never deleted) | The probation pauses through the registry, which is the auditable path. `test_the_pause_does_not_delete_the_source`. |
| **FR-16** | The zero-yield counter is a standing fact about a source — it sits on the catalog side of the AD-3 wall. |
| **AD-8** (a threshold lives in one place) | `ZERO_YIELD_RUN_THRESHOLD = 3` is in `shared/constants.py`, with the reason it is three and not one, and the reason it is in runs and not hours. |

**No secret reaches the audit or the log.** The probation reads no credential, and the fetch
path's credential handling (item 6) is unchanged — `provider_keys` still adds the key at fetch
time and it is still never stored.

## Deliberately not changed

| Not changed | Why |
|---|---|
| `backend/worker/tasks.py` | **No new Celery task.** The `tick()` enqueue list in `tests/worker/test_scheduling_tasks.py` is pinned by *exact equality* — 7 parametrized minutes, 7 exact ordered lists. A new task breaks all seven. The probation is event-driven: it runs when a run completes, which is exactly when it must run. |
| `backend/apps/ingestion/services/scheduling.py` | Untouched. The scheduler takes a paused source off the list; that is its own rule. |
| `frontend/` | Untouched. Item 9 (`browse-collecting-states`) owns the surface. |
| `backend/apps/ingestion/models.py` — `CityProvisioning.Status` | The choices were already right; this item made three of them reachable. |
| `shared/constants.py` — anything else | Only three constants were added. `PUBLISHED_COUNT_KEYS` and `YIELDED_COUNT_KEYS` are *sets of names*, not thresholds — the one threshold lives in one place (AD-8). |
| `tests/wall/test_schema_placement.py` | No new **model** and no new **table** — three columns on an existing row. The enumerations hold. |
| The `ingest_source` audit `details` | Unchanged: exactly `{"outcome", "counts"}`. `tests/ingestion/test_ingest_source.py:177,249` asserts it, and the mutation check would have caught a change. |

## The one thing a reviewer should look at hardest

**The three-way choice on a 304.** `classify_run` returns `LEAVE` for `not_modified`, and
`LEAVE` means "this run proves nothing either way". It is the only one of the three effects
that is not a move, and it is the only one whose correctness is a matter of judgement rather
than arithmetic.

The argument for it is in the code and in the mutation check. The counter moves **only on
evidence**, and a 304 is not evidence about the feed's contents.

The argument against it: a 304 *does* reach the feed, so one could argue it should reset a
counter that a previous empty run raised. That reading would make the counter reset on every
poll of a healthy-but-idle feed — which is exactly the failure mode `unchanged` was included to
prevent. **Leave** is right.

## Verification

```bash
uv run --directory backend ruff check apps/ingestion shared tests/ingestion tests/architecture
uv run --directory backend ruff format --check apps/ingestion shared tests/ingestion tests/architecture
uv run --directory backend lint-imports                                   # 21 kept, 0 broken
uv run --directory backend python manage.py makemigrations --check --dry-run   # No changes detected
uv run --directory backend python manage.py check                        # no issues
uv run --directory backend pytest -q                                     # 9001 passed, 0 failed
uv run --directory backend python ../.specs-fire/runs/run-eventpulse24-057/mutation/mutation_probe.py
                                                                     # All 14 mutations were caught
```

`ruff format` was scoped to the directories being worked in — **never** at the repo root, which
would drag the pre-existing drift in `backend/tests/shared/test_retention_published.py` into
the diff.

## Verdict

**Approved.** The item's central claim — *a city that yields nothing is told so, and a city
that publishes is told that too* — is enforced by tests that a mutation proves can fail, and
the two rules that would have made the probation a lie (a healthy source being paused for
doing its job, and a hand-pause being reported as a drought) are each pinned by a mutation.

**One caveat for the reviewer of the run**: the probation's trigger is event-driven, so a
provisioned city whose source is *never* scheduled (because the scheduler's rules exclude it)
would never be probated. The scheduler's due-list is unchanged by this item, and every
provisioned source is registered with `last_attempted_at IS NULL` — due immediately. The
gap, if there is one, is in the scheduler, not here.
