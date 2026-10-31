# Test report: digest-scheduling

**Work item:** `digest-scheduling` — Composition scheduling from the single tick
**Intent:** `pulse-digest-and-trust`
**Run:** `run-eventpulse24-021`
**Date:** 2026-10-31

---

## What was built

| Piece | Where | What it does |
|---|---|---|
| The selection rule | `backend/apps/personalization/services/digest_scheduling.py` | `is_due` — the local wall-clock comparison; `claim_due_digests` — the bounded, ordered, locked selection; `release_claim` |
| The claim column | `backend/apps/personalization/models.py` | `DigestPreference.digest_claimed_at` |
| The dispatcher | `backend/worker/tasks.py` | `schedule_digests` — claims, enqueues one composition per claim, releases on a broker failure |
| The composition job | `backend/worker/tasks.py` | `compose_digest_task` — composes, releases the claim in a `finally`, re-raises so Celery retries |
| The tick | `backend/worker/tasks.py` | the tick now also enqueues `schedule_digests`; its docstring records that this cadence does **not** nest |
| The enqueue seam | `backend/apps/personalization/services/digest_enqueue.py` | `enqueue_digest_composition` — sends `worker.tasks.compose_digest` by dotted name, carrying only the user id |
| The onboarding wiring | `backend/apps/personalization/services/onboarding.py` | all three completion paths register the enqueue on `on_commit(using=PERSONAL, robust=True)` |
| The migration | `backend/apps/personalization/migrations/0011_digestpreference_digest_claimed_at.py` | the `digest_claimed_at` column |
| The command | `backend/config/management/commands/compose_digest.py` | `manage.py compose_digest --user-id <uuid>` / `--all` |
| The constants | `backend/shared/constants.py` | `DIGEST_DISPATCH_BATCH`, `DIGEST_CLAIM_TTL`, `DIGEST_SCHEDULER_ACTOR` |

---

## The tests

**78 new tests** in five files, plus **7 updated** in the existing tick-order table.

### The due rule — 8 tests (`tests/personalization/test_digest_scheduling.py`)

| Test | What it pins |
|---|---|
| `test_a_user_is_not_due_before_their_delivery_time` | an hour early is not due |
| `test_a_user_is_due_exactly_at_their_delivery_time` | the comparison is **inclusive** — 09:00:00 is due, not 09:01 |
| `test_a_user_is_due_after_their_delivery_time` | an hour late is due |
| `test_the_delivery_time_is_the_users_own_local_clock` | one UTC instant, two answers — 17:00 UTC is 09:00 in Los Angeles and 12:00 in New York |
| `test_the_delivery_time_moves_with_the_clock_across_a_dst_change` | 09:00 local is due on both sides of the spring-forward, and not due an hour before on either |
| `test_the_utc_instant_of_a_local_delivery_time_moves_with_the_clocks` | **the two 9ams are different instants** — `after − before == 2 days − 1 hour` |
| `test_an_unknown_zone_falls_back_to_utc_rather_than_raising` | a hand-edited zone must not take the whole dispatcher down |

### The selection — 15 tests (same file)

| Test | What it pins |
|---|---|
| `test_a_user_with_a_preference_is_claimed_once_their_time_arrives` | the happy path |
| `test_a_user_before_their_time_is_not_claimed` | the schedule half of the rule |
| `test_a_user_who_already_has_a_digest_for_the_local_day_is_not_claimed` | **the fact beats the schedule** — the idempotence guard |
| `test_a_user_with_no_preference_is_never_due` | no preference, no zone, no due |
| `test_the_claim_is_recorded_on_the_preference` | the claim lives where the design says it does |
| `test_the_claim_is_audited_with_the_scheduler_actor` | the audit row names a **job**, never a user (AD-13) |
| `test_the_claim_is_ordered_by_the_user_id` | the id is a UUIDv7, so it is the creation time — the oldest first, so a new user is never starved |
| `test_the_claim_is_bounded_by_the_batch_size` | `DIGEST_DISPATCH_BATCH` |
| `test_a_claimed_user_is_not_claimed_again` | the second dispatcher skips the row |
| `test_a_claim_older_than_the_ttl_becomes_claimable_again` | a worker that died leaves a claim; the TTL is the backstop |
| `test_a_claim_inside_the_ttl_is_still_held` | the TTL's other side |
| `test_releasing_the_claim_makes_the_user_due_again` | the release works |
| `test_two_dispatchers_never_claim_the_same_user` | `SKIP LOCKED` — the second dispatcher claims nobody |
| `test_a_user_claimed_between_the_read_and_the_lock_is_not_claimed` | **the race the row lock exists for** — a dispatcher that claimed the user in the gap is not double-claimed |
| `test_a_due_user_in_a_different_zone_is_claimed_on_its_own_clock` | each row is compared in its own zone |

