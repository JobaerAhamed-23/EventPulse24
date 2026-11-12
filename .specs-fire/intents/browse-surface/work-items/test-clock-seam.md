---
id: test-clock-seam
title: A Clock Seam for the Tests — Fix the 17 Date-Expiry Failures
intent: browse-surface
complexity: medium
mode: confirm
status: completed
depends_on: []
created: 2026-11-12
run_id: run-eventpulse24-029
completed_at: 2026-11-12T08:56:00.929Z
---

# Work Item: A Clock Seam for the Tests — Fix the 17 Date-Expiry Failures

## Description

17 backend tests fail on `main`. Every one of them fails for the same reason: a hardcoded
absolute datetime that was in the future when it was written and is now in the past.

This is a defect class, not 17 defects. The fix is structural — a seam that lets a test
state *when* it is — not 17 edits that push the years out and reset the timer on the same
failure. Run 027 recommended exactly this and it was deferred twice; the count has since
grown from 16 to 17, because `test_reminder_plan_api.py`'s `AFTERNOON_START` (2026-11-12
02:00 UTC) expired *during* run 028.

It goes first in this intent because every later item is verified against the suite, and a
suite with 17 unrelated failures cannot tell anyone whether Browse works.

## Acceptance Criteria

- [ ] `make test-backend` exits 0 with no failures and no new skips or `xfail`s
- [ ] The exact count of previously failing tests is recorded in the run log, named
      individually, so the fix can be audited against the starting state
- [ ] The fix is a seam — `freezegun`, or an injected clock following the existing port
      pattern in `adapters/` — and not a bulk rewrite of literals to later dates
- [ ] A test asserting behaviour at a fixed instant states that instant explicitly; no test
      depends on the real wall clock to pass
- [ ] Each repaired test can still fail: for at least three of them, demonstrate in the run
      log that breaking the production code breaks the test
- [ ] `make lint-backend` and `make lint-imports` stay green — a clock seam must not violate
      the AD-1/AD-2 import contracts
- [ ] `coverage-backend` still meets its gates: ≥80% overall, 100% for `domain/`

## Technical Notes

The 17 failures were last counted during run 028 and are documented in `TRACEABILITY.md`
§"Open items carried out of this regeneration", item 3. **Re-count them at the start of this
item** rather than trusting that number — more may have expired since 2026-11-12, and the
delta is itself evidence for how badly the seam is needed.

`domain/` is pure stdlib with no Django and no I/O, and it must stay that way. Functions
there already take `now: datetime` as a parameter (see `ranking.recency_band`,
`ranking.why_this_tags`) — that is the existing seam and it works. The problem is in the
test and app layers, where `timezone.now()` is called directly and compared against
literals.

If `freezegun` is chosen, it is a new dev dependency and needs to go through `uv` into the
dev group, not the runtime one.

## Dependencies

(none)
