---
run: run-eventpulse24-030
work_item: digest-preference-read-helper
intent: digest-personal-events-control
reviewed: 2026-11-13T01:32:00Z
---

# Code Review Report

**Run**: run-eventpulse24-030
**Intent**: digest-personal-events-control
**Work item**: `digest-preference-read-helper` (item 1 of 6)
**Reviewed**: 2026-11-13T01:32:00Z
**Files Reviewed**: 2

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 0 | 0 | 0 |
| Security | 0 | 0 | 0 |
| Architecture | 0 | 0 | 0 |
| Testing | 0 | 1 | 0 |
| **Total** | **0** | **1** | **0** |

**Tests Status**: Passing — 11/11 in this file; 132 files / 2287 tests across the
frontend suite.

**One finding, and it was a real one.** The review found a coverage gap that the
mutation testing in the test report had missed: the `?? null` normalisation was
load-bearing and no test could fail if it were deleted. The gap was closed and the
closing test was itself mutation-verified.

---

## Files Reviewed

- `frontend/lib/digest-preference-read.ts` (created — the server-only read helper)
- `frontend/lib/digest-preference-read.test.ts` (created — its tests)

---

## Auto-Fixed Issues

No auto-fixes applied. Nothing in either file was mechanically fixable: no unused
imports, no console statements, no `debugger`, no trailing whitespace, no missing
final newline, no `any`/`!` assertions, no import-order violations. ESLint and
Prettier both reported clean on the first run.

---

## Applied Suggestions

### 1. [Testing] The `?? null` normalisation had no failing test

- **File**: `frontend/lib/digest-preference-read.ts:78-79`
- **Description**: The helper normalises the schedule fields with
  `response.data.digest.delivery_time ?? null` and
  `response.data.digest.timezone ?? null`. This normalisation is load-bearing: the
  generated schema types both fields as `delivery_time?: string | null` — an
  **optional** key, so the API may omit the field entirely, and the omitted field
  arrives as `undefined`. The helper's declared return type is `string | null`, and
  `undefined` is not in it, so `?? null` is what makes the declared type true.

  The existing suite covered only the explicit-`null` fixture. With that coverage,
  the `?? null` could be deleted and the whole suite would still pass — a test that
  cannot fail is not a test, and the testing standards require every test to be
  able to fail.

  The gap was confirmed by mutation, not by inspection: replacing
  `?? null` with a cast (`as string | null`) left all 10 original tests passing. The
  mutation was then reverted and a test was added.

- **Rationale**: The distinction is not cosmetic. A caller that changes the opt-out
  has to send the schedule back unchanged, because the endpoint has no
  "change one field" mode and refuses to half-apply the pair. `undefined` and
  `null` are different things in that body — one is a field with no value, the other
  is a field that is absent — and a serializer treats them differently. A screen that
  read `undefined` and sent it back would be sending a body the endpoint interprets
  differently from one carrying `null`.

- **Risk Level**: Low — additive test only; no production code was changed by this
  finding.

- **Approved**: applied directly under auto mode, as a mechanical test-coverage
  closure with no behavioural change to production code.

- **Diff**:

```diff
+  it("reads an absent delivery time and timezone as null, not undefined", async () => {
+    // **The schema permits the key to be missing, not just null.** `delivery_time` and
+    // `timezone` are `delivery_time?: string | null` — an *optional* key, so the API may
+    // omit them entirely. The read's declared type is `string | null`, and `undefined` is
+    // not in it, so an absent key must become `null`.
+    ...
+    GET.mockResolvedValue({
+      data: {
+        ...
+        // **The digest block with no delivery_time and no timezone keys at all.**
+        digest: {
+          city: null,
+          city_source: null,
+          include_personal_events: true,
+        },
+      },
+      response: new Response(null),
+    });
+
+    const read = await readDigestPreference();
+
+    expect(read.kind).toBe("found");
+    if (read.kind !== "found") throw new Error("expected the found branch");
+    expect(read.preference.delivery_time).toBeNull();
+    expect(read.preference.timezone).toBeNull();
+    // **Explicitly not `undefined`.** `toBeNull` alone would not catch a value that was
+    // `undefined`, and `toBeUndefined` alone would not catch one that was `null` — the
+    // pair is the claim.
+    expect(read.preference.delivery_time).not.toBeUndefined();
+    expect(read.preference.timezone).not.toBeUndefined();
+  });
```

**The closing test was mutation-verified.** With the new test in place, re-applying
the `as string | null` mutation makes it fail:

```
FAIL  lib/digest-preference-read.test.ts > readDigestPreference >
      reads an absent delivery time and timezone as null, not undefined
AssertionError: expected undefined to be null
- Expected: null
+ Received: undefined
```

The mutation was then reverted; the helper is back to `?? null` on both lines.

---

## Skipped Suggestions

No suggestions were skipped.

---

## Review Detail by Category

### Code Quality

Clean. No unused imports, no dead code, no debug statements, no formatting drift.
The helper is 27 lines of logic under a 24-line docstring — the docstring is longer
than the code because the two-answer shape and the cookie-bearing read are both
decisions a future reader would otherwise have to reverse-engineer. The same
rationale governs the comment density in the test file. This matches the house style
of the precedent it copies (`frontend/lib/conflict-list-read.ts`), which is
documented at the same ratio.

### Security

Clean.

- **No secrets, no hardcoded credentials.** The base URL comes from `apiBaseUrl()`,
  which reads configuration — never a literal.
- **The read is authenticated.** `sessionHeaders()` forwards the visitor's whole
  cookie jar. A server-side read without them would be anonymous, and an anonymous
  read of a digest preference answers with *somebody else's* default. This is
  asserted by the "reads the preference with the visitor's cookies" test, which pins
  both the path and the cookie string.
- **No PII exposure.** The helper returns three scalar fields — no email, no name,
  no city, no event content. This aligns with AD-13's no-PII rule, though the
  helper logs nothing at all, so the rule does not bind here.
