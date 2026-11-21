---
run: run-eventpulse24-057
work_item: source-city-timezone
intent: city-picker-and-auto-collection
generated: 2026-11-20
status: passed
---

# Test Report: A source carries its city's timezone

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|----------|--------|--------|---------|----------|
| Domain unit (new) | 13 | 0 | 0 | 100% |
| Constants / app / pipeline / admin (new) | 22 | 0 | 0 | — |
| Backend suite (full) | 7755 | 0 | 0 | 97.42% |
| **Total** | **7755** | **0** | **0** | **97.42%** |

35 tests added (7720 → 7755), 3 of them from a code-review finding (see `review-report-source-city-timezone.md`). `domain/` remains at **100%**, which the second CI gate
requires; `lint-imports` reports 21 contracts kept, 0 broken.

## Acceptance Criteria Validation

- ✅ **`Source.city_tz` added — nullable/blank IANA zone, validated through `canonical_zone` on write** — `CharField(max_length=64, blank=True)`. Cleaned by `_city_tz` in `source_registry._CLEANERS`, which refuses a non-zone and **canonicalizes** what it accepts, so `"US/Pacific"` is stored as `"America/Los_Angeles"` and the column holds one spelling per zone. `"EST"` is refused — it loads in `zoneinfo` but is not a zone an event can happen in.
- ✅ **`resolve_tz` accepts `city_tz` and uses it only when `source_zone` and `venue_tz` are absent** — the branch is the fourth arm of the existing `if/elif` chain, so it is unreachable while a source zone, an offset or a venue is present. Precedence is asserted, not assumed: `test_resolve_tz_city_zone_yields_to_more_specific_evidence` and `test_resolve_tz_an_instant_or_an_offset_ignores_the_city_zone` each check the resulting row code is *not* `C1b` **and** that the zone the city carried did not decide the answer.
- ✅ **A new confidence constant scores strictly below `TZ_SCORE_VENUE_REGISTRY`** — `TZ_SCORE_CITY_ZONE = Decimal("0.90")` vs `0.95`. Asserted twice and two different ways: by comparison in `tests/shared/test_constants.py`, and behaviourally in `test_resolve_tz_city_zone_scores_below_the_venue_registry`, which resolves the same wall-clock time both ways and compares the two confidences.
- ✅ **The resolution reports a distinct `reason`** — `"C1b"`. Distinct from `C1` (venue) and from the `C2` the FR-60 table already uses for the "nothing known → reject" row.
- ✅ **DST fold/gap caps apply exactly as they do to a venue-zone reading** — because the branch goes through the same `read_wall_clock` and sets `read_from_wall = True`. `test_resolve_tz_city_zone_carries_the_dst_caps` pins fold → `0.80` / `PUBLISH_FLAGGED` and gap → `0.65` / `IN_REVIEW`, the same numbers the venue row produces.
- ✅ **A date-only `startDate` with no venue and a `city_tz` resolves at PARTIAL instead of rejecting — asserted by a test that fails without the change** — `test_date_only_time_in_a_city_with_no_venue_publishes_on_the_city_zone`, through the real pipeline. Verified to fail when the branch is removed (see Mutation Check). Its control, `test_the_same_feed_without_a_city_zone_still_rejects`, runs identical bytes through a source differing in that one field and asserts `rejected:tz_unresolvable`.
- ✅ **A candidate with an explicit zone or instant ignores `city_tz` entirely** — four parametrized cases: explicit source zone, registered venue, UTC instant, fixed offset. Also asserted end-to-end in `test_a_registered_venue_still_outranks_the_city_zone`, where a source deliberately carries a *wrong* city zone (`Asia/Dhaka` for a San Francisco venue) and the venue's zone wins.
- ✅ **A source with `city_tz` unset behaves identically to today** — `test_resolve_tz_without_a_city_zone_is_exactly_todays_behaviour`, parametrized over `None` and `""`, asserts equality against the *same call without the argument* for three different resolution paths, rather than restating expected values. The pre-existing `test_none_tier_never_becomes_an_event` is unmodified and still passes.
- ✅ **`ingest_item` passes `run.source.city_tz` through** — one line, `city_tz=run.source.city_tz or None`. The `or None` keeps the blank-column case on the existing path rather than handing `resolve_tz` an empty string to canonicalize.
- ✅ **D5 untouched: no code path here creates a `Venue`** — `_venue_for` is not modified. `test_no_venue_is_ever_created_for_a_provisioned_city` asserts `Venue` table empty and `event.venue_id is None` after a successful city-zone publish.
- ✅ **Migration applies cleanly and is reversible** — `0014_source_city_tz`, a single `AddField`. Applied, reversed to `0013`, re-applied. `makemigrations --check --dry-run` reports no changes.

## Tests Written

### Domain unit — `tests/domain/test_timezones.py` (13)

The `C1b` row (zone, instant, tier, confidence, gate); scores below the venue row; yields
to a source zone and to a venue; is ignored by a UTC instant and by a fixed offset; carries
both DST caps; reads `end` in the same zone; an invalid `city_tz` is ignored rather than
raised (two cases); canonicalizes a legacy alias; and is byte-for-byte today's behaviour
when unset (two cases).