### The command — 8 tests (same file)

`test_the_command_composes_one_user_s_digest`,
`test_the_command_is_idempotent` (running it twice writes one digest),
`test_the_command_needs_exactly_one_mode`,
`test_the_command_rejects_a_user_that_is_not_a_uuid`,
`test_the_command_composes_only_the_due_users`,
`test_the_command_counts_a_digest_that_already_existed`,
`test_the_command_releases_its_claims`,
`test_the_command_releases_the_claim_when_a_composition_fails`.

### The scheduler actor — 1 test

`test_the_scheduler_actor_is_a_system_actor` — the actor is `system` / `digest_scheduler`.

### The enqueue — 10 tests (`tests/personalization/test_digest_enqueue.py`)

| Test | What it pins |
|---|---|
| `test_advancing_past_the_last_step_queues_the_first_digest` | completion by advancing |
| `test_skipping_the_last_step_queues_the_first_digest` | completion by skipping the last step |
| `test_skipping_everything_queues_the_first_digest` | completion by skipping everything |
| `test_an_earlier_step_queues_nothing` | only *completion* queues |
| `test_the_enqueue_happens_once` | not twice |
| `test_only_the_user_id_travels` | **one argument, a UUID** — no email, no city, no delivery time (AD-13) |
| `test_the_enqueue_waits_for_the_commit` | the enqueue is *registered*, not performed |
| `test_the_enqueue_is_registered_on_the_personal_alias` | the callback belongs to the transaction that wrote the rows |
| `test_a_broker_outage_does_not_fail_the_onboarding` | the onboarding stands |
| `test_a_robust_callback_does_not_raise_when_the_broker_is_down` | `robust=True` swallows the failure; `robust=False` does not |

### The worker — 14 tests (`tests/worker/test_digest_tasks.py`)

| Test | What it pins |
|---|---|
| `test_the_tick_enqueues_the_digest_dispatcher` | the tick asks the dispatcher to look |
| `test_the_digest_dispatcher_runs_on_every_beat` | **the cadence does not nest** — five ticks, five dispatcher enqueues |
| `test_the_tick_still_uses_exactly_one_static_beat` | the beat schedule is unchanged — one 60-second tick |
| `test_the_dispatcher_enqueues_one_composition_per_claim` | one job per claim |
| `test_the_dispatcher_releases_the_claim_when_the_broker_is_down` | a broker outage frees the claim so the next tick retries |
| `test_the_dispatcher_logs_the_failure_without_pii` | the log names the job and the error type |
| `test_the_composition_job_composes_the_digest` | the job composes |
| `test_the_composition_job_releases_the_claim` | the claim is released |
| `test_the_composition_job_releases_the_claim_when_the_composition_fails` | **the release is in a `finally`** — a crash cannot leave a user claimed until the TTL |
| `test_the_composition_job_re_raises_so_celery_retries` | a swallowed failure would leave the user with no digest and no retry |
| `test_the_composition_job_logs_the_error_type_and_no_pii` | the log names the job and the error type |
| `test_the_tasks_are_registered_under_their_dotted_names` | the dotted names the broker uses |
| `test_the_enqueue_seam_sends_only_the_user_id` | one argument |
| `test_the_seam_sends_the_job_through_the_loaded_celery_app` | the real `_send` goes through Celery by dotted name |

### The boundary — 5 functions, 13 cases (`tests/architecture/test_digest_composition_separation.py`)

