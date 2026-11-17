---
run: run-eventpulse24-036
work_item: pulse-ping-control
intent: traceability-gap-closure
date: 2026-11-17
---

# Test Report: Let a user turn the daily Pulse Ping off — FR-10

## New tests

**`backend/tests/delivery/test_pulse_ping_control.py` — 14 tests.**

| Group | Holds |
|---|---|
| `TestTheCommandPair` | off sets the opt-out; on clears it; on-when-already-on is a no-op; **turning it back on does not resurrect cancelled sends** |
| `TestThePatch` | an omitted field leaves the ping alone; the patch turns it off and on |
| `TestTheScopesNeverTouch` | turning the daily digest off leaves a pending **event reminder** pending (FR-11's split) |
| `TestTheWire` | the read reports "on" by default and "off" once off; `GET` carries it; `PUT` round-trips both ways; a `PUT` that does not mention it leaves it alone |

**`frontend/components/settings/pulse-ping-switch.test.tsx` — 10 tests.**

Renders the server's state; **the body is exactly one key** (asserted on the exact key set,
not on the presence of the right one); the server's answer overrides the optimistic guess;
both failure paths put the switch back; the accessible name is stable across states; the
state is readable as words.

**Why the one-key assertion matters.** The endpoint is a patch: any extra key would
silently rewrite a setting the user never opened. Asserting "contains `pulse_ping`" would
pass while doing that.

## One existing test changed, deliberately

`app/settings/general/digest-section.test.tsx` — *"carries exactly one status region in the
digest section"*.

It asserted **two** status regions in the digest section. The rule the test states is *"a
region belongs to a control, and the route adds none of its own"* — and the Pulse Ping
switch is a third control, so it brings a third region. **The invariant is unchanged; the
count follows the controls.** The test now enumerates all three (`[data-pulse-ping]`,
`[data-digest-delivery-time]`, `[data-digest-personal-events]`) and expects 3. Its comment
is updated to say why the number moved, so the next reader does not have to reconstruct it.

## Suite results

| Suite | Result |
|---|---|
| Backend | **7301 passed**, 6 failed |
| Frontend | **2641 passed, 160 files, 0 failed** |

The backend count rose by exactly the 14 added. **The 6 failures are the same pre-existing
ones** as the previous run — verified there against a clean checkout, and unchanged in
identity here. Two of them live in `tests/delivery/test_preferences_api.py`, the file next
to this work; they fail with `ScheduledSend.DoesNotExist`, which is a real defect rather
than an environment problem, and they are **not** this work item.

## Gates

| Gate | Result |
|---|---|
| `pytest` (backend) | 7301 passed, 6 pre-existing failures |
| `pnpm test` | 2641 passed, 0 failed |
| `pnpm typecheck` | clean |
| `ruff check` | All checks passed |
| `ruff format` | 1 file reformatted (applied), 674 unchanged |
| `lint-imports` | **19 kept, 0 broken** |
| `eslint` / `prettier` (touched files) | clean |
| `make client` | regenerated `openapi.json` + `schema.ts` (AD-19) |

## Not covered

- **The page was not opened in a browser.** Docker and the API are down, so the row is
  proven by component tests and the route's own render test, not by looking at it.
- **No end-to-end proof** that turning the Ping off stops a real mail arriving. The unit
  level asserts the cancellation of pending digest sends; the sweep itself is covered by
  its own existing tests.
