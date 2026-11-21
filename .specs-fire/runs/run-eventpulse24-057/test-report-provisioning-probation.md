---
run: run-eventpulse24-057
work_item: provisioning-probation
intent: city-picker-and-auto-collection
generated: 2026-11-21
status: passed
---

# Test Report: The city probation

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| `test_city_probation.py` (new) | 75 | 0 | 0 | 100% |
| `test_city_provisioning.py` (extended) | 245 | 0 | 0 | 100% |
| `test_source_registry.py` (extended) | 112 | 0 | 0 | 99% |
| `test_migrations.py` (fixture fixed) | 12 | 0 | 0 | — |
| Backend suite (full) | 9001 | 0 | 0 | 98.80% |

`apps/ingestion/services/city_probation.py` at **100%** — every statement, including the four
"cannot happen" guards, which are each exercised by a test of their own. `city_provisioning.py`
also at **100%** (the resume path's "register a missing source" branch was reached by a new
test). `lint-imports` 21 contracts kept, 0 broken. Overall coverage 98.80%.

## Acceptance Criteria Validation

- ✅ **A run that publishes moves the city to `live`** —
  `test_a_published_run_makes_the_city_live`; the change is audited by
  `test_the_change_is_audited`, and the audit row carries the city id and never the city name by
  `test_the_audit_row_carries_the_city_id_and_never_the_city_name`.
- ✅ **Only publication moves a city to `live`** —
  `test_a_run_that_only_updated_does_not_make_the_city_live`. Yield is not publication: a city
  that re-affirms old events forever is covered and producing, but it never *published*
  anything, and "live" must mean "there are events in this city's catalogue".
  `test_only_new_and_superseded_are_publication` pins the whole key set.
- ✅ **A city whose sources run three times with nothing is paused** —
  `test_below_the_threshold_the_source_is_not_paused` (counter 2 → still active) and
  `test_at_the_threshold_the_source_is_paused` (counter 3 → paused). The threshold is in runs,
  not hours, and the two tests are what make it three.
- ✅ **The pause is audited and the source is never deleted** —
  `test_the_pause_is_audited`, `test_the_pause_audit_details_stay_exactly_from_and_to`,
  `test_the_pause_does_not_delete_the_source`.
- ✅ **The city yields nothing only when *every* source is paused that way** —
  `test_a_city_whose_every_source_is_zero_yield_paused_yields_nothing`,
  `test_a_city_with_one_zero_yield_pause_and_one_active_source_stays_collecting`, and
  `test_the_provisioned_source_counts_as_a_source_of_the_city` — the last one is the one that
  matters, because it says the *provisioned* source counts and not only the ones a test
  happened to register.
- ✅ **A hand-pause says `paused`, not `yielded_nothing`** —
  `test_a_hand_paused_source_makes_the_city_paused_not_yielded_nothing`, and
  `test_a_source_paused_with_no_reason_is_treated_as_a_hand_pause` for the "we do not know"
  case — the conservative reading.
- ✅ **A `live` city stays `live`** — `test_a_live_city_stays_live_when_its_source_goes_quiet`
  and `test_a_live_city_is_untouched`. State B (covered, quiet) is not state C (never produced
  anything).
- ✅ **A city with no sources is not `yielded_nothing`** —
  `test_a_city_with_no_sources_is_not_yielded_nothing`. "We never tried" is a different fact
  from "we tried and got nothing", and `no_providers` is the more specific one.
- ✅ **A run that never reached the feed does not count** —
  `test_a_fetch_failure_leaves_the_counter_alone`, `test_a_parse_failure_leaves_the_counter_alone`,
  and — the one that took the most thought — `test_a_304_leaves_the_counter_alone`. A 304 *did*
  reach the feed, so it is not a zero-yield run; but it is also not evidence that the previous
  zero-yield runs were wrong, so it **leaves** the counter alone rather than resetting it.
- ✅ **A healthy source is not paused for doing its job** —
  `test_a_run_that_only_recognised_known_events_does_not_reset_but_still_yields`. `unchanged`
  counts as yield, and the mutation check proves the tests fail when it is taken out.
- ✅ **The city is told once, not repeatedly** —
  `test_a_second_published_run_writes_no_second_audit_row`,
  `test_no_audit_row_is_written_when_the_status_does_not_change`,
  `test_the_change_is_reported_once`.
- ✅ **A `yielded_nothing` city is resumed by a later pick, not duplicated** —
  `test_a_re_pick_puts_the_city_back_to_collecting`,
  `test_a_re_pick_resumes_the_source_rather_than_registering_a_second_one`,
  `test_a_resumed_source_starts_its_probation_afresh`,
  `test_a_re_pick_backfills_the_city_ref`,
  `test_a_re_pick_registers_a_source_that_was_missing`,
  `test_the_resume_audit_row_counts_the_resumed_and_the_registered`,
  `test_a_re_pick_writes_a_resume_audit_row`.
