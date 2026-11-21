---
run: run-eventpulse24-057
work_item: source-city-timezone
intent: city-picker-and-auto-collection
generated: 2026-11-20
mode: validate
---

# Implementation Walkthrough: A source carries its city's timezone

## Summary

A freshly provisioned city used to fetch cleanly, parse cleanly, and publish nothing —
forever. This item fixes that with one new link in FR-60's fallback chain:
`venue_tz` → `source.city_tz`.

The reason it was broken is structural, not accidental. `ingest_item._venue_for` never
creates a venue (D5), so a city with no registered venues resolves `venue=None` for every
candidate. `resolve_tz` then has nothing to read a naive or date-only wall-clock time in
and returns `TZ_UNRESOLVABLE`. And this is not hypothetical: `seed_dhaka_live.py` already
documents that the Eventbrite `/d/` directory — the most city-parameterizable feed shape
available — emits **date-only** `startDate`. Provisioning Chittagong would have fetched,
parsed, and rejected every candidate while the page said "collecting".

Now the source carries its city's zone, populated at provisioning time from the catalog
item 1 built, and that zone is read as the weakest tier of evidence in the chain.

## Structure Overview

```text
backend/
├── shared/constants.py          TZ_SCORE_CITY_ZONE = 0.90
├── domain/timezones.py          resolve_tz(..., city_tz=None) + the C1b branch
├── apps/ingestion/
│   ├── models.py                Source.city_tz
│   ├── admin.py                 the field, reachable by an editor
│   ├── migrations/0014_source_city_tz.py
│   └── services/
│       ├── source_registry.py   _city_tz cleaner, EDITABLE_SOURCE_FIELDS
│       └── ingest_item.py       passes it through; hashes it
```

## Architecture

### Pattern Used

Every decision stays in `domain`; `apps.ingestion` passes a value. That is AD-2's line, and
it is why the whole FR-60 behaviour below is tested with no database at all.

The new branch is the fourth arm of the `if/elif` chain `resolve_tz` already had:

```text
source_zone?  ──yes──▶  A1 / A2 / A3     explicit zone, 1.00 (0.60 on conflict)
     │ no
offset?       ──yes──▶  U1 / U2 / B1-B3  the time carries its own claim
     │ no
venue_tz?     ──yes──▶  C1               registered address,  0.95
     │ no
city_tz?      ──yes──▶  C1b   ◀── NEW    the source's city,   0.90
     │ no
             reject tz_unresolvable
```

**The precedence is the shape of the chain, not a rule to remember.** The branch is
unreachable while a source zone, an offset or a venue exists, so "ignores `city_tz`
entirely when something more specific is known" is true by construction. It is still
asserted — four cases in `domain`, one more through the real pipeline — because a
construction can be refactored away.

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `backend/apps/ingestion/migrations/0014_source_city_tz.py` | One `AddField`. Applied, reversed, re-applied |

### Modified

| File | Changes |
|------|---------|
| `backend/shared/constants.py` | `TZ_SCORE_CITY_ZONE = Decimal("0.90")`, with the reason it sits where it does |
| `backend/domain/timezones.py` | `city_tz` keyword arg; the `C1b` branch; docstrings for the chain and for the ignore-don't-raise asymmetry |
| `backend/apps/ingestion/models.py` | `Source.city_tz = CharField(max_length=64, blank=True)` |
| `backend/apps/ingestion/services/source_registry.py` | `_city_tz` cleaner; `city_tz` in `EDITABLE_SOURCE_FIELDS`, `_CLEANERS` and `register_source` |
| `backend/apps/ingestion/services/ingest_item.py` | `city_tz=run.source.city_tz or None` into `resolve_tz`; `city_tz` into `_content_hash` |
| `backend/apps/ingestion/admin.py` | The field in the first fieldset, with a help text (code-review finding) |
| 5 test files | +35 tests |

## Key Decisions

