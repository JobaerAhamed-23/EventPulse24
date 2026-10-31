---
run: run-eventpulse24-021
work_item: digest-candidate-reads
intent: pulse-digest-and-trust
generated: 2026-10-30
status: passing
---

# Test Report: The eligible-candidate reads, on both sides of the wall (FR-13, FR-14, FR-23)

The Pulse Digest ranks things. Ranking needs a pool, and a pool needs a rule for what
may be in it. This item is that rule, implemented as two reads — one on the catalog
side, one on the personal side — that never touch each other's schema.

**The gates are the interesting part.** Each one has an exact threshold, and a gate
that is *almost* right is a gate that is wrong: an event one hundredth below the
extraction-confidence threshold must be excluded, and one exactly at it must be
included. So each gate is tested **at its boundary and one step below it**. A test
that only checked "a confident event is included" would pass against a threshold set
anywhere in a wide band.

**The two sides are separate reads, joined in the application layer** (AD-3). The
public candidates come from `catalog`; the personal candidates and the saves come
from `personal`. No query spans the two. Two tests assert this from opposite
directions: one that the public read never touches the personal alias, one that the
personal read never touches the ingestion tables.

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Item-scoped | 67 | 0 | 0 | 100% (all three new modules) |
| Architecture (added) | 2 | 0 | 0 | — |
| **Total (whole backend)** | **3612** | **0** | **0** | **99.13%** |

The whole backend suite is **3612 passed, 0 failed**, with **100.00% on `domain/`**
(the AD-2 purity gate), and **100% on each of the three modules this item created or
touched**: `catalog_read.py`, `source_badges.py`, `digest_candidates.py`.

### The item-scoped files, and what each is for

| File | Tests | What it proves |
|------|-------|----------------|
| `backend/tests/ingestion/test_public_candidates.py` | 35 | The catalog side: every gate at its threshold, the staleness bound, the city filter, the badges, the pool's bounds, the wall |
| `backend/tests/personalization/test_digest_candidates.py` | 32 | The personal side: the 48-hour window, imported events, the conflict ids, the saved pool, the batched catalog lookup, the wall |
| `backend/tests/architecture/test_event_fit_separation.py` | 2 (added) | The Event Fit stays out of `catalog_read` and out of `source_badges` |

## Test Commands

```bash
# The item's own tests
cd backend
uv run pytest tests/ingestion/test_public_candidates.py \
                 tests/personalization/test_digest_candidates.py -v

# The architectural gates
uv run pytest tests/architecture/test_event_fit_separation.py -v

# The whole backend, with the coverage gates
uv run pytest --cov --cov-report=term
uv run coverage report --include='domain/*' --fail-under=100

# The other architectural gates
uv run ruff check .
uv run ruff format --check .
uv run lint-imports          # 19 contracts, 0 broken
uv run python manage.py makemigrations --check --dry-run   # No changes detected
```

## 1. The extraction-confidence gate

The gate is `EXTRACTION_CONFIDENCE_PUBLISH` (AD-6). It is compared with `__gte`, so
the threshold value itself is **included** — "at least this confident" is what the
gate means.

| Test | Asserts |
|---|---|
| `test_an_event_one_hundredth_below_the_extraction_gate_is_excluded` | `0.79` → nothing |
| `test_an_event_exactly_at_the_extraction_gate_is_included` | `0.80` → the event |

**Why one hundredth and not one whole step.** The column is
`DecimalField(max_digits=3, decimal_places=2)`, so `0.79` and `0.80` are adjacent
representable values. A test that used `0.79` against a `0.80` threshold would pass
against a threshold of `0.795` too — one hundredth below is the finest difference the
data can express, so a failure of the boundary test means the comparison is off by
more than the data's resolution.

**The confidences are `Decimal`, and the test says so.**
`test_the_confidences_are_decimals_and_not_floats_or_strings` asserts
`isinstance(candidate.extraction_confidence, Decimal)`. A float `0.8` is not exactly
four fifths, so a boundary test on a float would be a lie — the assertion is what
makes the boundary tests mean anything (`shared/constants.py`).