### Constants — `tests/shared/test_constants.py` (2)

`TZ_SCORE_CITY_ZONE` added to the gate-band parametrize (expects `Gate.PUBLISH`), plus
`test_the_city_zone_scores_below_the_venue_registry_and_still_publishes`, which pins both
halves of the decision as one assertion pair.

### App / registry — `tests/ingestion/test_source_registry.py` (11)

Stores and canonicalizes a zone; blank when unset; `tz_coverage` and `city_tz` are
unrelated (the Dhaka seed's shape: `tz_coverage="none"` with a real city zone); `update_source`
can set and clear it; an invalid value is refused and leaves the row unchanged; four new
rows in the existing invalid-field parametrize (`"Mars/Olympus_Mons"`, `"EST"`, over-length,
`None`).

### Admin — `tests/ingestion/test_admin.py` (3, added at code review)

The add form accepts and canonicalizes a city zone; a bad zone lands as a field error on
the form rather than a 500; and `test_every_editable_source_field_is_reachable_in_the_admin`
asserts `EDITABLE_SOURCE_FIELDS ⊆ flatten_fieldsets(SourceAdmin.fieldsets)` — the invariant
whose absence let the field slip out of the form in the first place.

### Pipeline — `tests/ingestion/test_ingest_tz.py` (6)

The cold-start case end to end and its control; a naive time read in the city zone; a
registered venue outranking a deliberately wrong city zone; `city_tz` added later
re-resolving an already-rejected item; and D5 (no venue created).

## Test Commands

```bash
uv run --directory backend pytest tests/domain/test_timezones.py tests/ingestion/test_ingest_tz.py -q
make test-backend
make coverage-backend
uv run --directory backend coverage report --include='domain/*' --fail-under=100
uv run --directory backend python manage.py makemigrations --check --dry-run
```

## Mutation Check

Per the standing rule that a test must be able to fail, both halves of the change were
removed in turn and the suite re-run.

**Removing the `elif city is not None:` branch from `resolve_tz`** — 10 tests fail:

```
tests/domain/test_timezones.py::test_resolve_tz_city_zone_reads_a_naive_time_and_publishes
tests/domain/test_timezones.py::test_resolve_tz_city_zone_scores_below_the_venue_registry
tests/domain/test_timezones.py::test_resolve_tz_city_zone_carries_the_dst_caps[gap]
tests/domain/test_timezones.py::test_resolve_tz_city_zone_carries_the_dst_caps[fold]
tests/domain/test_timezones.py::test_resolve_tz_city_zone_reads_the_end_in_the_same_zone
tests/domain/test_timezones.py::test_resolve_tz_city_tz_is_canonicalized_like_every_other_zone
tests/ingestion/test_ingest_tz.py::test_date_only_time_in_a_city_with_no_venue_publishes_on_the_city_zone
tests/ingestion/test_ingest_tz.py::test_a_naive_time_in_a_city_with_no_venue_reads_in_the_city_zone
tests/ingestion/test_ingest_tz.py::test_city_zone_added_later_resolves_the_rejected_item
tests/ingestion/test_ingest_tz.py::test_no_venue_is_ever_created_for_a_provisioned_city
```

The controls stayed green, which is the other half of the check: the precedence tests, the
"unset behaves as today" tests and the existing rejection test all still passed, confirming
they assert the absence of the feature rather than its presence.

**Removing `"city_tz"` from `_content_hash`'s material** — exactly one test fails,
`test_city_zone_added_later_resolves_the_rejected_item`, and nothing else. That is the
precise blast radius claimed for that change.

## Issues Found

One found by code review and fixed: `city_tz` was accepted by `update_source` but silently
dropped from the admin form, because `SourceForm` takes its fields from
`EDITABLE_SOURCE_FIELDS` while `SourceAdmin.fieldsets` lists them by hand. Put to the user,
who chose to expose it. Fixed, with a test that pins the two lists together so the next
field cannot slip the same way. Verified to fail without the fix (3 tests).

One self-inflicted and fixed: a repo-wide `ruff format .` reformatted
`backend/tests/shared/test_retention_published.py`, a file unrelated to this work that had
pre-existing formatting drift. Reverted with `git checkout` so the diff stays scoped to
this item. Worth knowing: that file is **not** `ruff format` clean on this branch, which is
why `ruff format --check .` reports one file. Every file this run touched is clean.

One stale comment corrected rather than left: `test_confidence_of_exactly_0_90_publishes_unflagged`
began "No resolve_tz row scores 0.90 (plan P2)". The `C1b` row now does. The test is
unchanged — it still pins the gate boundary independently of which row sits on it — but the
comment now says so instead of asserting something false.

## Ready for Completion

- [x] All tests passing (7755, zero failures)
- [x] Coverage target met (100% for `domain/`, 97.42% overall against an 80% floor)
- [x] All 11 acceptance criteria validated
- [x] No critical issues open

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-057*