- **No injection surface.** The helper takes no user input and issues one
  `GET` against a path literal. The endpoint path is not user-controlled.
- **No new API surface.** The helper reads an existing endpoint; it adds no route
  and no write. The route that *writes* the preference is a separate work item
  (`digest-settings-route`), and it was not in scope for this review.

### Architecture

Clean, and consistent with the precedent.

- **Placement is right.** `frontend/lib/` is where the house keeps its server-only
  read helpers (`conflict-list-read.ts`, `notification-settings-read.ts`). The helper
  imports `apiBaseUrl`, `api` from `@/lib/backend-client`, and `sessionHeaders` —
  the same three imports, in the same order, as `conflict-list-read.ts`.
- **AD-19 is respected.** Backend access goes through the generated client. No
  hand-written `fetch`, and ESLint's `no-restricted-globals` / `no-restricted-imports`
  rules confirm it.
- **The module is server-only by construction.** It reaches `next/headers` through
  `sessionHeaders()`. A grep across `frontend/` confirms **no `.tsx` file imports the
  helper**, so no `"use client"` component can reach it — a `"use client"` import
  would break the production build, and the architecture test would not catch it
  silently.
- **The returned shape is narrower than the API's.** The helper hand-writes a
  `DigestPreference` type rather than re-exporting the generated
  `DigestPreferenceOut`. This is the deliberate choice recorded in the plan: a
  later change to the onboarding state shape cannot break a settings screen that
  never asked for it, and the `city` cannot leak into a caller's save body. This is
  also why the earlier unused-`components`-import lint error was resolved by
  removing the import rather than by widening the type — the narrow type is the
  point.
- **Error handling is deliberate, not incidental.** The `try/catch` returns
  `"unavailable"` rather than propagating, and the two-answer discriminant keeps
  "the server said no" distinct from "the server could not answer". A page that
  folded them together would render "the opt-out is off" for a user who never
  changed it.

### Testing

One finding, now closed. See "Applied Suggestions" above.

