---
run: run-eventpulse24-030
work_item: browser-walkthrough-and-trace
intent: digest-personal-events-control
generated: 2026-11-13
mode: confirm
---

# Implementation Walkthrough: The Walkthrough — Seeing It Work, and Proving the Trace

## Summary

**This item is the intent's closing accounting, and it closed with the product working and
three defects found in the harness that was supposed to be proving it.**

FR-19's opt-out is now a control a user can find, press, and see change what their Pulse
Digest holds. The control lives at `/settings/digest`, is linked from the quiet-hours
page's "Pulse Digest" section, saves inline, and round-trips through a reload. A user with
no delivery time is told what to do rather than given a control that can only fail.

| # | Finding | Whose | Fixed here? |
|---|---|---|---|
| 1 | The Playwright web server bound to `localhost`, not `127.0.0.1` — so **React never hydrated** and every sign-in was a native GET submit that put the password in the query string | harness | **yes** |
| 2 | The e2e suite was **incapable of signing in at all** before finding 1 — the pre-existing browse specs failed the same way | harness | **yes** (by finding 1) |
| 3 | The sign-in throttle (10/IP/hour) made the walkthrough **unrepeatable** — a second run failed for a reason unrelated to the control | harness | **yes** — the walkthrough resets the allowance through the product's own `reset_sign_in_throttle` |
| 4 | The composition is **idempotent per local date** — a digest left by an earlier run is returned verbatim, so a walkthrough that did not clear it asserted against a stale answer | harness | **yes** — the walkthrough clears the days it composes for |
| 5 | The control's accessible name is **"Personal events in *the* Pulse Digest"**, not "your" — a locator that guessed it found nothing | walkthrough's own | **yes** |
| 6 | `advance_step` past the last step **completes onboarding without writing a `DigestPreference`** — a real user can reach a state with no schedule | product | **no** — the control handles it honestly; recorded as a finding |
| 7 | **Two writers of `include_personal_events`** — the onboarding endpoint and `digest_preferences.py` | product | **no** — follow-up |
| 8 | The matrix mis-flags A-5 and A-7 as uncited, misses the **A-10 ID collision**, and points FR-16's remediation at the wrong row | corpus | **no** — a separate intent, by design |

**Finding 1 is the one that matters most.** The e2e suite was not failing loudly; it was
failing *silently in the right direction*. A sign-in that never signs in still produces a
page, still produces a screenshot, still produces a "the form was submitted" URL — and
every assertion downstream would have been asserting against an anonymous session. **A
harness that cannot sign in cannot prove anything about a control behind a sign-in.**

## Structure Overview

The walkthrough is a Playwright spec, `frontend/e2e/digest-opt-out.spec.ts`, and it drives
the **real stack**: a real browser, the real Next.js app, the real Django API, the real
database.

The shape is **observe → act → observe again**, and the two observations are of different
things, because the seam this intent closed is precisely the gap between them:

- **The DOM** says what the control *shows*.
- **The API** says what the *server holds*.

A control that shows "off" while the server holds "on" would pass a DOM-only check and fail
the product. **So every state in this walkthrough is read from both sides.**

Three tests, in the order the acceptance criteria name them:

| Test | What it proves |
|---|---|
| `the control is findable, saves, and changes what the digest holds` | The control is **findable by following a link**, not by typing a URL; it shows the server's answer; the save lands; the schedule is undisturbed; it round-trips a reload; it is not write-once |
| `the digest the user receives changes: the personal event leaves Slot 1` | The **user-visible consequence**: the composed digest holds the personal event before, and does not after |
| `a user with no schedule is told what to do, not given a control that fails` | The **honest unavailable state**: disabled, with a sentence that names the next step |

## Architecture

### Pattern Used

**A walkthrough as an executable document.** The acceptance criteria name five things the
walkthrough must cover — initial state, save succeeding, failure path, digest changing,
control findable — and each is a test that can fail. **The document below is the account
of what happened; the spec is the proof.**

### The three layers the walkthrough touches

