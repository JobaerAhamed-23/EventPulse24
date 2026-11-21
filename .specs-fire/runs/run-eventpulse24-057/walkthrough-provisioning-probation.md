---
run: run-eventpulse24-057
work_item: provisioning-probation
intent: city-picker-and-auto-collection
generated: 2026-11-21
mode: confirm
---

# Implementation Walkthrough: The city probation

## Summary

Item 7 made a reader's pick become a collection. It wrote exactly one status —
`collecting` — because at that point nothing had happened yet, and `live` would have been a
claim the code could not keep.

**This item is what keeps the claim honest.** After each ingest run of a provisioned source, the
probation asks two questions: *did this city publish anything?* and *has this source produced
nothing three times running?* — and moves the city's provisioning status to say so.

A city that publishes becomes `live`. A source that fetches successfully three times and
publishes nothing is **paused** — audited, never deleted. A city whose *every* source is paused
that way becomes `yielded_nothing`. A city an editor paused by hand becomes `paused`, because
that is a different fact.

**The whole point is that the surface can stop claiming "we're collecting events for {city}"
about something that is not going to happen.**

## The three risks the item carried into planning

**1. A healthy source must not be paused for doing its job.** A source re-reports the events it
already published, and the pipeline counts those as `unchanged` — a content-hash match. If
`unchanged` did not count as yield, every healthy source would accrue a zero-yield run per
poll and be **paused after twelve hours of doing its job perfectly**. The counter would
condemn the most reliable sources in the registry.

**2. A hand-pause is not a drought.** An editor pausing a source is a decision; a source that
publishes nothing three times is a fact about the feed. The city has to say different things,
and it can only do that if it knows which happened.

**3. The city-wide work must not hold a row lock it does not own.** The probation reaches for
*every* source of a city. Two concurrent runs of two different sources of the same city would
each hold their own source's lock while reaching for the other — and deadlock.

## Structure Overview

```text
backend/apps/ingestion/services/city_probation.py
├── CounterEffect              StrEnum — reset | increment | leave
├── RunClassification           frozen — effect + published + yielded
├── ProbationOutcome            frozen — what the probation decided, as plain data
├── ACTOR_LABEL                 "city_probation"
├── PROBATION_ACTION            "city.probation"
├── published_something(counts)     only "new" and "superseded"
├── yielded_something(counts)       six keys, and "unchanged" is the one that matters
├── classify_run(outcome, counts)   the PURE function — no db, no clock, no actor
├── probation_actor()
├── probate_after_run(...)          the entry point the ingest path calls
├── _mark_city_live(...)            "live" is terminal
├── _probate_city_status(...)       the whole rule, in order
└── _write_probation_audit(...)     city_id, never the city's name
```

## The rules the service holds

| Rule | Why it is a rule |
|---|---|
| Only `new` and `superseded` are **publication**. | Only they put a row into the catalogue for the first time. `updated` and `silent_updated` re-affirm a row that is already there — and `updated` *requires* a pre-existing row, which requires a prior publication, so excluding them can never cause a false negative. |
| `unchanged` **is** yield. | It is what a healthy source returns on every poll after the first. Without it every healthy source accrues a zero-yield run per poll. |
| `bound_other_source` is yield but **not** publication. | The event is in the catalogue because *another* source published it. The city is not empty; this source is simply redundant. |
| A 304 **leaves** the counter alone. | It proves neither emptiness nor content. Resetting would let a source alternate "empty" / "304" forever and never be condemned. |
| A fetch or parse failure **leaves** the counter alone. | The run never reached the feed, so it says nothing about the feed's contents. |
| `live` is **terminal**. | State B (covered, quiet) is not state C (never produced anything). A drought may pause a `live` city's source; it cannot un-publish the city. |
| A city yields nothing only when **every** source is zero-yield-paused. | One active source means the city is still collecting. |
| A city with **no** sources is not `yielded_nothing`. | That is `no_providers` — "we never tried", which is more specific than "we tried and got nothing". |
| A hand-pause makes the city `paused`. | Somebody stopped this on purpose. Only the probation's own pauses say `yielded_nothing`. |
| An unknown reason is a hand-pause. | "We do not know" is read conservatively: "somebody paused this" is a stronger claim than "the probation paused this". |

## Where the counter moves, and where the consequence runs

**The counter moves inside the run's own transaction.** It is the run's fact, and it belongs
with the run's audit row.

**The city-wide consequence runs after the commit**, in its own transaction:

```text
ingest_source._close
├── transaction.atomic(CATALOG)
│   ├── the run's own state (last_ingested_at, failures, etag, …)
│   ├── classify_run(outcome, counts)
│   └── source.consecutive_zero_yield_runs  ← the counter moves HERE
└── (committed — the row locks are released)
    └── probate_after_run(...)          ← and only now
        ├── pause_source(...)            ← its own transaction
        └── _probate_city_status(...)    ← another transaction, never nested
```

Running the probation *inside* the ingest transaction would hold the source's row lock while
reaching for the city's other sources and the provisioning row. Two concurrent runs of two
different sources of the same city would each hold their own lock while reaching for the
other, and deadlock. Nesting `pause_source` inside `_probate_city_status` would invert the
lock order against a hand-pause happening concurrently.

**A failure in the probation does not fail a successful ingest.** The run's outcome is already
recorded; the probation is a consequence. The city is one step behind until the next run,
which is a smaller harm than a failed ingest — the events are in the catalogue either way, and
a failed run would say the fetch did not work when it did.

## The hand-pause marker

```python
class PausedReason(models.TextChoices):
    MANUAL = "manual", "Paused by an editor"
    ZERO_YIELD = "zero_yield", "Paused after three runs with no yield"
```