| Test | What it pins |
|---|---|
| `test_no_request_handler_composes_a_digest` (9 cases) | **AD-11**: no API module *calls* `compose_digest`. The module list is discovered — every `api.py` and `*_api.py` under `apps`, plus `config/api.py` |
| `test_the_request_modules_are_the_ones_we_think` | the discovery finds the modules a hand-written list names — so it is not silently finding nothing |
| `test_the_composition_is_reachable_from_the_worker` | **the boundary is a direction, not an absence** — the worker *must* still compose |
| `test_the_onboarding_path_enqueues_rather_than_composes` | the onboarding path calls the *enqueue*, never the composition |
| `test_the_enqueue_seam_does_not_import_the_composition` | the seam sends a job by name; it does not import the scoring code |

### The concurrency — 5 tests (`tests/personalization/test_digest_scheduling_concurrency.py`)

The acceptance criterion is explicit: "Two workers ticking at once must not compose
the same user's digest twice … **A test exercises the concurrent path rather than
assuming the constraint covers it.**"

Two real dispatchers, in two real threads, over a real **committed** row —
`transaction=True`, because without a commit the second thread cannot see the first
thread's rows and the test would pass vacuously.

| Test | What it pins |
|---|---|
| `test_two_concurrent_dispatchers_claim_the_user_once` | the user is claimed exactly once across the two dispatchers |
| `test_two_concurrent_dispatchers_do_not_collide` | neither dispatcher raises — a constraint violation must not surface as an error |
| `test_the_claim_is_left_on_the_preference` | the winning dispatcher set the claim, and it is still there |
| `test_two_concurrent_dispatchers_produce_one_digest` | **the criterion, end to end** — one digest, and exactly one of the two compositions created it |
| `test_two_concurrent_compositions_of_the_same_digest_do_not_collide` | the composition's own guard, exercised directly: two compositions, one digest, one id, no `IntegrityError` |

**The test was checked against a broken implementation**, and the result is recorded in
the test's docstring because it corrected the design:

| What was broken | What happened |
|---|---|
| the **row lock** removed | the test **failed** — the user was claimed twice |
| only `SKIP LOCKED` removed | the test **still passed** |
| only the candidate-read's claim filter removed | the test **still passed** |
| only the re-read's claim filter removed | the test **still passed** |

**So the design had it wrong.** The guarantee is the **row lock** — the second
dispatcher waits, then re-reads and finds the row already claimed. `SKIP LOCKED` is the
**liveness** half: it stops the second dispatcher *blocking* on the row the first is
holding. The design doc and the test's assertion message now say which line is which.

### The updated tick table

`tests/worker/test_scheduling_tasks.py` — the tick's enqueue list is pinned minute by
minute, and `worker.tasks.schedule_digests` now appears in **every** row. The two
cadences that *do* nest (the reconciler's five minutes and the refresh's fifteen) are
the ones that vary; the digest dispatcher is the one job that is always there.

---

## The failures the tests found

**Four real defects, and one of them was silent.**

### 1. The aware/naive time comparison — the silent one

`_local_time` used `timetz()`, which returns an **aware** time carrying the zone's
offset. The preference's `delivery_time` is a **naive** `HH:MM` wall clock.

**Python does not raise when an aware time is compared with a naive one.** It orders
them by their UTC equivalents and answers. So `timetz() >= delivery_time` returned the
**wrong answer** — quietly, for every user in every zone with a non-zero offset. A
Los Angeles user asking for 09:00 read as due only from 17:00 UTC, because the
offset-bearing "09:00 PST" was compared as if it were 17:00.

The fix is `.time()` instead of `.timetz()`: the conversion already accounts for the
offset, and carrying it into the comparison applies it twice.

**It was caught by `test_a_user_is_due_exactly_at_their_delivery_time`** — the
inclusive-boundary test — because that test's `NOW` is chosen to be 09:00 *local*. A
test that had used a fixed UTC hour would have agreed with the broken implementation.

### 2. The test's `NOW` was wrong

The first `NOW` was 16:00 UTC, described as "09:00 in Los Angeles". PST is UTC−8, so
09:00 Pacific is **17:00 UTC**. The comment and the value disagreed, and the value was
wrong.

### 3. The spring-forward date was wrong

The design said "2026-03-08 is the US spring-forward" and then used 17:00 UTC as 09:00
PST *on that date* — but the transition happens at 02:00 local **on** 2026-03-08, so
that morning is already PDT. The two 9ams are 2026-03-07 at 17:00 UTC and 2026-03-09
at 16:00 UTC.

