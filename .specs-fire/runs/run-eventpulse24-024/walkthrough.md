---
run: run-eventpulse24-024
work_item: e2e-proof-and-contract-tests
intent: public-pages-and-seo
generated: 2026-11-04
mode: confirm
---

# Implementation Walkthrough: Prove a stranger can get in — and that the proof can fail

## Summary

This is the last item of the run, and it is the only one whose deliverable is a
**proof about the other nine**. Every other item's tests assert a service's own
contract. This one asserts the **end state** — the thing a stranger actually meets —
and, more unusually, it asserts that **the proof could have failed**.

The claim being proven is narrow and checkable: *someone with no account and no cookie
can reach an event, see it in full, and be offered the Save to Pulse CTA — with no
redirect and no sign-in wall at any hop.* Every other item's proof could assume a
session. This one asserts the opposite, **because a sign-in wall that creeps onto a
public page is invisible to every test that logs in first.**

And then the harder half: **a test that cannot fail proves nothing.** Nine mutation
probes plant a real bug in each guarded behaviour, one at a time, and require the
exact suite to go red. Nine out of nine go red.

**That exercise found a vacuous assertion in the proof itself** — a slug compared
against a list of *paths*, which could not have failed whatever the feed did. And the
code review found that the probe harness itself was reporting an unusable suite run as
a catch, and that the contract file's comment stripper ate URLs and regex literals.
Both were fixed, and both fixes were themselves checked.

## Structure Overview

Four suites, one harness, and one rule about what a green result is allowed to mean.

- **`backend/tests/e2e/public_pages_fixtures.py`** — the catalog the proof walks.
  Cities, published events, an `in_review` event, current Event Fit rows, and the
  way to move an event on so a fit row is left stale behind it.
- **`backend/tests/e2e/test_public_pages_proof.py`** — the 34-test backend proof. It
  walks the anonymous crawl path against the real services: city page → event → full
  event and the CTA, with no cookie jar at any step.
- **`backend/tests/e2e/test_public_pages_contract.py`** — the 28-test contract file.
  It asserts on the **source** of the eight public modules, because some properties
  (a read that carries no session at all) are not observable from the outside.
- **`backend/tests/e2e/test_contract_stripper_proof.py`** — the 17-test proof of the
  contract file's own comment stripper. The stripper is load-bearing for every
  assertion that uses it, so it gets proved on itself.
- **`backend/tests/e2e/mutation_probe_public_pages_e2e.py`** — the 9-probe harness.
  It plants a bug, runs the exact suite, and requires a real test failure.
- **`frontend/tests/public-crawl-proof.test.tsx`** — the 24-test frontend crawl proof:
  the hop from the city page to the event page, the JSON-LD in the server-rendered
  markup, and the CTA.

### The flow

```text
  a stranger, no cookie jar
        │
        ▼
  GET /events-in/{city}          ──► the city page lists the event
        │
        ▼
  GET /events/{slug}             ──► 200, no redirect, no wall
        │
        ├─ server-rendered HTML carries the ld+json (JavaScript disabled)
        ├─ the visible state and the eventStatus agree  (AD-12)
        └─ the "Save to Pulse" CTA is present
```

## Key Implementation Details

### 1. "No session" is structural, not a missing step

The obvious way to write this test is to take the existing authed suite and *not log
in*. That is a step a later change can silently restore — someone adds a `login()`
call to a fixture, and the test still passes because the wall is back.

**So the proof uses a client with no cookie jar at all.** It cannot be signed in by
accident. And in the frontend the `next/headers` mock **throws** when `cookies()` is
called, which removes a second possibility: a page that read the cookies and then
chose not to send them would still have opted the route out of static generation and
made the page's content depend on who is asking — and the test would have passed.

The cookie plant makes this measurable: adding `await cookies()` to the public branch
turns **17 of 24** frontend tests red.

### 2. The JSON-LD is asserted with JavaScript disabled

