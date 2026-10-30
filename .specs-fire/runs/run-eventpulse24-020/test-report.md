---
run: run-eventpulse24-020
work_item: event-fit
intent: onboarding-and-account
generated: 2026-10-30
status: passing
---

# Test Report: Event Fit (AD-10, FR-26)

> **These are the post-review figures.** The code review added a package wall, four
> new tests and five new revert cases; the numbers below are the ones the tree
> produces **now**, not the ones it produced before the review.

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Item-scoped | 236 | 0 | 0 | 100% (every module this item created) |
| **Total (whole backend)** | **3098** | **0** | **0** | **99.01%** |

The 236 item-scoped tests are a subset of the 3098-test backend suite. The whole
backend suite is **3098 passed, 0 failed** in 83.72s; coverage is **99.01%** across
6662 statements, with **162 files at 100%**.

**Every module this item created or changed is at 100%**:

| Module | Coverage |
|--------|----------|
| `domain/event_fit.py` | 100% |
| `apps/ingestion/event_fit/__init__.py` | 100% |
| `apps/ingestion/event_fit/writes.py` | 100% |
| `apps/ingestion/event_fit/reads.py` | 100% |
| `config/management/commands/backfill_event_fit.py` | 100% |
| `worker/tasks.py` | 100% |

The 66 uncovered statements are pre-existing gaps elsewhere in the codebase.

## Test Commands

```bash
# The item's own tests
cd backend && .venv/bin/python -m pytest \
    tests/domain/test_event_fit.py \
    tests/ingestion/test_event_fit.py \
    tests/ingestion/test_event_fit_command.py \
    tests/architecture/test_event_fit_separation.py \
    tests/architecture/test_import_contracts.py -q

# The whole backend suite, with coverage
cd backend && .venv/bin/python -m pytest -q --cov --cov-report=term-missing

# The linter and the format check
cd backend && .venv/bin/python -m ruff check . && .venv/bin/python -m ruff format --check .

# The import contracts
make lint-backend

# Django's own checks
cd backend && .venv/bin/python manage.py check

# The coverage gates
make coverage-backend

# The revert verification harness
cd backend && bash revert_event_fit_check.sh
```

## What Was Added

| File | Tests | Covers |
|------|-------|--------|
| `backend/tests/domain/test_event_fit.py` | 36 | The pure function: every score band at its boundary, every tag rule, the local-day computation across a DST transition and across the date line, the city slug, determinism |
| `backend/tests/ingestion/test_event_fit.py` | 33 | The catalog side: the write, the ingest hooks, the read, the backfill, the staleness refresh, the city-change retirement |
| `backend/tests/ingestion/test_event_fit_command.py` | 7 | The `backfill_event_fit` command: idempotence, the dry run, the batching, the skipped-event report |
| `backend/tests/architecture/test_event_fit_separation.py` | 8 | AD-10: the two kinds of explanation never cross, in **both** directions, and the re-export bypass is planted |
| `backend/tests/architecture/test_import_contracts.py` | 4 new | The contract's *shape* is pinned, and two new planted violations for the package wall |

`backend/revert_event_fit_check.sh` is the **revert verification harness** — twenty-one
cases, each of which patches a rule out of the source, runs the tests, records the
outcome, and restores. It is how the revert table below was produced.

## What Was Changed in the Existing Tests

Five existing test files changed, all of them because the **model set grew**, the
**tick's job list grew**, or the **import contract's shape became load-bearing**:

| File | Change |
|------|--------|
| `backend/tests/ingestion/test_models.py` | The model count 7 → 8, and `EventFit` added to the retention-category table (`SOURCE_REGISTRY`) |
| `backend/tests/wall/test_schema_placement.py` | `ingestion_eventfit` added to the catalog-side table list |
| `backend/tests/worker/test_scheduling_tasks.py` | The tick's expected job list, plus the new refresh-cadence and refresh-task tests |
| `backend/tests/architecture/test_import_contracts.py` | The `event-fit-separation` plants updated for the package, plus a **new** pin on the contract's shape |

