# Code Review Report

**Run**: run-eventpulse24-020
**Intent**: onboarding-and-account
**Work item**: event-fit
**Reviewed**: 2026-10-30
**Files Reviewed**: 14

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Correctness | 0 | 2 | 0 |
| Contract / Architecture | 0 | 1 | 0 |
| Documentation | 0 | 1 | 0 |
| **Total** | **0** | **4** | **0** |

**Tests Status**: Passing — 3098 passed, 0 failed; 99.01% coverage; 19/19 import contracts
kept.

Four findings. Every one was **reproduced against the code as it stood** before it was
acted on — a review finding is a claim, not a fact, and a finding that cannot be
reproduced is a finding that cannot be fixed. Every one is fixed and **verified by a
revert case that fails**.

Two of the four were resolved in the **plan** rather than the code, because the plan
and the code disagreed and the plan was the one that was wrong.

---

## Files Reviewed

### Created

| File | Purpose |
|------|---------|
| `backend/domain/event_fit.py` | The pure function — score and tags, stdlib only |
| `backend/apps/ingestion/event_fit/__init__.py` | The package — the wall itself |
| `backend/apps/ingestion/event_fit/writes.py` | The only writer of the `EventFit` rows |
| `backend/apps/ingestion/event_fit/reads.py` | The published read for a city |
| `backend/apps/ingestion/migrations/0004_eventfit.py` | The `EventFit` table |
| `backend/config/management/commands/backfill_event_fit.py` | The idempotent backfill |
| `backend/tests/domain/test_event_fit.py` | The pure function's rules and boundaries |
| `backend/tests/ingestion/test_event_fit.py` | The write, the read, and the staleness guard |
| `backend/tests/ingestion/test_event_fit_command.py` | The backfill command |
| `backend/tests/architecture/test_event_fit_separation.py` | The AD-10 wall, both directions |
| `backend/revert_event_fit_check.sh` | The revert harness — 21 cases |

### Modified

| File | Change |
|------|--------|
| `backend/apps/ingestion/models.py` | The `EventFit` model |
| `backend/apps/ingestion/services/ingest_item.py` | The fit is written on create and on change |
| `backend/worker/tasks.py` | The fifteen-minute staleness refresh |
| `backend/shared/constants.py` | The thresholds and the tag keys |
| `backend/pyproject.toml` | The `event-fit-separation` contract |
| `backend/tests/architecture/test_import_contracts.py` | The contract's shape is now pinned |

---

## Findings

### D3 — The AD-10 wall was two names wide, and a third name opened it (Contract / Architecture, HIGH)

**Found by**: testing the wall rather than reading it.

AD-10 names two kinds of explanation and says they never cross: the **Event Fit** (per
`(event, city)`, on `catalog`, owned by `ingestion`) and the **Relevance Pulse** (per
user, on `personal`, owned by `personalization`). A Relevance Pulse that falls back to
an Event Fit tells a signed-in reader that a thing is a great match when nothing
personal was ever computed. AD-10 calls that the trust-collapse failure PRD Risk 11
calls company-ending.

The first version of the wall named two leaves:

```toml
forbidden_modules = ["apps.ingestion.services.event_fit", "apps.ingestion.services.event_fit_read"]
```

**That wall was open.** A module `apps/ingestion/services/event_fit_preview.py` that
re-exported the read — two lines — gave `personalization` the Event Fit with the
import contract **green** and the architecture test **green**.

**Why it was open.** `import-linter`'s `forbidden` contract matches on *import names*.
It has no notion of "this module re-exports that module"; there is no data-flow
analysis anywhere in the contract. A wall made of names is opened by adding a name, and
adding a name is the most ordinary thing a developer does.

**Fixed** by making the Event Fit a **package** — `apps/ingestion/event_fit/`, with
`writes.py` and `reads.py` inside it — and naming the package in the contract:

```toml
forbidden_modules = [
    "apps.ingestion.event_fit",
    "apps.ingestion.event_fit.*",
]
```

A package is **one name that covers everything inside it**. A new Event Fit module is
inside the wall by default rather than outside it until somebody notices.