The crawler's actual conditions are **no JavaScript** and **server-rendered HTML**. A
test that renders the page in jsdom with scripts running proves something the crawler
never sees. So the proof parses the `ld+json` script out of the **raw HTML**, parses
it as JSON, and validates it as a Schema.org `Event`.

### 3. Structured data is asserted *together with* the rendered page

A cancelled event's visible state and its `eventStatus` are asserted in the same test
(AD-12), so the two cannot drift. A suite that asserted the JSON-LD alone would pass
while the page said *"cancelled"* and the metadata said *"eventScheduled"*.

### 4. The revalidation round trip does not wait for a timer

This is the intent's central freshness promise, so it gets a dedicated test: change an
event's `status` to cancelled and assert the public page reflects it **immediately**.
The revalidation outbox's broker is a **seam** in `tests/e2e/conftest.py` — a test can
see the signal that was emitted, rather than sleeping and hoping.

### 5. The stale Event Fit is built the way it really happens

The city page drops a stale fit row, and the count is computed separately from the
listing — so a city could **claim to qualify** on a count that includes a fit its own
listing would not show. Both halves get a probe.

The fixture **does not** take an `event_version` override. A helper that could write a
deliberately wrong version describes a row the write path can never produce — and it
would have been a second, wrong way to say the same thing. The proof moves the *event*
on through the real write path and lets the fit fall behind, which is what happens.

### 6. The proof found a vacuous assertion in itself

**The `in_review` URL-feed assertion was vacuous**, and the probe harness is what found
it. The test read:

```python
assert unreviewed.slug not in [item["path"] for item in body["items"]]
```

**The feed carries paths, not slugs** — an event's entry is `/events/{slug}` — so a bare
slug is not in the list *whatever the feed did*. The assertion could not have failed.
The probe that leaked the `in_review` event into the feed went green, which is the
signal that the assertion was measuring nothing.

The fix is one line:

```python
assert f"/events/{unreviewed.slug}" not in [item["path"] for item in body["items"]]
```

**This is the whole argument for the probe harness.** A proof that is *shown* to be able
to fail finds its own vacuous assertions; a proof that is merely green does not.

### 7. The harness reported an unusable suite run as a catch

The code review found that `run_probe` decided its outcome from the exit code alone:

```python
if code == 0:
    return ProbeResult(probe, "fail", "the suite still passed")
return ProbeResult(probe, "ok", _tail(output))
```

**That is exactly the false green the harness's own second rule exists to prevent**,
and the harness was applying the rule to the mutations it planted while exempting
itself from it. A probe whose planted bug made the suite *uncollectable* — a missing
file, an import that no longer resolves, a `pytest` invocation that found no tests —
would have been reported as `OK ... caught`, and the walkthrough would have quoted it
as proof.

**This was not hypothetical.** While the probes were running, a concurrent `pytest`
invocation held the shared test database, and one probe came back:

```
FAIL  an in_review event is addressable at its own slug -- the suite did not fail a test — it could not run
```

— because the stricter check was already in place. **Under the old code that run would
have been reported as `OK ... caught`.**

**The fix** is `_is_a_test_failure(code, output)`, which reads the exit code *and* the
output. pytest's exit codes are specific (`1` is *tests failed*, `5` is *no tests
collected*), so only `1` counts and the output must show a failure summary rather than
an error summary; vitest's exit codes are not specific, so the output carries the
answer. **A suite that ran no tests cannot have caught anything**, so it is now a
`fail`.

The new check was itself checked, against eight synthetic cases:

```
PASS pytest failure -> True expected True
PASS pytest collection error -> False expected False
PASS pytest syntax error -> False expected False
PASS pytest no tests collected -> False expected False
PASS pytest usage error -> False expected False
PASS vitest failure -> True expected True
PASS vitest load error -> False expected False
PASS vitest passed -> False expected False
```

### 8. The comment stripper ate URLs and regex literals

The contract file asserts on **source text**, with the comments removed — and the
removal was a pair of regexes:

```python
return re.sub(r"/\*[\s\S]*?\*/", "", re.sub(r"//[^\n]*", "", text))
```

