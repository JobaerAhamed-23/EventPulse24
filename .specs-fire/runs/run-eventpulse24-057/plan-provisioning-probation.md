---
run: run-eventpulse24-057
work_item: provisioning-probation
intent: city-picker-and-auto-collection
generated: 2026-11-21
mode: confirm
---

# Item 8: `provisioning-probation` — Probation for a city that yields nothing

## Context

Run `run-eventpulse24-057`, intent `city-picker-and-auto-collection`, work item 8 of 11.

Item 7 landed the **city provisioning service** (`backend/apps/ingestion/services/city_provisioning.py`):
a reader's pick now mints the `City` row, registers a `Source` per provider spec, and writes a
`CityProvisioning` row whose status is the sentence the surface reads about a city.

But it writes exactly one status: `collecting`. The model's `Status` choices hold `live`,
`no_providers`, `yielded_nothing`, `paused` and `failed`, and **nothing in the codebase writes
them**. So today every provisioned city says "collecting" forever — including a city whose only
source fetches successfully every four hours and returns nothing, or returns a 404, or whose
provider serves a feed that will never have an event in it.

That is the problem this item closes. A thousand-city dropdown mints sources that fetch every
four hours forever, for cities with one reader and zero yield, and the page keeps claiming
"we're collecting events for {city}" about something that is not going to happen.

The outcome: the honesty clock and the cost ceiling. A city that publishes becomes `live`; a
city whose sources run three times with nothing becomes `yielded_nothing`, and its sources are
paused — audited, never deleted.

**The guarantee this run is held to** (intent guarantee #1): *"The stored city is the picked
city. Never silently rewritten to anything else."* The probation touches the *provisioning
status*, never the reader's stored preference. A reader's pick is not a retry request.

## The three decisions already made

Confirmed with the user before planning:

1. **`Source.city_ref` FK to `City`.** `Source.city` is a plain string; `CityProvisioning` links
   by FK. The probation must find "every source for a city" to decide `yielded_nothing`. A
   nullable `PROTECT` FK — mirroring `Venue.city_ref`, which already exists for exactly this
   reason — makes the join exact.
2. **The zero-yield counter lives on `Source`**, beside `consecutive_failures`, and is moved
   inside `ingest_source._close`'s existing transaction.
3. **Both open gaps are closed**: a marker distinguishes a hand-pause from the probation's own
   pause (hand → `paused`, probation → `yielded_nothing`), and `provision_city` gains a resume
   path for a `yielded_nothing` city.

## The design

### The status machine

| Current | Event | Result | Why |
|---|---|---|---|
| `collecting` | a run publishes (`new`/`superseded`) | `live` | the city has events |
| `collecting` | a run yields but publishes nothing | `collecting` | yield ≠ publication |
| `collecting` | 3 consecutive zero-yield runs → the source is paused | `collecting` | another source may still be active |
| `collecting` | **all** sources paused for zero yield | `yielded_nothing` | tried and gave nothing |
| `collecting` | a source paused **by an editor** | `paused` | a deliberate decision |
| `live` | anything | `live` | **terminal** |
| `live` | its source goes quiet 3× → the source is paused | `live` | the city still has events |
| `yielded_nothing` | re-provisioned | `collecting` | sources resumed, counter reset |
| `paused` | re-provisioned | `paused` | an editor's pause is not undone by a pick |
| `no_providers` / `failed` | anything | unchanged | a fact about coverage/attempt, not yield |
| (no sources at all) | anything | unchanged | "never tried" ≠ "tried and got nothing" |

### What counts as "published" and what counts as "yield"

Two named constant tuples in `backend/shared/constants.py`:

- **`PUBLISHED_COUNT_KEYS = ("new", "superseded")`** — the only two ways a row enters the
  catalogue. Only publication can move a city to `live`. (`updated` and `silent_updated`
  re-affirm an existing row; excluding them from publication can never cause a false negative,
  because `updated` requires a pre-existing row, which requires a prior publication.)
- **`YIELDED_COUNT_KEYS = ("new", "superseded", "updated", "silent_updated", "unchanged",
  "bound_other_source")`** — a superset. **`unchanged` is the critical member**: a content-hash
  match is what a *healthy* source returns on every poll after the first. Without it, every
  healthy source accrues a zero-yield run per poll and is paused after twelve hours of doing its
  job perfectly.

### The counter's three effects

`classify_run(outcome, counts)` — a **pure** function — returns one of three effects:

| outcome | effect | why |
|---|---|---|
| `ok`, yielded something | **reset** | the feed gave us something |
| `ok`, yielded nothing | **increment** | the honest zero-yield run |
| `not_modified` (304) | **leave** | the feed is alive and unchanged; it proves neither emptiness nor content |
| `fetch_failed` / `parse_failed` | **leave** | the run never reached the feed; it says nothing about the feed's contents |

**`not_modified` LEAVES the counter alone — it does not reset it.** The AC says a run "that never
reached the feed must not count toward the zero-yield probation"; a 304 *did* reach the feed, so
it is not a zero-yield run — but it is also not evidence that the previous zero-yield runs were
wrong. Resetting on a 304 would let a source alternate `ok`-empty / 304 forever and never be
condemned. **Leave** is the only option that only moves on evidence.

### When the probation runs

**In the ingest path, immediately after the run's transaction commits.** Not on a scheduler tick.

- A periodic job would need a new Celery task, a new beat entry and a new claim — and the
  `tick()` enqueue list is **pinned by exact equality** in `tests/worker/test_scheduling_tasks.py`
  (7 parametrized minutes, 7 exact ordered lists). Adding a task breaks all seven.
- Running it *inside* the ingest transaction would hold the source's row lock while doing
  city-wide work (a two-source deadlock) and would make the pause's audit row roll back with the
  run.

So: **`_close` moves the counter inside its transaction; the city-wide consequence runs after the
commit, in its own transaction.** The probation is **event-driven** — it runs when a run
completes, which is exactly when it must run.

**Two separate transactions, never nested.** `pause_source` opens its own atomic block and writes
its own audit row; `probate_city` opens another. Nesting them would invert the lock order against
a hand-pause happening concurrently.

### The hand-pause marker

**A new `Source.paused_reason` column** (`CharField(32, blank=True)`, `Source.PausedReason` =
`MANUAL` / `ZERO_YIELD`), set by `pause_source(reason=...)`.

- **A column, not the audit trail.** The probation needs "is it paused, and by whom, *right
  now*". The audit log is for accountability; the column is for state. (And `IngestionAuditEntry`
  is retained 24 months — beyond that the answer disappears.)