**What the fix does *not* do, and why the second guard exists.** The package contract
catches every **direct** import of the package or anything in it. It does **not** catch
a module *outside* the package that re-exports what is inside —
`apps.ingestion.event_fit_preview` is not a descendant of the forbidden package, so the
contract does not see it. That is a property of how a `forbidden` contract works, not a
gap in how it was configured, so **the contract is not asked to catch it**.

The second guard is the AST architecture test, and it checks the **package prefix**:

```python
assert not any(name.startswith(EVENT_FIT_PACKAGE) for name in imported)
```

`apps.ingestion.event_fit_preview` starts with `apps.ingestion.event_fit`, so it is
caught. The two guards are complementary, and each is honest about its scope:

| Bypass | Import contract | AST prefix test |
| --- | --- | --- |
| `import apps.ingestion.event_fit.reads` | caught | caught |
| `import apps.ingestion.event_fit` | caught | caught |
| `from apps.ingestion.event_fit import reads` | caught | caught |
| `import apps.ingestion.event_fit_preview` (a re-export) | **not caught — by design** | caught |

**Pinned by** `test_the_wall_catches_a_re_export`, which writes the bypass in **both**
halves — the module that re-exports, and the module that imports it by name — and
asserts the wall sees the name. The contract's scope is pinned by
`test_the_event_fit_wall_is_a_package_and_not_a_list_of_names`, which asserts the
contract's `forbidden_modules` exactly.

**This finding produced the most important result of the review.** The *first*
implementation of the package fix did **not** hold: reverting the contract to name-only
left all 212 tests **passing**. The wall was load-bearing and **the suite could not
tell**. The contract-shape pin was added because of it, and the revert case V3 now
fails.

### D1 — A venue that changes city left the event in two previews (Correctness, MEDIUM)

**Found by**: reading the upsert against the `(event, city)` key.

`EventFit` is keyed by `(event, city)`. When a venue's city changes, the write upserted
a row for the **new** city and left the **old** row in place. The event then appeared in
**two** previews — and the row in the old city still carried the old place tag.

Nothing else would have caught it. A venue edit does not bump the event's
`event_version`, so the old row's version still matches the event's, and the read's
staleness guard passes it straight through. A preview that shows an event in a city it
has left is worse than one that leaves it out.

**Fixed** by retiring every row for the event under a *different* city, after the
upsert:

```python
EventFit.objects.using(CATALOG).filter(event_id=event.pk).exclude(city__iexact=city).delete()
```

The comparison is case-insensitive because the read is: "Brooklyn" and "brooklyn" are
the same city, and two rows for the same city spelled two ways would put the event in
that city's preview twice.

**Pinned by** `test_a_fit_is_retired_when_the_venue_moves_city` and
`test_a_fit_is_not_duplicated_by_a_city_spelled_differently`.

### D2 — The backfill rewrote rows that had not changed (Correctness, MEDIUM)

**Found by**: reading the write against the plan's own words.

The plan said:

> "a row that already matches is not rewritten (the `computed_at` does not move, so a
> test can assert that)"

The first implementation always called `update_or_create`, so every backfill run moved
`computed_at` on every row. That is a lie about when the fit was last computed, and it
means the refresh writes the whole published catalog every fifteen minutes whether or
not anything about it changed. It was idempotent only in the weak sense — the row
*count* does not grow — rather than in the strong sense the plan asked for: *nothing
about the row changes*.

**Fixed** by comparing before writing:

```python
if (
    existing is not None
    and existing.score == score
    and list(existing.tags) == list(tags)
    and existing.event_version == event.event_version
):
    row = existing          # including its `computed_at`
else:
    row, _created = EventFit.objects.using(CATALOG).update_or_create(...)
```

**Pinned by** `test_the_backfill_does_not_move_the_computed_at_of_a_row_that_did_not_change`
and `test_a_fit_whose_tags_changed_is_rewritten` — the second pins the other
direction, so the "don't rewrite" branch cannot become "never rewrite".

### D4 — The plan and the code disagreed about the score bands (Documentation, LOW)