**A `//` inside a string literal is not a comment.** `"https://eventpulse24.test"`
becomes `"https:"`. **A `//` inside a regex literal is not a comment either** —
`/^https?:\/\//` holds `//` where a line comment starts, so the scanner truncates the
file there, and every assertion made on the truncated file is an assertion about the
file's first half.

**And this was not hypothetical.** `frontend/app/events/[id]/page.tsx` — one of the
eight modules the contract file asserts on — carries a regex literal. The *current*
stripper happens to survive that particular literal, but only because that literal has
no `//` in its body. One more character and the assertions on that file would have
been assertions about its first half.

**The fix** is a **string- and regex-aware scanner** that tracks whether it is inside
a string or a regex literal, recognises a regex only where one can appear (after `(`,
`=`, `,`, `:`, `[`, `!`, `&`, `|`, `?`, `{`, `;` or a keyword — a `/` after an
identifier is a **division**), and survives a regex's character class and flags.

**And the scanner is now proved, on itself**, by the 17-test stripper proof — a
two-sided proof: it removes what it must (including a comment *naming* a forbidden
call, which is the exact reason the stripper exists), it removes nothing else (a URL
in a string survives whole; a regex literal holding `//` survives whole; a division is
not mistaken for a regex), and it **reaches the end of every asserted file** — checked
by the file's braces still balancing, which is *non-vacuous in both directions*.

**The proof was shown able to fail.** Planting the old regex back inside
`strip_comments` — the implementation, not the caller — turned **two** of the
seventeen tests red:

```
FAILED ...::test_a_url_in_a_string_is_not_mistaken_for_a_comment
FAILED ...::test_a_regex_literal_whose_body_holds_two_slashes_survives
2 failed, 15 passed
```

**A note on the first attempt at this plant.** The first version replaced
`source_of`'s *body*, and it did **not** go red — replacing the caller left
`strip_comments` intact, and the synthetic tests exercised `strip_comments` directly.
**The plant has to reach the code that does the work.** The second plant went into the
function, and the proof went red.

## Security Considerations

| Concern | Approach |
|---------|----------|
| A sign-in wall on a public page | Asserted structurally: the backend proof uses a client with no cookie jar, and the frontend's `next/headers` mock **throws** on `cookies()`, so the public branch cannot read a session even by accident. |
| The public reads leaking the visitor's session | Asserted on the **source** — the three public read modules must contain no `sessionHeaders` call and no `cookies()` call — and mutation-probed by a plant that forwards the visitor's cookies (caught, 3 tests red). |
| `in_review` events leaking to the public | Asserted from all three directions (its own slug, the city page, the sitemap), with one probe per mechanism, because each is a separate line of code that could be broken independently. |
| The authed surfaces regressing | Asserted unbroken: `/events/{uuid}` and `/events/{uuid}/reminders` still work, proving the branching route did not regress the signed-in detail screen. |
| `robots.ts` leaking the authed routes | Asserted: the authed routes are disallowed and the public ones are allowed. |

## Performance Considerations