**No existing test's expectations were weakened.** The tick's parametrization was
*corrected*, not relaxed: see the note under "The refresh cadence" below.

## The Properties Pinned

### The score is the lower of two bands (and never a sum)

The score is the **minimum** of the proximity band and the confidence band. Taking the
lower is the honest rule: a badly-extracted event happening tonight is not a good fit,
however soon it is — and a weighted sum would need weights nobody can justify without
labelled data.

- `test_the_score_is_the_lower_of_the_two_bands` — a good event a week out beats a
  great-confidence event a fortnight out.
- `test_the_score_is_the_lower_of_the_two_bands_the_other_way` — and the reverse
  direction, so the rule is not accidentally one-sided.
- `test_the_confidence_bands` — eight parametrized cases, each pinned at the exact
  constant and at the band edges.
- `test_an_event_with_no_confidence_scores_on_proximity_alone` — no
  confidence is not a reason to refuse an indicator.

### The day boundary is the event's own local day, never UTC's

This is the rule the work item calls out as the easiest to get wrong, and the tests are
built around it.

- `test_an_event_tonight_is_not_tomorrow_even_when_utc_says_so` — an event at 23:30
  local on Friday is "tonight" on Friday, even when UTC has already rolled over to
  Saturday.
- `test_a_dst_transition_does_not_move_the_day` — the spring-forward and fall-back
  transitions, where the UTC day and the local day disagree by an hour.
- `test_a_date_line_crossing_keeps_the_events_day` — Auckland, where the local day is
  a day ahead of UTC's.
- `test_the_local_day_is_the_events_not_the_readers` — the general case.

### "This weekend" means the one weekend in view

The weekend rule took three attempts to get right, and the reasoning is worth
recording because the wrong answers are plausible.

- `test_the_weekend_in_view_from_each_day_of_the_week` — eight parametrized cases, one
  per weekday, each asking what "this weekend" means from that day.
- `test_the_weekend_after_the_one_under_way_is_not_in_view` — from a Saturday, the
  weekend seven days out is **not** "this weekend"; it is the one after.
- `test_the_next_weekend_from_a_saturday_is_still_the_weekend_in_view` — the Sunday of
  the weekend under way is still in view.
- `test_the_weekend_across_new_year_is_still_this_weekend` — the year boundary, where an
  ISO-week-number comparison would lose the weekend entirely (2027-01-01 is ISO week 53
  of 2026).

**Every weekend is named by its Saturday, and the comparison is between dates.** Three
formulations were rejected before that one worked: a plain "within seven days" bound
(wrong in both directions), an ISO-week-number comparison (wraps at the year boundary),
and a Monday-of-the-week comparison (wrong from a Saturday).

### The place tag is the venue's city, and it is plain ASCII

- `test_the_city_tag` — parametrized over the slug rules: `"San Francisco"` and
  `"san francisco"` produce the same key, `"São Paulo"` → `in_sao_paulo`,
  `"München"` → `in_munchen`. A tag key has to survive a JSON round-trip, a URL segment
  and a CSS selector unchanged, so accents are folded to their ASCII base.
- `test_the_place_tag_is_last` — the tag order is fixed: time tags first, place last.

### A fit is written when the event is created, and recomputed when it changes

- `test_a_new_event_gets_a_fit_from_the_ingest_path` — the fit is part of the event's
  creation, inside the same transaction, from the ingest path's **own hook** rather
  than from the writer called by hand.
- `test_a_changed_event_gets_a_recomputed_fit` — a lifecycle change moves the event, so
  the fit is recomputed against the new facts.
- `test_the_recomputed_fit_is_not_stale` — the regression this pins. The write bumps
  `event_version` in the database with `F()`, so the in-memory event still holds the old
  number; a fit computed from that stale instance would record the old version, and the
  read would skip it — the event would **silently vanish** from the preview rather than
  show a wrong tag.