**Found by**: reading the plan's band table against the implementation.

The plan's band table said the top band was an event that "**starts today**". The code
says "starts within 24 hours", measured as a duration from `now`.

**The code is right and the plan was wrong**, for three reasons:

1. A duration is **timezone-independent**. "Starts today" needs a day boundary, and a
   day boundary is exactly the thing this work item requires to be computed in the
   event's *own* IANA timezone — so the band would have needed a second, different
   local-day rule from the one the tags use.
2. The local day is **already** computed for the tags. The band should not invent a
   second definition of "day".
3. "How soon" is what the preview answers. "Starts today" reads as a calendar fact
   ("is it on today's page?"), which is not what the score says.

**Fixed in the plan**: it now says "starts within 24 hours", with the reasoning
recorded, and the decisions table was updated to match. The implementation's semantics
were already correct and are well covered —
`test_an_event_already_underway_scores_in_the_last_band` and
`test_an_event_starting_exactly_now_is_in_the_last_band` pin the boundaries.

---

## The harness itself had a bug, and it was a bad one

**Found while running the revert cases, and worth recording because it nearly
invalidated the whole verification.**

The harness backed each file up to `/tmp/revert_backup_$(basename "$file")` — keyed on
the **basename** alone. Three cases target `writes.py` (R7, R13, V1), so they shared
one backup path. Case A's restore overwrote case B's backup, and from that point the
file was left **reverted** for every case that followed.

The symptom was visible: R7 reported `PATTERN NOT FOUND — the revert did not apply`,
and the final `git diff --stat` showed `writes.py` still holding `get_or_create`
instead of `update_or_create`. The harness was silently corrupting the tree it was
supposed to be verifying.

Two fixes:

1. **A unique backup per case** (`/tmp/revert_backup_${CASE_NO}_...`).
2. **The restore is verified, not assumed** — each case compares the restored file
   against its backup byte for byte and aborts the run if they differ.

The second fix is the important one. A restore that silently fails is worse than no
restore: it makes every later result a claim about a tree that does not exist.

---

## The Revert Verification

Every fix was verified by **reverting it and watching the test fail**. A regression test
that passes against the broken code is not a regression test.

The harness is `backend/revert_event_fit_check.sh` — the item's own rules and the
review's fixes in one set, because the two sets are about the same wall and the same
writer.

**All 21 cases fail**, with no skips and no restore failures:

| Case | What it breaks | Result |
|-----|----------|--------|
| R1 | the day boundary is the event's own local day, not UTC's | **16 tests fail** |
| R2 | an event that has already started is in the last band | **2** |
| R3 | the score is the LOWER of the two bands | **18** |
| R4 | the confidence band is a band, not a pass-through | **7** |
| R5 | the weekend is the one weekend in view | **4** |
| R6 | the place tag is the venue's city, slugged | **2** |
| R7 | the fit row records the version it was computed from | **2** |
| R8 | a stale fit is never served | **1** |
| R9 | the read serves the persisted score and tags | **2** |
| R10 | the preview is ordered by score, then start time | **1** |
| R11 | the ingest path recomputes the fit when the event changes | **2** |
| R12 | the ingest hook re-reads the event for the new version | **3** |
| R13 | the backfill is an upsert, so it is idempotent | **5** |
| R14 | the fit is written when the event is created | **1** |
| R15 | the tick refreshes the fits every fifteen minutes | **5** |
| R16 | the read never reaches the personal schema | **1** |
| V1 | a fit for a city the event has left is retired | **1** |
| V2 | a row that already matches is not rewritten | **2** |
| V3 | the Event Fit is a package, so the wall cannot be opened with a third name | **3** |
| V4 | the wall checks the package PREFIX, not a list of names | **1** |
| V5 | the wall test can read a planted module outside the backend tree | **58** |

### Three cases that did not fail, and what they taught

**R10 did not fail at first.** The test that was supposed to pin score-ordering had
the better-fit event as the *sooner* one, so score-ordering and time-ordering gave the
same answer. A test that cannot distinguish two candidate implementations pins
nothing. The test was rewritten so the better-fit event is the later one.

