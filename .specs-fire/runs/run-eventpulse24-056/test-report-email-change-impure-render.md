# Test Report: email-change-impure-render

**Run:** run-eventpulse24-056 · **Date:** 2026-11-20 · **Result:** PASS

## The headline

**`pnpm lint` exits 0.** It has exited non-zero since `run-eventpulse24-043`, through
every commit of run-055.

| Check | Before | After |
|---|---|---|
| `pnpm lint` | 3 errors, 2 warnings — **exit 1** | 0 errors, 2 warnings — **exit 0** |
| `tsc --noEmit` | clean | clean |
| Frontend suite | 2847 | **2849** pass (177 files) |

The two surviving warnings are out of scope by plan: `source-mute-control.tsx`'s
`useCallback` dependency and `avatar-disc.tsx`'s documented `<img>`.

## Tests added, and their failure first

Both were written against the unfixed component and run before the fix.

### "reads the clock once per render"

```
AssertionError: expected 2 to be less than or equal to 1
```

**The defect, named directly.** It spies on `Date.now` and asserts one call per render.
This survives any refactor of the call site, because it describes the property rather than
the shape of the code.

### "does not let the guard and the sentence disagree"

`Date.now` stubbed to return `base`, then `base + 120_000`; `expiresAt` set 60 s after
`base`.

- **Before:** the guard read `base`, saw a live link and rendered the paragraph; the
  paragraph read `base + 120_000` and printed *"That link has expired — send a new one."*
  A guard and a body on opposite sides of one decision.
- **After:** one read at `base`, so the paragraph reads *"The link works for about 1 more
  minute."*

The test asserts both halves: the live sentence is present **and** the expired sentence is
absent.

## Existing tests: unchanged and passing

The three original expiry tests — *"says roughly how long the link still works"*, *"says a
dead link is dead"*, *"says nothing when the server sent no expiry"* — pass **without
modification**. That is the evidence this was a fix and not a redesign: the described
behaviour was already correct, and only the call site was wrong.

## The fix

```ts
const [now] = useState(() => Date.now());
const expiry = expiryLine(expiresAt, now);
```

One read on mount via a lazy initializer; pure at render; stable across re-renders.

**No `eslint-disable` anywhere.** The compiler rule was correct.

**No ticking countdown.** Deliberate, and recorded in the component: a sentence true at
page load is what `expiryLine` was written for, and an interval re-rendering a settings
screen every minute is a different product decision belonging to its own work item.

## Dead code removed

`e2e/digest-opt-out.spec.ts` — the `digest()` helper and its docstring, 30 lines.
Verified unreferenced before deletion (two occurrences in the file, both the definition).

## Acceptance criteria

| Criterion | Status |
|---|---|
| `expiryLine` called once per render, one `now` | ✔ |
| Not read from `Date.now()` during render | ✔ `useState` lazy initializer |
| No `eslint-disable` | ✔ |
| Boundary test covering the disagreement | ✔ |
| Already-expired case renders the dead-link sentence | ✔ existing test, still passing |
| Both new tests proved to fail first | ✔ |
| Unused `digest()` helper removed | ✔ |
| `pnpm lint` exits zero | ✔ |
| Existing `email-change` tests pass unchanged | ✔ 18/18 |