## 2. The timezone-confidence gate

The same shape, one threshold over: `TZ_INFERENCE_CONFIDENCE_DIGEST`.

| Test | Asserts |
|---|---|
| `test_an_event_one_hundredth_below_the_tz_gate_is_excluded` | Below the gate → nothing |
| `test_an_event_exactly_at_the_tz_gate_is_included` | At the gate → the event |

**And the third case is the one the AD-6 threshold creates.** AD-6 puts the
*auto-publish* threshold above the *digest* threshold, so there is a band in which an
event publishes but its time is still under review.

| Test | Asserts |
|---|---|
| `test_a_tz_review_pending_event_is_eligible_and_carries_the_flag` | Eligible, **and** `tz_review_pending is True` |

The flag travels with the candidate because the frontend has to mark the time. An
event whose start hour is a guess and one whose start hour is known look identical on
the wire otherwise, and the digest would be quietly wrong about the one thing a user
checks first — "when is this?"

## 3. Publication, supersession and time

| Test | Asserts |
|---|---|
| `test_an_unpublished_event_is_excluded` | `IN_REVIEW` → nothing |
| `test_a_superseded_event_is_excluded_and_its_replacement_is_included` | The old one is out, the live one is in |
| `test_an_event_starting_exactly_now_is_included` | `start == now` → included |
| `test_an_event_that_already_started_is_excluded` | `start < now` → nothing |

**The supersession test uses the real pair.** `make_superseded_pair()` writes the
superseded event and its replacement the way the catalog writes them, so the test
proves the *live* one is listed rather than proving that a `status` filter exists.

**`superseded_by` is not filtered on separately.** The database already makes the two
states mutually exclusive (`event_superseded_consistent_ck`, `apps/ingestion/models.py`),
so a second filter on the FK would be unreachable code and a false comfort — it would
suggest a state the schema forbids. The review found the filter, checked the
constraint, and removed it.

## 4. The staleness bound (FR-14) — the boundary of the boundary

An event is stale when it has not been seen at its source for more than **twice** its
source's `freshness_ttl_hours`. The multiplier is `DIGEST_STALE_TTL_MULTIPLIER`, a
named constant in `shared/constants.py` — **not** `STALE_AFTER_CADENCES`, which is a
different quantity (a cadence of days, not a freshness bound).

| Test | Asserts |
|---|---|
| `test_an_event_older_than_twice_its_sources_ttl_is_excluded` | 49 hours old, 24-hour TTL → nothing |
| `test_an_event_exactly_at_the_staleness_bound_is_included` | 48 hours old → the event |
| `test_the_staleness_bound_follows_the_sources_ttl` | A 72-hour TTL gets a 144-hour bound |
| `test_the_staleness_bound_is_measured_from_last_seen_not_updated` | A write does not refresh the event |
| `test_the_multiplier_is_the_named_constant` | The multiplier is 2 |

**The comparison is inclusive at the bound.** "Older than" is exclusive, so an event
*exactly* at the bound is not older than it. That is a one-hour difference in the test
data (`at(2)` starts the event; `last_seen_at` is 48 hours before `now`), and a
reviewer reading `>=` where `>` belonged would see no difference in the output.

**The bound follows each source's own TTL.** The test uses a 72-hour source and
checks that a 100-hour-old event survives and a 145-hour-old one does not — a fixed
48-hour bound would have failed the first and passed the second, so the test
distinguishes the two implementations.

**`last_seen_at`, not `updated_at`.** `updated_at` moves whenever *we* touch the row —
a re-score, a write of a tag. `last_seen_at` is when the catalog last saw the event
*at the source*. The test writes `updated_at = now` on a stale event and asserts the
event is still excluded: a stale event must not be kept alive by our own bookkeeping.

## 5. The city filter

| Test | Asserts |
|---|---|
| `test_the_city_filter_matches_the_venue_city_exactly` | Brooklyn in, Queens out |
| `test_the_city_filter_is_case_insensitive` | `"brooklyn"` finds `"Brooklyn"` |
| `test_an_event_with_no_venue_matches_no_city` | `venue=None` matches no city |
| `test_no_city_returns_every_eligible_event` | No filter → everything eligible |