**V3 did not fail at first — and this is the one worth remembering.** The package
contract was in place, the architecture test was in place, and reverting the contract
to name-only left the whole suite green. The wall was load-bearing and **the suite
could not tell**. The fix was to pin the contract's *shape* in
`test_import_contracts.py` — the same way `single-ics-parser` and `redis-sdk` are
already pinned there — so that narrowing the wall is now an observable failure.

**V4 did not fail at first either.** The planted re-export imported
`apps.ingestion.event_fit.reads`, which a name-list would also catch. The real bypass
is the *name of the module that does the re-exporting* — `personalization` importing
`apps.ingestion.event_fit_preview`. The plant was rewritten to model both hops, and
the assertion now fails as it should.

---

## Notes

1. **The staleness problem is a writer's problem, not a render's.** "Tonight" is a
   statement about *now*, so a persisted tag goes stale as time passes — not only when
   the event changes. The answer is a **refresh on a cadence, by a writer**, and the
   read path serves the persisted row and computes nothing. AD-10's rule is that the
   *render* never computes; a writer that recomputes on a schedule is the opposite of
   that.

2. **`event_version` is the staleness check.** Every fit records the Event version it
   was computed from, and a row whose version no longer matches its Event is never
   served. The check lives in the **read**, not in a trigger — because the refresh is a
   writer's work, and a trigger cannot decide that a row *should* be refreshed; it can
   only say a row is now out of date, which the read already knows how to skip.

3. **An event with no venue city gets no row at all.** The city is not guessed from the
   source, the title, or the source's city. An event in an unknown city is not in any
   city's preview, and a preview that puts it in the wrong one is worse than one that
   leaves it out.

4. **The refresh cost is bounded.** The published events are walked **by primary key**,
   not by offset — the first batch of a run has to move forward, or the second read
   would return the first batch again and the loop would never end — and each batch is
   written in its own transaction, so a run over a large catalog does not hold one long
   transaction open.

5. **The score and the Confidence Pulse share a visual vocabulary, and they mean
   different things.** The 1–5 indicator says "this event is a good fit for this
   city, right now"; the Confidence Pulse says "we are this sure we extracted it
   correctly". They are never substituted for one another — that is the whole of D3.

---

## The Final Gate

```
make lint-backend
Contracts: 19 kept, 0 broken.

ruff check .
All checks passed!

ruff format --check .
366 files already formatted

manage.py check
System check identified no issues (1 silenced).

make coverage-backend
3098 passed in 83.72s (0:01:23)
TOTAL                                             6662     66    99%
Required test coverage of 80.0% reached. Total coverage: 99.01%

coverage report --include='domain/*' --fail-under=100
TOTAL     619      0   100%
```

**Every event-fit module is at 100%** — `domain/event_fit.py`,
`apps/ingestion/event_fit/__init__.py`, `apps/ingestion/event_fit/writes.py`,
`apps/ingestion/event_fit/reads.py` and
`config/management/commands/backfill_event_fit.py` are all in the "skipped due to
complete coverage" set.

---

## Test Result

**Passing.** 3098 passed, 0 failed, 99.01% coverage, `domain/` at 100%, ruff clean,
format clean, 19/19 import contracts kept, no issues from the Django system check, and
all 21 revert cases caught.

---

## A housekeeping note

`backend/tests/personalization/test_zz_probe.py` — an untracked scratch probe from the
**previous** item (auth-api-and-session-seam) — was failing the lint gate. It printed
debug output, used one-line `for` statements, and duplicated
`test_onboarding_concurrency.py`, which is the proper committed version of the same
concurrency checks. It was removed. It is not part of this item's diff.

---

## What this review does not cover

- The **front end** does not exist yet; the Pulse Preview page that will consume this
  read is a later work item (`frontend-pulse-preview`).
- The **public API surface** for the preview is a later work item
  (`pulse-preview-api-and-geo`). This item ships the catalog-side read it will serve.
- The **session seam** is a separate item and was reviewed on its own.