- ✅ **Only `yielded_nothing` re-opens** — `test_a_live_city_is_not_dragged_back_to_collecting`
  and `test_a_paused_city_stays_paused`. An editor's pause is not undone by a reader picking the
  city.
- ✅ **The pause reason lives on the row, not in the audit** —
  `test_a_pause_records_the_reason_on_the_row`,
  `test_the_pause_reason_is_not_in_the_audit_details`,
  `test_a_pause_with_no_reason_records_none`,
  `test_a_resume_clears_the_reason`,
  `test_a_resume_clears_the_zero_yield_counter`.
- ✅ **AD-13: the city's name never reaches the audit or the log** —
  `test_the_audit_row_carries_the_city_id_and_never_the_city_name` asserts `"Portland"` is
  nowhere in the details; the same assertion is made for the resume audit row.
- ✅ **The write ownership is total (AD-16)** — the probation is inside `ingestion`, which owns
  `SOURCE`, `CITY` and `CITY_PROVISIONING`. `test_write_ownership.py` was updated: the
  `ingestion_cityprovisioning` entry's *comment* said "written only by
  `services/city_provisioning.py`", which is now false — the entry itself (the owner) is
  unchanged.
- ✅ **A probation failure does not fail a successful ingest** —
  `test_a_probation_failure_does_not_fail_a_successful_ingest` and
  `test_a_probation_failure_still_records_the_run`. The run's outcome is already recorded; the
  probation is a consequence, and the city is one step behind until the next run.

### The end-to-end shape

`TestThreeEmptyFeedsEndTheCity` runs the real `ingest_source` against a `ScriptedFetchPort`
serving an empty `calendar()` — three times:

- `test_the_first_two_runs_leave_the_source_active` — **the assertion that makes the threshold
  three.** A test that only checked the end would pass with a threshold of one.
- `test_the_third_run_pauses_the_source`
- `test_the_city_ends_at_yielded_nothing`
- `test_the_source_is_not_deleted`
- `test_the_pause_is_audited`
- `test_a_published_feed_makes_the_city_live_instead` — the other end of the same run.

**Why this test registers its own source.** The provisioned source for this city is a
Ticketmaster `api` source, and the `api` parser answers `unknown_api_provider` to an iCalendar
body — so the run would fail to *parse* rather than yield nothing, and a parse failure is not a
zero-yield run. The test needs a source whose parser accepts an empty calendar, and it needs
the city's *only* source to be that one (a city yields nothing only when every one of its
sources is paused).

## The mutation check

**The rule: a test must be able to fail.** A green suite proves the code does what it does; it
does not prove the tests *notice* when it stops doing it. Fourteen mutations were applied one at
a time, each reverted afterwards, and each was expected to turn the suite red.

The probe is at
`.specs-fire/runs/run-eventpulse24-057/mutation/mutation_probe.py` — **outside `tests/` on
purpose**, because it is a verification tool rather than a test, and pytest would collect it.

| # | Mutation | Caught by | Result |
|---|----------|-----------|--------|
| 1 | `ZERO_YIELD_RUN_THRESHOLD` 3 → 1 | 6 tests | ✅ |
| 2 | `unchanged` removed from `YIELDED_COUNT_KEYS` | 2 tests | ✅ |
| 3 | `not_modified` resets the counter instead of leaving it | 1 test | ✅ |
| 4 | `fetch_failed` increments the counter | 3 tests | ✅ |
| 5 | a `live` city is overwritten by the probation | 2 tests | ✅ |
| 6 | a hand-pause is treated as a zero-yield pause | 3 tests | ✅ |
| 7 | the resume path stops backfilling the city link | 1 test | ✅ |
| 8 | the resume path registers a duplicate instead of resuming | 2 tests | ✅ |
| 9 | the resume path does not reset the city's status | 1 test | ✅ |
| 10 | the counter is not reset on a resumed source | 1 test | ✅ |
| 11 | the pause reason is written into the audit details | 2 tests | ✅ |
| 12 | the city link is written into the register audit details | 1 test | ✅ |
| 13 | the probation runs inside the ingest transaction | 2 tests | ✅ |
| 14 | the counter is moved outside the run's transaction | 6 tests | ✅ |

**All 14 caught.**

**Mutation 13 was the one that found a gap.** "The probation runs inside the ingest
transaction" survived the first run of the check — because the try/except around
`probate_after_run` was load-bearing and *nothing tested it*. The fix was two new tests:
`test_a_probation_failure_does_not_fail_a_successful_ingest` and
`test_a_probation_failure_still_records_the_run`. **A mutation that survives is a missing
test**, and the probe is what finds it.