### A stale row is never served

- `test_a_stale_fit_is_never_served` — the Event moved on since the fit was computed,
  so the fit describes an event that no longer exists. It is skipped, not served.
- `test_the_read_skips_an_event_that_has_already_started` — an event that has started
  is not coming.
- `test_the_read_skips_an_unpublished_event` — an `in_review` event is not publicly
  listed (AD-6, AD-8).

### The read serves the persisted row; it computes nothing (AD-10)

- `test_the_read_does_not_compute_anything` — the score on the row is the score that is
  served, even when it disagrees with what a fresh computation would say. This is the
  AD-10 rule made testable: the read is not a calculator.
- `test_the_read_returns_the_persisted_tags_untouched` — the read serves the tags as
  they stand.
- The architecture test asserts the read module never calls `compute_event_fit` — a
  **static** check, so the guarantee survives a future edit that adds a call.

### The top N comes back in the right order

- `test_the_read_returns_the_best_fit_first` — the better-fit event is deliberately the
  **later** one, so the test cannot pass whichever way the query is written. (See
  "R10 — the case that did not fail" below.)
- `test_the_read_breaks_a_score_tie_on_the_start_time` — among equally good fits, the
  sooner one is the more useful one.
- `test_the_read_returns_three_by_default` and `test_the_read_honours_an_explicit_limit`.

### The backfill is idempotent, and in the strong sense

- `test_the_backfill_is_idempotent` — running it twice writes the same rows, not twice
  as many. The write is an upsert, which is what makes this true.
- `test_the_backfill_does_not_move_the_computed_at_of_a_row_that_did_not_change` — the
  **strong** sense: a row that already says the same thing is not rewritten at all, so
  its `computed_at` — which says when the fit was last *computed* — does not lie.
- `test_a_fit_whose_tags_changed_is_rewritten` — and the other direction, so the
  "don't rewrite" branch cannot become "never rewrite".
- `test_the_backfill_batches` — the batching is the bound on the refresh cost.
- `test_the_backfill_skips_an_unpublished_event`.

### A venue that changes city retires the old fit

- `test_a_fit_is_retired_when_the_venue_moves_city` — the event does not appear in the
  preview of a city it has left.
- `test_a_fit_is_not_duplicated_by_a_city_spelled_differently` — "Brooklyn" and
  "brooklyn" are one city, so there is one row and one preview entry.

### The refresh is what keeps "Tonight" from going stale

- `test_the_refresh_recomputes_the_fits` — the tick's answer to time passing. The
  refresh is a **writer**, not a render-time computation, which is the other half of
  AD-10's rule: the render never computes, and something has to.
- `test_the_refresh_batches` and `test_the_refresh_skips_an_event_with_no_venue_city`.

### The two kinds of explanation never cross (AD-10)

`tests/architecture/test_event_fit_separation.py` asserts this in **both** directions,
on the real tree, **AST-based** rather than import-based — a module can reach another
through an alias, through a re-export, or through a function it was handed, and a
runtime import check would only catch the first.

- `test_personalization_does_not_import_the_event_fit_read` — the wall, checked on the
  **package prefix**, so it catches a direct import, an alias, and a re-export alike.
- `test_the_wall_catches_a_re_export` — the bypass that broke the first wall is
  **planted**: a module that re-exports the read, and a module that imports *it*, and
  the assertion is that the wall sees the name. This is the case that proves the wall
  is a wall.
- `test_personalization_may_still_read_the_public_catalog` — the wall is **narrow on
  purpose**. Saving an event to your calendar needs the event's public facts, so
  `personalization` may import `catalog_read`. This test pins that the wall is not
  wider than it needs to be.
- `test_ingestion_does_not_import_personalization` — the Event Fit is computed on the
  catalog side, from catalog facts.