```text
┌──────────────────────────────────────────────────────────────────────┐
│  Browser — Chromium 1440×1000                                        │
│  /settings/quiet-hours → link → /settings/digest                     │
│  control: <button aria-pressed> · [data-saved] · [data-no-schedule]  │
├──────────────────────────────────────────────────────────────────────┤
│  The frontend — Next.js App Router                                   │
│  the control flips optimistically, then the server's answer replaces │
├──────────────────────────────────────────────────────────────────────┤
│  The API — Django + Django Ninja                                      │
│  GET  /api/personal/onboarding   → the stored preference            │
│  PUT  /api/personal/onboarding/digest-preference → the write        │
│  compose_digest(now=…) → the digest, composed through the worker   │
└──────────────────────────────────────────────────────────────────────┘
```

## Files Changed

### Created

| File | Purpose |
|------|---------|
| `frontend/e2e/digest-opt-out.spec.ts` | **The walkthrough.** Three tests, seven mutation-proven. |

### Modified

| File | Changes |
|------|---------|
| `frontend/playwright.config.ts` | **The web server now binds to `127.0.0.1`** — finding 1. Without it React never hydrates and every sign-in is a native GET submit. |
| `.gitignore` | `test-results/` and `playwright-report/` — Playwright's run artifacts are evidence, not source. |

## Key Implementation Details

### 1. The control is found by following a link, not by typing a URL

**There is no settings index and no settings sub-nav.** `/settings/digest` is reachable and
otherwise invisible, so the walkthrough starts at `/settings/quiet-hours` and clicks the
link — the way a user finds it.

> **A test that went straight to `/settings/digest` would pass whether the link existed
> at all.** This intent exists because a control with no path to it is not a control, and
> the only assertion that can tell the difference is one that *follows the path*.

This is why **finding 7's mutation** — the link's `href` pointed at `/settings` — was
caught: the "findable" assertion is the first thing test 1 does.

### 2. The button moves before the save lands, so the walkthrough waits for the save

**The control flips its state optimistically** — `setIncluded(next)` fires before the PUT
is even sent (`digest-personal-events.tsx:237`). **So `aria-pressed` changing is the
*guess*, not the *save*.** A walkthrough that waited for the button and then read the API
would be racing the request.

**So the walkthrough waits for the save's own signal**: `[data-saved]` — *"Saved."* — which
`SaveFeedback` renders only once the server's answer has replaced the guess
(`digest-personal-events.tsx:253-254`). **Waiting for `[data-saved]` or `[data-save-failed]`
is waiting for the round trip.**

This was found the hard way: the walkthrough passed once and then failed on the second
run, with the server holding `true` and the button showing `false`. **The optimistic flip
was the whole difference.**

### 3. The composition's idempotence is a trap the walkthrough has to step around

**The composition is idempotent per local date** — `_existing_digest`
(`digest_composition.py:562`) is consulted at `:699-712`, and when a digest exists for that
date the composition returns **the rows it persisted then**, not the rows it would compose
now.

So the "before" and the "after" cannot be the same date — and, more subtly, **a previous
run of the walkthrough may already have composed for that date**. A digest left behind
would be handed back verbatim, and the walkthrough would assert against a stale answer
while believing it had composed a fresh one.

**So the walkthrough clears the days it composes for**, and composes the "before" for one
local day and the "after" for another. **The assertion `tomorrow.local_date !== before.local_date`
is in the spec so that a future edit putting both on the same day fails loudly rather than
passing vacuously.**

### 4. The personal event is placed *for the day being composed*, not for wall-clock now

**The eligibility window is `[now, now + 48h]`, measured from the *composition's* clock**
(`digest_candidates.py:191`), not the wall clock. **So an event that qualifies for today's
digest does not qualify for tomorrow's** — a composition for tomorrow at 14:00 local reads
`[tomorrow 14:00, tomorrow+48h]`, and an event that started six hours ago is not in it.

**So the walkthrough creates its own event, two hours into the day it is composing for** —
inside the window, nowhere near its edge — and deletes any event a previous run left
behind.