| Decision | Choice | Rationale |
|---|---|---|
| **The score, and `tz_review_pending`** | `0.90` — publishes clean, no flag | **Put to you at the checkpoint; you took 0.90.** The work item asked these as two questions. They are one: `tz_gate` is `>= 0.90 publish`, and `_PUBLICATION[gate]` is what sets `tz_review_pending`. Any value below 0.90 flags **every event in every newly provisioned city** — a review queue nobody can clear, which is noise that buries the real queue rather than a safeguard. 0.90 is still strictly below the venue row's 0.95, as the AC requires |
| **Honesty, kept where it belongs** | The DST caps | 0.90 is not a claim that a city zone is almost as good as an address — it is a claim that *this reading* is sound. A city-zone reading of a time that occurs twice still caps to 0.80 (flagged) and one that does not exist to 0.65 (in review). Those are the readings that actually deserve a human, and they get one |
| **`_content_hash` includes `city_tz`** | Folded in | **Put to you at the checkpoint; you said fold it in.** D7's existing rule — "a venue tz added later re-resolves the item" — applied to the new field. Without it, a source that gains a zone has unchanged payloads, so every item it already rejected is skipped as unchanged and stays rejected forever: exactly the case the zone was added for |
| **An invalid `city_tz` is ignored, not raised** | Asymmetric with `venue_tz`, on purpose | The registry guarantees a venue's zone, so a bad one is a broken invariant worth stopping for. A `city_tz` is set by provisioning, and a bad one should cost that one city its date-only events — a state the product already shows honestly — not raise inside the ingest loop and take every other candidate in the run with it |
| **Row code `C1b`, not `C2`** | New code | `C2` already labels the "nothing known → reject" row in run-011's FR-60 table and is a pytest id. The codes are never persisted, so renumbering would have been *safe* — it would just have made two documents disagree for nothing |
| **Admin exposure** | Added at code review | **Put to you; you said add it.** `SourceForm` takes its fields from `EDITABLE_SOURCE_FIELDS`, but `SourceAdmin.fieldsets` lists them by hand and Django silently drops anything missing. `city_tz` would have been the only editable field an editor could not reach — and the admin is the only human path to `update_source` |
| **`tz_coverage` left alone** | No coupling | `tz_coverage` describes whether the *feed* carries zones; `city_tz` is a fact about the *city*. The Dhaka seed is honestly both at once, and a test says so |

## What Changes for an Existing Source

Nothing, and that is asserted rather than claimed. Every source that predates this carries
`city_tz = ""`, `ingest_item` passes `None`, and `resolve_tz` takes exactly the branch it
takes today. `test_resolve_tz_without_a_city_zone_is_exactly_todays_behaviour` checks this
by comparing against *the same call without the argument* across three resolution paths,
rather than restating expected values — so it keeps holding if those values are ever
retuned. The pre-existing rejection test is unmodified and still passes.

## Verification

The mutation check, since a test that cannot fail proves nothing:

| Removed | Tests that failed |
|---|---|
| The `elif city is not None:` branch | 10 — and every control (precedence, unset-behaves-as-today, the existing rejection test) stayed green |
| `"city_tz"` from `_content_hash` | exactly 1, the re-resolution test, and nothing else |
| The admin fieldset entry | 3 |

```bash
make test-backend                                          # 7755 passed
make coverage-backend                                      # 97.42% overall
uv run --directory backend coverage report --include='domain/*' --fail-under=100   # 100%
uv run --directory backend lint-imports                    # 21 kept, 0 broken
uv run --directory backend python manage.py check          # no issues
uv run --directory backend python manage.py makemigrations --check --dry-run       # no changes
```

## What This Unblocks

`city-provisioning-service` (item 7) can now register a source for a brand-new city and
expect it to publish: it reads `tz` from the catalog item 1 built and writes it to
`Source.city_tz` at registration. `browse-collecting-states` (item 9) can tell the
difference between "still collecting" and "this city has no machine-readable feed", because
a city with a feed now actually yields events instead of silently rejecting all of them.

The honest caveat from the brief still stands and is unchanged by this item: most of the
world has no machine-readable feed, and Chittagong itself will very likely still reach
`yielded_nothing`. What changed is that it will do so for the real reason, not because the
pipeline threw its events away.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-057*