- `test_the_event_fit_read_never_reads_the_personal_schema` — a visitor with no
  session (AD-12) gets this and nothing else; a read of `personal` would be a leak even
  if the value were discarded.
- `test_the_domain_function_is_the_only_place_a_fit_is_computed` — there is one place
  that computes, and it is the writer.

The two import-linter contracts (`event-fit-separation`, `event-fit-catalog-only`) make
the same wall **structural**, and `tests/architecture/test_import_contracts.py` plants
a violation for each so the contracts are known to break when they should. The
contract's **shape** is pinned too — see "The wall is a package" below.

## Acceptance Criteria Validation

| Criterion | Result | Where it is pinned |
|-----------|--------|-------------------|
| A **pure function** in `domain/event_fit.py` takes start, end, timezone, extraction confidence, city and "now"; returns an integer 1–5 and an ordered tuple of tag keys | ✅ | `domain/event_fit.py` — stdlib only, enforced by the `domain-pure` contract; `test_the_fit_is_frozen`, `test_the_score_is_never_outside_one_to_five` |
| Thresholds in `shared/constants.py` | ✅ | `shared/constants.py` — every band boundary is a named constant |
| Tags are generic, time- and place-based | ✅ | `test_tonight_needs_the_evening`, `test_tomorrow_is_the_next_local_day`, `test_the_city_tag`, `test_the_place_tag_is_last` |
| Day boundaries computed in the event's own IANA timezone, not UTC | ✅ | `test_an_event_tonight_is_not_tomorrow_even_when_utc_says_so`, `test_the_local_day_is_the_events_not_the_readers` |
| A test pins a DST transition and a date-line case | ✅ | `test_a_dst_transition_does_not_move_the_day`, `test_a_date_line_crossing_keeps_the_events_day` |
| The score is deterministic — no randomness, nothing computed at render time | ✅ | `test_the_same_inputs_always_give_the_same_output`, `test_the_fit_is_frozen`; `domain/` has no clock read at all |
| `domain/` coverage stays at 100% | ✅ | `make coverage-backend` → `domain/` TOTAL 619, 0 missed, 100% |
| An `EventFit` model on the catalog side keyed by `(event, city)`, with score, tags, `computed_at` and the input `event_version` | ✅ | `apps/ingestion/models.py`; the `event_fit_event_city_uq` unique constraint and the `event_fit_score_range_ck` check |
| AD-15 retention category; written **only** by `ingestion` | ✅ | `RetentionCategory.SOURCE_REGISTRY`; the `models-ingestion` protected contract; `test_the_domain_function_is_the_only_place_a_fit_is_computed` |
| Recomputed when the event is created or changes, inside the existing ingest path and transaction discipline | ✅ | `test_a_new_event_gets_a_fit_from_the_ingest_path`, `test_a_changed_event_gets_a_recomputed_fit` |
| A stale row is never served | ✅ | `test_a_stale_fit_is_never_served`, `test_the_recomputed_fit_is_not_stale` |
| The plan states how time-relative staleness is handled **and why it complies** with AD-10 | ✅ | `plan.md` — "The Staleness Problem"; the refresh is a **writer** on a cadence, so the render still computes nothing |
| A management command backfills and is idempotent | ✅ | `test_the_command_is_idempotent`, `test_the_dry_run_writes_nothing`, `test_the_command_batches` |
| A published read returns the top N (default 3) for a city, ordered by score then start time, with the persisted score and tags | ✅ | `test_the_read_returns_three_by_default`, `test_the_read_returns_the_best_fit_first`, `test_the_read_breaks_a_score_tie_on_the_start_time` |
| It never reads `personal` | ✅ | `test_the_event_fit_read_never_reads_the_personal_schema` (static) |
| Event Fit never feeds an authenticated surface as a Relevance Pulse substitute | ✅ | The `event-fit-separation` contract (a **package**); `test_personalization_does_not_import_the_event_fit_read`; `test_the_wall_catches_a_re_export` |
| An architecture test asserts `personalization` doesn't import the Event Fit read | ✅ | `tests/architecture/test_event_fit_separation.py` |
| `make lint-imports` passes | ✅ | 19 kept, 0 broken |
| `manage.py check` passes | ✅ | no issues (1 silenced) |
| The coverage gates pass | ✅ | 99.01% overall (≥80%), `domain/` 100% |
| Tests cover each tag rule at its boundaries, the score bands, the local-day computation across DST, recompute on version change, no stale row served, backfill idempotence, and the top-N ordering | ✅ | 236 tests across five files |

