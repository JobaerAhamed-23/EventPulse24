# Review Report: email-change-impure-render

**Run:** run-eventpulse24-056 · **Verdict:** PASS

## Scope

| File | Change |
|---|---|
| `components/settings/email-change.tsx` | one clock read on mount; `expiry` derived once; the two in-render `Date.now()` calls gone |
| `components/settings/email-change.test.tsx` | +2 tests |
| `e2e/digest-opt-out.spec.ts` | dead `digest()` helper removed |

## Checks

| Check | Result |
|---|---|
| Frontend suite | 2849 pass (177 files) |
| `tsc --noEmit` | exit 0 |
| `pnpm lint` | **exit 0** — first time since run-043 |

## Auto-fixes applied

**None.** One self-inflicted error was caught and corrected mid-implementation: the markup
was switched to a derived `expiry` before the derivation existed. `tsc` would have caught
it; it was fixed before the typecheck ran.

## Findings

### F-4 — closed

The three lint errors are gone. **Two were a genuine correctness bug**, not formatting:
a guard and its body computed from two clocks, with a visible wrong render at the expiry
boundary. The React compiler rule that flagged it was right, and the fix satisfies it
rather than suppressing it.

### F-8 (open, for a human) — CI lint was red for weeks and nothing stopped

`pnpm lint` exited 1 from `run-eventpulse24-043` until now. Runs 044–055 shipped **twelve
commits** over that window, including three in run-055 whose own review reports recorded
the failure as pre-existing and moved on.

**That is a process finding, not a code one**, and it is the reason the bug survived: the
signal existed and was not gating. Either the CI lint job is failing and being ignored, or
it does not run. Worth settling now that the baseline is green, because a green baseline is
the only state in which a lint gate is cheap to enforce.

## Observations, no action

- **The component is now provably pure at render**, which is what makes the compiler
  happy; the `useState` lazy initializer is the idiomatic shape and needs no comment to
  defend it, though one is there explaining what it replaced.
- **The "no ticking countdown" decision is recorded in the source**, not just the plan. A
  future reader seeing a frozen sentence should find the reasoning next to the code rather
  than conclude it is an oversight and add an interval.
- **The removed e2e helper was dead, not disabled.** No skipped test referenced it.

## Conclusion

Complete and green, and the repository's lint baseline is clean for the first time in a
month of runs.