| Requirement | Implementation |
|-------------|----------------|
| The proof must not wait on a timer | The revalidation outbox's broker is a **seam**, so the round trip is asserted on the emitted signal rather than on a sleep. |
| The probe harness must not be fooled by an unrelated failure | Each probe runs one named suite and nothing else, so a probe cannot pass for the wrong reason via an unrelated test going red. |
| The proof must not be slow | 34 backend tests in ~5s; 24 frontend tests in ~2s. The whole backend suite is 5265 tests in ~450s. |

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| How to make "no session" structural rather than incidental | A separate proof suite with its own cookie-less HTTP client, rather than omitting a login step from the existing authed suite. | Omitting a login step is a step a later change can silently restore. A client with no cookie jar at all cannot be signed in by accident, so the assertion survives refactoring. |
| How to prove each assertion can fail | Plant a CALL — not an import — in each guarded behaviour, run the exact suite named, and require a real test failure rather than any non-zero exit code. | A suite that could not be collected is a false green: it did not catch the bug, it failed to run. The harness reads the exit code and the output, and a run that collected no tests is reported as a failure to catch. |
| How to assert on source text without the comments | A string- and regex-aware scanner rather than a pair of regexes. | The regex stripper ate the tail of any URL and truncated a file at the first regex literal whose body holds a `//`. One of the eight asserted modules carries a regex literal, so this was a live trap rather than a theoretical one. |
| Whether to build the stale EventFit row by writing a wrong version | Build it the way it really happens — move the event on through the write path, and let the fit fall behind. | A helper that could write a deliberately wrong `event_version` describes a row the write path can never produce, and it would have been a second, wrong way to say the same thing. |
| How to assert the JSON-LD is crawlable | Assert against the server-rendered markup with JavaScript disabled, parsing the `ld+json` script out of the HTML and validating it as a Schema.org `Event`. | The crawler's actual conditions are no JavaScript and server-rendered HTML. A test that renders the page in jsdom with scripts running would prove something the crawler never sees. |
| Whether to re-run the probe harness after the review's fix | Yes — all nine, under the stricter rule. | The harness's own rule changed, so the numbers it produces had to be re-earned. A probe log quoted from before the fix would not have been evidence for the fix. |

## Deviations from Plan

**The plan called for three suites; the implementation has four.** The fourth is the
stripper's own proof (`test_contract_stripper_proof.py`, 17 tests), and it exists
because the code review found the stripper's two failure modes. The review report
records the change honestly: **the two strippers produce the same output on all eight
asserted modules today**, so this is *not* repairing a live assertion failure — it is
removing a trap before something walks into it, and the proof's own docstring says so
so a future reader does not mistake it for a fix of something that was broken.

**The probe harness's outcome rule was tightened** from "any non-zero exit" to "a real
test failure". This was not in the plan; it came out of the code review, which found
that the harness was applying its own false-green rule to the mutations it planted
while exempting itself from it.

## Dependencies Added

| Package | Why Needed |
|---------|------------|
| (none) | No new dependency. The proof uses `pytest`, `pytest-django` and `vitest`, all already present. |

## How to Verify

1. **Run the backend proof, the contract file and the stripper proof**

   ```bash
   cd backend && DJANGO_DB_ROLE=owner uv run pytest \
     tests/e2e/test_public_pages_proof.py \
     tests/e2e/test_public_pages_contract.py \
     tests/e2e/test_contract_stripper_proof.py -q
   ```

   Expected: **79 passed**.

2. **Run the frontend crawl proof**

   ```bash
   export PATH=$HOME/.nvm/versions/node/v24.22.1/bin:$PATH
   npx vitest run tests/public-crawl-proof.test.tsx
   ```

   Expected: **24 passed**.

3. **Run the mutation probes — the heart of this item**

   ```bash
   cd backend && DJANGO_DB_ROLE=owner uv run python tests/e2e/mutation_probe_public_pages_e2e.py
   ```

   Expected:

   ```
   OK    a stale Event Fit is served instead of skipped -- caught (1 failed, 33 passed in 4.80s)
   OK    a stale Event Fit is counted towards the city's threshold -- caught (1 failed, 33 passed in 4.74s)
   OK    an in_review event is addressable at its own slug -- caught (2 failed, 32 passed in 4.92s)
   OK    an in_review event leaks into the URL feed -- caught (1 failed, 33 passed in 5.01s)
   OK    an in_review event leaks onto the city page -- caught (1 failed, 33 passed in 4.84s)
   OK    the revalidation signal drops the city's path -- caught (1 failed, 33 passed in 4.86s)
   OK    the structured data drops the cancelled event's status -- caught (2 failed, 32 passed in 5.05s)
   OK    a public read forwards the visitor's cookies -- caught (3 failed, 25 passed in 2.17s)
   OK    the JSON-LD is not in the server-rendered markup -- caught (Tests  5 failed | 19 passed (24))

   All 9 public-pages probes were caught by the suite.
   ```