## Reverting Each Rule

Every rule was verified by **reverting it and watching the test fail**. A regression test
that passes against the broken code is not a regression test. The harness is
`backend/revert_event_fit_check.sh`; it patches the source, runs the test files,
records the outcome, restores, and ends with a `git diff --stat` that proves every
patch was put back.

| # | Rule | Reverted | Result |
|---|------|----------|--------|
| R1 | The day boundary is the event's own local day, not UTC's | both `astimezone` calls redirected to UTC | **16 tests fail** ✓ |
| R2 | An event that has already started is in the last band | the `until_start <= 0` check removed | **2 tests fail** ✓ |
| R3 | The score is the **lower** of the two bands | `min(proximity, confidence)` → `max(...)` | **18 tests fail** ✓ |
| R4 | The confidence band is a band, not a pass-through | the four comparisons replaced by `return 5` | **7 tests fail** ✓ |
| R5 | The weekend is the one weekend in view, named by its Saturday | the Saturday comparison replaced by a seven-day bound | **4 tests fail** ✓ |
| R6 | The place tag is the venue's city, slugged | the NFKD accent-folding removed | **2 tests fail** ✓ |
| R7 | The fit row records the version it was computed from | `event_version` hard-coded to 1 | **2 tests fail** ✓ |
| R8 | A stale fit is never served | the version check disabled | **1 test fails** ✓ |
| R9 | The read serves the persisted score and tags; it computes nothing | the served score/tags hard-coded | **2 tests fail** ✓ |
| R10 | The preview is ordered by score, then by start time | `-score` dropped from the ordering | **1 test fails** ✓ |
| R11 | The ingest path recomputes the fit when the event changes | the `outcome != "unchanged"` guard disabled | **2 tests fail** ✓ |
| R12 | The ingest hook re-reads the event, so the fit carries the new version | the re-read removed | **3 tests fail** ✓ |
| R13 | The backfill is an upsert, so it is idempotent | `update_or_create` → `get_or_create` | **5 tests fail** ✓ |
| R14 | The fit is written when the event is created, inside the same transaction | the create-path `_write_fit` call removed | **1 test fails** ✓ |
| R15 | The tick refreshes the fits every fifteen minutes | the refresh guard disabled | **5 tests fail** ✓ |
| R16 | The read never reaches the personal schema | `PERSONAL` added to the read's imports | **1 test fails** ✓ |
| V1 | A fit for a city the event has left is retired | the delete of the other-city rows removed | **1 test fails** ✓ |
| V2 | A row that already matches is not rewritten | the comparison removed | **2 tests fail** ✓ |
| V3 | The Event Fit is a package, so the wall cannot be opened with a third name | the contract narrowed to one module name | **3 tests fail** ✓ |
| V4 | The wall checks the package PREFIX, not a list of names | the prefix check replaced by an equality check | **1 test fails** ✓ |
| V5 | The wall test can read a planted module outside the backend tree | the outside-the-tree fallback removed | **58 tests fail** ✓ |

**All twenty-one reverts were restored** and the suite re-run green afterwards;
`git diff --stat` confirmed no revert artifacts remained.

### The cases that did not fail, and what they taught

Three of the twenty-one cases did not fail on the first run. All three were holes in
the suite wearing a harness's clothes, and all three are now caught.