### 5. The sign-in throttle is real, and the walkthrough gives the allowance back

`AUTH_THROTTLE_SIGN_IN_IP` is ten an hour per IP and `AUTH_THROTTLE_SIGN_IN_ACCOUNT` is
five an hour per account (`shared/constants.py:466-468`). **A walkthrough that signs in
once per test burns the account's five on its second run — and a walkthrough that fails on
its second run, for a reason that has nothing to do with what it is walking through, is a
walkthrough that cannot be repeated.**

**So the setup gives the allowance back**, through the product's own
`reset_sign_in_throttle` — the same function `make seed-browse` calls, and the same one the
password-reset flow calls. **It is not a backdoor around the throttle; it is the
throttle's own reset.**

### 6. The walkthrough resets the flag too, because it is a stored fact

**The walkthrough starts from a known state.** The seeded account's flag is a stored fact,
and the walkthrough's own last run left it off — **so a second run would start from a
different place than the first**, and the "the control renders the server's answer"
assertion would be asserting against a flag the walkthrough had set itself.

### 7. The no-schedule state is reachable, and the control handles it honestly

**`advance_step` past the last step completes onboarding without writing a
`DigestPreference`** (`onboarding.py:451` sets `progress.completed_at` and writes no
preference row). `skip_step` writes the default only when the step is the digest one, and
`skip_all` always writes it. **So "advance through all three steps" is a real route to a
user with no schedule** — a state the browser cannot otherwise produce.

**And the control's answer to it is honest.** The endpoint requires the delivery time and
the zone, so a user with no schedule has nothing to send; the control is **disabled**, and
says *"Set your delivery time first."* — a sentence the user can act on where a 422 is not.
**The pressed state still reports the server's value**, so the button reads pressed while
being unavailable, which is the truth.

### 8. The accessible name is spelled out, because a locator that guesses is a locator that fails for a reason nobody will guess

**The control's accessible name is "Personal events in *the* Pulse Digest"** — *the*, not
*your*. The visible text is different again: "Personal events *are in your* Pulse Digest".
**The name names the thing being controlled, so it does not change with the state; the
visible text carries the state in words, so colour is never the sole carrier of meaning.**

The name is written out in the spec rather than imported, because **the first version of
this walkthrough guessed "your" and found nothing** — and a locator that fails on a typo
in the product's copy is a locator that fails for a reason nobody will guess.

## Security Considerations

**Nothing in this item adds a surface.** No endpoint, no schema, no model, no migration.

**The walkthrough's own credentials are the seeded local ones** — `free@browse.example.test`
with its local password, read out of `backend/config/browse_seed.json` by
`seedAccount()` rather than written into the spec. **A copy in the spec would be a second
source of truth**, and a test that hard-codes an address would keep passing its own
assertion after the seed renamed the account.

**The walkthrough's shell-outs do not log anything the product would not.** The scripts
that reset the throttle, place the event and compose the digest print a digest's rows and
nothing else; **AD-13's no-PII-in-logs rule is not weakened by a test harness**, because
the harness never logs the credentials it uses — it reads them from the seed file.

**One thing worth naming.** Before finding 1's fix, the walkthrough's sign-in put the
password **in the query string** of `/signin?email=...&password=...`, because an
unhydrated form falls back to a native GET submit. That is a real leak into browser
history and server access logs, and it was happening in **the pre-existing browse specs
too**. **The fix removes it.**

## Performance Considerations

**The walkthrough is not a performance test and does not claim to be.** Three tests,
~8.9 seconds end to end, against a stack that is already up.

**The slowest part is the shell-outs** — each `manage.py shell` invocation starts a Python
process and boots Django. There are four per run (two resets, one event, one digest
reset, one compose — five, counting both composes).

**They are worth it.** The alternative — reaching into the database from the browser test —
would need a second connection and would assert something about the *database* rather than
about the *product*. **The seam this intent closed is the product's, so the walkthrough
has to cross it the way the product crosses it.**

