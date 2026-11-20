# Plan: email-change-impure-render

**Run:** run-eventpulse24-056 · **Mode:** confirm · **Complexity:** low

## The bug, precisely

```tsx
{expiryLine(expiresAt, Date.now()) !== null ? (
  <p … data-pending-expiry>{expiryLine(expiresAt, Date.now())}</p>
) : null}
```

Two reads of the clock, one sentence. `expiryLine` is pure and takes `now` as an argument
precisely so it can be reasoned about; the call site then hands it two different values.

**What a user can actually see.** The guard reads `T`, the body reads `T + ε`. If the link
expires inside `ε`, the guard computes *"The link works for about 1 more minute"*, lets the
paragraph render, and the paragraph then renders *"That link has expired — send a new
one."* The two halves of one decision disagree. Crossing any minute boundary inside `ε`
produces the milder version: a guard that saw 2 minutes and a body that prints 1.

**Why the compiler objects.** `Date.now()` in render is impure. Beyond the inconsistency,
the sentence never updates — nothing re-renders when the clock passes the expiry, so a
page left open shows a countdown frozen at whatever it was when React last rendered.

## The fix

```ts
const [now] = useState(() => Date.now());
```

One read, on mount. Pure at render, stable across re-renders, and the lazy initializer
means it is not re-evaluated.

**Deliberately not a ticking countdown.** An interval that re-renders every minute is a
different product — a live countdown rather than a sentence that is true when the page
loads. The existing tests describe the latter and this item is a bug fix. If a live
countdown is wanted, it is its own work item with its own decision about whether a settings
page should animate.

**No `eslint-disable`.** The rule is correct and the code was wrong.

## The tests, and how each fails first

Both are written against the current implementation and **must fail** before the fix.

1. **"reads the clock once per render"** — spy on `Date.now`, render a pending change,
   assert one call. Currently two. This encodes the defect directly rather than a
   downstream symptom.
2. **"the guard and the sentence cannot disagree"** — stub `Date.now` to return `T` then
   `T + 120_000`, with `expiresAt` 60 s after `T`. Current behaviour: the guard passes on
   `T` and the body prints *"That link has expired"*. Correct behaviour: one read at `T`,
   so the paragraph reads *"about 1 more minute"*. A clean fail → pass.

The three existing expiry tests must pass **unchanged** — they describe behaviour that is
correct and is not being altered.

## Also in scope

`e2e/digest-opt-out.spec.ts:102` — a `digest()` helper nothing calls. Verified: two
occurrences in the file, both the definition. Deleted.

## Verification

- `pnpm lint` exits **zero** — the whole point
- Frontend suite green
- `tsc --noEmit` clean

## Out of scope

The two remaining lint **warnings**: `source-mute-control.tsx`'s `useCallback` dependency,
and `avatar-disc.tsx`'s `<img>`. Warnings, not errors, and the `<img>` is a documented
deliberate choice. Touching either would make this commit two things.
