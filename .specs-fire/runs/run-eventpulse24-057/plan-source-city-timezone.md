---
run: run-eventpulse24-057
work_item: source-city-timezone
intent: city-picker-and-auto-collection
mode: validate
checkpoint: plan-approval
status: approved
approved_at: 2026-11-20
---

# Implementation Plan: A source carries its city's timezone

## Approach

One new link in the FR-60 fallback chain: `venue_tz` → `source.city_tz`. Four small
changes, in dependency order — a constant, a `domain` function, a model field with its
cleaner, and one call site.

**Everything decisive stays in `domain`.** `resolve_tz` gains one keyword argument and one
new branch; the score and the row code are constants. `apps.ingestion` only passes the
value through, which is the division AD-2 already draws and the reason this can be tested
without a database.

**Strictly additive, and the test suite is the proof.** An existing source has no
`city_tz`, so `resolve_tz(..., city_tz=None)` takes exactly the branch it takes today. The
existing rejection test (`tests/domain/test_timezones.py`, the `C2` case) is not modified
— it keeps asserting that naive + nothing known still rejects, which is now also the
assertion that the new argument defaults to off.

## Decisions taken at the checkpoint

Both were put to the user before implementation and both were confirmed:

1. **`TZ_SCORE_CITY_ZONE = Decimal("0.90")`** — publishes clean, no `tz_review_pending`.
2. **`_content_hash` includes `city_tz`** — folded in, see "Re-resolution" below.

## The score, and why 0.90

**Where the new score sits decides whether every event in every new city is flagged, and
these are the same decision, not two.** `tz_gate` is `>= 0.90 publish`, `>= 0.70 publish
flagged`, below that in review; `_PUBLICATION[gate]` is what sets `tz_review_pending`. So
the score *is* the flag decision:

| Score | Gate | Result |
|---|---|---|
| `0.90` | `PUBLISH` | Publishes clean. No `tz_review_pending`. |
| `0.85` or any value in `[0.70, 0.90)` | `PUBLISH_FLAGGED` | Publishes, digest-eligible, **and sets `tz_review_pending` on every event in every newly provisioned city**. |

**Recommendation: `TZ_SCORE_CITY_ZONE = Decimal("0.90")`.** It satisfies the AC (strictly
below `TZ_SCORE_VENUE_REGISTRY` at 0.95), it publishes, and it does not flag. The work
item asks for the `tz_review_pending` question to be decided explicitly: this decides it
as **no**, on the work item's own argument — flagging every event in every new city
creates a review queue nobody can clear, which is not a safeguard, it is noise that buries
the real queue.

The honesty is not lost, it is just put where it belongs: the DST caps still apply, so a
city-zone reading of a time that occurs twice caps at `0.80` (flagged) and one that does
not exist at `0.65` (in review). Those are the readings that actually deserve a human.

**Confirmed at the checkpoint: 0.90.**

## Files to Modify

| File | Changes |
|------|---------|
| `backend/shared/constants.py` | `TZ_SCORE_CITY_ZONE = Decimal("0.90")`, placed between `TZ_SCORE_VENUE_REGISTRY` and `TZ_SCORE_FIXED_ZONE` with a comment saying why it sits where it does |
| `backend/domain/timezones.py` | `resolve_tz(..., city_tz: str | None = None)`; new `elif` branch after the `venue is not None` branch; docstring row table gains the row |
| `backend/apps/ingestion/models.py` | `Source.city_tz = models.CharField(max_length=64, blank=True)` beside `city` |
| `backend/apps/ingestion/services/source_registry.py` | `_CLEANERS["city_tz"]` validating through `canonical_zone`; `city_tz` added to `EDITABLE_SOURCE_FIELDS` and to `register_source`'s signature |
| `backend/apps/ingestion/services/ingest_item.py` | `city_tz=run.source.city_tz or None` passed to `resolve_tz`; `city_tz` added to `_content_hash`'s material |

## Files to Create

| File | Purpose |
|------|---------|
| `backend/apps/ingestion/migrations/00XX_source_city_tz.py` | Add the nullable/blank column. Additive, reversible, no data migration |
| (tests) `backend/tests/domain/test_timezones.py` additions | The new row, its precedence, its caps, and the unchanged-without-it assertion |
| (tests) `backend/tests/ingestion/` additions | The cleaner's validation, and the end-to-end date-only-with-no-venue case |

## Technical Details

### The new branch

```python
elif venue is not None:
    zone, tier, score, reason = venue, Tier.PARTIAL, TZ_SCORE_VENUE_REGISTRY, "C1"
    instant, cap = read_wall_clock(wall, venue)
    read_from_wall = True
elif city is not None:                      # NEW
    zone, tier, score, reason = city, Tier.PARTIAL, TZ_SCORE_CITY_ZONE, "C1b"
    instant, cap = read_wall_clock(wall, city)
    read_from_wall = True
else:
    return TzRejection(RejectReason.TZ_UNRESOLVABLE)
```

Placed **after** the `venue` branch and inside the same `elif` chain, which is what makes
the precedence an assertion of structure rather than of discipline: the branch is only
reachable when `source_zone` is absent (the chain's first test), the offset is absent (its
second) and `venue_tz` is absent (its third). The AC's "ignores `city_tz` entirely when an
explicit zone or instant exists" is then true by construction, and is still tested.