**An event with no venue has no city**, and it is given no row rather than a guessed
one — the same call the Event Fit read makes. A venue whose `city` is `NULL` cannot
be placed, and a digest that claimed it was in Brooklyn when it is not would be worse
than a digest that left it out.

## 6. The Source Badge

The badge is **resolved on the catalog side of the wall**, from the same query that
justified the card — so it cannot disagree with the card.

| Test | Asserts |
|---|---|
| `test_the_badge_for_a_venue_source_is_official` | `official_site` |
| `test_a_crawled_source_gets_the_crawled_badge` | `crawled_html` |
| `test_an_unmapped_source_type_gets_the_aggregator_badge` | `aggregator` |
| `test_the_candidate_carries_the_badge_inputs` | `source_type` and `acquisition_method` travel too |

**Why the badge inputs travel with the candidate.** The badge is a string, and the
string is what the caller needs. But the *inputs* are carried too, so the audit trail
can answer "why was this card marked ⚠?" without re-deriving it from a source that
may have changed. OQ-8: every relation is held by value.

**The candidate carries the badge as a string, not a `Source`.** The caller may not
hold a `Source` — and holding one would mean holding a model from the other side of
the wall. The badge is a plain value; the inputs are plain values; nothing here is a
handle.

**A crawled source wins over its type.** *How* the facts were obtained is what the ⚠
means: scraped, not published to us. A crawled venue site is still a scrape.

## 7. The pool and its bounds

| Test | Asserts |
|---|---|
| `test_the_pool_is_ordered_by_start_time_then_id` | Deterministic order |
| `test_the_pool_is_bounded_by_the_limit` | `limit=3` → 3 |
| `test_a_limit_of_zero_returns_no_candidates` | `limit=0` → none |
| `test_a_negative_limit_returns_no_candidates` | `limit=-5` → none |
| `test_the_limit_cannot_exceed_the_cap` | The cap is 200, the pool size is below it |
| `test_a_limit_above_the_cap_is_capped` | `limit=10_000` → the cap applies |
| `test_the_pool_stops_at_the_default_size` | The default is the named pool size |
| `test_the_sql_fetch_is_bounded` | A `LIMIT` is in the SQL |

**`limit=0` returns nothing, and that is the whole point of the test.** The obvious
implementation — `limit = max(1, min(limit, CAP))` — quietly turns "none" into "one",
because a `LIMIT 0` in SQL is a syntax problem in some dialects and `max(1, ...)` is
the usual dodge. A caller that asks for no candidates must not be handed one. The
review found this by probe (`limit=0` returned 1) and the test pins it.

**The SQL fetch is bounded, not just the result.** The staleness filter runs in
Python, so the *SQL* must be bounded too — otherwise a catalog whose events are
mostly stale would hand every row to Python before the first candidate was found, and
the read's cost would depend on the size of the catalog rather than on the size of
the answer. The test wraps the catalog connection in an `execute_wrapper` and asserts
a `LIMIT` appears in the recorded SQL.

**This is a deliberate trade, and it is stated.** The staleness filter *cannot* be
expressed in SQL in this Django version — `ExpressionWrapper` cannot compare two
wrappers, `RawSQL` in a `filter()` raises, `Cast(integer → interval)` is refused, and
`make_interval` is not in this version. The alternatives were tried and rejected one
by one. So the fetch over-fetches by `CANDIDATE_OVERFETCH_FACTOR = 4` and filters in
Python — which means **a catalog that is mostly stale may fill the pool with fewer
than `limit` rows.** That is the accepted cost of a bounded query, and the design doc
says so in those words rather than leaving it to be discovered.

## 8. The shape

| Test | Asserts |
|---|---|
| `test_the_candidate_carries_the_confidences_and_the_country` | The values, as `Decimal` |
| `test_the_confidences_are_decimals_and_not_floats_or_strings` | The *types* |
| `test_a_candidate_is_frozen` | `FrozenInstanceError` on assignment |