**Mutations 5 and 6 are the ones that carry the item's meaning.** #5 says "a city that has
published once can be un-published by a drought" — false, and `live` is terminal. #6 says "a
hand-pause and a drought are the same fact" — also false, and the whole point of the
`paused_reason` column is that they are not.

## Tests written

### `backend/tests/ingestion/test_city_probation.py` — **75 tests, new**

| Class | Tests | What it holds |
|---|---|---|
| `TestTheClassification` | 16 | The pure function: every count key's published/yield verdict, and the three counter effects. No database. |
| `TestAPublishedRunMakesTheCityLive` | 8 | A published run makes the city `live`; yield alone does not; `live` is terminal; the audit row carries the city id and not the name. |
| `TestTheZeroYieldThreshold` | 8 | The pause happens *at* three, not before; the reason is on the row; the audit details stay `{"from", "to"}`; the source is not deleted; an already-paused source is out of scope. |
| `TestTheCityStatus` | 12 | The whole rule, in order: no sources → not `yielded_nothing`; one active source → `collecting`; all zero-yield-paused → `yielded_nothing`; a hand-pause → `paused`; `live`/`no_providers`/`failed` untouched; no audit row when nothing changed. |
| `TestTheGuardsThatShouldNeverFire` | 4 | The four "cannot happen" branches — a city with no provisioning row, a `no_providers` city, a missing provisioning row, the actor factory. |
| `TestTheRegistrySeam` | 6 | A pause or a resume re-decides the city; a resume clears the reason and the counter; a source with no city is not re-probated; a probation failure does not undo the pause. |
| `TestTheIngestSeam` | 8 | The counter moves inside the run's transaction; a zero-yield run increments it; a published run resets it; a failed run and a 304 leave it alone; a probation failure does not fail the ingest. |
| `TestThreeEmptyFeedsEndTheCity` | 6 | **The headline.** The real `ingest_source` against an empty calendar, three times. |
| `TestTheResumePath` | 7 | Resume rather than duplicate; the counter reset; the `city_ref` backfill; the resume audit row; `live` and `paused` untouched. |
| `TestTheRegistryRefusesAName` | 3 | `city_ref` is a link, not a text field — a name and an id are both refused; the link is not in the audit details. |
| `TestTheOutcomeIsPlainData` | 2 | The outcome is frozen and does not expose the model (AD-16). |

### `backend/tests/ingestion/test_city_provisioning.py` — **10 tests added**

`TestAYieldedNothingCityIsResumed`: the city goes back to `collecting`; the source is resumed
rather than duplicated; the counter starts afresh; the `city_ref` is backfilled; the error code
is cleared; the resume audit row carries the city id and not the name; a missing source is
registered; a `live` city is not dragged back; a `paused` city stays paused.

### `backend/tests/ingestion/test_source_registry.py` — **5 tests added**

The pause records the reason on the row; the reason is *not* in the audit details; a pause with
no reason records none; a resume clears the reason; a resume clears the zero-yield counter.

### `backend/tests/ingestion/test_migrations.py` — **fixture fixed, no test added**

The `constraint_dropped()` fixture's `finally` block could not re-add the ceiling constraint
once `Source` had a `PROTECT` foreign key: Django creates such a FK `DEFERRABLE INITIALLY
DEFERRED`, so the row the test inserted queued a deferred FK trigger event, and PostgreSQL
refuses to `ALTER TABLE` a relation with pending trigger events. The fixture now issues
`SET CONSTRAINTS ALL IMMEDIATE` before the `ALTER TABLE`, which evaluates the pending events
inside the test's transaction without committing it. **The fixture simulates the *pre*-migration
database**, so this is about the schema the migration test needs, not about the new foreign key.

## Commands run

```bash
uv run --directory backend ruff check apps/ingestion shared tests/ingestion tests/architecture
uv run --directory backend ruff format apps/ingestion shared tests/ingestion tests/architecture
uv run --directory backend lint-imports                                   # 21 kept, 0 broken
uv run --directory backend python manage.py makemigrations --check --dry-run   # No changes detected
uv run --directory backend python manage.py check                        # no issues
uv run --directory backend pytest -q                                     # 9001 passed
uv run --directory backend python ../.specs-fire/runs/run-eventpulse24-057/mutation/mutation_probe.py
```

**`ruff format` was scoped to the directories being worked in.** Running it at the repo root
drags the pre-existing drift in `backend/tests/shared/test_retention_published.py` into the
diff — that file is untouched by this item.

## What is not covered

- `apps/ingestion/services/source_registry.py:290` — `find_source_by_url` with a URL it cannot
  canonicalise. **Pre-existing**, not introduced by this item, and out of scope.
- The frontend reads none of this yet — item 9 (`browse-collecting-states`) owns the surface.