**One thing the walkthrough deliberately does not do:** it does not compose through HTTP,
because no request handler composes a digest — **AD-11 forbids it**, and
`backend/tests/architecture/test_digest_composition_separation.py` enforces it. So the
compose is a direct call to the same service the worker's task runs
(`worker/tasks.py:481`), with an explicit clock.

## Decisions Made

### 1. The "before" and the "after" are composed on different local dates

**The alternative — same date, cleared between** — was rejected because it does not prove
the same thing. Composing on two dates proves the digest is **composed fresh** each time
and that the difference is the flag, not a leftover row. **Both dates are cleared first**,
so a previous run cannot poison either.

### 2. The walkthrough reads the server's state over the API, not from the DOM

**The DOM says what the control shows; the API says what the server holds.** The seam is
the gap between them. **The walkthrough asserts both, every time.**

### 3. The walkthrough resets its own state rather than assuming a clean database

**A walkthrough that only works on a fresh database is not a walkthrough the next person
can run.** Every mutable thing it touches — the flag, the throttle, the event, the
digests — is put back to a known state in `beforeEach` or immediately before the
assertion that depends on it.

### 4. The corpus corrections are **named, not fixed**

The A-10 ID collision in particular is a **corpus defect** — two different amendments share
one ID, which makes the whole amendment ID space unreliable for any tool that reads it.
Fixing it means renumbering and propagating across the PRD, DESIGN.md, EXPERIENCE.md and
the mockups. **That is an intent of its own**, and folding it in here would put a
corpus-wide renumbering inside a feature change — exactly the kind of scope bleed that
makes a traceability matrix stop being trustworthy.

### 5. The walkthrough's spec lives in `frontend/e2e/`, not in a new suite

**The Vitest suite is fast, hermetic, and runs on every commit; these tests need a stack
up and a seeded database.** The Playwright config's `testDir` is `./e2e` and its Vitest
`include` is `**/*.test.{ts,tsx}`, so the two runners cannot pick up each other's files —
**which is why the spec is named `*.spec.ts` and not `*.test.ts`.**

## Deviations from Plan

### 1. The plan said the walkthrough would "drive the real thing." It found that the harness could not.

**The work item's premise was that the walkthrough would confirm the control works.** It
did — but only after finding 1, and **the walkthrough could not have confirmed anything
before it.** The e2e suite was silently incapable of establishing a session.

**This is a deviation from the plan in the only way that matters: the plan assumed a
working harness and there was not one.**

### 2. The plan said to compose for "today" and "after." It composes for two future local dates.

Because the composition is idempotent per local date and the personal-event window is
measured from the composition's own clock, "today" is a trap in both halves. **Two future
dates, cleared before each, is the honest way to get two fresh digests.**

### 3. The walkthrough needed a second account that the seed does not provide.

**`nosched-walkthrough@example.test` is a real account the walkthrough created** — one
that completed onboarding by *advancing* rather than by skipping, so it has no
`DigestPreference`. **No browser flow can produce that state**, and the seed does not
provide it, so the walkthrough makes it.

### 4. `playwright.config.ts` was changed, and that is outside this intent's stated scope.

**The change is one line** — the web server's `--hostname 127.0.0.1` — **and it is
load-bearing for every e2e test in the repository, not just this intent's.** It is
recorded here prominently because a reviewer reading only the intent's diff would
otherwise see an unexplained change to shared tooling.

## Dependencies Added

**None.** The walkthrough uses the seeded accounts, the product's own `reset_sign_in_throttle`,
and the product's own `compose_digest`. **It adds no package and no service.**

## What was walked, and how

**A real browser, against the real stack, against real data.** Chromium at 1440×1000 — the
desktop size the design's locks are stated for.