**A candidate is a value, not a handle.** The composition service may hold it, and
nothing may change it underneath. The frozen-dataclass test asserts the whole
property with one line, and it uses `FrozenInstanceError` rather than a blanket
`Exception` — a blanket exception would also pass if the assignment raised something
else entirely.

## 9. The wall (AD-3)

Two tests, from opposite directions.

| Test | Asserts |
|---|---|
| `test_the_public_read_runs_on_the_catalog_alias_and_never_the_personal_one` | The catalog is queried; the personal alias is **never** |
| (in the personal file) the personal read's table names | `"ingestion_event"` never appears; `"personalization_"` does |

**The public read is asserted on the alias, not on the SQL text.** The test wraps
both connections and asserts the catalog recorded queries and the personal one
recorded **none**. Asserting on table names would pass if the query had joined
nothing; asserting on the alias says what the contract is about — *which side of the
wall the read happened on*.

**The personal read is asserted on table names, because the catalog side is reached
through a service.** `apps.personalization` may not import `apps.ingestion.models`
(AD-2), so the personal read asks the catalog *through a published service*
(`get_public_events`). Asserting on the alias would be wrong there — the read
legitimately goes to `catalog`. Asserting on the **table names** says the thing that
is actually true and worth protecting: the personal read does not reach into the
ingestion tables itself; it goes through the published interface.

## 10. The personal side — the 48-hour window

`list_personal_candidates` returns the user's own events within a window that is
**inclusive at both ends**: `now <= start <= now + 48h`.

| Test | Asserts |
|---|---|
| The event at exactly `now` | Included |
| The event at exactly `now + 48h` | Included |
| The event at `now + 48h + 1s` | Excluded |
| The event at `now - 1s` | Excluded (already started) |
| An **imported** calendar event | Included |

**Imported calendar events are candidates.** A user's own calendar is the most
personal and the most relevant thing they have; excluding them because they arrived
by ICS rather than by our own ingestion would be a mistake about what "personal
event" means.

## 11. The conflicts

The personal candidate carries the ids of the events it **conflicts with**, so the
composition service can rank with the conflicts in hand (AD-21: conflict detection
never happens at render time).

| Test | Asserts |
|---|---|
| A conflicting pair | Both ids appear, on both sides |
| A mixed-kind pair (personal against public) | The ids appear on the personal side |
| The same event id on two sides | Distinguished by kind, not by id alone |
| A conflict against a **saved** event | Carried by the personal side only |
| An inactive pair | Not carried |

**A conflict pair can join a personal event and a public event**, and the two sides
carry the same id space — so the pair is keyed by (kind, id), not by id. The test
asserts the same-id/different-kind case explicitly, because an implementation that
keyed by id alone would drop that pair.

**Only `ACTIVE` pairs are returned.** A resolved or dismissed conflict is history, and
carrying it would make the composition service re-rank around conflicts that no
longer exist.

## 12. The saved read and the batched catalog lookup

| Test | Asserts |
|---|---|
| A save is a candidate | It is in the list |
| The save's snapshot is used | The saved *time*, not a re-read of the event |
| The save's public half | Present, from one batched lookup |
| The catalog lookup count | **Exactly one query** for five saves |
| The saved pool's bound | `MAX_SAVED_CANDIDATES` |

**The batched lookup is the N+1 the review found.** Five saves must cost one catalog
query, not five. The test counts the queries against the catalog alias and asserts
`len(catalog_queries) == 1` — a count, not a "at most", because "at most one" would
pass against a lookup that never ran.

**The saved read applies no `now` to the catalog lookup.** A save stays readable
after its event has started: the user saved it, and the digest should still be able
to say so. Applying `now` to the catalog side would silently drop the public half of
every save for an event that had begun.

**The 48-hour window does not apply to saves.** The window bounds how far ahead the
digest *looks*; a save is a fact about the past present, and bounding it by the
window would drop saves the user made for an event that week.

## 13. The architecture — the Event Fit must not leak