4. **Reproduce the two frontend plants by hand**

   In `frontend/components/public-event/public-event-page.tsx`, replace
   `<Link href="/signup">Save to Pulse →</Link>` with `<button>`. Re-run step 2.
   Expected: **exactly one** test goes red — and only once the assertion is scoped to
   the element carrying `data-public-save-cta`. The page carries a *second* `/signup`
   link (the closing invitation), so a bare substring search is satisfied by the wrong
   link.

   Then add `await cookies()` to the public branch. Re-run step 2.
   Expected: **17 of 24** go red, because the `next/headers` mock throws.

5. **Reproduce the stripper proof going red**

   In `backend/tests/e2e/test_public_pages_contract.py`, replace the body of
   `strip_comments` with
   `re.sub(r"/\*[\s\S]*?\*/", "", re.sub(r"//[^\n]*", "", text))`. Re-run step 1.
   Expected: **2 failed, 15 passed** — the URL test and the `//`-in-a-regex test.

6. **Check the whole project is green**

   ```bash
   make lint-backend && make lint-web
   make coverage-backend
   cd frontend && npx vitest run
   ```

   Expected: backend **5265 passed**, **99.05%** coverage with `domain/` at **100%**;
   frontend **1577 passed** across **99 files**; **19 import contracts kept, 0 broken**.

7. **Check the generated client is in sync** — the drifted client fails the build

   ```bash
   make openapi && make client && git diff --exit-code -- frontend/lib/api/
   ```

   Expected: **no diff**. (This is the CI `contract` job.)

## Test Coverage

- Tests added: **103** (34 backend proof + 28 contract + 17 stripper proof + 24 frontend crawl proof)
- Coverage: **99.05%** overall, `domain/` at **100%**
- Status: **passing** — backend 5265, frontend 1577; all 9 mutation probes caught

## Ready for Review

- [x] All acceptance criteria met
- [x] Tests passing
- [x] No critical issues
- [x] Developer notes captured

## Developer Notes

**The probe harness is the point of this item.** Everything else in the run asserts
that the system works; this asserts that the assertions *can fail*. If you add a
behaviour to the public path, the question to ask is not *"is it tested?"* but
**"what would have to be true for my test to go red?"** — and if the answer is
"nothing", the test is not a test.

**A mutation must produce a wrong answer, not a crash.** A `SyntaxError` is a false
green: the suite "caught" it because it could not be collected. This is why the
JSON-LD probe needs two edits (the `hidden` attribute *and* the emptied `__html`) —
a half-planted bug that does not compile is caught by the interpreter, not by the rule.

**The plant has to reach the code that does the work.** Twice in this item, a plant
missed: once because it replaced a *caller* while the tests exercised the function,
and once because a concurrent `pytest` run held the shared test database and the
suite could not run at all. The second is now a **reported failure** rather than a
silent catch — which is how it was found.

**One pytest run at a time.** The backend suite shares one test database. Two
concurrent runs collide, and the collision shows up as a spurious failure in one of
them.

**Node 24 is required.** The shell's default `PATH` resolves an older Node than the
project requires; with `~/.nvm/versions/node/v24.22.1/bin` prepended, everything runs.

**The FIRE tooling had the same defect this item's proof was looking for.** The
completion path marked an intent's work items completed and promoted the intent's
*brief*, but never the intent's own `status` in `state.yaml` — so an intent whose
every work item was done still read `in_progress`, and the state file did not tell
the truth. Seven intents in this repo had needed a manual `chore(fire)` commit to
paper over it. **The fix is in `complete-run.cjs`**, and the repair path is
`syncIntentStatuses()`, which derives the expected status from the work items rather
than asserting it, so it cannot drift from them.

**A note on the run's own final state.** This item's completion promoted the
`public-pages-and-seo` intent to `completed`, so all eight intents in the project now
read `completed`, all 82 work items are `completed`, and there are no active runs.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-024*