- **Coverage.** Every branch of the helper is exercised by a test that fails if the
  branch is removed: the base-URL guard ("answers 'unavailable' when there is no API
  to ask"), the missing-body guard ("answers 'unavailable' when a 200 carries no
  payload" and "answers 'unavailable' when the API answers with an error"), the
  throw path ("answers 'unavailable' when the request fails"), the `?? null`
  normalisation (the newly added test), and the found path.
- **Mock strategy follows the house pattern.** `vi.mock` on `@/lib/backend-client`,
  `@/lib/api-base-url` and `next/headers`, with `cookies` resolving to an object
  whose `toString()` is the cookie jar — exactly `conflict-list-read.test.ts`. The
  fake is at the port boundary; no ORM is mocked, and there is no database involved
  in a server-side read helper.
- **The assertions are load-bearing.** The three-key shape test asserts the exact
  key set, not a subset, so a widened shape fails. The "never answers 'unavailable'
  as if the user had opted out" test asserts the absence of the `preference` key, so
  a future refactor that folded the two arms fails rather than silently changing the
  screen's meaning.
- **No placeholder assertions.** No `or`-fallbacks, no `toBeTruthy()` where a
  specific value is claimed.

**A note on how coverage was measured.** The frontend project does not have
`@vitest/coverage-v8` installed, so the coverage figure cannot be produced by a
tool run in this environment. The 100% claim in the test report rests on manual
branch enumeration, and the review re-derived it independently by listing each
branch in the helper and matching it to a failing test. The newly added test closed
the one branch (`?? null`) that manual enumeration had counted as covered but
mutation testing proved was not.

---

## Project Tooling Used

- **ESLint** (`eslint.config.mjs`): `npx eslint lib/digest-preference-read.ts lib/digest-preference-read.test.ts` — clean, both before and after the fix.
- **Prettier** (`.prettierrc`): `npx prettier --check` on both files — clean, both before and after the fix.
- **TypeScript**: `npx tsc --noEmit` — clean.
- **Vitest**: `npx vitest run lib/digest-preference-read.test.ts` — 11/11 passing.
- **Full frontend suite**: `npx vitest run` — 132 files, 2287 tests, 0 failed.

---

## Standards Referenced

- `.specs-fire/standards/coding-standards.md`
- `.specs-fire/standards/testing-standards.md`
- `.specs-fire/standards/constitution.md`

---

## Verdict

**Approved.** The helper is ready for work item 2.

One finding was raised and closed within the review: the `?? null` normalisation had
no test that could fail. The closing test was itself mutation-verified against the
mutation it targets, and the mutation was reverted. No production code was changed
as a result of the review — the fix was entirely in the test file.

No suggestions require user approval. No security, architectural, or behavioural
change was made or is pending.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-030*

---

# Code Review Report — Work Item 2 of 6

**Run**: run-eventpulse24-030
**Intent**: digest-personal-events-control
**Work item**: `personal-events-digest-toggle` (item 2 of 6)
**Reviewed**: 2026-11-13T01:48:00Z
**Files Reviewed**: 4

---

## Summary

| Category | Auto-Fixed | Applied | Skipped |
|----------|------------|---------|---------|
| Code Quality | 0 | 1 | 0 |
| Security | 0 | 0 | 0 |
| Architecture | 0 | 1 | 0 |
| Testing | 0 | 1 | 0 |
| **Total** | **0** | **3** | **0** |

**Tests Status**: Passing — 31/31 in the new file; 133 files / 2319 tests across the
frontend suite.

**Three findings, all closed.** Two were found by the compiler and the mutation
testing respectively; one was found by reading the accessible structure.

---

## Files Reviewed

- `frontend/components/settings/digest-personal-events.tsx` (created — the toggle and its pure body builder)
- `frontend/components/settings/digest-personal-events.test.tsx` (created — its tests)
- `frontend/app/settings/quiet-hours/page.tsx` (modified — the discoverability link)
- `frontend/app/settings/quiet-hours/page.test.tsx` (modified — the link's assertion)

---

## Applied Suggestions

### 1. [Architecture] The schedule was two nullable fields; a half-schedule was representable

- **File**: `frontend/components/settings/digest-personal-events.tsx` — the props type
- **Description**: The first draft took `deliveryTime: string | null` and
  `timezone: string | null` as two independent props. Three problems followed.
  First, a **half-schedule** — a time with no zone — was representable, even though
  the server can never produce one (`DigestPreference.delivery_time` and `.timezone`
  are both non-nullable columns) and the endpoint can never accept one (it refuses to
  half-apply the pair). Second, the `canSave` guard was a separate boolean, so
  TypeScript could not see that the fields were non-null inside the handler — the
  compiler rejected the body with `Type 'string | null' is not assignable to type
  'string'`. Third, the natural fix (a cast, or `?? ""`) would have sent an empty
  string the server would reject with a message the user could do nothing with.
- **Rationale**: The schedule is **one** fact with two halves, and it should be one
  value. `schedule: { deliveryTime: string; timezone: string } | null` makes a
  half-schedule unrepresentable, makes the compiler narrow the schedule inside the
  handler, and makes the impossible body unbuildable — rather than leaving it to a
  guard a refactor could forget.
- **Risk Level**: Low — a props-shape change to a component that has no caller yet
  (the route is work item 3).
- **Approved**: applied directly under auto mode — a mechanical type-level correction
  with no behavioural change.
- **Diff**:

```diff
-  /** The stored delivery time — `HH:MM:SS`, or `null` if the user has no schedule yet. */
-  deliveryTime: string | null;
-  /** The stored zone, or `null` if the user has no schedule yet. */
-  timezone: string | null;
+  /**
+   * The stored schedule — **the time and its zone, together or not at all**.
+   *
+   * **`null` when the user has no schedule yet.** ...
+   * **One value rather than two, and that is deliberate.** ...
+   */
+  schedule: { deliveryTime: string; timezone: string } | null;
```

### 2. [Testing] The "no schedule" guard was unreachable, so no test could hold it

- **File**: `frontend/components/settings/digest-personal-events.tsx` — the guard
- **Description**: The guard that stops a request without a schedule lived in the
  click handler. **The button is `disabled` without a schedule**, and a `disabled`
  button does not fire React's click handler — so the branch was unreachable and no
  test could reach it. A probe confirmed it: `fireEvent.click` on the disabled button
  issued no `PUT` at all.

  **The mutation survived.** Removing `if (schedule === null) return;` left all 29
  tests passing. A guard that no test can hold is a guard that can be silently
  removed.
- **Rationale**: The fix was **not** a contrived test that forces a click past a
  disabled attribute. It was to move the guarantee out of the event handler and into a
  **pure function** — `digestPreferenceBody(schedule, includePersonalEvents)` — that
  returns `null` when there is nothing to send. "There is nothing to send" is now a
  *value the caller has to deal with*, and it is asserted directly: "builds nothing
  without a schedule".
- **Risk Level**: Low — the pure function is the same logic, relocated.
- **Approved**: applied directly under auto mode.
- **Diff**:

```diff
+export function digestPreferenceBody(
+  schedule: DigestPersonalEventsProps["schedule"],
+  includePersonalEvents: boolean,
+): { include_personal_events: boolean; delivery_time: string; timezone: string } | null {
+  if (schedule === null) return null;
+  return {
+    include_personal_events: includePersonalEvents,
+    delivery_time: schedule.deliveryTime,
+    timezone: schedule.timezone,
+  };
+}
```

  The handler now reads:

```diff
-    if (schedule === null) return;
+    const body = digestPreferenceBody(schedule, !included);
+    if (body === null) return;
```

### 3. [Code Quality] The section's accessible name collided with the button's

- **File**: `frontend/components/settings/digest-personal-events.tsx` — the `<section>`
- **Description**: The section was labelled `"Personal events in the Pulse Digest"` —
  the same string as the button's `aria-label`. A screen reader would have announced
  *"Personal events in the Pulse Digest, Personal events in the Pulse Digest, toggle
  button, pressed"* — the same phrase twice, for two different things.

  The house pattern is a **short noun phrase**: `"Digest delivery time"`,
  `"Quiet hours"`, `"Reminder plan editor"`. This one was a full sentence, and the
  collision was the symptom.
- **Rationale**: The section names the *group*; the button names the *control*. They
  are different things, so they should not be the same string. A probe confirmed the
  collision before the fix and the fix's shape after it.
- **Risk Level**: Low — an `aria-label` on a landmark region.
- **Approved**: applied directly under auto mode.
- **Diff**:

```diff
-    <section aria-label="Personal events in the Pulse Digest" data-digest-personal-events>
+    <section aria-label="Personal events" data-digest-personal-events>
```

  And a test was added to hold it — "sits in a labelled region whose name is not the
  button's name" — which fails if the two strings ever collide again.
  **Mutation-verified**: restoring the colliding label fails that test.

---

## Skipped Suggestions

No suggestions were skipped.

---

## Review Detail by Category

### Code Quality

Clean. No unused imports, no `console` statements, no `debugger`, no trailing
whitespace, no `any` or non-null assertions, no trailing-comma or quote drift.
Prettier, ESLint, and `tsc --noEmit` all report clean.

**The docstring density is house style, not excess.** The component carries a long
module docstring and per-constant docstrings, which is the same ratio as
`detail-mute-control.tsx` — the precedent it copies. Each block states a *decision*
and *why*, not a restatement of the code: why the button rather than a switch, why the
accessible name is stable while the visible text is not, why the schedule travels with
the flag, why the state after a save is the server's answer, and why a user with no
schedule has nothing to send.

**The `schedule` prop is a plain object, not a `readonly` type.** That matches the
house — `DigestDeliveryTimeProps` and `DetailMuteControlProps` are plain too.

### Security

Clean.

- **No secrets, no PII.** The component renders two fixed sentences and sends three
  scalar fields. It logs nothing. The failure line is either the API's own message
  (written for the user) or the route's own line — never a raw error.
- **No injection surface.** The only dynamic value in the DOM is React-escaped text.
  The endpoint path is a literal. The request body is three typed fields.
- **The opt-out is written to the user's own preference.** The endpoint is behind the
  session cookie, and the read helper in item 1 carries the visitor's cookies, so the
  value read and the value written belong to the same person.
- **CSRF.** The write goes through the frontend's own origin via the existing
  `api` client, which is the house's path for every settings write. No new
  cross-origin call is introduced.

### Architecture

Clean, and consistent with the house.

- **Placement is right.** `frontend/components/settings/` is where the settings
  islands live. The component is a `"use client"` island, like every other settings
  control, and it reaches the backend only through `api` from `@/lib/backend-client`
  (AD-19). ESLint's `no-restricted-globals` and `no-restricted-imports` rules confirm
  it — no `fetch`, no `openapi-fetch` outside the client.
- **The toggle pattern follows the recorded house decision.** `<button>` +
  `aria-pressed`, **not** `role="switch"` — the codebase's own docstring in
  `reminders/reminder-picker.tsx:20` records that the Detail Screen used to use
  `role="switch"` and that the chips are `<button>`s with `aria-pressed` instead. This
  item follows that decision rather than reopening it.
- **The one status region holds.** `SaveFeedback` renders the page's single
  `role="status"`. A probe confirmed exactly one status region and no alert until a
  failure occurs — and a test now holds both counts. This is the rule
  `detail-mute-control.tsx:215-228` records, and work item 3 (the route) must not add
  a second status region.
- **The failure split is the house's.** `saveFailureMessage(error, offline)` —
  the API's own message when the API refused, the route's own line when the request
  never arrived. The same function `digest-delivery-time.tsx` uses.
- **No new tokens.** The class list is `min-h-[44px] text-ink-secondary underline
  underline-offset-4 [font:var(--type-scale-meta-md)] disabled:cursor-default` —
  every part of it appears in `detail-mute-control.tsx` verbatim. **No hex, no new CSS
  variable, no new spacing token, and no `DESIGN.md` edit.** The button does not use
  `bg-warm-personal`, so `pulse-card.test.tsx`'s architecture assertion still holds.
- **The pure builder earns its place.** Extracting `digestPreferenceBody` was not
  premature abstraction: it is the seam where "exactly three keys" and "no schedule,
  no body" are decided, and it is the only part of the component a test can reach for
  the no-schedule case.
- **The discoverability link is in the right place.** It sits in the quiet-hours
  page's existing "Pulse Digest" section — where the digest's other setting already
  lives. With no settings index and no settings sub-nav, this link is the only thing
  that makes `/settings/digest` findable, which is why the work item made it a
  *condition* of choosing a separate route.

### Testing

Clean. 31 tests, all able to fail.

- **Coverage.** Every branch of the component is exercised: the schedule-present
  path, the schedule-absent path, the success path, the API-refusal path, the
  no-payload path, the throw path, and the in-flight path. The pure builder's two
  branches are both covered directly.
- **The body assertions are exact-key-set**, not subset checks — "builds exactly the
  three keys the endpoint needs" asserts `Object.keys(...).sort()` equals the three
  names, so a widened body fails.
- **The accessible structure is pinned**: the button's name is stable across both
  states, `aria-pressed` flips, the visible text changes with the state, the region
  label does not collide with the button's name, the region contains the button, and
  the page carries exactly one status region and no alert until a failure.
- **The state-after-save test is the strong one**: the server answers with the
  *opposite* of what the user asked for, and the control shows the server's value.
  A client that used its own optimistic guess would fail it.
- **The failure tests cover all three cases**: the API's refusal (verbatim, and the
  generic line asserted *absent*), the request that never arrived, and a 500 whose
  body is not the project's error shape.
- **Mutation-verified.** Seven mutations were applied and reverted; each was caught:

| Mutation | Caught by |
|----------|-----------|
| Added `city` to the body | 5 failures — the two pure-builder tests and the three wire-body tests |
| Hardcoded the schedule (`"00:00:00"` / `"UTC"`) | 4 failures |
| Removed the rollback in the `catch` | "puts the state back when the save fails" |
| Made the accessible name vary with the state | 5 failures |
| Used the client's optimistic guess instead of the server's answer | "takes the server's answer after a save, not the user's guess" |
| Removed the "no schedule" guard | "builds nothing without a schedule" — **after finding 2 moved it** |
| Restored the colliding section label | "sits in a labelled region whose name is not the button's name" |

**The sixth is the finding worth recording.** It survived the first pass of the suite
entirely, because the guard lived in the click handler and the button is `disabled`
without a schedule — so the branch was unreachable, and an unreachable branch cannot
be held to by a test. The fix was not to contrive a test that forces a click past a
disabled attribute; it was to move the guarantee into a pure function whose return
value is the claim.

---

## Project Tooling Used

- **ESLint** (`eslint.config.mjs`): clean on all four files.
- **Prettier** (`.prettierrc`): clean on all four files.
- **TypeScript**: `npx tsc --noEmit` — clean.
- **Vitest**: `npx vitest run components/settings/digest-personal-events.test.tsx` — 31/31.
- **Full frontend suite**: `npx vitest run` — 133 files, 2319 tests, 0 failed.

---

## Standards Referenced

- `.specs-fire/standards/coding-standards.md`
- `.specs-fire/standards/testing-standards.md`
- `.specs-fire/standards/constitution.md`

---

## Verdict

**Approved.** The toggle is ready for work item 3.

Three findings were raised and closed within the review: the schedule was modelled
as two nullable fields (making a half-schedule representable), the "no schedule"
guard was unreachable and therefore untestable, and the section's accessible name
collided with the button's. All three are fixed, and each fix is held by a test that
was mutation-verified against the change it guards.

No security, architectural, or behavioural concern is pending. No suggestion requires
user approval.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-030*

---

# Work Item 3 of 6: `digest-settings-route` (confirm)

## Summary

The route was reviewed independently against the house pattern, the architectural rules
(AD-2, AD-10, AD-19), the design-token and spacing-scale gates, and the acceptance
criteria in the work item.

**The route's logic is correct.** The five-step pattern is followed in order, the
schedule join is right, and there are no rule violations. **The first pass of the test
suite, however, had four weaknesses** — and two of them were serious enough that the
suite would not have caught a route doing the wrong thing.

**Four findings. All four are closed.**

## Findings

### 1. The `redirect` mock only recorded the call — High — **Closed**

**The problem.** The mock was `redirect: vi.fn()`, a no-op. **The route therefore kept
going past the redirect and served the page anyway.** The assertion
`expect(redirect).toHaveBeenCalledWith("/preview")` passed while the page did the
opposite of what the test claimed to check.

The anonymous case was masked: the `session.kind !== "signed-in"` branch caught the
anonymous session afterwards and rendered the failure state instead. **The
half-onboarded case was not masked** — a signed-in user with incomplete onboarding
passed straight through to the toggle, so the test passed over a route that served a
half-onboarded visitor a control that could write a preference before the onboarding
they were in the middle of.

**The fix.** The mock now throws, as the real `redirect` does:

```typescript
redirect: vi.fn(() => {
  throw new Error("NEXT_REDIRECT");
}),
```

and the tests await the rejection and assert both that the route redirected **and**
that the page was not served (`readDigestPreference` was never called).

### 2. The schedule's values were never asserted — High — **Closed**

**The problem.** The test asserted `expect(toggle()).not.toBeDisabled()`. **That is the
weakest form the assertion could take** — a route that passed `timezone: "UTC"` and
`deliveryTime: "00:00:00"` would satisfy it, and the user would have their digest time
and zone silently rewritten by their next save.

**This was the route's most important invariant**, and it was pinned by an assertion
that could not fail against a wrong implementation.

**The fix.** The schedule is now observed the only way it can be observed — by
pressing the control and reading the body it sends:

```typescript
fireEvent.click(toggle());
await waitFor(() => expect(PUT).toHaveBeenCalled());
expect(PUT.mock.calls[0][1].body).toEqual({
  include_personal_events: false,
  delivery_time: "09:00:00",
  timezone: "America/New_York",
});
```

Two new mutations were applied and confirmed to fail against it: hardcoding the
timezone to `"UTC"`, and hardcoding the delivery time to `"00:00:00"`.

### 3. The two failure branches could not be told apart — Medium — **Closed**

**The problem.** Step 3 (the session was never answered) and step 4 (the read failed)
render **the same `SettingsStates`**, and the test asserted only that element's
presence. A route that swapped the two `AppShell` prop sets — showing the account name
to a visitor whose session was never answered, or hiding it from a user whose session
*was* answered — would pass every test.

**The fix.** The account row's name is the observable difference, so it is asserted:

- `""` when the session could not be answered (step 3),
- `"Maya"` when it could (step 4).

A new test was added for step 4, and a new helper reads the name from the `aria-label`
attribute rather than the accessible name — **the accessible-name computation trims the
trailing space `"Account: "` carries, so an unnamed account's name would read as
`"Account:"`**. This was found by a probe, not by reading the code.

### 4. The half-schedule case asserted only that an element existed — Low — **Closed**

**The problem.** `expect(document.querySelector("[data-no-schedule]")).not.toBeNull()`
would pass against an **empty** element, and an empty element is not an explanation. The
no-schedule case asserted the exact sentence; the half-schedule case did not.

**The fix.** The half-schedule case now asserts the exact sentence too, and a **second**
half-schedule test was added for the other direction — a zone with no time. The join is
symmetric, and a join that only checked one side would have let the second through. That
mutation was applied and is caught.

## Things the review confirmed as correct

- **The five-step pattern** — present, in order, with `redirect` outside any try/catch.
- **The schedule join** — `delivery_time !== null && timezone !== null` — a half-schedule
  is unrepresentable downstream, because the toggle's prop type makes it a compile
  error. The review verified the premise against the backend schema independently
  (`schemas.py:653-654`, `onboarding.py:727-728`) and against the generated client.
- **`displayName()`** — a copy, which is correct per the house rule; extracting a shared
  helper is a different change.
- **One `role="status"` region** — verified by rendering.
- **No new tokens, no new spacing steps, no animation** — `tokens.test.ts`,
  `spacing-scale.test.ts` and `motion.test.ts` all pass.
- **The endpoint** — `GET /api/personal/onboarding` through `lib/digest-preference-read.ts`,
  the correct owner (`apps.personalization`, not the `apps.delivery` notification
  settings); the toggle PUTs `/api/personal/onboarding/digest-preference`, the only
  endpoint that accepts `include_personal_events`.
- **AD-19** — `make client` leaves `frontend/lib/api/` clean.
- **The copy** — the lede matches the sibling pages' register.

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| The skeleton's `w-64` was off the DESIGN.md spacing scale — and `tokens.css` resets Tailwind's spacing multiplier, so the class generates **no CSS at all** | Medium | **Fixed** — `w-30`, as the other four skeletons use. Caught by `tests/spacing-scale.test.ts` |
| The `redirect` mock was a no-op, so the route served the page past the redirect | High | **Fixed** — the mock throws, as the real one does |
| The schedule's values were asserted only as "the control is enabled" | High | **Fixed** — the PUT body is now asserted |
| The two failure branches were indistinguishable to the suite | Medium | **Fixed** — the account row's name is asserted in both |

## Mutation Verification

**Thirteen mutations** were applied to the route and the test file and reverted. **All
thirteen were caught.** The full table is in the test report.

**Two of them survived the first version of the suite** — hardcoding the schedule's
timezone and hardcoding its delivery time — and both were found by mutation testing
rather than by inspection. That is the point of the standard: the review said the
schedule test "cannot fail against a route that passes a wrong but complete schedule",
and the mutation confirmed it.

## Ready for Completion

- [x] All tests passing (16 in this item; 2335 across the frontend suite)
- [x] Coverage target met
- [x] All acceptance criteria validated
- [x] All four findings closed and mutation-verified
- [x] No critical issues open

No security, architectural, or behavioural concern is pending. No suggestion requires
user approval.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-030*

---

# Work Item 4 of 6: `onboarding-opt-out-decision` (confirm)

## Summary

The decision was reviewed against the corpus, not just against the plan that made it.
**The decision is correct**, and the reasoning holds on every leg — the review verified
each claim against the PRD and the design corpus independently.

**Four findings. Three are closed; one is recorded as a follow-up outside this item's
scope.**

## The decision is right

| Claim | Verdict |
|-------|---------|
| FR-1 names the onboarding step contents and the opt-out is not among them | **True** — `prd.md:246` |
| "Configure later" supports deferring the opt-out | **True, and correctly used** — `prd.md:236` is corroborating, not load-bearing |
| No design document specifies an onboarding opt-out | **True** — a sweep of `EXPERIENCE.md`, `DESIGN.md`, the PRD, the addendum and the reconcile brief found zero; `EXPERIENCE.md:1230` gives step 3 as "digest time + timezone", and the step-3 mockup has no toggle |
| Every opt-out the corpus *does* specify is Settings-scoped | **True** — `EXPERIENCE.md:451,453,997`, Amendment A-18 (source mute), A-19 (per-day quiet hours) |
| No PRD requirement puts the opt-out at onboarding | **True** — FR-19 (`prd.md:606`) states the capability and names no surface |

**The strongest argument is the negative one**, and the review agreed it is the right
one to lead with: *no corpus specification* ⇒ implementing one would be a **new design
decision**, not an implementation of an existing specification. **The review also
confirmed the endpoint's capability is not an ownership argument** — the endpoint's own
OpenAPI summary is *"Set the digest delivery time, timezone, home city and
personal-events opt-out"*, and the settings toggle PUTs to the **same** endpoint. Two
clients, one endpoint, two body shapes — correct under the endpoint's contract, and
correctly not treated as a reason for onboarding to own the field.

## Findings

### 1. The new test only inspected the *first* matching call — Medium — **Closed**

**The problem.** The assertion used `PUT.mock.calls.find(...)`, which returns the
**first** matching call. The exact-body assertion beside it uses
`toHaveBeenCalledWith`, which matches **any** call. So a flow that sent a **second**
`PUT` to the same endpoint — one carrying the opt-out — would have left the clean
first call satisfying both assertions, and the offending one invisible.

**The shipping code was correct throughout.** But the test's own comment claimed that
*"a flow which started sending it would fail here with a message that says why"* — and
it would not have. **A test that promises a failure it cannot produce is the same class
of defect as the false signal this item exists to remove.**

**The fix.** The assertion now runs over **every** call to the endpoint:

```typescript
const bodies = PUT.mock.calls
  .filter((call) => call[0] === "/api/personal/onboarding/digest-preference")
  .map((call) => call[1]?.body);

expect(bodies.length).toBeGreaterThan(0);
for (const body of bodies) {
  expect(Object.keys(body).sort()).toEqual(["delivery_time", "timezone"]);
  expect(body).not.toHaveProperty("include_personal_events");
}
```

**Verified by mutation** — the second-PUT mutation now fails the test.

### 2. The docstring's phrasing was ambiguous — Low — **Closed**

*"reachable from the quiet-hours page's 'Pulse Digest' section"* reads as if
`/settings/digest` **were** the quiet-hours page. It is a separate route. Now
*"linked from"*.

### 3. The plan no longer described what shipped — Low — **Closed in the plan**

The plan said the docstring changes would be "one sentence each"; the shipped text is a
short section each. **The essays are accurate and more useful than one sentence** — a
bare assertion invites the next reader to re-derive the reasoning — so the *plan* was
amended rather than the code trimmed, and the amendment says why.

### 4. The opt-out is unusable for a user with no stored schedule — Low — **Recorded, not fixed**

**This is the one real gap in the "the promise has an answer" argument, and it was
found by the review rather than by the author.**

The settings toggle disables itself when the user has no stored schedule
(`canSave = schedule !== null`, `digest-personal-events.tsx:216`). A user who skipped
onboarding's digest step has no schedule — so **the opt-out is unreachable for them**,
even though the setting is technically in Settings.

**It is not this item's defect.** The disable is item 2's deliberate, correct behaviour:
the endpoint requires the delivery time *and* the zone, so a user with no schedule has
no valid request body, and a control that can only fail is worse than one that is
honestly unavailable. **The gap is in the server's data** — every user ought to have a
schedule — not in either control.

**Recorded here so that the walkthrough (item 6) checks it**, and so that it is not
rediscovered as a surprise.

## Things the review confirmed as correct

- **The false signal is gone.** `include_personal_events` appears in
  `onboarding-flow.test.tsx` exactly twice: the mock and the negative assertion.
  Nothing else in the file implies the flow sends or reads it. **A repo-wide grep
  confirms no test anywhere asserts that onboarding sends the field.**
- **No behaviour changed.** The diff on the two source files, filtered to non-comment
  lines, is **empty**. `DigestValues` is still two fields, `initialDigestValues()` still
  seeds two, `ONBOARDING_STEP_COUNT` is untouched, the `PUT` body is still
  `{ delivery_time, timezone }`, `TITLES` is untouched.
- **No copy was edited** — correct per the criterion, since the decision changed no
  control.
- **AD-10 clean** — the flow seeds from `state.digest` and invents nothing; the
  settings toggle re-seeds from the server's answer after a save.
- **The fixture's field stays** — defensible on the same grounds as before: the server
  really sends all five fields, and a mock that hid one would be its own kind of false
  signal.
- **The decision's placement is right** — a decision that lives only in a run artifact
  gets re-litigated, and both docstrings are where a developer would look. Both cite
  the corpus rather than restating it, so they will not rot.

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| The new test inspected only the **first** matching `PUT` call, so a second call carrying the opt-out would pass every test | Medium | **Fixed** — the assertion now covers every call to the endpoint; mutation-verified |
| The docstring's *"reachable from the quiet-hours page"* read as if `/settings/digest` **were** that page | Low | **Fixed** — now *"linked from"* |
| The plan's "one sentence each" no longer described what shipped | Low | **Fixed in the plan** |
| The opt-out is unusable for a user with no stored schedule | Low | **Recorded** — outside this item's scope; to be checked in the walkthrough (item 6) |

## Mutation Verification

**Five mutations** were applied and reverted. **All five were caught**, including the
second-`PUT` mutation that the review found surviving the first version of the suite.
The full table is in the test report.

## Ready for Completion

- [x] All tests passing (24 in this file; 2336 across the frontend suite)
- [x] Coverage target met
- [x] All acceptance criteria validated
- [x] The three fixable findings closed and mutation-verified
- [x] No critical issues open

No security, architectural, or behavioural concern is pending. No suggestion requires
user approval.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-030*

---

# Work Item 5 of 6: `digest-composition-proof` (confirm)

## Summary

| Category | Count | Notes |
|----------|-------|-------|
| Files reviewed | 1 new (`backend/tests/personalization/test_digest_opt_out_seam.py`) | plus the four production files it exercises |
| Findings | 4 | all fixed or recorded; none pending |
| Critical issues | 0 | — |

**Verdict: approve.** The seam is real, the test proves it, and every assertion has
been shown able to fail.

## What the review checked

The work item is a *proof*, so the review's question is not "does this code look right"
but **"can this test be satisfied by a broken product?"** Three ways it can be, and all
three were closed:

1. **The assertion holds either way.** Checked by mutation — seven applied, seven
   caught.
2. **The path is simulated rather than exercised.** Checked by reading the file for any
   direct write of the flag. **There is none.** The only way the flag reaches the
   database in this file is the HTTP `PUT`.
3. **The setup makes the outcome inevitable.** Checked by tracing the candidate read and
   the 48-hour window, and by pinning `last_seen_at` and deriving `end_utc`.

## Findings

### 1. The work item's premise was too strong — and the correction matters (Medium, fixed in the report)

The work item says a write-path regression *"would leave every existing backend test
green and the product broken."* **That is not true of `test_onboarding_api.py`**, which
asserts the response body — and the response body echoes the stored state, so a dropped
flag fails it. The mutation table confirms: mutations 1, 3 and 7 (every write-path
break) each produced **2 failures in `test_onboarding_api.py`**.

The premise's *conclusion* holds — a seam test is worth having — but its *justification*
was inaccurate, and an inaccurate justification is how a future reader concludes the
seam test is redundant and deletes it. **The accurate statement**: the composition
suite's four opt-out tests all write the flag with a direct ORM factory write, so
**nothing proved the two halves agree**; and only the new file asserts the *composed
digest*, which is the user-visible consequence rather than a row's field.

**Fixed in the test report**, which states it plainly rather than repeating the
work item's claim.

### 2. There are two writers of `include_personal_events`, and the endpoint uses the onboarding one (Medium, recorded)

The first mutation applied to this item was placed at `digest_preferences.py:336` — a
real `include_personal_events` write, in the update branch. **The new seam test did not
catch it.** The endpoint does not go through `digest_preferences.py`; it goes through
`onboarding.set_digest_preference` → `_write_digest` → `onboarding.py:370`. The two are
separate implementations of the same preference.

**Neither is untested** — `test_digest_preferences.py` covers the service path, this
file covers the endpoint path — so this is not a defect. But a reader who assumed "the
flag is written in `digest_preferences.py`" would test the wrong code, **and the first
mutation did exactly that.** The re-applied mutation at `onboarding.py:370` was caught
immediately.

**Recorded as a follow-up for the intent:** if the two writers are ever consolidated,
this file's value does not change — it writes over HTTP either way.

### 3. The opt-back-in test composed twice, and the second compose returned the first digest (High, fixed)

The first run failed with the digest holding the public event. The cause is that the
composition is **idempotent per local date** — `_existing_digest`
(`digest_composition.py:562`) is consulted at `:699-712`, so a second compose returns
the persisted first digest unchanged.

This was the *most valuable* failure in the item, because it exposes a trap for the
next reader: **composing while opted out and then composing again proves nothing about
the flag** — the second compose never re-reads the preference. The test now composes
**once, after the opt-back-in**, and the docstring names the idempotence and the reason.
**Without the docstring, the obvious "fix" is to put the compose back**, and the test
would go green for the wrong reason again.

### 4. The fixture details were load-bearing, not incidental (Low, fixed)

- `last_seen_at` at the column default (the wall clock) is days stale against a `NOW` in
  the future — the candidate read would drop the event before the composition saw it,
  and the test would pass with an empty digest. **Pinned to `NOW`.**
- Overriding `start_utc` without deriving `end_utc` trips the model's
  `end_after_start_ck`. **The end is now derived.**

Both are documented in the docstrings, so a future edit that "simplifies" them fails
loudly rather than silently.

## Things the review confirmed as correct

- **The seam is exercised, not simulated.** No ORM write of the flag anywhere in the
  file. The user is real (`User.objects.create_user`), the session is real
  (`CsrfClient` + `force_login`), and `request.user.pk` — a UUID — is the same id space
  as `DigestPreference.user_id`, so the seam's hinge is sound.
- **The positive case is present and meaningful.** A digest that never contained
  personal events would satisfy the opt-out assertion; the second test forecloses that.
- **The fallback assertion is the one that makes the first test honest.** Asserting
  `rows["must_know"].event_id == public.id` separates "the opt-out removed it" from
  "there was never one".
- **The count assertion is not decoration.** `personal_qualifying_count == 0` is the
  difference between "not shown" and "the product does not know about it" — the
  quieter leak of the same bug.
- **Time is frozen explicitly and no expiring datetime was added.** `NOW` is a
  Wednesday; the personal event is three hours out, well inside the 48-hour window
  rather than on its edge.
- **The databases are right.** `@pytest.mark.django_db(databases=[PERSONAL, CATALOG])`,
  because the composition reads a real preference row from `PERSONAL` and the public
  candidate from `CATALOG`.
- **The existing composition tests are untouched** — `git diff` shows no change to
  `test_digest_composition.py`, and all 63 of its tests pass.
- **The docstrings explain *why*, in the house style** — every fixture and every
  assertion carries its reason, so the next reader does not "fix" the deliberate
  choices away.

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| The work item's premise claimed a write-path regression would leave every existing test green — `test_onboarding_api.py` catches it | Medium | **Corrected in the report** — the real gap is stated |
| Two writers of `include_personal_events`; the endpoint uses the onboarding one, and the first mutation hit the other | Medium | **Recorded** — both paths are covered; the finding is in the report |
| The opt-back-in test composed twice and read back the persisted first digest | High | **Fixed** — compose once, after the opt-back-in, with the reason in the docstring |
| `last_seen_at` left at the wall-clock default; `end_utc` not derived from `start_utc` | Low | **Fixed** — both pinned, both explained |

## Mutation Verification

**Seven mutations** were applied across three production files and reverted; **all seven
were caught** by the new file. The full table — including which mutation the *existing*
suites also caught, and which one was caught only after being moved to the right code
path — is in the test report.

## Ready for Completion

- [x] All tests passing (3 in this file; 6870 across the backend suite)
- [x] Coverage target met — the three cases the work item names
- [x] All acceptance criteria validated
- [x] The four findings closed or recorded, and mutation-verified
- [x] No critical issues open

No security, architectural, or behavioural concern is pending. No suggestion requires
user approval.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-030*

---

# Work Item 6 of 6: `browser-walkthrough-and-trace` (confirm)

## What was reviewed

**The walkthrough itself — `frontend/e2e/digest-opt-out.spec.ts` — and the change it
forced: `frontend/playwright.config.ts`.**

The review read the spec the way the spec claims to read the product: **can each
assertion fail?** Seven mutations were applied and reverted; all seven were caught.

## Issues Found

| Issue | Severity | Status |
|-------|----------|--------|
| The Playwright web server bound to `localhost`, not `127.0.0.1` — **React never hydrated**, so every sign-in was a native GET submit that put the password in the query string | **High** | **Fixed** — the config now matches `make web` |
| The e2e suite was therefore **incapable of signing in at all** — the pre-existing browse specs failed the same way | **High** | **Fixed** by the above; the browse specs pass now |
| The walkthrough waited on `aria-pressed`, which the control flips **optimistically** — so it raced the save | **High** | **Fixed** — it now waits on the save's own signal, `[data-saved]` |
| The composition is **idempotent per local date** — a digest left by an earlier run was returned verbatim, and the walkthrough asserted against a stale answer | **High** | **Fixed** — the walkthrough clears the days it composes for |
| The sign-in throttle made the walkthrough **unrepeatable** | Medium | **Fixed** — reset through the product's own `reset_sign_in_throttle` |
| The control's accessible name is **"the Pulse Digest"**, not "your" — the first locator found nothing | Low | **Fixed** — the name is spelled out in the spec, with the reason |
| `advance_step` past the last step **completes onboarding with no `DigestPreference`** | Medium | **Recorded** — the control handles it honestly; the state is a follow-up |
| **Two writers of `include_personal_events`** | Medium | **Recorded** — carried over from item 5's finding |
| The corpus corrections (A-5, A-7, A-10, FR-16) | — | **Recorded** — a separate intent, by design |

## The two findings that changed the *claims*, not the code

**Finding 1 — the harness could not sign in, and did so silently.** The failure mode is
unusual: an unhydrated form falls back to a **native GET submit**, so the browser's URL
becomes `/signin?email=…&password=…`. The page still renders, the form still *appears*,
and the failure presents as a timeout waiting for the URL to leave `/signin` — which reads
like a slow app rather than a broken harness. **Every claim the walkthrough makes was
false until this was fixed**, and a reviewer should treat the e2e suite's green as new
information rather than as confirmation of an existing guarantee.

**The optimistic flip — and why waiting on `aria-pressed` was wrong.** The control sets
its state *before* the PUT is sent (`digest-personal-events.tsx:237`), so `aria-pressed`
changing is the **guess**, not the **save**. The first version of the walkthrough waited
on the button and then read the API, and **it passed once and then failed on the second
run** with the server holding `true` and the button showing `false`. The fix waits on
`[data-saved]`, which `SaveFeedback` renders only once the server's answer has replaced
the guess.

## Mutation Verification

**Seven mutations** were applied across four production files and reverted; **all seven
were caught.** The full table — which mutation each test caught — is in the test report.

## Scope note for the reviewer

**`frontend/playwright.config.ts` changed, and that is outside this intent's stated
scope.** The change is one line — the web server's `--hostname 127.0.0.1` — and it is
load-bearing for **every e2e test in the repository**, not just this intent's. It is
called out here because a reviewer reading only the intent's diff would otherwise see an
unexplained change to shared tooling.

**The change is right**: it makes the e2e server the same server `make dev` starts. **And
it deserves an explicit yes rather than a silent merge.**

## Ready for Completion

- [x] All tests passing (3 walkthrough; 9 e2e; 6870 backend; 2336 frontend)
- [x] Coverage target met — seven mutations, all caught
- [x] All acceptance criteria validated
- [x] Every finding closed or recorded, and mutation-verified
- [x] No critical issues open

No security, architectural, or behavioural concern is pending. No suggestion requires
user approval.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-030*
