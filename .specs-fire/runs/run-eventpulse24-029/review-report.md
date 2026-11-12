---
run: run-eventpulse24-029
work_item: test-clock-seam
intent: browse-surface
generated: 2026-11-12
status: passed
---

# Code Review: A Clock Seam for the Tests

## Scope

```
backend/domain/quiet_hours.py                          |  8 +-   (1 pragma comment)
backend/pyproject.toml                                 |  1 +
backend/uv.lock                                        | 14 +
backend/tests/delivery/test_reminder_plan_api.py       | 33 +-
backend/tests/domain/test_quiet_hours.py               | 14 +
backend/tests/domain/test_weekly_quiet_hours.py        | 28 +-
backend/tests/e2e/test_personal_events_and_saved_catalog.py | 20 +
backend/tests/e2e/test_save_race.py                    | 22 +
backend/tests/e2e/test_timeline_and_conflict_proof.py  | 19 +
backend/tests/ingestion/test_url_feed_read.py          | 27 +-
```

283 insertions, 7 deletions. Nine of the ten files are tests or packaging. The tenth is a
comment.

## Standards compliance

`.specs-fire/standards/testing-standards.md`, "Mock Strategy", line 97:

> **"Freeze time explicitly. Never depend on wall-clock or local timezone."**

**The 17 failures were a standing violation of a rule this project had already written down.**
This item did not invent a convention; it enforced one that existed and was unenforced. That
is the strongest argument that the approach is right, and it is worth recording because it
reframes the work: not "a clever fix for flaky dates" but "the standard, finally applied".

The same section's neighbouring rules are also satisfied:

| Rule | Status |
|---|---|
| Fake at the **port** boundary; never mock the ORM or the database | **kept** — no ORM or DB mocking was added; `freeze_time` patches the clock, not persistence |
| Use a real Postgres for app and worker tests | **kept** — unchanged |
| No `time.sleep` in tests | **kept** — none added |
| Explicit UTC + IANA tz on every temporal fixture | **kept** — every frozen instant is tz-aware; the two deliberate naive values are wall clocks passed to a function documented to take them, each carrying a `noqa` and a reason |
| Include DST-boundary cases for any time logic | **kept** — `FAR_AFTERNOON_START` was chosen specifically so both it and `AFTERNOON_START` sit in PST (US DST ended 2026-11-01), preserving the quiet-hours property under test |

Architecture contracts: **19 kept, 0 broken** (`make lint-imports`). `domain/` gained no import
— it is still pure stdlib and importable with Django absent, which its own module docstring
requires.

## Findings

### Auto-fixed (mechanical, non-semantic)

| # | Finding | Fix |
|---|---|---|
| 1 | `I001` import block unsorted in `test_reminder_plan_api.py` after adding `freezegun` | `ruff check --select I --fix` |
| 2 | Blank-line formatting in `test_timeline_and_conflict_proof.py` after inserting the fixture | `ruff format` |

Both re-verified: `make lint-backend` → "All checks passed!".

### Confirmed with the user before acting

| # | Finding | Why it needed confirmation | Outcome |
|---|---|---|---|
| 3 | `domain/` coverage gate at 99%, needing a production-file edit to close | The work item explicitly promised no production code changes; a `pragma` is still an edit to a production file | Approved; closed with 2 tests + 1 pragma |

### Reviewed and accepted

| # | Observation | Judgement |
|---|---|---|
| 4 | `tick=True` on all five freezes | **Correct and necessary.** UUIDv7 keys order by timestamp prefix and four of these modules assert on identity or ordering. A hard freeze would have traded a dated bug for a flaky one. |
| 5 | Two tests changed their *fixtures*, not just their clock (`FAR_AFTERNOON_START`, events created a day back) | **Justified, and the production code was right in both cases.** Each is documented in `test-report.md` Issue 1 with the reasoning inline in the test. Both were mutation-checked afterwards. |
| 6 | `# noqa: DTZ001` used twice rather than adding `tzinfo` | **Correct.** `_ends_covering` takes a wall clock and its docstring calls the values naive. A `tzinfo` would assert an instant the value does not mean — the lint rule would be satisfied and the code would be less true. |
| 7 | `pragma: no cover` carries 6 lines of justification | **Deliberate.** The risk with an unreachable line under a hard 100% gate is that someone eventually lowers the gate. The comment names the test that pins the unreachability. |
| 8 | `freezegun==1.5.5` exact-pinned | **Matches house convention** — every other dev dep is exact-pinned. `uv.lock` diff shows freezegun only; no other version moved, ruff included (verified 0.17.3 before and after). |

### Open — recorded, not fixed

| # | Finding | Severity | Why not fixed here |
|---|---|---|---|
| 9 | `test_a_custom_slot_is_minted` asserts the send exists but never its **due time** — the "90 minutes" in `custom:90` is unverified | low | Outside this item's acceptance criteria. Found by accident when a mutation to `slot_offsets` left the test passing. Silently widening scope is the habit this run is meant to break. |
| 10 | Backend suite takes **12m14s**; `pytest-xdist` not installed | low | Raised at checkpoint 1 and explicitly declined for this item. |

## The thing worth saying plainly

This item was scoped as "fix 17 failing tests". It found **three** red gates, all pre-existing,
all masked by the first:

1. `make test-backend` — 17 failures
2. `make lint-backend` — 2 `DTZ001` errors, red since run 027 (`54ecf50`)
3. `make coverage-backend` — `domain/` at 99%, and **never evaluated**, because `make` aborts
   at the failing pytest step before reaching the gate

Runs 027 and 028 both closed while 2 and 3 were red. That is not a criticism of those runs so
much as a property of the setup: **a gate behind a failing gate is not a gate.** If one thing
survives this item beyond the fix itself, it should be that `coverage-backend` runs its second
command even when the first fails, or that CI reports each gate independently.

All three are green as of this review.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-029*