`read_from_wall = True` is what makes the DST caps and the `end` handling apply to a
city-zone reading exactly as they do to a venue-zone one — the AC asks for this, and it
comes from reusing `read_wall_clock` rather than writing a second path.

### Validation, and where it goes

`city_tz` is cleaned through `domain.timezones.canonical_zone`, the same function that
already validates `venue.tz` on write. Invalid input is refused at the registry boundary,
which is why `resolve_tz` can treat a present `city_tz` the way it treats `venue_tz` —
except that an invalid `city_tz` will be **ignored, not raised**.

**This differs from `venue_tz` deliberately.** An invalid `venue_tz` raises
`InvalidTimezoneError` because the venue registry guarantees its zones. A source's
`city_tz` is set by provisioning, and a bad one there should degrade a new city to
"no events yet" — the state the system already knows how to show honestly — rather than
raise inside the ingest loop and fail the whole run for every other candidate. Both
behaviours get a test.

### Row code: `C1b`, not `C2`

`C2` is already the label for "naive; nothing known → reject" in run-011's FR-60 table and
is used as a test id in `tests/domain/test_timezones.py`. The code is never persisted
(only `TzRejection.reason` is written to a record, and the rejection path does not emit a
row code), so renumbering would be *safe* — but it would make two documents disagree about
what `C2` means for no gain. `C1b` reads as what it is: the C1 family, weaker evidence.

### Re-resolution: `_content_hash` includes `city_tz` (confirmed at the checkpoint)

`_content_hash` already includes `venue_tz` precisely so that "a venue tz added later
re-resolves the item (D7)". `city_tz` now joins it on the same reasoning: without it,
setting `city_tz` on a source that already has rejected records would leave them rejected
forever, because the payload is unchanged and the item is skipped as unchanged.

This does not affect a newly provisioned city — a brand-new source has no stored records —
so it is insurance for the backfill path rather than the path this intent walks. It is two
lines in `_content_hash`'s `material` dict plus a test that a rejected record re-resolves
once its source gains a `city_tz`.

### One thing the ACs do not ask for, left out deliberately

**`tz_coverage` and `city_tz` are left unrelated.** `tz_coverage` describes whether the
   *feed* carries zones; `city_tz` is a fact about the *city*. A source can honestly be
   `tz_coverage="none"` and still carry a `city_tz` — that is exactly the Dhaka seed's
   shape. No coupling, no derived value, no validation between them.

### AD-13

Not engaged. A `Source`'s `city` is already written into `register_source`'s audit
`details={"fields": fields}` — it is editorial data about a public feed, not location data
about a person. `city_tz` goes in the same dict on the same reasoning. The AD-13 line in
the brief is about `DigestPreference.city`, which this item does not touch.

### D5

Untouched. No code path in this item constructs or saves a `Venue`; `_venue_for` is not
modified. The whole point of the item is to make the no-venue path resolvable instead of
making a venue.

## Tests

| Test File | Coverage |
|-----------|----------|
| `tests/domain/test_timezones.py` | The `C1b` row: naive + no source zone + no venue + `city_tz` → `PARTIAL`, zone, `0.90`, `Gate.PUBLISH`. Precedence: an explicit `source_zone`, a UTC instant, a fixed offset, and a `venue_tz` each ignore `city_tz` — one parametrized case per claim, each asserting the reason code is *not* `C1b`. DST fold caps to `0.80`, gap to `0.65`, both via `read_wall_clock`. `end` is read in the city zone. An invalid `city_tz` is ignored and the result is the unchanged rejection. `city_tz=None` is byte-for-byte today's behaviour. |
| `tests/ingestion/test_source_registry.py` | `register_source` / `update_source` accept a valid zone, normalize a legacy alias through `canonical_zone`, refuse `"Mars/Phobos"` and `"EST"` with a `city_tz`-named error, and accept `""` |
| `tests/ingestion/test_ingest_item.py` | A rejected record re-resolves once its source gains a `city_tz` (the `_content_hash` change; fails without it). **The AC's load-bearing test**: a date-only `startDate` candidate, no registered venue, source with `city_tz` → an Event is written with `publication_status` published and `tz_review_pending` False — and the same candidate with `city_tz=""` still rejects `tz_unresolvable`. Asserted on `publication_status` directly, as the work item requires, not inferred from the score |
| migration | `makemigrations --check` clean afterwards; `migrate` then `migrate` back one applies and reverses |

Coverage: `domain/` must stay at 100%, so the new branch and both cap paths need direct
tests — they are listed above.

## Risks

| Risk | Mitigation |
|---|---|
| A score change silently moves existing events between gates | The score is **new** and only reachable through a **new** branch that needs a **new** field that no existing row has. No existing resolution can reach it. The full suite re-run is the check |
| `resolve_tz`'s signature change breaks a caller | It is keyword-only with a `None` default; `ingest_item` is the only production caller (`grep` confirms) |
| The migration is not reversible | Single `AddField`, blank/default `""`. Reversibility is asserted by running it both ways |

---
*Plan approved at checkpoint 2 of 2 (validate mode). Execution follows.*