**R10 — the ordering test could not tell two orderings apart.**
`test_the_read_returns_the_best_fit_first` had the better-fit event as the **sooner**
one (2 hours vs 5 days), so ordering by score and ordering by start time gave the
**same answer** and the test passed whichever way the query was written. The fix was
in the test, not the source: the better-fit event is now the **later** one.

**V3 — the wall was load-bearing and the suite could not tell.** With the package
contract in place, reverting it to name-only left **all 212 tests passing**. The fix
was to pin the contract's *shape* in `test_import_contracts.py` — the same way
`single-ics-parser` and `redis-sdk` are already pinned there — so that narrowing the
wall is now an observable failure.

**V4 — the planted bypass was not the real bypass.** The re-export plant imported
`apps.ingestion.event_fit.reads`, which a wall made of a *list* of names would also
catch. The real bypass is the **name of the module that does the re-exporting**:
`personalization` importing `apps.ingestion.event_fit_preview`. The plant was
rewritten to model both hops — the module that re-exports, and the module that imports
*it* — and the assertion now fails as it should.

### The harness had a bug, and it was a bad one

The harness backed each file up to `/tmp/revert_backup_$(basename "$file")` — keyed on
the **basename** alone. Three cases target `writes.py` (R7, R13, V1), so they shared one
backup path; case A's restore overwrote case B's backup, and the file was left
**reverted** for every case that followed. R7 reported `PATTERN NOT FOUND — the revert
did not apply`, and the final `git diff --stat` showed `writes.py` still holding
`get_or_create`.

Two fixes: a **unique backup per case**, and — the important one — **the restore is
verified, not assumed**. Each case compares the restored file against its backup byte
for byte and aborts the run if they differ. A restore that silently fails is worse than
no restore: it makes every later result a claim about a tree that does not exist.

## Notes on the Implementation

Five decisions are worth recording, because each one could reasonably have gone the
other way.

### The Event Fit is a **package**, and that is what makes the wall hold

AD-10 forbids the two kinds of explanation from crossing, and the obvious way to enforce
that is a check on import *names*. But `personalization` legitimately imports
`catalog_read` — saving an event to your calendar needs the event's public facts.

The first version of the wall named **two leaves**
(`apps.ingestion/services/event_fit.py` and `.../event_fit_read.py`). A third module
that re-exported the read — `event_fit_preview.py`, two lines — walked straight
through it, with the import contract **green** and the architecture test **green**. A
wall made of names is opened by adding a name.

So the Event Fit became a **package** — `apps/ingestion/event_fit/`, with `writes.py`
and `reads.py` inside it — and the contract names the package:

```toml
forbidden_modules = [
    "apps.ingestion.event_fit",
    "apps.ingestion.event_fit.*",
]
```

A package is **one name that covers everything inside it**, so a new Event Fit module
is inside the wall by default rather than outside it until somebody notices.

**And the two guards are complementary, each honest about its scope.** The import
contract catches every *direct* import of the package or anything in it. It cannot
catch a module *outside* the package that re-exports what is inside — a `forbidden`
contract matches on import names and has no data-flow analysis — so the AST test
checks the **package prefix** instead, and `apps.ingestion.event_fit_preview` starts
with `apps.ingestion.event_fit`.

`test_personalization_may_still_read_the_public_catalog` pins that the wall is narrow
on purpose.

### The staleness refresh is a writer on a cadence, and that is how it complies

"Tonight" is a statement about *now*, so a persisted tag goes stale as time passes and
not only when the event changes. AD-10 says the *render* never computes — so the
recompute has to live somewhere else. It lives in `worker.tasks.refresh_event_fits`,
enqueued by the tick every fifteen minutes, which recomputes the fits of the published
events and writes them.

The rule is unchanged in substance: the render path reads a persisted row and computes
nothing. What the refresh adds is the *writer* half, which is what makes "tonight" mean
today's evening rather than the evening it was written on.

