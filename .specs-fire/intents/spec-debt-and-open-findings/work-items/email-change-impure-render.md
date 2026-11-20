---
id: email-change-impure-render
title: The expiry line is computed from two clocks, and lint has been red since
  run-043
intent: spec-debt-and-open-findings
complexity: low
mode: confirm
status: completed
depends_on: []
created: 2026-11-20
run_id: run-eventpulse24-056
completed_at: 2026-11-20T12:14:45.640Z
---

# Work Item: Two clocks, one sentence

## Description

`components/settings/email-change.tsx` calls `Date.now()` twice during render:

```tsx
{expiryLine(expiresAt, Date.now()) !== null ? (
  <p … data-pending-expiry>{expiryLine(expiresAt, Date.now())}</p>
) : null}
```

**The guard and the value do not share a clock.** `expiryLine` returns `null` only when
`iso` is empty or unparseable — but it returns a *different sentence* once `at <= now`
("That link has expired"), and the two calls can land on either side of any boundary. The
`null` case is reachable at render time only through a prop change, but the **minute
boundary is reachable constantly**: the guard can compute "2 minutes" while the paragraph
computes "1 minute", and at the expiry instant the guard can pass while the body renders
the expired sentence.

**It is also why the React compiler rejects it.** `Date.now()` in render is impure: the
value is not stable across re-renders, and nothing causes a re-render when the clock
passes the expiry, so the sentence goes stale and stays stale.

**This has kept `pnpm lint` red since `run-eventpulse24-043`.** Three commits in run-055
ran with it red. Either CI is failing and being ignored, or lint is not gating — both
worth knowing.

Also in scope: `e2e/digest-opt-out.spec.ts:102` defines a `digest()` helper nothing calls.

## Acceptance Criteria

- [ ] `expiryLine` is called **once per render**, from a single `now`
- [ ] The value is not read from `Date.now()` during render — it comes from state seeded
      on mount, so the component is pure and the compiler's rule is satisfied rather than
      suppressed
- [ ] **No `eslint-disable` is used.** The rule is correct; the code was wrong
- [ ] A test covers the boundary: a pending change whose `expiresAt` is seconds away
      renders one coherent sentence, not a guard and a body that disagree
- [ ] A test covers the already-expired case rendering "That link has expired — send a new
      one." rather than an empty paragraph
- [ ] Both tests **proved to fail** against the current implementation before the fix
- [ ] The unused `digest()` helper is removed from `e2e/digest-opt-out.spec.ts`
- [ ] `pnpm lint` exits **zero**
- [ ] Existing `email-change` tests pass unchanged — this is a fix, not a redesign

## Technical Notes

- The minimal correct shape is `const [now] = useState(() => Date.now())`, which is pure
  at render and stable. **Do not add a ticking interval** unless the existing tests show
  one is wanted: a countdown that updates every second is a different product decision
  from a sentence that is correct when the page loads, and this item is a bug fix.
- `expiryLine` itself is already pure and well-tested in shape — it takes `now` as an
  argument precisely so it can be tested. The bug is entirely at the call site.
- The two remaining lint warnings (`source-mute-control.tsx` `useCallback` dependency,
  `avatar-disc.tsx` `<img>`) are **not** in scope. They are warnings, not errors, and the
  `<img>` one is a deliberate choice in a file that explains itself.

## Dependencies

(none)
