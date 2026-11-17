---
run: run-eventpulse24-037
work_item: timeline-block-detail-contract
intent: traceability-gap-closure
date: 2026-11-17
---

# Test Report: Send the Timeline block its location — FR-32 (contract)

## New tests

`backend/tests/personalization/test_timeline_place.py` — **7 tests.**

| Group | Holds |
|---|---|
| `TestAPublicBlock` | carries the venue's name; falls back to the city when the venue has none; **null when the catalog no longer holds the event** — an unknown place, not an absent one, asserted alongside `name` degrading the same way |
| `TestAPersonalBlock` | carries the user's own location; null when they gave none |
| `TestTheRebuild` | a cross-midnight event keeps its place on **both** days it covers |
| `TestTheCost` | four saves still cost one catalog read — the place adds no query per block |

**Two of these are defect-catchers rather than feature tests.**

`TestTheRebuild` exists because the per-day loop **rebuilds** `TimelineBlock` field by
field. I added `place` to the dataclass and to both construction sites, and the rebuild
silently dropped it on every block — the field was set, then thrown away before it reached
a day. Found by reading the loop, not by a failing test, so the test now stands where the
hole was.

`TestTheCost` exists because the place is only free while `get_public_events` keeps its
`select_related("venue", "source")`. A refactor dropping that would add one query per saved
event per week-read and nothing else would notice.

## Suite results

| Suite | Result |
|---|---|
| Backend | **7308 passed** (7301 + the 7 added), 6 failed |
| Frontend | **2641 passed, 0 failed** |

The 6 failures are the same pre-existing time bombs, now written up as the
`time-bomb-tests` work item with their root cause.

## Gates

| Gate | Result |
|---|---|
| `pytest` | 7308 passed, 6 pre-existing |
| `ruff check` / `format` | clean (1 file reformatted, applied) |
| `lint-imports` | **19 kept, 0 broken** |
| `pnpm typecheck` / `pnpm test` | clean / 2641 passed |
| `make client` | `place?: string \| null` now in `schema.ts` (AD-19) |

## Not covered

- **No frontend behaviour yet.** This item is the contract; `timeline-hover-detail`
  consumes it. The regenerated type is proven only by the typecheck.
- **The Why-this tag §13 also names is not here**, by decision — see
  `timeline-why-this-tag` for the finding and the deferral.