The review added `test_the_utc_instant_of_a_local_delivery_time_moves_with_the_clocks`
for the property that actually matters: **the two 9ams are different instants**.

### 4. The factory's `user_id=None` was written to the column

`DigestPreferenceFactory(user_id=None)` writes `NULL` — the `LazyFunction` default is
overridden by an explicit `None`. Every test that passed `user_id=None` hit
`null value in column "user_id" violates not-null constraint`. The helper now only
passes `user_id` when it has one.

---

## The gate

```
uv run pytest --cov --cov-report=term-missing -q
→ 3888 passed, 99.19% total coverage

uv run ruff check .
→ All checks passed!

uv run ruff format --check .
→ 419 files already formatted

uv run lint-imports
→ Contracts: 19 kept, 0 broken.

uv run coverage report --include='domain/*' --fail-under=100
→ TOTAL 750 0 100%

uv run python manage.py makemigrations --check --dry-run
→ No changes detected

uv run python manage.py export_openapi_schema --api config.api.api --indent 2 --sorted \
      --output ../frontend/lib/api/openapi.json
→ no diff — the API surface is unchanged, as D5 predicts

pnpm --dir frontend typecheck
→ Types generated successfully

pnpm --dir frontend lint
→ (clean)
```

**The contract did not change.** This item adds no endpoint: the enqueue is a
background job, not a route, and the command is a management command. The design
predicted this and the generator agreed.

**The frontend is untouched** by this item, so the node engine warning
(`wanted: node >=24.15, current: 24.14.1`) is pre-existing and unrelated.

### Coverage of the new code

```
apps/personalization/services/digest_enqueue.py          8      0  100%
apps/personalization/services/digest_scheduling.py       49      0  100%
config/management/commands/compose_digest.py             44      0  100%
worker/tasks.py                                         (the two new tasks)  100%

TOTAL (the eight new/changed files)                    513      0  100%
```

Every new module is at **100%**. The last line to be covered was the command's
"already existed" branch — the case where the command reaches a user whose digest was
composed between the scheduler's read and its claim — and a test now drives it.

---

## The acceptance criteria

| Criterion | Met by |
|---|---|
| The digest is composed on a schedule, as worker work | `schedule_digests` + `compose_digest_task`, in `worker/tasks.py` |
| The composition happens at or before the user's delivery time | `is_due` compares the local wall clock inclusively; the dispatcher composes as soon as it is due |
| The first digest is composed as soon as onboarding completes | all three completion paths enqueue it, after the commit |
| The schedule hangs off the single tick | the tick enqueues `schedule_digests`; the beat schedule is unchanged and pinned |
| Two dispatchers never compose the same digest twice | the `FOR UPDATE SKIP LOCKED` claim, the TTL, and the release in a `finally` |
| The composition is idempotent | the composition service returns the existing digest with `created=False`; the command and the dispatcher both rely on it |
| No request handler composes | the AST boundary test, 9 API modules |
| The command composes on demand | `manage.py compose_digest --user-id` / `--all` |

---

## What the tests do not cover

- **The broker is never real.** Every enqueue is intercepted by the `enqueued` fixture
  or by a patched `_send`, so the tests prove *what would be sent*, not that Redis
  accepts it. The wiring from `current_app.send_task` to a live broker is Celery's.
- **The worker's *actual* Celery registration is not exercised** beyond the dotted
  names. A task that is registered but not routed would pass these tests.
- **The command's `--all` mode is tested against the wall clock**, so its delivery
  times are relative to "now". That is honest — the command composes against the real
  clock — but it means the test cannot pin an exact date.
- **No test composes a digest with real candidates through the dispatcher.** The
  dispatcher's job is the *claim*; the composition itself is `digest-composition`'s
  subject, and its 52 tests cover it.
- **The concurrency tests race two threads, not two processes.** The claim is a
  database row lock, so the mechanism is the same either way — but a test of two
  *processes* would additionally exercise the connection pool's behaviour under
  contention, which is Celery's and psycopg's, not this item's.
- **The concurrency tests do not assert *which* dispatcher won.** They assert the
  outcome — one claim, one digest — because which thread wins is a scheduling detail
  with no bearing on the guarantee.
