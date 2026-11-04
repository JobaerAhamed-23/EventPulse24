# Backend Research: The Revalidation Signal

**Scope:** backend side of the "revalidation signal" feature (public-pages-and-seo / `revalidation-signal` work item).
**Date:** 2026-11-02
**Branch:** `feature/public-pages-and-seo`
**Status:** Research only. No project file was edited.

Every claim below is a file:line reference or an exact quote from the repository at the state
of commit `52080a0` plus the uncommitted working-tree changes listed in `git status`.

---

## Table of contents

1. [`Event.LIFECYCLE_FIELDS`](#1-eventlifecycle_fields)
2. [The `catalog.guard_event_write` trigger](#2-the-catalogguard_event_write-trigger)
3. [`backend/worker/tasks.py` — the tick, `_enqueue`, task registration, retries](#3-backendworkertaskspy--the-tick-_enqueue-task-registration-retries)
4. [`propagate_state_change`](#4-propagate_state_change)
5. [Post-commit patterns (`on_commit`) — every usage site](#5-post-commit-patterns-on_commit--every-usage-site)
6. [Outbound HTTP — the `http-client` contract, `SourceFetchPort`, the adapter/port pattern](#6-outbound-http--the-http-client-contract-sourcefetchport-the-adapterport-pattern)
7. [Credentials and secrets](#7-credentials-and-secrets)
8. [`catalog_read.py` — `get_public_event_by_slug` and `PublicEventPage`](#8-catalog_readpy--get_public_event_by_slug-and-publiceventpage)
9. [Redis / queue / cache infrastructure](#9-redis--queue--cache-infrastructure)
10. [The `personal` vs `catalog` DB aliases, and how a worker task reaches the catalog](#10-the-personal-vs-catalog-db-aliases-and-how-a-worker-task-reaches-the-catalog)
11. [Existing webhook / notify / signal / publish concepts](#11-existing-webhook--notify--signal--publish-concepts)
12. [Appendix A — the frontend's side (context only)](#12-appendix-a--the-frontends-side-context-only)
13. [Appendix B — test seams and fixtures](#13-appendix-b--test-seams-and-fixtures)
14. [Appendix C — design-relevant observations](#14-appendix-c--design-relevant-observations)

---

## 1. `Event.LIFECYCLE_FIELDS`

### 1.1 Location and exact contents

**File:** `backend/apps/ingestion/models.py`
**Lines:** 243–251

```python
    # Mirrors the trigger in migration 0001: a change to any of these needs a version bump.
    LIFECYCLE_FIELDS: ClassVar[tuple[str, ...]] = (
        "start_time_utc",
        "end_time_utc",
        "start_time_tz",
        "status",
        "is_sold_out",
        "venue",
        "superseded_by",
    )
```

**Type:** `ClassVar[tuple[str, ...]]` — exactly 7 entries, in this exact order:

| # | Field | Model column | Notes |
|---|-------|--------------|-------|
| 1 | `start_time_utc` | `start_time_utc` | `models.DateTimeField()` (`models.py:269`) |
| 2 | `end_time_utc` | `end_time_utc` | nullable (`models.py:273`) |
| 3 | `start_time_tz` | `start_time_tz` | IANA name, `max_length=64` (`models.py:277`) |
| 4 | `status` | `status` | `scheduled`/`postponed`/`cancelled`/`superseded` (`models.py:236-240`, `284`) |
| 5 | `is_sold_out` | `is_sold_out` | `BooleanField(default=False)` (`models.py:285`) |
| 6 | `venue` | `venue_id` (FK to `Venue`) | nullable, `on_delete=PROTECT` (`models.py:263-265`) |
| 7 | `superseded_by` | `superseded_by_id` (self-FK) | nullable, `on_delete=PROTECT` (`models.py:288-290`) |

### 1.2 Important caveats

- **The Python tuple and the SQL trigger are two separate lists that must be kept in step.**
  The model comment says so explicitly (`models.py:242`: *"Mirrors the trigger in migration 0001: a change to any of these needs a version bump."*). The SQL comment says the same in reverse
  (`migrations/0001_initial.py:37-38`: *"Keep the column list in step with apps.ingestion.models.Event.LIFECYCLE_FIELDS."*).
  **There is no test that pins them to each other in this repo** — I searched; the only
  references to `LIFECYCLE_FIELDS` are `models.py` itself and the two comments. A design
  that relies on the tuple MUST either add such a test or read the SQL directly.

- **`venue` and `superseded_by` are FK *names*, not column names.** The column is
  `venue_id` / `superseded_by_id`. The trigger compares `NEW.venue_id IS DISTINCT FROM OLD.venue_id`.
  So `LIFECYCLE_FIELDS` mixes field names and column names. Any code that maps a
  `LIFECYCLE_FIELDS` entry to a DB column must special-case those two (Django's
  `attname`).

- **`LIFECYCLE_FIELDS` is NOT the set of facts a public page renders.** The public page
  (`PublicEventPage`, see §8) also renders `title`, `description`, `canonical_url`,
  `venue_name`, `venue_city`, `venue_country_code`, `venue_address`, `source_name`.
  **`title`/`description`/`canonical_url` changes do NOT bump `event_version`** — they go
  through `apply_silent_update` (`apps/ingestion/services/event_writes.py:228-239`), which
  deliberately writes **no version bump and no state change**:
  > *"Title, description and URL (and the gates) follow the source with no version bump and no state change (D9): live reads show the new text, and nobody is notified of a typo fix."*

  **This is the single most important fact for the revalidation design.** A silent update
  changes what the public page renders and produces **no** `EventStateChange` row, so a
  design that listens only on state changes will **miss title and description edits**.
  `EventFit` has the same staleness concept (`event_fit/reads.py` — a fit whose
  `event_version` no longer matches its Event is stale and is never served).

- `publication_status` (`published`/`in_review`) is also **not** in `LIFECYCLE_FIELDS`.
  It is written by `IncomingEvent.gating()` (`event_writes.py:90-97`) which rides along in
  both `apply_lifecycle_change` (first statement) and `apply_silent_update`. So an
  unpublish may or may not bump the version depending on which path it took.

---

## 2. The `catalog.guard_event_write` trigger

### 2.1 Which migration defines it

**File:** `backend/apps/ingestion/migrations/0001_initial.py`
**Definition:** lines 39–69 (inside the `TRIGGERS` string constant, lines 15–83)
**Applied:** line 721 — `migrations.RunSQL(TRIGGERS, reverse_sql=DROP_TRIGGERS)`
**Trigger bindings:** lines 77–82
**Reversal:** `DROP_TRIGGERS` string, lines 85–92

The migration comment at line 13 states: *"Every name is schema-qualified: this migration runs on the `catalog` alias as the owner role."*

### 2.2 The exact SQL (quoted verbatim)

```sql
-- Event versioning and lifecycle (D7, D10). Keep the column list in step with
-- apps.ingestion.models.Event.LIFECYCLE_FIELDS.
CREATE FUNCTION catalog.guard_event_write() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'INSERT' THEN
    IF NEW.event_version <> 1 OR NEW.status = 'superseded' THEN
      RAISE EXCEPTION 'a new Event starts at event_version 1 and is not superseded'
        USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
  END IF;
  IF OLD.status = 'superseded' THEN
    RAISE EXCEPTION 'superseded Event % is terminal', OLD.id USING ERRCODE = 'restrict_violation';
  END IF;
  IF NEW.event_version NOT IN (OLD.event_version, OLD.event_version + 1) THEN
    RAISE EXCEPTION 'event_version may only stay or rise by 1 (% -> %)',
      OLD.event_version, NEW.event_version USING ERRCODE = 'restrict_violation';
  END IF;
  IF NEW.event_version = OLD.event_version AND (
       NEW.start_time_utc IS DISTINCT FROM OLD.start_time_utc
    OR NEW.end_time_utc IS DISTINCT FROM OLD.end_time_utc
    OR NEW.start_time_tz IS DISTINCT FROM OLD.start_time_tz
    OR NEW.status IS DISTINCT FROM OLD.status
    OR NEW.is_sold_out IS DISTINCT FROM OLD.is_sold_out
    OR NEW.venue_id IS DISTINCT FROM OLD.venue_id
    OR NEW.superseded_by_id IS DISTINCT FROM OLD.superseded_by_id) THEN
    RAISE EXCEPTION 'a lifecycle change to Event % needs event_version + 1', OLD.id
      USING ERRCODE = 'restrict_violation';
  END IF;
  RETURN NEW;
END
$$;

CREATE TRIGGER event_guard_insert
  BEFORE INSERT ON catalog.ingestion_event
  FOR EACH ROW EXECUTE FUNCTION catalog.guard_event_write();
CREATE TRIGGER event_guard_update
  BEFORE UPDATE ON catalog.ingestion_event
  FOR EACH ROW EXECUTE FUNCTION catalog.guard_event_write();
```

### 2.3 What it enforces, precisely

1. **INSERT:** `event_version` must be exactly `1` and `status` must not be `'superseded'`.
2. **UPDATE of a superseded Event:** any update to a row whose `OLD.status = 'superseded'`
   raises. **Superseded is terminal.**
3. **UPDATE:** `event_version` may only stay the same or rise by exactly 1 **per statement**.
   (A change of *k* kinds therefore takes *k* statements — see `event_writes.py:197-201`.)
4. **UPDATE:** if `event_version` did **not** change, then none of the 7 lifecycle columns may
   have changed. If any did, raise `'a lifecycle change to Event % needs event_version + 1'`.

**Corollary the design must respect:** the trigger does **not** require a version bump for
changes to `title`, `description`, `canonical_url`, `publication_status`,
`tz_review_pending`, `tz_inference_confidence`, `extraction_confidence`, `series_id`,
`first_seen_at`, `last_seen_at`. A design that uses `event_version` as the "did anything
visible change" signal will miss those.

### 2.4 The other trigger in the same migration (relevant: `propagated_at`)

`forbid_history_mutation()` — `migrations/0001_initial.py:19-35`:

```sql
CREATE FUNCTION catalog.forbid_history_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    IF current_setting('eventpulse.retention_purge', true) = 'on' THEN
      RETURN OLD;
    END IF;
  ELSIF TG_NARGS = 1 THEN
    IF (to_jsonb(OLD) ->> TG_ARGV[0]) IS NULL
       AND (to_jsonb(NEW) ->> TG_ARGV[0]) IS NOT NULL
       AND (to_jsonb(NEW) - TG_ARGV[0]) IS NOT DISTINCT FROM (to_jsonb(OLD) - TG_ARGV[0]) THEN
      RETURN NEW;
    END IF;
  END IF;
  RAISE EXCEPTION '% is append-only', TG_TABLE_NAME USING ERRCODE = 'restrict_violation';
END
$$;
```

Applied to `catalog.ingestion_eventstatechange` with `'propagated_at'` as the one mutable
column (`migrations/0001_initial.py:71-73`):

```sql
CREATE TRIGGER eventstatechange_append_only
  BEFORE UPDATE OR DELETE ON catalog.ingestion_eventstatechange
  FOR EACH ROW EXECUTE FUNCTION catalog.forbid_history_mutation('propagated_at');
```

**Design consequence:** `EventStateChange` is append-only. The **only** mutable column is
`propagated_at`, and it may only go NULL → a value. **A design cannot add a
"revalidated_at" or "delivered_at" column to `EventStateChange`** without a new migration
(and a new trigger argument, or a new column in the `to_jsonb` subtraction set). If a
revalidation ledger is needed, it must be a **separate table** (like `EventStateChange`
itself is separate from `Event`).

### 2.5 Grants (same migration)

`migrations/0001_initial.py:96-112`:

```sql
REVOKE UPDATE, DELETE ON catalog.ingestion_eventstatechange, catalog.ingestion_ingestionauditentry
  FROM ep_catalog;
GRANT UPDATE (propagated_at) ON catalog.ingestion_eventstatechange TO ep_catalog;
```

Plus a `DO` block that raises if the privileges were not applied (lines 100–111). The
runtime role `ep_catalog` can INSERT/SELECT but only set `propagated_at`.

---

## 3. `backend/worker/tasks.py` — the tick, `_enqueue`, task registration, retries

### 3.1 The module docstring (verbatim, lines 1–5)

```python
"""Worker tasks. Beat and the Celery app find these by dotted string (`config/celery.py`).

Each task wraps one `ingestion` command and returns None (Celery would otherwise log the return
value). Jobs are sent through `_enqueue`, the single seam tests replace.
"""
```

### 3.2 The `_enqueue` helper — exact signature

**File:** `backend/worker/tasks.py`, **lines 40–41**

```python
def _enqueue(task, *args) -> None:
    task.delay(*args)
```

- **Signature:** `_enqueue(task, *args) -> None` — untyped parameters, `task` is a Celery
  task object (has `.delay`), `*args` are the task's positional arguments.
- **Queue backend:** **Celery 5.6.3 with the Redis broker** (`celery[redis]==5.6.3` in
  `backend/pyproject.toml:13`; `CELERY_BROKER_URL = env.redis_url` in
  `backend/config/settings.py:189`).
- **No result backend:** `CELERY_TASK_IGNORE_RESULT = True` (`config/settings.py:191`) —
  *"no result backend: tasks report through the database"*.
- **The seam:** `tests/worker/conftest.py:8-13` monkeypatches `tasks._enqueue` for every
  worker test.

### 3.3 The Celery app

**File:** `backend/config/celery.py`

```python
TRACE_HEADER = "trace_id"
TICK_SECONDS = 60.0

app = Celery("eventpulse24", include=["worker.tasks"])
app.config_from_object("django.conf:settings", namespace="CELERY")

app.conf.beat_schedule = {
    "tick": {"task": "worker.tasks.tick", "schedule": TICK_SECONDS},
}
```
(`config/celery.py:18-28`)

- **One static beat entry:** `worker.tasks.tick`, every **60.0 seconds**.
- **No `django-celery-beat`** — the comment at `config/celery.py:25-26` says so.
- The app is loaded by `config/__init__.py:4` (`from config.celery import app as celery_app`),
  so `shared_task`s bind to it in both runtimes.

### 3.4 The 60-second tick pattern — `tick`

**File:** `backend/worker/tasks.py`, **lines 44–83**

```python
@shared_task(name="worker.tasks.tick")
def tick() -> None:
    """The periodic tick (AD-7): the only beat entry. It enqueues and never touches the
    database, so a slow query can't delay the next tick.
    ...
    """
    _enqueue(schedule_sources)
    _enqueue(schedule_calendars)
    _enqueue(schedule_digests)
    _enqueue(sweep_due_sends)
    if _now().minute % OUTBOX_RECONCILE_EVERY_MINUTES == 0:
        _enqueue(reconcile_outbox)
    if _now().minute % EVENT_FIT_REFRESH_EVERY_MINUTES == 0:
        _enqueue(refresh_event_fits)
    logger.info("Tick", extra={"job": "tick"})
```

**Key properties:**
- The tick **never touches the database**. It only enqueues.
- 4 jobs on every tick + 2 conditional jobs on minute-modulo cadences.
- Cadence constants (`shared/constants.py`):
  - `OUTBOX_RECONCILE_EVERY_MINUTES = 5` (line 81)
  - `EVENT_FIT_REFRESH_EVERY_MINUTES = 15` (line 90)
- **The tick's docstring explicitly warns** (`tasks.py:56-58`):
  > *"The two cadences nest — every multiple of 15 is also a multiple of 5 — so the refresh always lands on a reconciler minute. That is a consequence of the numbers, not a design: the refresh's cadence is a divisor of the reconciler's, and if the two are ever made independent, the tick test that pins the enqueue order will say so."*

  → **`tests/worker/test_tick.py` pins the enqueue order.** Adding a tick entry will break that test. Read it before changing `tick`.

### 3.5 Task registration — every `@shared_task` in the file

All tasks are `@shared_task(name="worker.tasks.<x>")`. Full inventory:

| Line | Task name | Function | Signature |
|------|-----------|----------|-----------|
| 44 | `worker.tasks.tick` | `tick` | `() -> None` |
| 86 | `worker.tasks.refresh_event_fits` | `refresh_event_fits` | `() -> None` |
| 110 | `worker.tasks.schedule_sources` | `schedule_sources` | `() -> None` |
| 132 | `worker.tasks.ingest_source` | `ingest_source` | `(source_id: str) -> None` |
| 154 | `worker.tasks.propagate_state_change` | `propagate_state_change` | `(state_change_id: str) -> None` |
| 165 | `worker.tasks.schedule_calendars` | `schedule_calendars` | `() -> None` |
| 194 | `worker.tasks.sync_calendar` | `sync_calendar` | `(connection_id: str) -> None` |
| 231 | `worker.tasks.reconcile_outbox` | `reconcile_outbox` | `() -> None` |
| 238 | `worker.tasks.schedule_digests` | `schedule_digests` | `() -> None` |
| 272 | `worker.tasks.compose_digest` | `compose_digest_task` | `(user_id: str) -> None` |
| 344 | `worker.tasks.sweep_due_sends` | `sweep_due_sends` | `() -> None` |

**Note the naming asymmetry:** the function is `compose_digest_task` but the task name is
`worker.tasks.compose_digest` (`tasks.py:272-273`).

**No task uses `bind=True`, `autoretry_for`, `retry_backoff`, `max_retries`, `acks_late`,
or `self.retry()`.** I grepped the whole backend: there are **zero** occurrences of
`self.retry`, `autoretry`, `retry_backoff`, `max_retries`, or `acks_late`. See §3.7.

### 3.6 The dispatcher → claim → enqueue → release pattern (the canonical shape)

This 4-step shape is repeated three times (`schedule_sources` 110–129,
`schedule_calendars` 165–191, `schedule_digests` 238–269). Verbatim from
`tasks.py:110-129`:

```python
@shared_task(name="worker.tasks.schedule_sources")
def schedule_sources() -> None:
    """Flag stale sources, claim the due ones and enqueue one ingest job per claim (FR-13)."""
    now = _now()
    stale = scheduling.flag_stale_sources(now=now)
    claimed = scheduling.claim_due_sources(now=now)
    enqueued = 0
    for source_id in claimed:
        try:
            _enqueue(ingest_source, str(source_id))
            enqueued += 1
        except Exception as exc:  # broker down: free the claim so the next tick retries
            scheduling.release_claim(source_id)
            logger.warning(
                "Ingest not enqueued",
                extra={"source_id": source_id, "error_type": type(exc).__name__},
            )
    logger.info("Sources scheduled", extra={"job": "schedule_sources", "count": enqueued})
    if stale:
        logger.warning("Sources stale", extra={"job": "schedule_sources", "count": stale})
```

**The four steps:**
1. **Claim** — `claim_due_sources(now=now)` (`apps/ingestion/services/scheduling.py:38-65`)
   uses `select_for_update(skip_locked=True)` inside `transaction.atomic(using=CATALOG)`,
   and stamps `ingest_claimed_at=now`.
2. **Enqueue** — one job per claim, via `_enqueue`.
3. **Release on enqueue failure** — `except Exception: scheduling.release_claim(source_id)`
   so the *next tick* retries rather than waiting for the TTL.
4. **Release in `finally`** in the worker task itself (`tasks.py:143-144`).

### 3.7 Existing retry / backoff patterns

**There is no Celery-level retry anywhere.** The project's retry strategy is
**"record it on the row, retry at the next cadence, never re-run the batch."**

| Situation | Pattern | Source |
|---|---|---|
| Provider call fails | Log + swallow; the row owns the outcome | `tasks.py:375-387` (`sweep_due_sends`) — *"A failure in the sweep does not reach Celery as a retry… The exception is logged and swallowed; the rows own the outcome."* |
| Unexpected exception in a worker job | Log + **`raise`** so Celery sees it and retries | `tasks.py:330-339` (`compose_digest_task`), `tasks.py:216-226` (`sync_calendar`) |
| Business errors (paused, ToS, missing) | Catch specific exceptions, log, skip | `tasks.py:141-142` (`ingest_source`) |
| Broker down at enqueue | Release the claim; the next tick retries | `tasks.py:121-126` and its two twins |
| Email send retries | Bounded count on the row: `SEND_MAX_ATTEMPTS = 3` | `shared/constants.py:850` |
| Unpropagated outbox rows | Time-based reconciler re-offers them | `apps/ingestion/services/outbox.py:43-56` |

**The canonical "raise so Celery retries" shape** (`tasks.py:330-341`):

```python
    except Exception as exc:
        logger.warning(
            "Digest composition failed",
            extra={
                "job": "compose_digest",
                "user_id": str(identifier),
                "error_type": type(exc).__name__,
            },
        )
        raise
    finally:
        digest_scheduling.release_claim(identifier)
```

**Design implication:** because there is no `max_retries`/`retry_backoff` anywhere, the
"retried and surfaced" acceptance criterion in the work item has **no existing machinery**.
A new retry policy must be built — either at the Celery level (`autoretry_for` /
`max_retries` / `retry_backoff`) or with a row-owned bounded counter (the pattern
`ScheduledSend` already uses).

### 3.8 The logging convention

- `logger = logging.getLogger(__name__)` (`tasks.py:33`).
- `extra={"job": "<job_name>", ...}` on every line.
- **No PII** (AD-13). The `compose_digest_task` docstring explains the shape
  (`tasks.py:313-329`): `digest_created`, `is_empty`, `ping_minted`, `ping_suppressed`,
  `ping_reason` — and the comment at line 318-319 explains why the key is not `created`:
  > *"`LogRecord` already has a field by that name, and `extra` may not shadow one."*

### 3.9 The trace-id plumbing (`config/celery.py`)

- `@before_task_publish.connect` → `attach_trace_id` sets a `trace_id` header
  (`config/celery.py:39-43`).
- `@task_prerun.connect` → `bind_task_trace_id` reads the inbound header or mints
  `uuid7().hex` (`config/celery.py:50-58`).
- `@task_postrun.connect` → `reset_task_trace_id` (`config/celery.py:61-65`).
- `@setup_logging.connect` → `keep_django_logging` prevents Celery from installing its own
  unredacted handlers (`config/celery.py:31-36`).

---

## 4. `propagate_state_change`

### 4.1 It is a no-op placeholder

**File:** `backend/worker/tasks.py`, **lines 147–162** (comment block + task)

```python
# The `delivery` half of AD-17 already exists and is tested:
# `apps.delivery.services.scheduled_sends.apply_lifecycle_change`. It is deliberately NOT
# called from here yet — `propagated_at` may only be set once *every* owner has applied a
# change, and the `personalization` half (SAVED_EVENT snapshot + conflict re-evaluation) is
# FR-53/54 work. Wiring one half would either churn the outbox forever or make the future
# consumer skip these changes. Decided with the user 2026-10-31; see the delivery-and-reminders
# brief and `send-minting-and-rescheduling-design.md` D8.
@shared_task(name="worker.tasks.propagate_state_change")
def propagate_state_change(state_change_id: str) -> None:
    """AD-17 placeholder consumer: no propagation into `personal` exists yet (FR-53-55).

    It deliberately leaves `propagated_at` NULL: marking the row would claim a propagation that
    never happened, and the real consumer would then skip it. The reconciler keeps re-offering
    it until that consumer arrives.
    """
    logger.debug("State change not propagated yet", extra={"state_change_id": state_change_id})
```

**It is a genuine no-op.** It logs at DEBUG and returns. It does not touch the database.

### 4.2 Who calls it

**Callers of `propagate_state_change`:**

| Caller | Location | Mechanism |
|---|---|---|
| `outbox.enqueue_propagation` | `apps/ingestion/services/outbox.py:25-27` | `current_app.send_task(PROPAGATE_TASK, [str(id)])` |
| `outbox.reconcile_outbox` | `apps/ingestion/services/outbox.py:43-56` | re-offers rows older than `OUTBOX_RECONCILE_AFTER` |
| `outbox._send` (the seam) | `apps/ingestion/services/outbox.py:21-22` | `current_app.send_task(task_name, args=args)` |

`PROPAGATE_TASK = "worker.tasks.propagate_state_change"` — `apps/ingestion/services/outbox.py:18`

**Call chain from a lifecycle change:**

```
Event write (event_writes._record_change)
  └─ transaction.on_commit(partial(enqueue_propagation, change.id), using=CATALOG, robust=True)
       └─ outbox.enqueue_propagation(change.id)
            └─ outbox._send(PROPAGATE_TASK, [str(change.id)])
                 └─ celery.current_app.send_task(...)      → Redis broker
                      └─ worker.tasks.propagate_state_change(state_change_id)   [NO-OP]
```

**Reconciler path:**

```
worker.tasks.tick  (every 5th minute)
  └─ _enqueue(reconcile_outbox)
       └─ worker.tasks.reconcile_outbox()
            └─ outbox.reconcile_outbox()
                 └─ for each id: enqueue_propagation(id)
```

### 4.3 How it fans out on lifecycle changes — it does not

`propagate_state_change` **does not fan out at all**. It is the *terminal* consumer
placeholder. The fan-out structure is:

- **The producer** is `_record_change` in `apps/ingestion/services/event_writes.py:153-177`.
  It is called **once per lifecycle kind** by `apply_lifecycle_change`
  (`event_writes.py:189-225`) and **once** by `supersede_event` (`event_writes.py:242-282`).
- **`apply_lifecycle_change` writes one `EventStateChange` row per kind.** The docstring
  (`event_writes.py:197-201`):
  > *"The first statement writes every fact at version + 1; each further kind is a bump-only statement, so the versions are v+1..v+k (the trigger allows +1 per statement)."*

  So **one lifecycle change of k kinds produces k `EventStateChange` rows and therefore k
  `on_commit` enqueues.**
- **`EventStateChange.Kind` values** (`apps/ingestion/models.py:468-475`):
  `time_moved`, `postponed`, `cancelled`, `reinstated`, `sold_out`, `detail_changed`,
  `superseded`.

**Important gap:** `apply_silent_update` (`event_writes.py:228-239`) writes **no**
`EventStateChange` and therefore **no** `on_commit` enqueue. Title/description/URL changes
are invisible to the outbox.

### 4.4 The `EventStateChange` model

**File:** `apps/ingestion/models.py:461-505`

```python
class EventStateChange(AppendOnlyModel, ActorColumns, UUIDv7Model):
    class Kind(models.TextChoices):
        TIME_MOVED = "time_moved"
        POSTPONED = "postponed"
        CANCELLED = "cancelled"
        REINSTATED = "reinstated"  # cancelled -> live again, or postponed -> scheduled (D12)
        SOLD_OUT = "sold_out"
        DETAIL_CHANGED = "detail_changed"
        SUPERSEDED = "superseded"

    retention_category = RetentionCategory.SOURCE_REGISTRY
    append_only_mutable = frozenset({"propagated_at"})

    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name="state_changes")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    event_version = models.PositiveIntegerField()  # the Event's version after this change
    before = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    after = models.JSONField(default=dict, encoder=DjangoJSONEncoder)
    occurred_at = models.DateTimeField(default=timezone.now)
    propagated_at = models.DateTimeField(null=True, blank=True)
```

Constraints (`models.py:488-505`):
- `state_change_version_uq` — `UniqueConstraint(fields=["event", "event_version"])`
- `state_change_version_positive_ck` — `event_version >= 1`
- `state_change_actor_ck` — `actor_check("state_change_actor_ck")`
- Index `state_change_unpropagated_idx` — `fields=["occurred_at"]`,
  `condition=Q(propagated_at__isnull=True)`

**Note:** the `UniqueConstraint` on `(event, event_version)` means **at most one state change
per event version**. Combined with `apply_lifecycle_change`'s one-row-per-kind behaviour
(which bumps the version once per kind), the versions line up 1:1.

### 4.5 The outbox module in full

**File:** `backend/apps/ingestion/services/outbox.py` (57 lines, complete)

```python
"""The AD-17 outbox: enqueue propagation for committed state changes, and the reconciler that
re-enqueues the ones nobody has propagated.

`ingestion` can't import `worker` or `config` (layers), so jobs are sent by task name through
the Celery app `config/__init__` loads. `_send` is the single seam; tests replace it.
"""

from datetime import datetime
from uuid import UUID

from celery import current_app
from django.utils import timezone

from apps.ingestion.models import EventStateChange
from shared.constants import OUTBOX_RECONCILE_AFTER, OUTBOX_RECONCILE_BATCH
from shared.db import CATALOG

PROPAGATE_TASK = "worker.tasks.propagate_state_change"


def _send(task_name: str, args: list[str]) -> None:
    current_app.send_task(task_name, args=args)


def enqueue_propagation(state_change_id: UUID) -> None:
    """Queue one state change for propagation. Run it from `on_commit(using=CATALOG)` only."""
    _send(PROPAGATE_TASK, [str(state_change_id)])


def mark_propagated(state_change_id: UUID, *, now: datetime | None = None) -> bool:
    """Record that a state change reached `personal` (design D23). False if it already had.

    The conditional form is idempotent under the job's retries and the reconciler.
    """
    updated = (
        EventStateChange.objects.using(CATALOG)
        .filter(pk=state_change_id, propagated_at__isnull=True)
        .update(propagated_at=now or timezone.now())
    )
    return updated == 1


def reconcile_outbox(*, now: datetime | None = None, limit: int = OUTBOX_RECONCILE_BATCH) -> int:
    """Re-enqueue the oldest state changes unpropagated for longer than
    `OUTBOX_RECONCILE_AFTER`, at most `limit` of them. Returns how many were enqueued.
    """
    cutoff = (now or timezone.now()) - OUTBOX_RECONCILE_AFTER
    ids = list(
        EventStateChange.objects.using(CATALOG)
        .filter(propagated_at__isnull=True, occurred_at__lt=cutoff)
        .order_by("occurred_at", "id")
        .values_list("id", flat=True)[:limit]
    )
    for state_change_id in ids:
        enqueue_propagation(state_change_id)
    return len(ids)
```

### 4.6 `scheduled_sends.apply_lifecycle_change` — the unwired consumer

- `apps/delivery/services/scheduled_sends.py:51` — *"**`propagate_state_change` is deliberately not wired to this module yet.** AD-17 sets…"*
- `apps/delivery/services/scheduled_sends.py:659` — *"Not wired to `propagate_state_change` yet; see the module docstring."*

### 4.7 Design summary for `propagate_state_change`

- It is a **placeholder**, and it is deliberately a no-op.
- Its `propagated_at`-never-set behaviour means the reconciler **re-offers every
  unpropagated state change every 5 minutes forever**. Today that is harmless (the task
  does nothing). **If the revalidation feature wires into this task, the reconciler will
  re-deliver the same signal every 5 minutes** — which is arguably the "retry" mechanism,
  but it also means the reconciler is not a *bounded* retry and the row never leaves the
  unpropagated set.
- `mark_propagated` (`outbox.py:30-40`) is the existing idempotency primitive: a
  conditional `UPDATE ... WHERE propagated_at IS NULL` returning `True` only on the first
  write. **A revalidation feature can reuse this exact pattern** for a "delivered" marker.

---

## 5. Post-commit patterns (`on_commit`) — every usage site

I searched for `on_commit`, `transaction.on_commit`, `transactional.on_commit` across the
whole backend. There are **exactly two production `on_commit` call sites** and one
non-production reference in `apps/personalization/services/onboarding.py` that *documents*
the pattern (the actual call is elsewhere).

### 5.1 Production call site 1 — the outbox (catalog)

**File:** `backend/apps/ingestion/services/event_writes.py`, **line 176**

```python
    # robust: a failed enqueue (broker down) is logged and the item stays committed; the next
    # callbacks still run, and the reconciler re-sends what was lost (AD-17).
    transaction.on_commit(partial(enqueue_propagation, change.id), using=CATALOG, robust=True)
```

Full enclosing function — `_record_change`, `event_writes.py:153-177`:

```python
def _record_change(
    *,
    event_id: UUID,
    kind: str,
    version: int,
    before: dict,
    after: dict,
    actor: Actor,
    now: datetime,
) -> EventStateChange:
    change = EventStateChange.objects.using(CATALOG).create(
        event_id=event_id,
        kind=kind,
        event_version=version,
        before=before,
        after=after,
        occurred_at=now,
        actor_kind=actor.kind,
        actor_id=actor.id,
        actor_label=actor.label,
    )
    transaction.on_commit(partial(enqueue_propagation, change.id), using=CATALOG, robust=True)
    return change
```

**Properties:**
- `using=CATALOG` — the callback is bound to the **catalog** connection's transaction.
- `robust=True` — a broker outage logs and does not roll back the transaction.
- The payload is `partial(enqueue_propagation, change.id)` — a **UUID**, no PII.

### 5.2 Production call site 2 — the digest enqueue (personal)

**File:** `backend/apps/personalization/services/onboarding.py`, **lines 444–448**

```python
    transaction.on_commit(
        partial(enqueue_digest_composition, user_id),
        using=PERSONAL,
        robust=True,
    )
```

Enclosing function — `_enqueue_first_digest`, `onboarding.py:428-448`. Its docstring is
the canonical statement of the pattern (`onboarding.py:429-443`):

> *"**The enqueue is registered, not performed.** The composition reads the digest preference, and a job enqueued *inside* the transaction would run before the commit and find no preference — it would compose nothing. So the enqueue is registered with `transaction.on_commit`, which runs it once the command's work is durable.*
>
> ***`robust=True` means a broker outage does not fail the onboarding.** … **The scheduler is the backstop, and the enqueue is the fast path.**"*

### 5.3 Supporting module — `digest_enqueue.py`

**File:** `backend/apps/personalization/services/digest_enqueue.py` (complete, 55 lines)

```python
COMPOSE_DIGEST_TASK = "worker.tasks.compose_digest"


def _send(task_name: str, args: list[str]) -> None:
    current_app.send_task(task_name, args=args)


def enqueue_digest_composition(user_id: UUID) -> None:
    """Queue one user's digest composition. Run it from `on_commit(using=PERSONAL)` only.

    **The user id is the only argument, and it is a UUID.** No email, no city, no
    delivery time — the worker reads what it needs from the rows, and nothing about the
    user travels through the broker (AD-13).
    """
    _send(COMPOSE_DIGEST_TASK, [str(user_id)])
```

### 5.4 The module docstring that names the pattern

**File:** `backend/apps/ingestion/services/outbox.py:4-5`
> *"`ingestion` can't import `worker` or `config` (layers), so jobs are sent by task name through the Celery app `config/__init__` loads. `_send` is the single seam; tests replace it."*

**File:** `backend/apps/ingestion/services/digest_enqueue.py:5-6`
> *"This is the same shape `apps.ingestion.services.outbox` uses for AD-17's propagation, and for the same reason."*

### 5.5 The architecture test that enforces `using=` on `on_commit`

**File:** `backend/tests/architecture/checkers.py:78-103` — `alias_violations()`

```python
            if name in ("atomic", "on_commit") and "using" not in keywords:
                violations.append(f"{node.lineno}: {name}() without using=")
```

**A new `on_commit` call without `using=` will fail the architecture test suite.**
The rule also bans string literals for `using=`:

```python
            if "using" in keywords and _is_literal(keywords["using"]):
                violations.append(f"{node.lineno}: using= literal")
```

So it must be `using=CATALOG` or `using=PERSONAL` (the `shared.db` constants).

**Related test:** `backend/tests/architecture/test_database_alias.py` (lines 24–43) pins
that `transaction.on_commit` must carry `using=`.

### 5.6 The "post-commit" test pattern

**File:** `backend/tests/ingestion/test_ingest_lifecycle.py:138-163`

```python
    source, jazz, sent_jobs, django_capture_on_commit_callbacks
...
    with django_capture_on_commit_callbacks(using=CATALOG, execute=True) as callbacks:
...
    assert sent_jobs == []  # on_commit never fired
```

This is the exact fixture for proving "the signal fires post-commit" — the acceptance
criterion in the work item. `django_capture_on_commit_callbacks` is Django's built-in test
helper.

### 5.7 Summary table — every `on_commit` site

| File | Line | Code | `using=` | `robust=` |
|------|------|------|----------|-----------|
| `backend/apps/ingestion/services/event_writes.py` | 176 | `transaction.on_commit(partial(enqueue_propagation, change.id), using=CATALOG, robust=True)` | `CATALOG` | `True` |
| `backend/apps/personalization/services/onboarding.py` | 444 | `transaction.on_commit(partial(enqueue_digest_composition, user_id), using=PERSONAL, robust=True)` | `PERSONAL` | `True` |

**Test-only references** (not production): `tests/personalization/test_digest_enqueue.py:53,63,69,253`; `tests/architecture/test_database_alias.py:24,26,43`; `tests/ingestion/test_ingest_lifecycle.py:140`.

---

## 6. Outbound HTTP — the `http-client` contract, `SourceFetchPort`, the adapter/port pattern

### 6.1 The import-linter contract

**File:** `backend/pyproject.toml`, **lines 230–252**

```toml
[[tool.importlinter.contracts]]
id = "http-client"
name = "AD-9 only adapters.crawl imports an HTTP client (source fetches go through SourceFetchPort)"
type = "forbidden"
source_modules = [
    "domain",
    "apps",
    "ports",
    "config",
    "worker",
    "shared",
    "formats",
    "adapters.billing",
    "adapters.calendar",
    "adapters.email",
    "adapters.geo",
    "adapters.llm",
    "adapters.logging",
    "adapters.throttle",
]
forbidden_modules = ["httpx", "httpcore", "requests", "urllib3"]
# Wiring the adapter in (config -> adapters.crawl -> httpx) is the intended path.
allow_indirect_imports = true
```

**Critical detail:** `allow_indirect_imports = true`. This means the contract forbids a
**direct** import of `httpx`/`httpcore`/`requests`/`urllib3` from any module in
`source_modules`, but it explicitly **allows** the `config → adapters.crawl → httpx`
wiring. It also means **`adapters.calendar` is in `source_modules`** and therefore
forbidden from importing `httpx` directly — which is exactly why the calendar adapter
reuses the crawl adapter's client (see §6.5).

Note also that `adapters.crawl` is **NOT** in `source_modules` — it is the one place that
may import an HTTP client.

### 6.2 The layers contract (which governs where a new port/adapter may live)

**File:** `backend/pyproject.toml`, **lines 91–102**

```toml
[[tool.importlinter.contracts]]
id = "layers"
name = "AD-2 layers point inward; AD-1 API and worker runtimes don't import each other"
type = "layers"
layers = [
    "config | worker",
    "apps | adapters",
    "formats",
    "ports",
    "domain",
    "shared",
]
```

**Reading:** `config` and `worker` are the outermost layer; `apps` and `adapters` sit
below them at the same level; `ports` below those; `domain` below that; `shared` at the
bottom. **A layer may import only layers below it.**

**The `worker-not-api` contract** (`pyproject.toml:104-111`):

```toml
[[tool.importlinter.contracts]]
id = "worker-not-api"
name = "AD-1 the worker never imports the API surface"
type = "forbidden"
source_modules = ["worker"]
forbidden_modules = ["apps.*.api", "config.api"]
```

So `worker/tasks.py` may not import `apps.*.api` or `config.api`.

**The `apps | adapters` separation** is enforced by the `layers` contract: `apps` and
`adapters` are at the same level, so **an `apps.*` module may not import an `adapters.*`
module.** Apps reach adapters only through `ports/registry.py`.

### 6.3 `SourceFetchPort` — the exact port

**File:** `backend/ports/fetch.py`, **lines 125–137**

```python
class SourceFetchPort(ABC):
    @abstractmethod
    def fetch(
        self,
        url: str,
        *,
        etag: str | None = None,
        last_modified: str | None = None,
        source_id: UUID | None = None,
        allow_cross_host_redirect: bool = False,
        limits: FetchLimits | None = None,
        credential: bool = False,
    ) -> FetchResult: ...
```

Supporting types in the same file:

```python
NOT_MODIFIED = 304

@dataclass(frozen=True)
class FetchLimits:
    user_agent: str
    max_bytes: int = 10 * 1024 * 1024
    dns_timeout: float = 3.0
    connect_timeout: float = 5.0
    read_timeout: float = 15.0
    write_timeout: float = 5.0
    total_timeout: float = 30.0
    max_redirects: int = 5
    allowed_ports: frozenset[int] = field(default_factory=lambda: frozenset({80, 443}))

@dataclass(frozen=True)
class FetchResult:
    status: int  # 200, 203, or 304
    final_url: str  # after same-host redirects
    content_type: str | None
    body: bytes = b""  # decoded; empty for a 304
    etag: str | None = None
    last_modified: str | None = None
```

Error hierarchy (`ports/fetch.py:65-122`): `FetchError` (base, `code = "fetch_failed"`),
`FetchTimeoutError`, `FetchTooLargeError`, `FetchBlockedError` (with
`POLICY_REFUSAL_REASONS = frozenset({"scheme", "userinfo", "port", "address", "cross_host_redirect"})`),
`FetchHTTPError`, `FetchRedirectError`, `FetchContentError`, `FetchNetworkError`.

**Crucially: `SourceFetchPort.fetch` is `GET`-only.** The HTTP client in
`adapters/crawl/http.py:534` does `client.stream("GET", target, headers=headers)`. There
is **no `POST` anywhere** in the fetch path. A revalidation signal to a Next.js
revalidation endpoint would need either a **new method** on the port, a **new port**, or a
new adapter.

### 6.4 The adapter/port pattern — exact mechanics

**The registry** — `backend/ports/registry.py`:

```python
PORT_KEYS: dict[type, str] = {
    LLMPort: "llm",
    EmbeddingPort: "embedding",
    EmailPort: "email",
    BillingPort: "billing",
    CalendarPort: "calendar",
    SourceFetchPort: "fetch",
    GeoPort: "geo",
    ThrottlePort: "throttle",
}


def get_adapter[P](port: type[P]) -> P:
    key = PORT_KEYS[port]
    path = settings.ADAPTERS.get(key)
    if not path:
        raise ImproperlyConfigured(f"settings.ADAPTERS has no '{key}' adapter.")
    try:
        adapter = import_string(path)
    except ImportError as exc:
        raise ImproperlyConfigured(f"ADAPTERS['{key}'] = '{path}' cannot be imported.") from exc
    if not (isinstance(adapter, type) and issubclass(adapter, port)):
        raise ImproperlyConfigured(
            f"ADAPTERS['{key}'] = '{path}' does not implement {port.__module__}.{port.__name__}."
        )
    return cast(P, adapter())


def get_fetch_port() -> SourceFetchPort:
    return get_adapter(SourceFetchPort)
```

(`ports/registry.py:22-79`)

**The pattern in six steps:**
1. **Define an ABC in `ports/`** — e.g. `ports/fetch.py` → `SourceFetchPort`. `ports` is
   pure-ish (it may read Django settings via `ports/registry.py`; it must not import
   `apps`, `adapters`, `worker`, or `config`).
2. **Implement it in `adapters/<x>/`** — e.g. `adapters/crawl/http.py` → `HttpFetchAdapter`.
   This is the **only** layer allowed to import `httpx`/`httpcore`.
3. **Name the class by dotted string in settings** — `config/adapters.py`.
4. **Resolve it through `ports.registry.get_adapter(PortClass)`**.
5. **Apps import the *port*, never the adapter.** The `layers` contract enforces this.
6. **The `adapters-independent` contract** (`pyproject.toml:174-178`) forbids adapters
   importing each other — so a new adapter may not import `adapters.crawl.http` either.

**The adapter table** — `backend/config/adapters.py`:

```python
FAKE_ADAPTERS = {
    "llm": "adapters.llm.fake.FakeLLMAdapter",
    "embedding": "adapters.llm.fake.FakeEmbeddingAdapter",
    "email": "adapters.email.smtp.SmtpEmailAdapter",
    "billing": "adapters.billing.fake.FakeBillingAdapter",
    "calendar": "adapters.calendar.fake.FakeCalendarAdapter",
    "fetch": "adapters.crawl.fake.FakeFetchAdapter",
    "geo": "adapters.geo.fake.FakeGeoAdapter",
    "throttle": "adapters.throttle.memory.InMemoryThrottleAdapter",
}

HTTP_FETCH_ADAPTER = "adapters.crawl.http.HttpFetchAdapter"
FETCH_ADAPTERS = {"fake": FAKE_ADAPTERS["fetch"], "http": HTTP_FETCH_ADAPTER}
CALENDAR_ADAPTER = "adapters.calendar.ics.IcsCalendarAdapter"
HEADER_GEO_ADAPTER = "adapters.geo.header.HeaderGeoAdapter"

REAL_ADAPTERS: dict[str, str] = {
    "fetch": HTTP_FETCH_ADAPTER,
    "calendar": CALENDAR_ADAPTER,
    "geo": HEADER_GEO_ADAPTER,
    "throttle": "adapters.throttle.redis.RedisThrottleAdapter",
}
```

`adapter_paths(mode, fetch)` (`config/adapters.py:45-62`) returns the fake or real table,
and `ADAPTER_MODE=real` **fails at startup** if any port lacks a real adapter
(`ImproperlyConfigured`, lines 56-61).

**Settings wiring** — `config/settings.py` sets `ADAPTERS = adapter_paths(env.adapter_mode, env.source_fetch)`.
`env.adapter_mode: Literal["fake", "real"] = "fake"` (`config/env.py:76`);
`env.source_fetch: Literal["fake", "http"] | None = None` (`config/env.py:80`).

### 6.5 The precedent for a *second* adapter reusing the crawl HTTP client

**`backend/adapters/calendar/ics.py:1-13`** (docstring, verbatim):

> *"**The fetch.** The adapter never opens a socket. It resolves `SourceFetchPort` from the registry and calls `fetch()` — so the hardened client in `adapters/crawl/` does the SSRF policy, the size limits, the deadline and the decompression budget, *unchanged*, and this adapter cannot have a second, weaker copy of any of them. The one thing it asks for that a source fetch does not is `allow_cross_host_redirect=True`: all three providers redirect the address the user pasted to a CDN host. That relaxes the **host**, never the address."*

**This is the template for a revalidation HTTP call.** A new adapter (e.g.
`adapters/revalidation/http.py`) would resolve `SourceFetchPort` and call `fetch()` —
but **`fetch()` is GET-only**, and a Next.js `revalidatePath`/`revalidateTag` endpoint
normally wants a POST with a JSON body. Options:

| Option | Cost |
|---|---|
| **(a) New port + new adapter** (`ports/revalidation.py` → `RevalidationPort` with a `notify(url, payload)` method), implemented by a new `adapters/revalidation/http.py` that imports `httpx` directly | New port, new adapter, new `ADAPTERS` key, new `REAL_ADAPTERS`/`FAKE_ADAPTERS` entries, **and the `http-client` contract must add `adapters.revalidation` to `source_modules` exclusion** (it currently forbids `httpx` from everything except `adapters.crawl`, but `adapters.crawl` is *not* in `source_modules` — so a new `adapters.revalidation` package would need `adapters.crawl` renamed in the contract, or a new contract). |
| **(b) Extend `SourceFetchPort` with a POST method** | Changes a shared port used by 4+ call sites; the `FetchResult` shape (`status`, `final_url`, `body`) is reusable but `FetchLimits.allowed_ports` defaults to `{80,443}` and the SSRF/address policy still applies — which is desirable. |
| **(c) Reuse `HttpFetchAdapter` via `get_fetch_port()` with a GET carrying the signal in the query string** | **No new port, no new adapter, no contract change.** But a GET with a secret in the URL is exactly what AD-18 forbids for credentials (`ports/fetch.py:140-160` explains that httpx logs the URL). The `credential=True` flag exists precisely for this: it suppresses httpx's URL logging (`adapters/crawl/http.py:273-310`). |
| **(d) Do the HTTP call inside the worker task directly** | **FORBIDDEN.** `worker` is in the `http-client` contract's `source_modules` (`pyproject.toml:241`), so `worker/tasks.py` may not import `httpx`/`httpcore`/`requests`/`urllib3`. |

### 6.6 Can the backend make an outbound HTTP call at all? — YES, with constraints

**Answer: yes, but only through the port/adapter pattern.** The mechanical requirements:

1. **A port ABC in `ports/`.** `ports` may not import `django` models or `apps`; it may
   read settings (only `ports/registry.py` does).
2. **An adapter in `adapters/<new>/`.** `adapters.*` packages may not import each other
   (`adapters-independent` contract). It is the only layer allowed to import `httpx`.
3. **A dotted string in `config/adapters.py`** and an entry in `settings.ADAPTERS`.
4. **A fake adapter** for tests (`ADAPTER_MODE=fake` is the default and the CI default).
5. **A real adapter** — otherwise `ADAPTER_MODE=real` refuses to boot
   (`config/adapters.py:56-61`).

**The SSRF/address policy applies to any outbound call that goes through
`SourceFetchPort`.** `adapters/crawl/http.py`:
- scheme must be `http`/`https` (`_check_target`, lines 465-484)
- no userinfo
- port must be in `allowed_ports` (default `{80, 443}`)
- same-host redirects only unless `allow_cross_host_redirect=True`
- every resolved address is checked against `fetch_deny_policy()` at connect time
  (`GuardedBackend.connect_tcp`, lines 177-213)
- a `Deadline` bounds DNS + connect + TLS + body + hops
- `max_bytes` output budget on the decompressed body
- `_url_logging_suppressed(credential=True)` suppresses httpx's URL logging
  (lines 273-310)
- TLS verification is enforced; a non-verifying `SSLContext` is **refused** with
  `ValueError` (`_assert_context_verifies`, lines 253-270)

**Practical consequence for a revalidation call to a Next.js deploy:** the target is
likely `https://<deploy-host>/api/revalidate` — scheme OK, port 443 OK, address OK (a
public IP), same-host redirect OK. **But** if the deploy is on a private network address
(e.g. `10.x`, `172.16-31.x`, `192.168.x`, or a link-local metadata address), the address
policy **will refuse it**. `domain/address_policy.py` holds the deny table.

### 6.7 The address-policy escape hatch (test-only)

**File:** `backend/ports/fetch_policy.py`

```python
@contextmanager
def allow_loopback_fetch() -> Iterator[None]:
    """Admit loopback for the duration of the block. **Test settings only.** ..."""
```

Two gates, both required (`_allowance_refusal_reason`, lines 166-184):
1. `settings_module_name() == "config.settings_test"` — the **name**, checked via
   `os.environ.get("DJANGO_SETTINGS_MODULE", "")`, not `django.conf.settings`.
2. `runner_is_active()` — `PYTEST_CURRENT_TEST` must be set (lines 128-163).

If either fails, the context manager **raises `LoopbackAllowanceUnavailable`** rather than
silently granting. `fetch_deny_policy()` (lines 221-230) returns the real `is_denied`
unless inside an open allowance block.

### 6.8 The `redis-sdk` contract (relevant to §9)

**File:** `backend/pyproject.toml`, **lines 254–274**

```toml
[[tool.importlinter.contracts]]
id = "redis-sdk"
name = "Only adapters.throttle and config.health talk to Redis"
type = "forbidden"
source_modules = [
    "domain", "apps", "ports", "worker", "shared",
    "adapters.billing", "adapters.calendar", "adapters.crawl",
    "adapters.email", "adapters.llm", "adapters.logging",
]
forbidden_modules = ["redis"]
allow_indirect_imports = true
```

**`worker` is in `source_modules`** — so `worker/tasks.py` may **not** import `redis`
directly. It cannot publish to a Redis pub/sub channel or push to a Redis list to signal
the frontend. **The only outbound mechanism available to the worker is Celery** (which
uses Redis internally via the broker).

---

## 7. Credentials and secrets

### 7.1 The mechanism — three-layer split

| Layer | Module | Responsibility | May import `cryptography`? |
|---|---|---|---|
| `shared` (pure, stdlib only) | `backend/shared/credential_key.py` | **Format only** — parse/validate the key | No |
| `apps.personalization` | `backend/apps/personalization/credentials.py` | **The cipher** — encrypt/decrypt/fingerprint | **Yes** (the only module) |
| `config` | `backend/config/env.py` | **Validation at boot** — parse the key, raise `ImproperlyConfigured` | No |

The rationale (`shared/credential_key.py:1-17`):
> *"This module parses `CALENDAR_CREDENTIAL_KEY` into a key and the id it is known by. It does not encrypt anything: the cipher lives in `apps.personalization.credentials`, which is the only module allowed to reach the `cryptography` library.*
>
> *The split exists so that `config` can validate the key at startup without dragging the cipher into the settings layer. `config` is above `apps` in AD-2's layering, so a `config → apps.personalization` import would point the wrong way — and it would make the settings module able to reach the key-handling code, which is exactly what the `crypto-library` import contract exists to prevent. So the *format* lives here, in `shared`, where it is pure and importable from anywhere above the cipher."*

### 7.2 The environment variable and its format

`shared/credential_key.py`:
- `KEY_BYTES = 32` (line 31) — AES-256.
- `KEY_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,32}$")` (line 35).
- **`KEY_ENV_VAR = "CALENDAR_CREDENTIAL_KEY"`** (line 39).

Format (`parse_key`, lines 100-140):
> *"The format is `<key_id>.<base64url-32-bytes>` — for example `k1.aGVsbG8...`. The id and the key live in one variable so they cannot drift apart: rotating the key means writing a new value, and the id in the envelope then says which key wrote each row."*

Example from `.env.example`:
```
CALENDAR_CREDENTIAL_KEY=k1.ZXZlbnRwdWxzZTI0LWxvY2FsLWNyZWRkZXktMzJieXQ
```

**No fallback to `SECRET_KEY`** — `shared/credential_key.py:107-116`:
> *"A missing or malformed value raises `InvalidCredentialKey`, never a fallback. There is no default and no derivation from `SECRET_KEY`: the credential key is separate from the session key on purpose (AD-18), and a silent fallback would defeat that."*

`config/env.py:66-74`:
> *"**Required, with no default and no fallback.** A missing or malformed value aborts the boot (settings are loaded at startup), rather than leaving an app that boots healthy and fails later, when a user connects a calendar."*

### 7.3 The envelope format

`apps/personalization/credentials.py`:
- `ENVELOPE_PREFIX = "EPENC1"` (line 50)
- `ENVELOPE_PARTS = 4` (line 53)
- `NONCE_BYTES = 12` (line 57) — fresh `os.urandom` per encryption.
- `AAD = b"eventpulse24.calendar_connection.credential"` (line 63)

Envelope: `EPENC1.<key_id>.<base64url-nonce>.<base64url-ciphertext>`, base64url **unpadded**
(`shared/credential_key.py:68-72`).

Functions: `encrypt(plaintext, key) -> str` (line 66), `is_envelope(value) -> bool` (line 81),
`decrypt(envelope, key) -> str` (line 86), `normalise_for_fingerprint(url) -> str` (line 148),
`fingerprint(url, key) -> str` (line 175 — HMAC-SHA256 keyed digest, hex).

**Every failure mode is the same error:** `CredentialDecryptionError` from `domain.errors`
— a malformed envelope, the wrong key, a tampered ciphertext are indistinguishable
(lines 86-145).

### 7.4 The import contracts that protect the key

**`crypto-library`** (`pyproject.toml:276-305`): only `apps.personalization` may import
`cryptography`. `apps.ingestion` is **in** `source_modules` (line 286) — so
**`apps.ingestion` may not import `cryptography`**.

**`credential-key`** (`pyproject.toml:307-335`): only `apps.personalization` may import
`apps.personalization.credentials`. `apps.ingestion` is in `source_modules` (line 316).

> *"`shared.credential_key` holds only the *format* — it cannot encrypt — so `config` may validate a key with it without being able to read a credential."* (lines 326-329)

**Design implication for revalidation:** if the revalidation signal needs a shared secret
(e.g. an HMAC the frontend verifies), **it cannot use `CALENDAR_CREDENTIAL_KEY`** — that
module is `apps.personalization`-only and the key is documented as *the calendar
credential's* key. A **new** secret would need:
- a new env var in `config/env.py` (`Settings`),
- a new format module in `shared/` (stdlib-only) or a new contract exception,
- an entry in `.env.example`,
- and a contract decision if it must be readable from `apps.ingestion` / `worker`.

**Note the `crypto-library` contract's `source_modules` list does NOT include
`apps.delivery`, `apps.identity`, `apps.editorial`? — it DOES include them (lines 283-285:
`"apps.catalog", "apps.delivery", "apps.editorial", "apps.identity", "apps.ingestion"`).
`apps.personalization` is deliberately absent** (line 295-296).

### 7.5 Other secrets in the codebase

| Secret | Where | Mechanism |
|---|---|---|
| `DJANGO_SECRET_KEY` | `config/env.py:25` (`django_secret_key: str`) | Django sessions + `django.core.signing.Signer` |
| `CALENDAR_CREDENTIAL_KEY` | `config/env.py:74` | see above |
| `DATABASE_URL_OWNER` | `config/env.py:58` | `database_url_owner: str \| None = None` — required only in the `owner` role |
| `DATABASE_URL_CATALOG` | `config/env.py:59` | `database_url_catalog: str` |
| `DATABASE_URL_PERSONAL` | `config/env.py:60` | `database_url_personal: str` |
| `REDIS_URL` | `config/env.py:62` | `redis_url: str` |
| `SMTP_HOST` / `SMTP_PORT` | `config/env.py:63-64` | Mailpit locally |

**Signing salts** (not secrets — `shared/constants.py:213-221`):
- `UNSUBSCRIBE_SIGNING_SALT = "eventpulse24.email.unsubscribe"` (line 220)
- `CLICK_SIGNING_SALT = "eventpulse24.email.click"` (line 221)

> *"**These are salts, not secrets.** A salt is a public label that says what a signature is *for*; the secret is Django's `SECRET_KEY`, which is configuration and never appears in the code."*

**The `Credential` wrapper** (`ports/calendar.py:68-89`) — the pattern for carrying a secret
in a port without leaking it:
```python
class Credential:
    """A secret (e.g. a secret ICS URL). Its value never appears in `repr`, `str` or logs."""
    __slots__ = ("_value",)
    def __init__(self, value: str) -> None: self._value = value
    def reveal(self) -> str: return self._value
    def __repr__(self) -> str: return "Credential('[redacted]')"
    __str__ = __repr__
```

### 7.6 The `.env` file (present, git-ignored)

`/home/bs1346/Documents/P-project/EventPulse24/.env` exists (2051 bytes) and is read by
`config/env.py:14-15`:
```python
REPO_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = REPO_ROOT / ".env"
```
It is **not** committed (`.gitignore`).

---

## 8. `catalog_read.py` — `get_public_event_by_slug` and `PublicEventPage`

**File:** `backend/apps/ingestion/services/catalog_read.py` (721 lines)

### 8.1 `PublicEventPage` — the exact dataclass

**Lines 524–584** (dataclass body); the docstring spans 526–555.

```python
@dataclass(frozen=True)
class PublicEventPage:
    id: UUID
    slug: str
    title: str
    #: The stripped, truncated description. Empty when the source had none.
    description: str
    canonical_url: str
    start_time_utc: datetime
    #: The IANA zone name (AD-6). The JSON-LD needs it, and it is the only display
    #: conversion input the payload carries.
    start_time_tz: str
    end_time_utc: datetime | None
    venue_name: str | None
    #: The venue's address, as the schema holds it: the venue's own name with its city
    #: and country. `Venue` has no street line — there is no address column — so this is
    #: everything the address can honestly say. Inventing a street field here would be
    #: inventing a fact the registry does not have.
    venue_address: str | None
    venue_city: str | None
    venue_country_code: str | None
    status: str
    #: A-15 / FR-53: the event is sold out.
    is_sold_out: bool
    event_version: int
    source_name: str
    tz_review_pending: bool
    #: The Schema.org `Event` object, projected from the fields above (AD-12). A plain
    #: dict, because JSON-LD is JSON — the page embeds it without reshaping it.
    schema_org: dict[str, object]
```

**Exactly 18 fields.** Field order as declared above.

### 8.2 The docstring's key sentences (verbatim, lines 534–554)

> *"**The fields are the JSON-LD's inputs (AD-12).** ARCHITECTURE-SPINE.md:166 requires the Schema.org `Event` JSON-LD to be *"emitted from the same data the page renders"*. So this carries everything the page and its structured data need, from one read: the title, the description, both times, the IANA zone, the venue's name and address parts, the canonical URL, the status, the sold-out flag and the version."*
>
> *"**`event_version` is the Event's own counter**, read from the row and never re-derived. The `catalog.guard_event_write` trigger bumps it on every lifecycle change, and the revalidation work item compares it against a cached copy to decide whether a page is current. A re-derived number would not be the number the trigger wrote."*
>
> *"**`schema_org` is the finished structured data**, projected from the fields above by `domain.schema_org`. It is carried on the DTO rather than built at the surface, so the projection happens **once, from the same read** — which is what makes AD-12's *"the same data the page renders"* a property of the code rather than a convention. The page embeds what it is given, verbatim."*

**This is the single most on-point statement in the codebase for this feature: the
`event_version` field exists *specifically* so the revalidation work item can compare it
against a cached copy.**

### 8.3 `get_public_event_by_slug` — the exact function

**Lines 637–700** (function body 676–700; docstring 638–675).

```python
def get_public_event_by_slug(*, slug: str) -> PublicEventPage:
    """One public event's page facts, by slug.

    **This is a different question from `get_public_event`.** That one answers "what may
    a person browse?" and bounds the answer by *has not started yet* — the right rule for
    a digest and the wrong rule for a page. This one answers "what is this URL?", and
    **there is no time bound**: a page for an event that already happened stays
    addressable and stays indexed. A page that 404s the moment the doors open throws
    away every bit of ranking it spent months earning, and a Schema.org page for a
    concert last month is legitimate content, not an error.

    **The slug alone addresses the event.** `Event.slug` carries `event_slug_uq`, a
    global unique constraint, so no city or date segment is needed and there is no
    ambiguity to resolve.

    **The lookup is exact, not case-insensitive.** ...

    **The row is fetched unfiltered and the visibility rules are applied to it.** A
    filtered query — published, not superseded — can answer "is this public?", but it
    cannot answer "was this superseded, and by what?" And that second question is the one
    this read has to answer: a superseded event is 404 at its own slug, but the 404
    carries the successor's slug so the link a crawler already holds resolves *forward*
    rather than dying.

    **The successor costs no extra query.** `superseded_by` is a self-FK, so
    `select_related("superseded_by")` brings the replacement's row along with the
    original.

    **An `in_review` event is never publicly addressable.** ...

    **Nothing here writes.** The slug is minted once at creation and never re-minted on
    retitle (`services/slugs.py`), so these URLs are permanent by construction, and this
    read adds no path that could rewrite one.
    """
    try:
        event = (
            Event.objects.using(CATALOG)
            .filter(slug=slug)
            .select_related("venue", "source", "superseded_by")
            .get()
        )
    except Event.DoesNotExist:
        raise EventNotFoundError(details={"slug": slug}) from None

    if event.publication_status != Event.PublicationStatus.PUBLISHED:
        # `in_review` is not publicly listed (AD-6, AD-8). It reads as absent, exactly as
        # an unknown slug does — a 403 would confirm that it exists.
        raise EventNotFoundError(details={"slug": slug})

    if event.status == Event.Status.SUPERSEDED:
        # The event existed and was replaced. The successor's slug travels with the 404 so
        # the caller can send the crawler forward instead of leaving a dead link.
        successor = event.superseded_by
        details: dict = {"slug": slug}
        if successor is not None:
            details["superseded_by_slug"] = successor.slug
        raise EventNotFoundError(details=details)

    return _to_public_event_page(event)
```

**Signature: `get_public_event_by_slug(*, slug: str) -> PublicEventPage` — keyword-only,
no `now` parameter.**

### 8.4 The projector `_to_public_event_page`

**Lines 587–634.**

```python
def _to_public_event_page(event: Event) -> PublicEventPage:
    venue = event.venue
    venue_address = None
    if venue:
        parts = [venue.name, venue.city, venue.country_code]
        venue_address = ", ".join(part for part in parts if part)
        venue_address = venue_address or None

    schema_org = project_schema_org_event(
        title=event.title,
        description=event.description,
        start_time_utc=event.start_time_utc,
        start_time_tz=event.start_time_tz,
        end_time_utc=event.end_time_utc,
        status=event.status,
        is_sold_out=event.is_sold_out,
        venue_name=venue.name if venue else None,
        venue_city=venue.city if venue else None,
        venue_country_code=venue.country_code if venue else None,
        canonical_url=event.canonical_url,
    )

    return PublicEventPage(
        id=event.id,
        slug=event.slug,
        title=event.title,
        description=event.description,
        canonical_url=event.canonical_url,
        start_time_utc=event.start_time_utc,
        start_time_tz=event.start_time_tz,
        end_time_utc=event.end_time_utc,
        venue_name=venue.name if venue else None,
        venue_address=venue_address,
        venue_city=venue.city if venue else None,
        venue_country_code=venue.country_code if venue else None,
        status=event.status,
        is_sold_out=event.is_sold_out,
        event_version=event.event_version,
        source_name=event.source.name,
        tz_review_pending=event.tz_review_pending,
        schema_org=schema_org,
    )
```

### 8.5 `EventNotFoundError`

**Lines 80–83:**
```python
class EventNotFoundError(NotFoundError):
    """The requested event isn't in the public catalog (or was never published)."""
    default_message = "We couldn't find that event."
```

### 8.6 The wire shape — `PublicEventPageOut`

**File:** `backend/apps/catalog/schemas.py`, **lines 82–129**

```python
class PublicEventPageOut(Schema):
    id: UUID
    slug: str
    title: str
    description: str
    canonical_url: str
    start_time_utc: datetime
    start_time_tz: str
    end_time_utc: datetime | None = None
    venue_name: str | None = None
    venue_address: str | None = None
    venue_city: str | None = None
    venue_country_code: str | None = None
    status: str
    is_sold_out: bool
    event_version: int
    source_name: str
    tz_review_pending: bool = False
    schema_org: dict[str, object]

    @classmethod
    def from_public_event_page(cls, event: PublicEventPage) -> "PublicEventPageOut":
        """Project the read interface's plain data onto the wire shape."""
        return cls(**vars(event))
```

**The docstring at lines 100–101 says it outright:**
> *"**`event_version` is here because the revalidation work item needs it** to prove a cached page is current."*

**Note:** `cls(**vars(event))` — the wire shape is built by `vars()`, so **the dataclass
field set and the schema field set must match exactly** (both have the same 18 fields).
Adding a field to `PublicEventPage` **requires** adding it to `PublicEventPageOut`.

### 8.7 The API endpoint

**File:** `backend/apps/catalog/api.py`, **lines 127–155**

```python
@router.get(
    "/events/by-slug/{slug}",
    response={200: PublicEventPageOut, 404: ErrorOut},
    summary="Get one public event page, by slug",
    description=(...),
)
def get_event_page(request, response: HttpResponse, slug: str):
    """One public event's page facts.

    **The not-found is handled here rather than left to the exception handler.** An
    unknown slug is a clean, cacheable answer — a crawler that asks for a URL that does
    not exist should not hammer the origin — but django-ninja's exception path builds a
    *fresh* response, which would drop the cache headers set on the injected response.
    Catching it here keeps them on the 404.
    """
    _cacheable(response)
    try:
        page = get_public_event_by_slug(slug=slug)
    except EventNotFoundError as exc:
        return Status(
            404,
            ErrorOut(code=exc.code, message=exc.message, details=exc.details),
        )
    return PublicEventPageOut.from_public_event_page(page)
```

And the cache-header helper, `apps/catalog/api.py:64-79`:

```python
def _cacheable(response: HttpResponse) -> HttpResponse:
    """Mark a response as a public, cacheable, per-URL response. ..."""
    response["Cache-Control"] = PUBLIC_PAGE_CACHE_CONTROL
    response["Vary"] = PUBLIC_PAGE_VARY
    return response
```

### 8.8 The cache-control constants

**File:** `backend/shared/constants.py`, **lines 795–815**

```python
# The public event page's cache headers (FR-26). The browser holds it for an hour, a
# shared cache for an hour too, and a shared cache may serve a slightly stale copy while
# it refreshes in the background.
#
# The TTL is longer than the preview's, because this page is indexed. A crawler that
# has spent months earning a ranking on `/events/{slug}` must not be told to come back in
# sixty seconds. The revalidation work item is what makes the page *current*; the cache
# TTL is only how long a page may sit without being revalidated, and the two are separate
# facts.
#
# `stale-while-revalidate` is the point of the third number: a crawler is never made to
# wait on the origin for a page it could have had a moment ago.
PUBLIC_PAGE_CACHE_CONTROL = "public, max-age=3600, s-maxage=3600, stale-while-revalidate=86400"

# The public event page's `Vary` header. **Nothing session-related may appear here.**
#
# A response that varies on the cookie is not cacheable, and — worse — a shared cache
# that stores one variant under a key that ignores the cookie would serve one visitor's
# response to another. The public page sets no cookie and reads no session (AD-12), so
# the response is identical for everyone and the cache key is the URL.
PUBLIC_PAGE_VARY = "Accept-Encoding"
```

Also relevant (lines 774–793):
```python
PREVIEW_CACHE_CONTROL = "public, max-age=60, s-maxage=300, stale-while-revalidate=600"
PREVIEW_VARY = "Accept-Encoding"
```

**The `PUBLIC_PAGE_CACHE_CONTROL` comment explicitly names this work item:**
> *"The revalidation work item is what makes the page **current**; the cache TTL is only how long a page may sit without being revalidated, and the two are separate facts."*

### 8.9 The other public reads (for context)

| Function | Line | Signature |
|---|---|---|
| `list_public_events` | 138 | `(*, now, city=None, starts_after=None, starts_before=None, page=1, page_size=DEFAULT_PAGE_SIZE) -> tuple[list[PublicEvent], int]` |
| `get_public_event` | 174 | `(*, event_id: UUID, now: datetime \| None = None) -> PublicEvent` |
| `list_public_candidates` | 288 | `(*, now, city=None, limit=CANDIDATE_POOL_SIZE) -> list[PublicEventCandidate]` |
| `get_public_events` | 396 | `(*, event_ids: set[UUID]) -> dict[UUID, PublicEvent]` |
| `get_public_event_detail` | 497 | `(*, event_id: UUID, now: datetime \| None = None) -> PublicEventDetail` |
| **`get_public_event_by_slug`** | **637** | **`(*, slug: str) -> PublicEventPage`** |

**The shared visibility predicate** — `_public_events()`, lines 109–116:

```python
def _public_events() -> QuerySet:
    """Published, not superseded. The venue and source come along in the same query."""
    return (
        Event.objects.using(CATALOG)
        .filter(publication_status=Event.PublicationStatus.PUBLISHED)
        .exclude(status=Event.Status.SUPERSEDED)
        .select_related("venue", "source")
    )
```

**Note:** `get_public_event_by_slug` does **not** use `_public_events()` — it fetches
unfiltered and applies the rules in Python (see §8.3).

---

## 9. Redis / queue / cache infrastructure

### 9.1 Redis client setup

There are exactly **two** places that create a Redis client:

**1. `backend/adapters/throttle/redis.py`** (the throttle adapter):

```python
KEY_PREFIX = "throttle:"
REDIS_TIMEOUT_SECONDS = 2.0

class RedisThrottleAdapter(ThrottlePort):
    def __init__(self, url: str | None = None, client=None) -> None:
        self._client = client or _client_from_settings(url)

    def check(self, key: str, *, limit: int, window_seconds: int) -> ThrottleDecision:
        redis_key = KEY_PREFIX + key
        count = self._client.incr(redis_key)
        if count == 1:
            self._client.expire(redis_key, window_seconds)
        ...


def _client_from_settings(url: str | None):
    from django.conf import settings
    return redis.Redis.from_url(
        url or settings.CELERY_BROKER_URL,
        socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
        socket_timeout=REDIS_TIMEOUT_SECONDS,
    )
```
(`adapters/throttle/redis.py:16-54`)

**2. `backend/config/health.py:78-90`** (`check_redis`) — creates a client, pings, closes:
```python
def check_redis() -> ComponentOut:
    client = redis.Redis.from_url(
        settings.CELERY_BROKER_URL,
        socket_connect_timeout=REDIS_TIMEOUT_SECONDS,
        socket_timeout=REDIS_TIMEOUT_SECONDS,
    )
    try:
        client.ping()
    except redis.RedisError as exc:
        return _down("redis", "unreachable", exc)
    finally:
        client.close()
    return OK
```

**Key facts:**
- **Both use `settings.CELERY_BROKER_URL`** — Redis is *only* the Celery broker, not a
  separate cache. `env.redis_url` (`config/env.py:62`) is the single source.
- `REDIS_URL=redis://127.0.0.1:6380/0` in `.env.example`. Docker service `redis:
  8-alpine`, port `EP_REDIS_PORT:-6380`, **no persistence** (`--save "" --appendonly no`),
  comment: *"Celery broker only: carries the beat tick and pipeline jobs, never the reminder
  schedule (AD-7)"*.

### 9.2 Queue names

**There are no named queues.** The Celery app config is:

```python
CELERY_BROKER_URL = env.redis_url
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_TASK_IGNORE_RESULT = True  # no result backend: tasks report through the database
CELERY_TIMEZONE = "UTC"
CELERY_ENABLE_UTC = True
CELERY_WORKER_HIJACK_ROOT_LOGGER = False
```
(`config/settings.py:188-195`)

**No `CELERY_TASK_QUEUES`, no `CELERY_TASK_DEFAULT_QUEUE`, no `task_routes`.**
All tasks therefore go to Celery's **default queue** (`"celery"`). The comment at
`config/settings.py:188`:
> *"Celery (config/celery.py). AD-7: Redis carries the tick and pipeline jobs only."*

**Design implication:** a revalidation task would land on the same default queue as
everything else. If it needs isolation (so a slow revalidation cannot delay a digest
composition), a **new queue + routing rule** would have to be introduced — there is no
such machinery today.

### 9.3 Cache key naming conventions

**There is no Django cache framework in use.** Grepping `settings.py` for `CACHES`
returns nothing. The only cache in the project is:

1. **HTTP caching** via `Cache-Control` / `Vary` headers (constants in
   `shared/constants.py` — see §8.8). No server-side cache; the CDN/shared cache does it.
2. **Redis keys** — only the throttle namespace.

**The only Redis key-naming convention that exists:**

```python
#: Namespace for the counter keys, so a throttle key can never collide with anything else
#: in the shared Redis instance.
KEY_PREFIX = "throttle:"
```
(`adapters/throttle/redis.py:14-16`)

> *"Redis is also the Celery broker, so this shares the same instance; the keys are namespaced with a `throttle:` prefix and never collide with the broker's own keys."* (lines 6-8)

**There is no other key namespace in the codebase.** A new Redis-backed feature (e.g. a
"pending revalidation" set, or an idempotency ledger) would need a new `prefix:` namespace
following the same pattern. But note the **`redis-sdk` import contract** (`pyproject.toml:254-274`)
forbids `worker` and `apps` from importing `redis` — so any Redis use must be behind a
**port + adapter** (e.g. extend `ports/throttle.py` or add a new port), exactly like
`ThrottlePort` → `RedisThrottleAdapter`.

### 9.4 Cache-key naming in the frontend

The frontend has no cache-key concept either; Next.js's `revalidatePath`/`revalidateTag`
would introduce one. The frontend currently has **no** `/events/[slug]` route and **no**
`revalidatePath`/`revalidateTag`/`unstable_cache`/`cacheTag` usage (verified by grep —
see §12.1).

---

## 10. The `personal` vs `catalog` DB aliases, and how a worker task reaches the catalog

### 10.1 The two aliases

**File:** `backend/shared/db.py` (complete, 8 lines)

```python
"""Database aliases (AD-3). Always pass one explicitly: `using=PERSONAL` / `using=CATALOG`.

`default` is the personal schema because Django requires a `default` alias and the user table
must share an alias with the personal data that references it.
"""

PERSONAL = "default"
CATALOG = "catalog"
```

**`PERSONAL = "default"`** — Django requires a `default` alias, and it is mapped to the
`personal` Postgres schema.

### 10.2 The schema mapping and the connection config

**File:** `backend/config/databases.py`

```python
Role = Literal["runtime", "owner"]

SCHEMA_FOR_ALIAS = {PERSONAL: "personal", CATALOG: "catalog"}


def build_databases(env: Settings, role: Role | None = None) -> dict[str, dict]:
    """Return Django DATABASES for `role` (defaults to env.django_db_role).

    runtime: each alias connects as its schema's DML-only role.
    owner:   both aliases connect as the owner role (migrations, tests), each with its own
             search_path so tables land in the right schema.
    """
    role = role or env.django_db_role
    if role == "owner":
        if not env.database_url_owner:
            raise ImproperlyConfigured("DATABASE_URL_OWNER is required for the owner role")
        urls = {PERSONAL: env.database_url_owner, CATALOG: env.database_url_owner}
    else:
        urls = {PERSONAL: env.database_url_personal, CATALOG: env.database_url_catalog}

    databases = {}
    for alias, url in urls.items():
        config = dj_database_url.parse(url, conn_max_age=60)
        schema = SCHEMA_FOR_ALIAS[alias]
        config.setdefault("OPTIONS", {})["options"] = f"-c search_path={schema},public"
        config["ATOMIC_REQUESTS"] = False
        config["TEST"] = {
            "NAME": f"test_{config['NAME']}",
            "TEMPLATE": f"{config['NAME']}_test_template",
        }
        databases[alias] = config
    return databases
```
(`config/databases.py:1-47`)

**Both aliases point at the same Postgres database**, differing only by:
- the connection role (`ep_personal` vs `ep_catalog` in runtime mode),
- and the `search_path` (`-c search_path=personal,public` vs `catalog,public`).

**`ATOMIC_REQUESTS = False`** — pinned off deliberately:
> *"Pinned off: it would wrap only this alias, suggesting requests are atomic across both schemas when no transaction can span them (AD-3)."* (lines 37-38)

**`conn_max_age=60`** — persistent connections.

### 10.3 The router

**File:** `backend/config/db_router.py` (complete, 41 lines)

```python
def alias_for(app_label: str) -> str | None:
    for alias, app_labels in settings.DATABASE_ROUTING.items():
        if app_label in app_labels:
            return alias
    return None


class SchemaRouter:
    def _required_alias(self, model) -> str:
        alias = alias_for(model._meta.app_label)
        if alias is None:
            raise ImproperlyConfigured(
                f"App '{model._meta.app_label}' is not in DATABASE_ROUTING; "
                "add it to the catalog or personal set."
            )
        return alias

    def db_for_read(self, model, **hints):
        return self._required_alias(model)

    def db_for_write(self, model, **hints):
        return self._required_alias(model)

    def allow_relation(self, obj1, obj2, **hints):
        alias1 = alias_for(obj1._meta.app_label)
        alias2 = alias_for(obj2._meta.app_label)
        return alias1 is not None and alias1 == alias2

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        return alias_for(app_label) == db
```

**Fail-closed:** an app missing from `settings.DATABASE_ROUTING` raises `ImproperlyConfigured`
rather than silently going to `default`.

### 10.4 The architecture test that enforces explicit `using=`

**File:** `backend/tests/architecture/checkers.py:78-103` — `alias_violations()`:

```python
            if name in ("atomic", "on_commit") and "using" not in keywords:
                violations.append(f"{node.lineno}: {name}() without using=")
            if "using" in keywords and _is_literal(keywords["using"]):
                violations.append(f"{node.lineno}: using= literal")
            if name == "using" and isinstance(node.func, ast.Attribute):
                if node.args and _is_literal(node.args[0]):
                    violations.append(f"{node.lineno}: .using() literal")
        elif isinstance(node, ast.Subscript):
            if isinstance(node.value, ast.Name) and node.value.id == "connections":
                if _is_literal(node.slice):
                    violations.append(f"{node.lineno}: connections[] literal")
        elif isinstance(node, ast.ImportFrom) and node.module == "django.db":
            if any(alias.name == "connection" for alias in node.names):
                violations.append(f"{node.lineno}: django.db.connection is always 'default'")
```

**Four rules:**
1. `atomic()` / `on_commit()` **must** have `using=`.
2. `using=` **must not** be a string literal — it must be the `shared.db` constant.
3. `.using("literal")` is banned.
4. `from django.db import connection` is banned (it is always `default`).

**A new worker task reading the catalog MUST write `Event.objects.using(CATALOG)`** or the
architecture test fails.

### 10.5 How a worker task reaches the catalog — the exact mechanism

There is **no cross-alias transaction**. The pattern is:

1. **Read/write with an explicit alias.** `Event.objects.using(CATALOG)`.
2. **`atomic(using=CATALOG)`** for a transaction on the catalog side.
3. **`transaction.on_commit(..., using=CATALOG)`** to fire after that transaction commits.

**The `worker` runtime can freely reach both aliases.** `worker/tasks.py` already does:
- `worker.tasks.refresh_event_fits` → `refresh_stale_event_fits(...)` → reads/writes
  `catalog` (`apps/ingestion/event_fit/writes.py`).
- `worker.tasks.ingest_source` → `run_ingest(UUID(source_id))` → the whole ingest pipeline,
  entirely on `catalog`.

**The "personal" side is reached the same way** — `apps.personalization.services.*` use
`using=PERSONAL`.

**Layer rules for a worker task:**
- `worker` **may** import `apps.*.services` (the layers contract puts `config | worker` at
  the top, `apps | adapters` below).
- `worker` **may NOT** import `apps.*.api` or `config.api` (`worker-not-api` contract).
- `worker` **may NOT** import `apps.*.models` — the `models-ingestion` contract
  (`pyproject.toml:160-165`) protects `apps.ingestion.models`; **only `apps.ingestion`**
  may import it. So a worker task that needs an `Event` must go through
  `apps.ingestion.services.*` (a published read interface), not the model.

**This is why `apps/ingestion/services/catalog_read.py` exists** — its module docstring
(`apps/catalog/api.py:26-27`):
> *"This module never imports `apps.ingestion.models` (import contract `models-ingestion`), and it never writes: the catalog is read-only here, and `ingestion` is the sole writer (AD-4, AD-16)."*

### 10.6 The transaction-spanning rule (AD-3)

**No transaction can span both schemas.** `config/databases.py:37-39` explains it, and the
`on_commit(using=...)` split (§5) is the enforcement mechanism: a callback registered
`using=CATALOG` fires when the *catalog* transaction commits, and one registered
`using=PERSONAL` fires when the *personal* transaction commits.

**Design implication:** a revalidation signal that must observe the committed Event row
must be registered `using=CATALOG` — exactly like `event_writes.py:176`.

---

## 11. Existing webhook / notify / signal / publish concepts

I searched the entire backend for `notify|notification|webhook|publish|revalidat|rebuild`.

### 11.1 There is NO webhook concept

- **No `webhook` model, table, endpoint, port, or adapter exists.** The only hit for
  `revalidat` is `shared/constants.py:801` (the `PUBLIC_PAGE_CACHE_CONTROL` comment).
- There is no outbound HTTP call to a third-party webhook anywhere.

### 11.2 There is NO "signal" concept in the Django sense

- No `django.dispatch.Signal`, no `post_save`/`post_delete` receiver, no
  `AppConfig.ready()` signal wiring.
- The only `signal` hits are **Celery's own signals** in `config/celery.py`:
  `from celery.signals import before_task_publish, setup_logging, task_postrun, task_prerun`
  (`config/celery.py:10`) and the four `@...connect` handlers (lines 31-65).

### 11.3 The "notification" concept is entirely about **email to users**

`apps/delivery/` is a whole app for user-facing email notifications. It is unrelated to
the frontend revalidation:

| Module | Purpose |
|---|---|
| `apps/delivery/models.py` | `NotificationPreference`, `ScheduledSend` |
| `apps/delivery/services/delivery_sweep.py` | The sweep that claims and sends due sends |
| `apps/delivery/services/pulse_ping.py` | `mint_ping_send` — decides whether to send the daily digest ping |
| `apps/delivery/services/scheduled_sends.py` | `apply_lifecycle_change` (AD-17) — **the unwired consumer** |
| `apps/delivery/services/notification_preferences.py` | Quiet hours, reminder plans |
| `apps/delivery/api.py`, `email_api.py`, `preferences_api.py` | HTTP surfaces |
| `apps/delivery/preferences_api.py:1` | *"The notification settings endpoints — quiet hours, the default plan, and the delivery time."* |

**There is no `apps/notify`, no `apps/webhooks`, no `apps/events` app.**
The `apps` directory contains exactly: `catalog`, `delivery`, `editorial`, `identity`,
`ingestion`, `personalization`.

### 11.4 The "publish" concept is about **catalog visibility**, not about pushing

`publish` appears as:
- `Event.PublicationStatus.PUBLISHED` / `IN_REVIEW` (`apps/ingestion/models.py:232-234`).
- `domain/confidence.py:24-25` — `PUBLISH = "publish"`, `PUBLISH_FLAGGED = "publish_flagged"`.
- `apps/catalog/schemas.py` — `is_published` on `CityPageOut` (FR-27's threshold).
- `apps/catalog/api.py` — the cacheable public endpoints.

**None of these push anything anywhere.**

### 11.5 The closest existing analogues to "signal the frontend"

| Analogue | What it is | Why it's the closest |
|---|---|---|
| **AD-17 outbox** (`apps/ingestion/services/outbox.py`) | A DB row + `on_commit` enqueue + a reconciler + a no-op consumer | **The exact structural precedent**: "a change happened → a signal is queued → a worker consumes it → the reconciler re-offers what wasn't consumed." |
| **`mark_propagated`** (`outbox.py:30-40`) | Conditional `UPDATE ... WHERE propagated_at IS NULL` | The existing idempotency primitive for "this signal was delivered." |
| **`apply_lifecycle_change`** (`apps/delivery/services/scheduled_sends.py`) | The AD-17 consumer half that exists and is tested but is not wired | Proves the pattern; also shows how "one consumer, many owners" was meant to work. |
| **The `Celery` signal plumbing** (`config/celery.py:39-65`) | `before_task_publish` / `task_prerun` / `task_postrun` | The trace-id chain; if a revalidation signal needs a trace id across the hop, this is where it would ride. |
| **`apps/ingestion/services/slugs.py`** | Mints the slug once, never re-mints | The reason the public page URL is stable — the revalidation target key. |

### 11.6 The "publish/unpublish" write path

**There is no editorial publish command.** `apps/editorial/` contains only:
- `admin.py` (empty-ish), `api.py`:
```python
from ninja import Router

router = Router()
```
- `models.py`, `schemas.py` — all effectively empty.

**Every publish state change therefore comes through the ingestion pipeline**
(`apps/ingestion/services/ingest_item.py`), which calls `apply_lifecycle_change` (line 352)
or `apply_silent_update` (line 358) or `supersede_event` (line 345).

**This matters:** there is no "editorial publishes an event" API runtime write path today.
The work item's note *"Who fires it — API runtime or worker. Lifecycle changes arrive from
both: user-facing writes on the API runtime, and the ingest pipeline and state polling on
the worker"* is **currently asymmetric** — the only lifecycle writes in the repo are on
the worker side (ingest pipeline). The `on_commit(using=CATALOG)` seam is in
`apps/ingestion/services/event_writes.py`, which is **runtime-agnostic**: it runs wherever
the transaction runs, so it covers both.

### 11.7 The `EventFit` staleness mechanism (a working precedent for "the version changed")

**File:** `backend/apps/ingestion/models.py:399-458` — `EventFit`:

```python
    #: The Event version this fit was computed from. A mismatch means stale.
    event_version = models.PositiveIntegerField()
```

Docstring (`models.py:406-410`):
> *"**The row is **persisted and served as it stands** (AD-10: "never recomputed at render"). `event_version` is the Event version the fit was computed from: a row whose `event_version` no longer matches its Event is **stale** and is never served. The staleness check is the read's job, not a trigger's, because the refresh is a writer's work."*

**And the reader** — `apps/ingestion/services/city_read.py:147-168`:

```python
def _current_rows(*, city_ref_id: UUID, since: datetime) -> list[EventFit]:
    ...
    rows = (
        EventFit.objects.using(CATALOG)
        .filter(city_ref_id=city_ref_id)
        .select_related("event", "event__venue")
        .filter(event__publication_status=Event.PublicationStatus.PUBLISHED)
        .exclude(event__status=Event.Status.SUPERSEDED)
        .filter(event__start_time_utc__gte=since)
        .order_by("event__start_time_utc", "event_id")
    )
    return [row for row in rows if row.event_version == row.event.event_version]
```

**This is the established pattern for "compare a stored version to the live version":**
*read both, compare in Python* (because SQL cannot compare two joined columns).

The staleness refresh is `worker.tasks.refresh_event_fits` → `refresh_stale_event_fits`
(`apps/ingestion/event_fit/writes.py`), a **15-minute-cadence writer**.

---

## 12. Appendix A — the frontend's side (context only)

*(Included because the design must specify the receiving end. The user asked for backend
research; this is the minimum the backend design needs.)*

### 12.1 There is NO public event page route in the frontend yet

`frontend/app/` contains: `conflicts/`, `dev/health/`, `events/[id]/`, `events/[id]/reminders/`,
`layout.tsx`, `onboarding/`, `page.tsx`, `preview/`, `reset-password/`,
`settings/quiet-hours/`, `settings/reminders/`, `signin/`, `signup/`, `timeline/`.

- **`/events/[id]`** exists (the **Detail Screen**, keyed by UUID, personal, signed-in or
  anonymous) — it is `export const dynamic = "force-dynamic"` (`frontend/app/events/[id]/page.tsx:34`).
- **`/events/[slug]`** (the public SEO page) does **not** exist. Its work item is
  `.specs-fire/intents/public-pages-and-seo/work-items/frontend-public-event-page.md`.

**Grep for `revalidate|unstable_cache|noStore|cacheTag|revalidateTag|cacheLife` in the
frontend returns ZERO hits.** The only `revalidate` hit is a negative assertion in
`frontend/app/preview/page.test.tsx:43`:
```typescript
    expect("revalidate" in page).toBe(false);
```

Every route in the frontend is `export const dynamic = "force-dynamic"`. **No Next.js
caching / ISR machinery exists today.**

### 12.2 The Next.js config is empty

**File:** `frontend/next.config.ts` (complete):
```typescript
import type { NextConfig } from "next";

const nextConfig: NextConfig = {};

export default nextConfig;
```

### 12.3 The proxy

**File:** `frontend/proxy.ts` — rewrites `/api/*` to the Django backend:
```typescript
export const config = { matcher: "/api/:path*" };
```
`apiBaseUrl()` reads `API_BASE_URL` per request (`frontend/lib/api-base-url.ts`).

**Design implication:** a **revalidation endpoint on the frontend** would live at
`/api/revalidate` on the Next.js side and would **collide with the proxy matcher**
(`/api/:path*`) — the proxy would rewrite it to Django. A revalidation endpoint therefore
needs a **non-`/api` path** (e.g. `/revalidate`) or the proxy must exclude it. **This is a
concrete, checkable constraint.**

### 12.4 The generated API client

- `frontend/lib/api/openapi.json` and `frontend/lib/api/schema.ts` — generated from Django
  ninja (`openapi-typescript`).
- `frontend/lib/backend-client.ts` — the fetch wrapper.

---

## 13. Appendix B — test seams and fixtures

### 13.1 The `_enqueue` seam (worker tests)

**File:** `backend/tests/worker/conftest.py` (complete):
```python
@pytest.fixture(autouse=True)
def enqueued(monkeypatch):
    """Record every job a task enqueues instead of publishing it to the broker (Redis)."""
    jobs: list[tuple[str, tuple]] = []
    monkeypatch.setattr(tasks, "_enqueue", lambda task, *args: jobs.append((task.name, args)))
    return jobs
```

### 13.2 The `_send` seam (ingestion tests)

**File:** `backend/tests/ingestion/conftest.py` (complete):
```python
@pytest.fixture(autouse=True)
def sent_jobs(monkeypatch):
    """Record every job the outbox sends instead of reaching the Celery broker (Redis)."""
    jobs: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(outbox, "_send", lambda name, args: jobs.append((name, list(args))))
    return jobs
```

**The `sent_jobs` fixture is autouse in `tests/ingestion/`** — it patches
`apps.ingestion.services.outbox._send` only. A new module with its own `_send` seam needs
its own conftest fixture.

### 13.3 The `on_commit` capture fixture

**File:** `backend/tests/ingestion/test_ingest_lifecycle.py:138-163`
```python
    with django_capture_on_commit_callbacks(using=CATALOG, execute=True) as callbacks:
...
    assert sent_jobs == []  # on_commit never fired
```

`django_capture_on_commit_callbacks` is Django's built-in
(`django.test.TestCase.captureOnCommitCallbacks`).

### 13.4 The `on_commit` interception pattern (personalization tests)

**File:** `backend/tests/personalization/test_digest_enqueue.py:53-69`
```python
def on_commit(monkeypatch):
    """Capture the `on_commit` callbacks the command registers.

    **The real `on_commit` is kept in place** — only the *dispatch* is intercepted, so
    ...
    """
    original = transaction.on_commit
    ...
    monkeypatch.setattr(transaction, "on_commit", capture)
```

And `:253`:
```python
        transaction.on_commit(boom, using=PERSONAL, robust=True)
```

### 13.5 The existing outbox tests

**File:** `backend/tests/ingestion/test_outbox.py` — 5 tests:
- `test_enqueue_propagation_sends_the_task_by_name` (line 32)
- `test_send_goes_through_the_loaded_celery_app` (line 40)
- `test_reconcile_enqueues_only_rows_unpropagated_past_the_age_oldest_first` (line 51)
- `test_reconcile_respects_the_batch_limit` (line 64)
- `test_mark_propagated_is_idempotent` (line 71)
- `test_placeholder_consumer_leaves_the_row_unpropagated` (line 81)
- `test_reconcile_task_calls_the_command_and_logs_the_count` (line 94)

`pytestmark = pytest.mark.django_db(databases=[PERSONAL, CATALOG])` (line 22).

### 13.6 The trigger tests

`backend/tests/ingestion/test_triggers.py` exists and references `guard_event_write`.

---

## 14. Appendix C — design-relevant observations

Facts distilled from the above, each traceable to a file:line.

### C.1 The signal already exists — but only for 7 of the ~14 page-visible fields

`LIFECYCLE_FIELDS` (`models.py:243-251`) = `start_time_utc`, `end_time_utc`,
`start_time_tz`, `status`, `is_sold_out`, `venue`, `superseded_by`.

`PublicEventPage` (`catalog_read.py:557-584`) = 18 fields, of which these are **NOT**
lifecycle fields: `title`, `description`, `canonical_url`, `venue_name`,
`venue_address`, `venue_city`, `venue_country_code`, `source_name`.

- `title`/`description`/`canonical_url` change via `apply_silent_update`
  (`event_writes.py:228-239`) → **no version bump, no `EventStateChange`, no outbox row.**
- `venue_name`/`venue_city`/`venue_country_code`/`venue_address` are **derived from the
  `Venue` row**, not the `Event` row. A rename of a `Venue` changes what the page renders
  without touching the `Event` at all — **and `venue_id` on the Event does not change
  either.** The trigger cannot see it.
- `source_name` comes from the `Source` row; a `Source` rename changes the page too.

**Consequence:** the "signal already exists" claim in the work item is **true for the
lifecycle fields and false for the rest of the page.** A design that treats
`event_version` as "the page changed" will be wrong for title edits and venue renames.

### C.2 The trigger does not fire on silent updates, and `EventStateChange` is append-only

- `apply_silent_update` writes no state change → **no outbox row → no signal.**
- `EventStateChange.append_only_mutable = frozenset({"propagated_at"})`
  (`models.py:478`) and the DB trigger (`migrations/0001_initial.py:71-73`) allows only
  `propagated_at` to change, NULL → value.
- **A "revalidation delivered" marker cannot live on `EventStateChange`.** It needs a new
  table (or a new column + a new trigger argument + a new grant).

### C.3 `propagate_state_change` is a no-op, and the reconciler re-offers forever

- `tasks.py:154-162` — logs at DEBUG, returns `None`, touches no row.
- `reconcile_outbox` (`outbox.py:43-56`) re-enqueues every row with
  `propagated_at IS NULL` and `occurred_at < now - 5 min`, oldest first, max 500.
- Because nothing ever sets `propagated_at`, **every unpropagated state change is
  re-delivered every 5 minutes, forever.**
- **This is the natural "retry" mechanism** for the revalidation feature — but it is
  *unbounded* and *unacknowledged*. A design that wants "retried and surfaced" must decide
  whether to use it (and add a bound) or to build a new one.

### C.4 There is exactly ONE post-commit enqueue site on the catalog side

`apps/ingestion/services/event_writes.py:176`. It fires once per lifecycle kind. It is
`robust=True`, so a broker outage does not roll back the write.

**This is the natural attachment point for the revalidation signal** — and it is
already the point where "the transaction has committed" is guaranteed.

### C.5 The backend CAN make an outbound HTTP call, but only through the port/adapter pattern

- `worker` and `apps` **may not** import `httpx`/`httpcore`/`requests`/`urllib3`
  (`pyproject.toml:230-252`).
- `worker` **may not** import `redis` either (`pyproject.toml:254-274`).
- The precedent for a second adapter reusing the hardened client:
  `adapters/calendar/ics.py` resolves `SourceFetchPort` from the registry rather than
  opening a socket.
- **`SourceFetchPort.fetch` is GET-only** (`adapters/crawl/http.py:534`). A revalidation
  endpoint that wants a POST body needs either a new port, an extended port, or a GET
  with a query-string payload.
- The SSRF policy (scheme, port, address, redirect, deadline, size) applies to anything
  routed through `SourceFetchPort`.

### C.6 The credential key cannot be reused for the revalidation secret

- `CALENDAR_CREDENTIAL_KEY` is `apps.personalization`-only
  (`credential-key` contract, `pyproject.toml:307-335`).
- `apps.ingestion` and `worker` **may not** import
  `apps.personalization.credentials`, and **may not** import `cryptography`.
- A new shared secret for signing the revalidation signal needs a **new env var** and a
  **new place for the format** — most likely `shared/` (stdlib-only, importable by
  `config`, `apps` and `worker`), which is exactly what `shared/credential_key.py` does
  for the calendar key.
- `shared/constants.py` already holds **signing salts** (`UNSUBSCRIBE_SIGNING_SALT`,
  `CLICK_SIGNING_SALT`) — but those are *labels*, and the secret is `DJANGO_SECRET_KEY`.
  Django's `Signer` with a per-purpose salt is the established precedent
  (`shared/constants.py:213-221`).

### C.7 The `personal` vs `catalog` split and the "who fires it" question

- All catalog writes happen in `apps/ingestion/services/event_writes.py` (and
  `apps/ingestion/event_fit/writes.py`).
- `apps/editorial` is **empty** — there is no editorial publish API.
- So today, lifecycle changes arrive **only from the worker** (the ingest pipeline).
  The work item's premise ("lifecycle changes arrive from both: user-facing writes on
  the API runtime, and the ingest pipeline on the worker") is **not yet true** — but the
  `on_commit(using=CATALOG)` seam is runtime-agnostic and covers both if an editorial
  write path is added later.
- **A worker task must use `Event.objects.using(CATALOG)`** — the architecture test
  (`checkers.py:78-103`) bans a missing or literal `using=`.

### C.8 Cache headers vs. revalidation — two separate facts, already stated

`shared/constants.py:795-815`:
- `PUBLIC_PAGE_CACHE_CONTROL = "public, max-age=3600, s-maxage=300..."` → actually
  `"public, max-age=3600, s-maxage=3600, stale-while-revalidate=86400"`.
- `PUBLIC_PAGE_VARY = "Accept-Encoding"`.

The comment says the revalidation work item *"is what makes the page current; the cache
TTL is only how long a page may sit without being revalidated, and the two are separate
facts."*

**The frontend currently has no `/events/[slug]` route and no ISR machinery.** The
backend's `PUBLIC_PAGE_CACHE_CONTROL` is set on the *Django* response, which the frontend
proxies — but the frontend's own page cache (Next.js) does not exist yet.

### C.9 The city's membership (AC #2) is a second, harder problem

- `City` has `slug`, `name`, `country_code`, `normalized_key`, `region`
  (`models.py:144-189`). `city.slug` is minted once and never re-minted.
- An event's city comes from `Venue.city_ref` (`models.py:204-207`) → `City`.
- The city page's read is `apps/ingestion/services/city_read.py:237-297`
  (`get_city_page`), which filters `EventFit` rows by `city_ref_id`.
- **`EventFit.city` is the venue's free text** (`models.py:427`); `EventFit.city_ref` is
  the canonical city (`models.py:430-432`).
- **Changing an event's venue changes the city** — and `venue_id` IS a lifecycle field,
  so the version bumps and a state change IS written. **But the *old* city and the *new*
  city are not both in the state change**: `_KIND_FACTS[ChangeKind.DETAIL_CHANGED]` includes
  `venue_fingerprint`, not the venue id (`event_writes.py:30-32`), and `_STATUS_KINDS`
  captures only `status` + times (`event_writes.py:26`). So **the affected city pages for
  a venue move are not derivable from the state-change row alone** — the consumer would
  have to look up the old city.
- `EventFit` rows are refreshed every 15 minutes by `worker.tasks.refresh_event_fits`.
  A city page's *content* therefore changes on that cadence regardless of the event
  change — **the city page has a different staleness profile than the event page.**

### C.10 The "idempotent and safe to repeat" criterion has a ready-made primitive

`outbox.mark_propagated` (`outbox.py:30-40`):
```python
    updated = (
        EventStateChange.objects.using(CATALOG)
        .filter(pk=state_change_id, propagated_at__isnull=True)
        .update(propagated_at=now or timezone.now())
    )
    return updated == 1
```
A conditional `UPDATE ... WHERE <col> IS NULL` returning `True` only on the first write.
This is the established "delivered exactly once" marker, and it is the model for any
revalidation ledger.

### C.11 `worker.tasks.tick` has a test that pins the enqueue order

`backend/tests/worker/test_tick.py` — **read it before adding a tick entry.**

### C.12 The frontend revalidation endpoint would collide with the Next.js proxy

`frontend/proxy.ts`: `export const config = { matcher: "/api/:path*" }` — everything under
`/api/` is rewritten to Django. **A Next.js revalidation endpoint must not live under
`/api/`** (or the proxy must be amended).

---

*End of report.*