| Step | What was done | What was seen |
|---|---|---|
| 1 | `make up`, then the API and web dev servers | PostgreSQL and Redis healthy; Django on 8000, Next on 3000 |
| 2 | `make seed-browse` | *"Fitted 65 event(s) for the city's coverage"* |
| 3 | Signed in as `free@browse.example.test` through the real form | The session took; `sessionid` cookie set; `/api/auth/me` → 200 |
| 4 | Opened `/settings/quiet-hours` | **"What's in your Pulse Digest"** link present |
| 5 | Clicked the link | `/settings/digest` loaded |
| 6 | Read the control | `aria-pressed="true"`, text **"Personal events are in your Pulse Digest"** |
| 7 | Read the server's answer | `include_personal_events: true` — **the control and the server agree** |
| 8 | Pressed the control | `aria-pressed="false"`, text **"Personal events are not in your Pulse Digest"**, then **"Saved."** |
| 9 | Read the server's answer again | `include_personal_events: false`; **delivery time and timezone unchanged** |
| 10 | Reloaded the page | The control still reads `false` — **it round-trips** |
| 11 | Pressed it again | `true` restored; the server holds `true` — **it is not write-once** |
| 12 | Composed a digest with a personal event on the agenda | **Slot 1 is the personal event**; `personal_qualifying_count: 1` |
| 13 | Opted out **in the browser** | The server holds `false` |
| 14 | Composed a digest for the next local date | **Slot 1 is not the personal event**; every card is `public`; `personal_qualifying_count: 0` |
| 15 | Signed in as `nosched-walkthrough@example.test` | The control is **disabled**, and reads **"Set your delivery time first."** |

## The trace

### FR-19's opt-out is now traced to a surface a user can reach

**The PRD's testable consequence at `prd.md:605`** — *"A user can opt out of personal events
appearing in the Pulse Digest"* — moves from *satisfied by machinery, unmet by experience*
to **met**. The matrix's row for FR-19 now points at a place a user can reach:

| | Before this intent | After this intent |
|---|---|---|
| The opt-out **exists** | yes — `DigestPreference.include_personal_events`, read by the composition at `digest_composition.py:628` | yes |
| A user can **find** it | **no** — no control, no route, no link | **yes** — `/settings/digest`, linked from the quiet-hours page |
| A user can **press** it | **no** | **yes** — a `<button aria-pressed>`, inline save |
| The press **reaches** the digest | **yes** (by machinery) | **yes** (and now *provably* — the seam test and the walkthrough both assert the composed digest) |
| The matrix's row points at | machinery | **a working surface** |

### The corrections the audit surfaced — recorded, not fixed

**These belong to a separate intent.** Fixing them here would put a corpus-wide
renumbering inside a feature change.

| # | Correction | Why it is not fixed here |
|---|---|---|
| 1 | The matrix **mis-flags A-5 and A-7 as uncited** — both are cited (`EXPERIENCE.md:64,229,1152` and `:1200`) | A matrix fix, not a feature fix |
| 2 | The matrix **misses the A-10 ID collision** — PRD `prd.md:751` defines A-10 as FR-22's formula amendment while `DESIGN.md:349` and `EXPERIENCE.md:294` define it as the Browse route | **A corpus defect.** Two amendments share one ID, so the whole amendment ID space is unreliable for any tool that reads it. Fixing it means renumbering and propagating across four documents and the mockups |
| 3 | **FR-16's remediation points at the wrong row** — `EXPERIENCE.md` row 15 claims FR-13 | A matrix fix, not a feature fix |

## What did not pass, and what happened to it

### Finding 1 — the harness could not sign in, and did so silently — **fixed**

**The web server Playwright started bound to `localhost`.** The browser and the server
ended up on different addresses, the **HMR WebSocket could not be made**, and **React never
hydrated**.

**What that looks like is a trap.** The page still renders — the server sends the HTML — so
the sign-in form still *appears*. Its inputs are controlled React state, so with no React
attached the form has **no `onSubmit` handler**, and the browser falls back to **a native
GET submit**: the URL becomes
`/signin?email=free%40browse.example.test&password=browse-free-local`.

**No session is established. The password is in the query string.** And the failure looks
like a timeout waiting for the URL to leave `/signin`, which reads like a slow app rather
than a broken harness.

**The fix is one line** — the same `--hostname 127.0.0.1` `make web` already uses, so the
server the e2e run talks to is the same server `make dev` starts:

```ts
command: `pnpm dev --hostname 127.0.0.1 --port ${WEB_PORT}`,
```

**And the effect is larger than this intent.** The **pre-existing browse specs failed the
same way** — the e2e suite had been unable to sign in at all. **They pass now.** Finding 2
is not a separate finding; it is finding 1 seen from the other specs.

> **A harness that cannot sign in cannot prove anything about a control behind a sign-in.**
> Everything this walkthrough claims was false until this was fixed.

### Finding 3 — the sign-in throttle made the walkthrough unrepeatable — **fixed**

**Fixed by giving the allowance back** through the product's own `reset_sign_in_throttle`,
in `beforeEach`. **Not by weakening the throttle** — the throttle is doing its job, and a
walkthrough that disabled it would be testing a product that does not exist.

### Finding 4 — the composition's idempotence returned a stale digest — **fixed**

**Fixed by clearing the digests for the days the walkthrough composes for.** The
alternative — composing on a day that happens to be empty — is not a fix, it is a hope.

### Finding 5 — the accessible name is "the Pulse Digest", not "your" — **fixed**

**The walkthrough's own locator was wrong**, not the product. The name is written out in
the spec now, with the reason.

### Finding 6 — a user with no schedule is reachable — **not fixed, and not a defect**

**`advance_step` past the last step completes onboarding without writing a
`DigestPreference`** (`onboarding.py:451`). That is a real route to a state with no
schedule. **The control handles it honestly** — disabled, with *"Set your delivery time
first."* — **so the product is correct.**

**But the state is surprising, and it is worth a follow-up:** a user who walks through all
three onboarding steps and never touches the digest step ends up with **no delivery time
and no timezone at all**, which means they get no digest. **Whether advancing past the
digest step should write a default is a product question, not a test question**, and it is
recorded here rather than decided here.

### Finding 7 — two writers of `include_personal_events` — **not fixed, follow-up**

**The onboarding endpoint writes the flag** (`onboarding.py:370`) **and
`digest_preferences.py:336` writes it too.** The seam test caught this during its mutation
work: a mutation applied to the *second* writer was **not** caught by the seam test, and
had to be re-applied at the first to be caught at all.

**Two writers of one flag is a defect waiting to happen** — they can disagree about what
"leave it alone" means. It is named, not fixed.

### Finding 8 — the corpus corrections — **not fixed, by design**

See **The trace** above.

## Test Coverage

**Seven distinct mutations, each proven to fire against this walkthrough.** The walkthrough
is not a confirmation of existing coverage; it is the first coverage of "the control
*changes what the user receives*".

| # | Mutation | Caught by | What it proves |
|---|---|---|---|
| 1 | `onboarding.py:371` — the write path ignores the flag and writes `True` | **2 tests** | The save really reaches the server |
| 2 | `digest_composition.py:489` — the composition ignores the opt-out gate | test 2 | The digest really honours the flag |
| 3 | `digest_composition.py:681` — the count is not suppressed | test 2 | "Not shown" is not "not known about" |
| 4 | `digest-personal-events.tsx:176` — the body always sends `include_personal_events: true` | **2 tests** | The client sends the flag it means to send |
| 5 | `digest_composition.py:628` — the composition reads the flag as `True` | test 2 | The composition reads the *stored* value |
| 6 | `digest/page.tsx:106` — the control renders a hardcoded `true` | test 1 | The control shows the **server's** answer, not a constant |
| 7 | `quiet-hours/page.tsx:174` — the link points elsewhere | test 1 | The control is **findable** |

**Every mutation was reverted and the working tree verified clean** — `git diff --stat`
shows no mutation residue.

**The full e2e suite is green: 9 passed** — the 6 pre-existing browse specs plus this
intent's 3.

## Ready for Review

**Yes, with two named follow-ups and one caveat a reviewer should read first.**

**The caveat:** this walkthrough found that **the e2e suite could not sign in.** Every
claim in it was false until `playwright.config.ts` was fixed. **A reviewer should treat
the e2e suite's green as new information, not as confirmation of an existing guarantee** —
the browse specs were passing before, and failing for a reason nobody had looked for.