**A column, not the audit trail.** The probation needs "is it paused, and by whom, *right
now*". The audit log is for accountability; the column is for state. And
`IngestionAuditEntry` is retained 24 months — beyond that the answer disappears and a paused
source would silently become a hand-pause.

**The audit `details` stay exactly `{"from", "to"}`**, because
`tests/ingestion/test_source_registry.py:621` asserts exact equality on `(action, details)` and
every other status change in the registry has that shape.

## The resume path

`provision_city`'s idempotency early return is narrowed to re-open **only** `yielded_nothing`:

- A `live` city stays `live` (item 7's contract).
- A `paused` city stays `paused` — **an editor's pause is not undone by a reader picking the
  city.**
- A `yielded_nothing` city resumes.

The resume looks each source up **first** (`find_source_by_url`), because `register_source`
**raises** on a duplicate URL and never updates an existing row. Then: a paused source is
**resumed**, a missing source is **registered**, a source with no `city_ref` gets it
**backfilled** (without it the probation would never see it again, and the city could never
yield nothing a second time), the counter is reset, and the city goes back to `collecting`.

## The key decisions

| Decision | The alternative | Why this one |
|---|---|---|
| The counter lives on `Source`, beside `consecutive_failures`. | A city-level counter. | A source is what actually goes quiet. A city-level counter would condemn a city with one dead source and one healthy one. |
| `city_ref` is a nullable `PROTECT` FK. | A text join on `Source.city`. | "Portland, Oregon" against a catalog row of "Portland, OR" — a text join misses rows. `Venue.city_ref` already exists for exactly this reason. |
| The registry never resolves the city name. | The registry calls `resolve_city`. | A second source of truth about which city a source belongs to — and a disagreement would mint a second `City` for the same place. Item 7's bug, re-opened. |
| The reason is a column. | The reason is in the audit details. | The audit details are pinned to `{"from", "to"}` by an existing assertion, and the audit log is retained 24 months. |
| `not_modified` **leaves** the counter. | `not_modified` resets it. | A 304 proves neither emptiness nor content. Resetting lets a source alternate "empty" / "304" forever and never be condemned. |
| Event-driven, not a scheduler tick. | A new Celery task. | The `tick()` enqueue list is pinned by *exact equality* — 7 parametrized minutes, 7 exact ordered lists. A new task breaks all seven. And a city that yields nothing should say so the moment it is known. |
| Only `yielded_nothing` re-opens. | Every status re-opens. | A `live` city must not be dragged back to `collecting`; an editor's pause must not be undone by a pick. |
| The counter moves inside the run's transaction. | Outside it. | It is the run's fact and belongs with the run's audit row. |

## What the mutation check found

**14 mutations, 14 caught.** The probe is at
`.specs-fire/runs/run-eventpulse24-057/mutation/mutation_probe.py` — outside `tests/` on
purpose, because it is a verification tool rather than a test and pytest would collect it.

**One mutation survived the first run, and it found a missing test.** "The probation runs
inside the ingest transaction" survived — the try/except around `probate_after_run` was
load-bearing and *nothing tested it*. Two tests were added and the mutation is now caught.

**A mutation that survives is a missing test**, and the probe is what finds it.

The two mutations that carry the item's meaning:

| Mutation | What it would mean | Caught by |
|---|---|---|
| `unchanged` removed from the yield set | Every healthy source is paused after twelve hours of doing its job perfectly | 2 tests |
| A hand-pause treated as a zero-yield pause | An editor's decision is reported as a drought | 3 tests |
| A `live` city overwritten | A city that published once can be un-published by a drought | 2 tests |
| The threshold lowered to one | Every source is paused after one empty poll | 6 tests |

## The trap worth remembering

**A `PROTECT` foreign key is `DEFERRABLE INITIALLY DEFERRED`.** Django creates it that way, so
inserting a child row queues a deferred FK trigger event that is only evaluated at commit. And
PostgreSQL refuses to `ALTER TABLE` a relation with pending trigger events:

```
django.db.utils.OperationalError: cannot ALTER TABLE "ingestion_source"
because it has pending trigger events
```

This broke 11 tests in `tests/ingestion/test_migrations.py` — a fixture that drops a
constraint, lets a test insert a row, and puts the constraint back in a `finally` block. The
fix is one line before the `ALTER TABLE`:

```python
cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
```

It evaluates the pending events inside the test's transaction, without committing it.

**How it was located.** The work was stashed (`git stash push -u`), the tests re-run, and the
stash restored: the same 12 tests passed before the change and failed after it. The regression
was mine, and it was proved before the fix was written.

**Why the fixture changed and not the design.** The fixture simulates the *pre-migration*
database — it drops a constraint to build a state the migration can then be tested against.
The new foreign key has nothing to do with the cadence ceiling, and `PROTECT` is right by
default: a city is never deleted (`Venue` and `EventFit` already protect it). The guard
`test_every_ingestion_foreign_key_is_protect` was **not** relaxed.

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

`city_probation.py` and `city_provisioning.py` at **100%** coverage. Overall 98.80%.

**No API surface changed** → no `make client`, and `tests/api/test_contract.py` is unaffected.

## What this unblocks

Item 9 (`browse-collecting-states`) needs the four honest states on Browse. This item writes
three of the four statuses it will read:

- **`live`** — the city has events.
- **`live` but quiet** — covered, and its sources have gone quiet. The surface shows both,
  because they are different facts.
- **`yielded_nothing`** — tried, and gave nothing. Not `no_providers` (never tried).
- **`paused`** — an editor stopped it.

Item 9 turns them into copy.