- **The audit `details` stay exactly `{"from", "to"}`.** `tests/ingestion/test_source_registry.py:621`
  asserts exact equality on `(action, details)`; the reason lives on the **row**.
- **An empty reason means "we do not know"**, and the city treats it as a hand-pause — the
  conservative reading. Only the probation's own pauses should produce `yielded_nothing`.

### The resume path

`provision_city`'s idempotency early return is narrowed to re-open **only** `YIELDED_NOTHING`:

- A `live` city stays `live` on a re-pick (item 7's contract).
- A `paused` city stays `paused` — an editor's pause is not undone by a reader picking the city.
- A `yielded_nothing` city resumes: `find_source_by_url` first (a URL that is already registered
  **raises** `SourceAlreadyRegisteredError` and never updates), `resume_source` for the paused
  ones, `register_source` only for genuinely missing ones, the counter reset, and the city back
  to `collecting`.

The resume also **backfills `city_ref`** on sources that predate the column — without it the
probation would never see them again.

## Files to change

### New

- `backend/apps/ingestion/services/city_probation.py` — the service:
  `classify_run`, `published_something`, `yielded_something`, `CounterEffect` (a `StrEnum`),
  `RunClassification`, `ProbationOutcome` (frozen), `probate_after_run`, `probate_city`.
  Lives inside `ingestion` (AD-16 — it owns `SOURCE`, `CITY` and `CITY_PROVISIONING`).
- `backend/apps/ingestion/migrations/0016_source_city_ref_and_probation.py` — three `AddField`s:
  `Source.city_ref` (FK, `PROTECT`, `null=True`, `blank=True`, `related_name="sources"`),
  `Source.consecutive_zero_yield_runs` (`PositiveIntegerField(default=0)`),
  `Source.paused_reason` (`CharField(32, blank=True)`).
  Additive and nullable — **no data migration, no backfill** (the resume path backfills lazily).
- `backend/tests/ingestion/test_city_probation.py` — the item's own proof.

### Modified

- `backend/apps/ingestion/models.py` — the three `Source` fields + `Source.PausedReason`.
  `city_ref` uses the **string** `"City"` (the `City` class is defined *after* `Source`).
- `backend/apps/ingestion/services/ingest_source.py` — `_close` classifies the run, moves the
  counter inside its transaction, and calls `probate_after_run` **after** the commit (wrapped so
  a probation failure never fails a successful ingest; the log carries no city name — AD-13).
  **The `ingest_source` audit `details` are unchanged** — `{"outcome", "counts"}` exactly, which
  `tests/ingestion/test_ingest_source.py:177,249` asserts.
- `backend/apps/ingestion/services/source_registry.py` — `pause_source(reason="")`,
  `_set_status(reason="")`, `resume_source` clears the reason **and** the counter,
  `register_source(city_ref=None)`, and a `_reprobate_city` hook after a status change.
  **The lazy import of `city_probation` inside the function is required** — `city_probation`
  imports `source_registry` at module level, so a module-level import back would be a cycle.
  (`city_ref` bypasses `clean_source_input` — the cleaner cannot resolve a city *name*, and
  letting the registry re-resolve it would re-open item 7's "second source of truth" bug. The
  reason is written to the **row**, not into the audit `details`, so the audit shape is
  byte-identical to every other `register_source` row.)
- `backend/apps/ingestion/services/city_provisioning.py` — `city_ref=city` on registration (the
  load-bearing link), the `YIELDED_NOTHING` re-open, `_resume_choice`, the `city.resumed` audit
  row (city id, never the city name — AD-13).
- `backend/apps/ingestion/admin.py` — the two new display fields in `readonly_fields`; the
  `pause_sources` action passes `reason=Source.PausedReason.MANUAL`.
- `backend/shared/constants.py` — `ZERO_YIELD_RUN_THRESHOLD = 3`, `PUBLISHED_COUNT_KEYS`,
  `YIELDED_COUNT_KEYS`.
- `backend/tests/architecture/test_write_ownership.py` — the `ingestion_cityprovisioning` comment
  ("written only by `services/city_provisioning.py`") is now **false**; `services/city_probation.py`
  writes it too. Update the comment — the ownership entry itself is unchanged.

### Unchanged, deliberately

- `backend/worker/tasks.py` — **no new Celery task**. See "When the probation runs" above.
- `backend/apps/ingestion/services/scheduling.py` — untouched.
- `backend/tests/ingestion/test_models.py`, `tests/wall/test_schema_placement.py` — no new
  **model** and no new **table**, so the enumerations hold. `test_every_ingestion_foreign_key_is_protect`
  is satisfied by making `city_ref` `PROTECT` (the guard is right by default).
- `frontend/` — untouched. `browse-collecting-states` (item 9) owns the surface.

## Tests

New file `backend/tests/ingestion/test_city_probation.py`:

- **Pure classification** (no DB): every `counts` key's published/yield verdict; `not_modified`
  leaves the counter; `fetch_failed` / `parse_failed` leave it.
- **Service behaviour** (DB): a published run makes the city `live`; a `live` city stays `live`
  when its source goes quiet; the pause happens *at* the threshold (counter 2 → not paused); the
  pause is audited and does not delete the source; the city yields nothing only when **every**
  source is zero-yield-paused; a hand-paused source makes the city `paused`, not
  `yielded_nothing`; a city with no sources is not `yielded_nothing`; no audit row when the
  status does not change; the audit row carries the city id and never the city name.
- **End-to-end** (real `ingest_source`, `ScriptedFetchPort` serving an empty `calendar()`):
  **the AC's headline test** — three empty feeds pause the source and move the city to
  `yielded_nothing`, with the "still active" assertions after runs 1 and 2 being what make it
  fail if the threshold is one.

Added to `backend/tests/ingestion/test_city_provisioning.py`: the resume tests (resumes rather
than duplicates; a `live` city is not dragged back to `collecting`; a `paused` city stays paused;
a resumed source starts its probation afresh).

Added to `backend/tests/ingestion/test_source_registry.py`: the pause records the reason **on the
row** (the `details` stay `{"from", "to"}`); the resume clears the reason and the counter.

**Mutation check** — the run's rule is *a test must be able to fail*. Each of these must be caught:
threshold → 1; `unchanged` removed from `YIELDED_COUNT_KEYS`; `fetch_failed` increments; a
`live` city overwritten; a manual pause treated as zero-yield; the `city_ref` backfill removed
from the resume path.

## Verification

```bash
uv run --directory backend ruff check apps/ingestion shared tests/ingestion
uv run --directory backend ruff format apps/ingestion tests/ingestion   # NEVER from the repo root
uv run --directory backend lint-imports                                   # 21 kept, 0 broken
uv run --directory backend python manage.py makemigrations --check --dry-run
uv run --directory backend pytest -q
```

`ruff format` is scoped to `apps/ingestion` and `tests/ingestion` **only** — running it at the
repo root drags the pre-existing drift in `backend/tests/shared/test_retention_published.py`
into the diff.

No API surface changes → **no `make client`**, and `tests/api/test_contract.py` is unaffected.

## Artifacts

Per the run's practice, each work item owes three artifacts in
`.specs-fire/runs/run-eventpulse24-057/`:

- `plan-provisioning-probation.md` — this plan.
- `test-report-provisioning-probation.md` — the AC-by-AC validation, the mutation table, the
  tests-written breakdown, the commands.
- `review-report-provisioning-probation.md` — the findings, the security/architecture notes, the
  "deliberately not changed" list.
- `walkthrough-provisioning-probation.md` — the summary, the risks, the structure overview, the
  rules held, the key decisions, what the mutation check found, verification, and what it unblocks.

Then: advance the phase to `review`, run `complete-run.cjs … --complete-item
provisioning-probation`, update `run.md`, and commit.

## What this unblocks

Item 9 (`browse-collecting-states`) needs the four honest states on Browse: `collecting`,
`live`-but-quiet, `no_providers`/`yielded_nothing`, `paused`. This item writes three of the four
statuses it will read (`live`, `yielded_nothing`, `paused`); item 9 turns them into copy.