**The thing to check first in the diff** is the `playwright.config.ts` change. It is one
line and it is outside this intent's stated scope, and it changes the behaviour of every
e2e test in the repository. **It is the right change** — it makes the e2e server the same
server `make dev` starts — **and it is the kind of change that deserves an explicit
"yes" rather than a silent merge.**

**And the two follow-ups are named, not fixed:** finding 7 (two writers of the flag) and
finding 6 (advancing past the digest step leaves a user with no schedule).

## How to Verify

1. `export PATH="$HOME/.nvm/versions/node/v24.22.1/bin:$PATH"` — Node 24 is required.
2. `make up`, then `make dev` (or start Django on 8000 and the web server on 3000).
3. `make seed-browse` → *"Fitted 65 event(s) for the city's coverage"*.
4. `cd frontend && npx playwright test e2e/digest-opt-out.spec.ts` → **3 passed**.
5. `cd frontend && npx playwright test` → **9 passed** (the whole e2e suite).
6. `make test-backend` → **6870 passed**.
7. `make test-web` → **2336 passed**.
8. `make client` → **no diff** in `frontend/lib/api/` — the AD-19 contract gate, confirming
   no backend schema changed.
9. **In a browser**: sign in as `free@browse.example.test`, open `/settings/quiet-hours`,
   follow **"What's in your Pulse Digest"**, and press the control. It reads
   **"Personal events are in your Pulse Digest"**, then **"Personal events are not in your
   Pulse Digest"** with a **"Saved."** beneath it.

## Developer Notes

**If you touch the control's copy, the walkthrough's locator will find nothing.** The
accessible name is `"Personal events in the Pulse Digest"` — *the*, not *your* — and the
visible text is a *different* string again. **They are deliberately different**, and
changing one without the other breaks the walkthrough in a way that reads like a
timeout.

**If you touch `playwright.config.ts`, read the `webServer` comment first.** The
`--hostname 127.0.0.1` is not cosmetic. **Remove it and the e2e suite stops signing in**,
quietly, in a way that looks like a slow page.

**The walkthrough's shell-outs are the seam it exists to cross.** The compose goes through
the same service the worker runs (`worker/tasks.py:481`), with an explicit clock, because
AD-11 forbids a request handler from composing a digest. **Do not "simplify" it into an
HTTP call** — the architecture test will fail, and it would be right to.

**The `beforeEach` resets are not test hygiene — they are what makes the walkthrough
repeatable.** Three things are stored facts the walkthrough changes: the flag, the sign-in
throttle, and the digests. **A walkthrough that only works on a fresh database is not a
walkthrough the next person can run.**

---

# The Trace, and What It Closes

**This intent opened because a traceability matrix reported a gap. It closes with the gap
closed and the matrix more truthful than it found it.**

**FR-19's opt-out** moved from *satisfied by machinery, unmet by experience* to **met** —
and the trace now points at a place a user can reach, not at a column in a table.

**The intent's own work items** are recorded in `.specs-fire/state.yaml`, and the run
records what was actually built: four features, one proof, one walkthrough.

**The corrections the audit surfaced** — the A-5 and A-7 mis-flags, the A-10 ID collision,
and FR-16's remediation pointing at the wrong row — **are named as follow-up work and not
fixed here.** That is the correct outcome, and it is worth saying why one more time:

> **The A-10 collision is a corpus defect.** Two different amendments share one ID. That
> makes the whole amendment ID space unreliable for any tool that reads it — including the
> matrix that found the other two corrections. **Fixing it means renumbering and
> propagating across the PRD, DESIGN.md, EXPERIENCE.md and the mockups.** Putting a
> corpus-wide renumbering inside a feature change is exactly the kind of scope bleed that
> makes a matrix stop being trustworthy.

**A matrix that reports a defect and has the defect quietly patched inside an unrelated
intent is worse than one that reports it and leaves it visible.**