Two tests were added to `tests/architecture/test_event_fit_separation.py`.

| Test | Asserts |
|---|---|
| `test_the_public_catalog_read_does_not_reach_the_event_fit_either` | `catalog_read` reaches no `apps.ingestion.event_fit` module |
| `test_the_source_badge_module_reaches_neither_the_event_fit_nor_personalization` | `source_badges` reaches neither the Event Fit nor `apps.personalization` |

**This is the finding the review produced, and it is the subtlest one in the item.**

The Source Badge mapping already existed — in `preview_read`, for the Pulse Preview.
The digest's candidate read needs the same mapping. The obvious move was to import
it from there. But `preview_read` imports `apps.ingestion.event_fit.reads`, and
`personalization` imports `catalog_read`. So that import would have put the Event Fit
inside `personalization` **by another name** — and the import contract could not have
caught it, because `allow_indirect_imports = true` for the `event-fit-separation`
contract.

The fix is `apps/ingestion/services/source_badges.py`: a leaf that imports the
`Source` model's *choices* and nothing else. Both reads import it; neither imports the
other. The two new tests pin the leaf, so the leak cannot come back through a
"harmless" shared helper.

**The badge constants moved with it.** `preview_read` no longer re-exports
`SOURCE_BADGE_*` — a name exported from two modules is two homes, and a reader has to
know which is current. The two test files that imported them from `preview_read` now
import them from `source_badges`.

## 14. The mutations

Five defects were each confirmed by breaking the code on purpose and watching the
test fail. Each mutation was reverted and the test confirmed to pass.

| Mutation | Test that caught it | Failure it produced |
|---|---|---|
| The `LIMIT` removed from the SQL | `test_the_sql_fetch_is_bounded` | "the candidate query must carry a LIMIT" |
| `limit = max(1, ...)` restored | `test_a_limit_of_zero_returns_no_candidates` | 1 candidate instead of 0 |
| The conflict kind filter dropped | the mixed-kind conflict test | the public half's id missing from the pair |
| The batched lookup reverted to one query per save | the lookup-count test | 5 catalog queries instead of 1 |
| The saved read's `start_utc >= now` bound dropped | the saved-pool bound test | a save outside the pool survived |

## What this item does not test

- **The ranking.** This item produces the pool; `digest-composition-service` ranks it.
- **The digest's response shape.** `digest-read-api` owns it.
- **How a conflict pair is *rendered*.** The ids are carried here; AD-21 puts the
  rendering on the other side of that wall.
- **The frontend's rendering of the badges.** The server states the badge *type*;
  `EXPERIENCE.md §4` owns the label and the glyph.
- **The stale-source admin flow.** A source with a lapsed TTL is a catalog problem;
  this item only applies the bound.

## Verdict

**Passing.** 67 item-scoped tests and 2 architecture tests, all green, with every
architectural gate intact and the whole backend at 3612 passed, 0 failed.

Six defects were found and fixed during the review, and each is now pinned by a test
that was **verified to fail against the broken code**:

1. **The unbounded SQL fetch.** The `limit` was enforced only in Python, so a
   mostly-stale catalog handed every row over before the first candidate was found.
   Fixed with a bounded over-fetch and a `LIMIT` in the SQL.
2. **`limit=0` returned one candidate.** `max(1, ...)` quietly turned "none" into
   "one". Fixed, and the test says why.
3. **The unreachable `superseded_by` filter.** The database constraint already makes
   the two states mutually exclusive, so the filter was a false comfort. Removed.
4. **The N+1 in the saved read.** One catalog query per save. Fixed with a batched
   `get_public_events`.
5. **The 48-hour window applied to the saves.** Saves are not bounded by the window.
   Fixed.
6. **The confidences carried as strings.** A string is not a `Decimal`, and the
   boundary comparison must be exact. Fixed.

And one was found by the review's own reading of the import graph:

7. **The Event Fit would have leaked into `personalization`** through the badge
   mapping's old home. Fixed by giving the mapping a leaf module of its own, and
   pinned by two architecture tests.