### The cadence is approximate, and the two cadences nest

The tick keeps no state, so "every fifteen minutes" means "on every tick whose minute is
a multiple of fifteen" — approximate in the same way the reconciler's five minutes is.

The first version of the tick test assumed minutes 15, 30 and 45 were **not** multiples
of five. Every multiple of fifteen *is* a multiple of five, so the refresh always lands
on a reconciler minute and the two cadences nest: the refresh never runs alone. The
test's expectations were corrected and the nesting is now documented in the tick's own
docstring, so the next person does not make the same arithmetic mistake.

### The score band is a duration, and the plan said "today"

The plan's band table originally said the top band was an event that "**starts
today**". The code says "starts within 24 hours", measured as a duration from `now` —
and the **code is right**, because a duration is timezone-independent, because the local
day is already computed for the tags (a second "day" rule would be a second truth), and
because "how soon" is what the preview answers while "starts today" reads as a calendar
fact. The plan was corrected, not the code, and the reasoning is recorded there.

### An event with no venue city gets no row at all

The city is not guessed from the source, the title, or the source's city. An event in an
unknown city is in no city's preview, and a preview that puts it in the wrong one is
worse than a preview that leaves it out. The `city` column therefore has a
`CheckConstraint` forbidding the empty string, and `test_an_event_with_no_venue_city_gets_no_fit_row`
pins the behaviour.

There is a subtlety the command test found: an event with **no venue at all** is never
even *seen* by the backfill's query, so it is not in the count either — while an event
with a venue whose city is blank **is** seen and **is** skipped, and the command says so.
Hiding the difference would make the output look like a bug.

## The Final Gate

```
pytest -q --cov --cov-report=term-missing
3098 passed in 83.72s (0:01:23)
TOTAL                                             6662     66    99%
162 files skipped due to complete coverage.
Required test coverage of 80.0% reached. Total coverage: 99.01%

pytest tests/domain/test_event_fit.py \
         tests/ingestion/test_event_fit.py \
         tests/ingestion/test_event_fit_command.py \
         tests/architecture/test_event_fit_separation.py \
         tests/architecture/test_import_contracts.py -q
236 passed in 5.47s

coverage report --include='domain/*' --fail-under=100
TOTAL     619      0   100%

coverage report --include='domain/event_fit.py,apps/ingestion/event_fit/*,config/management/commands/backfill_event_fit.py'
TOTAL     207      0   100%
5 files skipped due to complete coverage.

ruff check .
All checks passed!

ruff format --check .
366 files already formatted

lint-imports
Contracts: 19 kept, 0 broken.

manage.py check
System check identified no issues (1 silenced).

revert_event_fit_check.sh
R1–R16 and V1–V5: every case caught (each run failed at least one test)
```

## What This Item Does Not Cover

- **The Pulse Preview endpoint and the geo lookup** — `pulse-preview-api-and-geo` owns
  the HTTP surface, the geolocation and the city resolution. This item ships the
  **read service** that surface will call: `list_event_fit_for_city(city=..., now=...)`.
- **The frontend preview** — `frontend-pulse-preview` owns the surface that renders the
  score and the tags.
- **The Relevance Pulse** — this item is the other half of AD-10's pair, and the
  separation between them is the point. The Relevance Pulse itself is
  `personalization`'s, and nothing here reaches it.
- **The SEO pages** — AD-10 names the SEO pages as one of the Event Fit's surfaces, but
  this item delivers the read; the pages are a separate surface.
- **`end_time_utc`** — the pure function accepts it "for completeness — a long event
  still starts when it starts, and the fit is about the start". It is not used yet, and
  saying so is better than pretending it is.

### Test Result

**Passing.** 3098 passed, 0 failed, 99.01% coverage, 100% on all six modules this item
created or changed, ruff clean, format clean, 19/19 import contracts kept, and all
**twenty-one** rules pinned by a revert that was watched to fail.
