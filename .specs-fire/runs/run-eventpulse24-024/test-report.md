---
run: run-eventpulse24-024
work_item: e2e-proof-and-contract-tests
intent: public-pages-and-seo
generated: 2026-11-04
status: passed
---

# Test Report: Prove a stranger can get in — and that the proof can fail

## Summary

| Category | Passed | Failed | Skipped | Coverage |
|---|---|---|---|---|
| The backend proof (`tests/e2e/test_public_pages_proof.py`) | 34 | 0 | 0 | — |
| The contract file (`tests/e2e/test_public_pages_contract.py`) | 28 | 0 | 0 | — |
| The stripper's own proof (`tests/e2e/test_contract_stripper_proof.py`) | 17 | 0 | 0 | — |
| The frontend crawl proof (`tests/public-crawl-proof.test.tsx`) | 24 | 0 | 0 | — |
| **The four new suites together** | **103** | **0** | **0** | — |
| **Whole frontend suite** | **1577** | **0** | **0** | **99 files, all green** |
| **Whole backend suite** | **5265** | **0** | **0** | **99.05%** |

**The frontend suite stood at 1553 before this work item and stands at 1577 after it.**
The difference is **24** — the new crawl proof, and nothing else.

**The backend suite stood at 5186 before this work item and stands at 5265 after it.**
The difference is **79** — the 34 backend proof tests, the 28 contract tests and the 17
stripper-proof tests, and nothing else.

**Lint and types**: `npx eslint .` clean; `npx next typegen && npx tsc --noEmit` clean;
`npx prettier --check .` clean; `uv run ruff check .` clean; `uv run ruff format --check .`
clean; `uv run lint-imports` clean (**19 contracts kept, 0 broken**).

**Node 24 is required.** The shell's default `PATH` resolves an older Node than the
project requires; with `~/.nvm/versions/node/v24.22.1/bin` prepended, everything runs.

**The numbers above are the post-review ones.** The code review added a fourth new
suite — a 17-test proof of the contract file's comment stripper — and tightened the
probe harness. Both are described below and in the review report.

---

## The part of this item that is different from every other item in the run

Every other work item's report ends with *"all tests passing"*. That is the wrong claim
for this one. **A test that cannot fail proves nothing** — and the acceptance criteria
say so in their own words: *"Each assertion is shown to fail when its behaviour is
removed, recorded in the walkthrough."*

So the report is not *"86 tests pass"*. The report is: **86 tests pass, and each of
the behaviours they guard was removed on purpose and the suite went red.**

### The mutation probes

`backend/tests/e2e/mutation_probe_public_pages_e2e.py` plants **one real bug** in the
implementation, runs the **exact suite** that is supposed to catch it, and requires
that at least one test fails. Then it puts the file back.

**The output, verbatim:**

```
OK    a stale Event Fit is served instead of skipped -- caught (1 failed, 33 passed in 4.29s)
OK    a stale Event Fit is counted towards the city's threshold -- caught (1 failed, 33 passed in 4.28s)
OK    an in_review event is addressable at its own slug -- caught (2 failed, 32 passed in 4.38s)
OK    an in_review event leaks into the URL feed -- caught (1 failed, 33 passed in 4.32s)
OK    an in_review event leaks onto the city page -- caught (1 failed, 33 passed in 4.33s)
OK    the revalidation signal drops the city's path -- caught (1 failed, 33 passed in 4.30s)
OK    the structured data drops the cancelled event's status -- caught (2 failed, 32 passed in 4.27s)
OK    a public read forwards the visitor's cookies -- caught (3 failed, 25 passed in 1.79s)
OK    the JSON-LD is not in the server-rendered markup -- caught (Tests  5 failed | 19 passed (24))

All 9 public-pages probes were caught by the suite.
```

**Three rules make that output mean something**, and each is inherited from the
delivery intent's proof:

1. **Plant a CALL, not an import.** An imported-but-uncalled function computes nothing,
   so the probe would "pass" while proving nothing.
2. **The mutation must still parse and run.** A `SyntaxError` is a *false green* — the
   suite "caught" it only because it could not be collected. So every probe still
   produces a **wrong answer**, not a crash. This is why the JSON-LD probe needs two
   edits (the `hidden` attribute *and* the emptied `__html`): a half-planted bug that
   does not compile is caught by the interpreter, not by the rule.
3. **Never plant a bug in dead code.** A probe that mutates a branch the scenario never
   runs proves nothing.

**And a fourth rule this item added: name the exact suite.** A probe that mutated the
implementation and ran the *whole* backend suite would pass for the wrong reason — some
unrelated test would go red, and the probe would look like it proved the rule when it
proved nothing about *this* rule. Each probe names one file:
`tests/e2e/test_public_pages_proof.py`, `tests/e2e/test_public_pages_contract.py`, or
`tests/public-crawl-proof.test.tsx`.

**The probes come in pairs where the promise has two halves.** The `in_review`
invisibility is carried by three separate mechanisms — the slug read refuses it, the
city listing filters it, the feed filters it — and **one probe per mechanism**, because
each is a separate line of code that could be broken independently. A single probe on
the slug read would prove nothing about the feed. The same applies to the stale fit:
the *listing* and the *count* are computed by two different implementations of the same
rule, and the count's failure is the worse one — a city would **claim to qualify** on a
count that includes a fit its own listing would not show.

### The two frontend plants, by hand

The frontend has no harness for this, so the plants were done directly and are recorded
here so a reader can repeat them.

- **The CTA plant.** `<Link href="/signup">Save to Pulse →</Link>` → `<button>`. Exactly
  **one** test went red — after the assertion was first scoped to the CTA's own block.
  **The first attempt did not go red at all**, and that is the more interesting fact: the
  page carries a *second* `/signup` link (the closing invitation at the foot), so a bare
  substring search was satisfied by the wrong link. **The assertion was scoped to the
  element carrying `data-public-save-cta`**, and only then did the plant go red.
- **The cookie plant.** An `await cookies()` in the public branch. **17 of 24** frontend
  tests went red — because the mock for `next/headers` *throws* when `cookies()` is
  called. That is the point: the anonymity is **structural**, not a convention. The
  cookie jar is not merely empty on the public path; it is **unreachable**.

### The bug the probes found in the proof itself

**The `in_review` URL-feed assertion was vacuous**, and the probe harness is what found
it. The test read:

```python
assert unreviewed.slug not in [item["path"] for item in body["items"]]
```

**The feed carries paths, not slugs** — an event's entry is `/events/{slug}` — so a bare
slug is not in the list *whatever the feed did*. The assertion could not have failed.
The probe that leaked the `in_review` event into the feed went green, which is the
signal that the assertion was measuring nothing.

**The fix** is one line:

```python
assert f"/events/{unreviewed.slug}" not in [item["path"] for item in body["items"]]
```

**This is the whole argument for the probe harness.** A proof that is *shown* to be able
to fail finds its own vacuous assertions; a proof that is merely green does not.

### And the harness itself was reviewed — and it had the same defect

**The code review found that the probe harness was reporting an unusable suite run as
a catch.** Its outcome was decided by the exit code alone, so a suite that could not be
collected — or that collected no tests at all — was reported as *"the bug was caught"*.

**That is exactly the false green the harness's own second rule exists to prevent**, and
the harness was applying the rule to the mutations it planted while exempting itself
from it. **A probe whose planted bug made the suite uncollectable would have been
reported as `OK ... caught`, and the walkthrough would have quoted it as proof.**

**It was not hypothetical.** While the probes were running, a concurrent `pytest` run
held the shared test database, and one probe came back *"the suite did not fail a test —
it could not run"*. **Under the old code that run would have been reported as a catch.**

**The fix** is `_is_a_test_failure(code, output)`: pytest's exit codes are specific
(`1` is *tests failed*, `5` is *no tests collected*), so only `1` counts and the
output must show a failure summary rather than an error summary; and vitest's exit
codes are not, so the output carries the answer.

**All nine probes still pass under the stricter rule**, and the run log quoted above is
the post-fix output.

### The stripper's own proof — a fourth suite

**The review also found that the contract file's comment stripper ate the tail of any
URL and any regex literal.** `re.sub(r"//[^\n]*", "", text)` truncates
`"https://eventpulse24.test"` to `"https:"`, and truncates a file at the first regex
literal whose body holds a `//`. **No current assertion was broken** — none of the
eight asserted modules holds a URL string — but `app/events/[id]/page.tsx` *does*
carry a regex literal, so the helper was a live trap.

**The fix** is a string- and regex-aware scanner, and the scanner is now proved on
itself** by `backend/tests/e2e/test_contract_stripper_proof.py` — 17 tests, two-sided:
it removes what it must (a comment naming a forbidden call included) and removes
nothing else (a URL, a real call, a regex literal with `//` in its body, a character
class, a division, the flags). **And it reaches the end of every asserted file** — the
check is that the file's braces still balance, which is non-vacuous in both
directions.

**That proof was itself shown able to fail.** Planting the old regex back inside
`strip_comments` turned **two** of the seventeen tests red.

---

## Acceptance Criteria Validation

- ✅ **The anonymous crawl path, with no cookie jar at any step: land on
  `/events-in-{city}` → open an event → see the full event and the "Save to Pulse" CTA.
  No redirect, no wall, at any hop.**
  The frontend crawl proof (`frontend/tests/public-crawl-proof.test.tsx`) renders both
  pages in a **node** environment with `next/headers` mocked so that **both `cookies()`
  and `headers()` throw**. A public read that reached for the cookie jar would not
  return a page — it would fail the test. The city page renders, links to the event, and
  the event page renders with the description, the status line, and the CTA.
  **The backend half asserts the same thing from the other side**: the city response
  **sets no cookie** and **does not vary by a session cookie**, and the event page's
  response sets no cookie either.
- ✅ **The JSON-LD is in the server-rendered HTML and parses as a valid Schema.org
  `Event`, asserted with JavaScript disabled.**
  The crawl proof runs in the **node** environment — there is no DOM and no
  `ReactDOM` — and reads the JSON-LD out of the **markup string** with a regex, then
  `JSON.parse`s it and asserts `@type: "Event"` and the name it carries. A crawler reads
  bytes, not a hydrated tree, so the assertion is made against bytes.
  **And the JSON-LD is asserted to be the payload's own object**, not a second one the
  page rebuilt — otherwise the structured data and the rendered page could drift, which
  is the next criterion.
- ✅ **Structured data agrees with the rendered page: a cancelled event's visible state
  and its `eventStatus` are asserted together (AD-12).**
  One test asserts the *visible* line ("Cancelled") and the *structured*
  `eventStatus` in the same assertion, and a second asserts the mirror image: a
  **scheduled** event's structured data says **nothing** about the lifecycle, because
  `SCHEMA_ORG_EVENT_STATUS` has no entry for it and the payload must not invent one.
  The backend proof asserts the same pairing at the API boundary.
- ✅ **The revalidation round trip: change an event's `status` to cancelled → the public
  page reflects it without waiting for a timer.**
  The proof calls the **real write path** — `apply_lifecycle_change` with a faithful
  `IncomingEvent` — and asserts that **one** `RevalidationRequest` is written, that it
  names **both** the event's page and the city's, that it carries the **newest** version,
  that it is **open**, and that the enqueue is offered to the broker **after the commit**.
  **No timer is involved anywhere** — the signal is a row, written synchronously with
  the change, and the proof reads it directly.
- ✅ **A past event still resolves — the case `catalog.get_event` deliberately refuses —
  asserted as a real 200 with content.**
  Three tests: the public page answers **200** for the past event; it answers **with
  content** (the title is in the body — a 200 with an empty body would satisfy a
  status-only assertion and prove nothing); and **the same event is a 404 by id**,
  which is the deliberate refusal the criterion names.
- ✅ **A stale `EventFit` row is absent from the city page, not rendered wrong (AD-10).**
  Three tests: the stale fit's event is **not listed**; the stale fit is **not counted**
  towards the threshold; and it is **absent rather than wrong** — the card is not
  rendered with a stale score. The staleness rule is `fit.event_version ==
  event.event_version`, and the fixture makes a stale row by bumping the event's
  version **through the write path**, which is how it really happens.
- ✅ **`in_review` is invisible from every direction: not at its slug, not on a city
  page, not in the sitemap.**
  Five tests. The slug read **raises a 404, not a 403** — and one test asserts *that
  specifically*, because a 403 would **confirm that the event exists**. The city page
  does not list it. The URL feed does not carry it. And an `in_review` event **does not
  make a city published** — the threshold is a count of *public* fits, so a city of
  unreviewed events stays unpublished.
- ✅ **The sitemap contains no URL that 404s — every entry is fetched and asserted.**
  Four tests, and the shape matters: **every** event path in the feed is fetched and
  asserted to resolve; **every** city path likewise; the feed **carries** the city page
  of a qualifying city; and the feed **does not carry** a city below the threshold. The
  third and fourth are the pair that stops the first two from passing vacuously — a
  feed that carried nothing would make "every URL resolves" true and prove nothing.
- ✅ **`robots.ts` disallows the authed routes and allows the public ones.**
  Asserted in `frontend/tests/sitemap-robots.test.ts` (from the `sitemap-and-robots`
  work item) and **re-asserted in the contract file** — the contract file asserts that
  the public branches carry **no** `noindex`, that the Detail Screen's noindex sits
  **inside the detail branch**, and that the public branches carry a **canonical URL**.
- ✅ **The existing authed surfaces are unbroken: `/events/{uuid}` and
  `/events/{uuid}/reminders` still work.**
  The backend proof asserts the detail endpoint **still answers for a public event** and
  **still refuses a started event**. The crawl proof asserts the route **reads the
  detail endpoint for a UUID, and not the public one** — and reads it **even though the
  public one would answer**, which is the branch the whole design turns on.
- ✅ **Contract tests for the new public endpoints, and the regenerated client is in sync
  (AD-19) — a drifted client fails the build.**
  `tests/e2e/test_public_pages_contract.py` asserts the **committed** `openapi.json`
  equals the **live** API schema; that the document **names** the three public
  endpoints; and that each public endpoint declares **both** a 200 and a 404 — the 404
  is part of the contract, because the frontend's three answers (`found` /
  `not-found` / `unavailable`) are built on that distinction.
  **The generated client is regenerated rather than compared to a second copy.** The
  test runs the exact command `make client` runs — `pnpm --dir frontend exec
  openapi-typescript lib/api/openapi.json --output lib/api/schema.ts` — and compares
  the result to what is committed. **The committed file is restored in a `finally`**, so
  the check is a **measurement and not a rewrite** — and a drifting repository stays
  drifting until somebody runs `make client` on purpose.
  **This check was itself mutation-tested.** A planted drift was appended to
  `frontend/lib/api/schema.ts`; the test failed with *"The generated client has
  drifted"*; the file was restored. **A test that was silently skipping would have
  looked exactly like a passing one**, so it was not left on trust.
- ✅ **Each assertion is shown to fail when its behaviour is removed, recorded in the
  walkthrough.**
  Nine mutation probes, all caught — output above. Two frontend plants by hand, both
  red — described above. **One vacuous assertion found and fixed** by the harness.

---

## Tests Written

### The backend proof — `backend/tests/e2e/test_public_pages_proof.py` (34 tests)

Nine groups, one per promise the intent makes.

| Group | Tests | What it pins down |
|---|---|---|
| `TestTheCityLanding` | 5 | A stranger reaches the city page; it lists the qualifying events; it is published *because* six qualify; the response sets no cookie; the response does not vary by a session cookie |
| `TestTheEventPage` | 5 | A stranger reaches the event page; it carries the facts a reader needs; it carries the structured data a crawler reads; it sets no cookie |
| `TestTheStructuredDataAgreesWithThePage` | 3 | A cancelled event says so in its structured data; a scheduled event says so too (by saying nothing); a cancelled event still has a page |
| `TestAPastEventStillResolves` | 3 | The past event answers a real 200; with content; and is a 404 by id |
| `TestAStaleFitIsAbsent` | 3 | The stale fit is not listed, not counted, and absent rather than wrong |
| `TestAnUnreviewedEventIsInvisible` | 5 | Not at its slug; a 404 that does not confirm it exists; not on the city page; not in the feed; and it does not make a city published |
| `TestTheRevalidationRoundTrip` | 5 | One request written; both paths named; the newest version carried; offered to the broker after the commit; open when written |
| `TestTheSitemapCarriesNoDeadURL` | 4 | Every event path resolves; every city path resolves; a qualifying city is carried; a sub-threshold city is not |
| `TestTheAuthedSurfacesAreUnbroken` | 2 | The detail endpoint still answers; still refuses a started event |

**The fixture is a shared root, and that is deliberate.**
`make_published_city()` builds a city with **six** current fits — FR-27's threshold is
`> 5`, so five does not qualify and six does. The crawl's event is **one of those six**
(`events[0]`), not an extra one, because the city page's listing is built from the
Event Fit rows: an event with no fit is not on the page, and the proof's first hop is
*"the city page lists the event the crawl then opens"*. **One shared root means the
count is the same number everywhere** — the threshold, the listing, and the crawl all
agree, and no assertion depends on which fixtures a test happens to request.

**The `IncomingEvent` builder is faithful, and that was a real trap.**
`apply_lifecycle_change` does `rows.update(**incoming.columns(), …)` — a **wholesale
write**. The repository's shared `incoming()` helper defaults `venue_id: None` and a
fixed `start_utc`, so using it for a lifecycle change would have **erased the event's
venue** — and with it the city's identity, which is exactly what the revalidation
signal reads to compute the city's path. The proof builds its own
`incoming_for(event, **overrides)`, which starts from the event's own columns and
overrides only what the change is about.

### The contract file — `backend/tests/e2e/test_public_pages_contract.py` (28 tests)

Seven groups, each a property **no single request can reveal**.

| Group | Tests | What it pins down |
|---|---|---|
| `TestTheCommittedContractMatchesTheLiveApi` | 3 | The committed document equals the live schema; it names the three public endpoints; each declares a 200 **and** a 404 |
| `TestTheGeneratedClientIsInSync` | 1 | The committed TypeScript is what `openapi-typescript` produces **today** — regenerated, then restored |
| `TestTheImportContractsHold` | 3 | `lint-imports` passes; there are **nineteen** contracts (the count is itself a contract); the catalog cannot reach another app's models |
| `TestThePublicReadsCarryNoSession` | 12 | For each of the three public reads: no `sessionHeaders`, no `getSession`, no `cookies(`, no `headers:` at all, no `@/lib/session` import, no `next/headers` import |
| `TestTheAuthedReadsStillCarryASession` | 2 | The two authed reads **still** forward a session — so the public rule cannot be satisfied by deletion |
| `TestThePublicMetadataIsIndexable` | 3 | Neither public branch carries a noindex; the Detail Screen's noindex sits inside the detail branch; both public branches carry a canonical URL |
| `TestThePublicReadsAreCachedUnderTheirOwnPath` | 4 | The event read is tagged with the event path; the city read with the city's; the two path builders match the backend's conventions; the revalidation handler clears both caches |

**The comments are stripped before the source is asserted on.** The public read's own
docstring says *"there is no `sessionHeaders()` call here, and there must never be
one"* — so a naive substring search would find `sessionHeaders` in a file that has no
such call, and the assertion would be measuring **the documentation rather than the
code**.

**"No session" is asserted on the module, not on a request.** A request-level assertion
cannot see a call that reads a session and then ignores it — and a session read that is
*ignored* is exactly the failure that rots quietly, because every test that logs in
first still passes.

### The stripper's own proof — `backend/tests/e2e/test_contract_stripper_proof.py` (17 tests)

The contract file asserts on **source text**, with the comments removed — so the
stripper is load-bearing: if it stopped removing comments, the assertions would start
measuring the *documentation* (and this codebase's comments deliberately name the
forbidden things); and if it removed too much, it would take a real call with it and
the assertion would pass for the wrong reason.

| Group | Tests | What it pins down |
|---|---|---|
| `TestTheStripperRemovesWhatItMust` | 4 | Line comments, block comments, multi-line block comments, and a comment naming a forbidden call — all removed |
| `TestTheStripperRemovesNothingElse` | 6 | A URL in a string survives; a real call survives; a regex literal survives; a regex with `//` in its body survives; a character class survives; a division is not a regex; the flags survive |
| `TestTheStripperLeavesTheAssertedFilesIntact` | 7 | Every asserted file keeps its code; no file still carries a comment marker; the stripper reaches the end of every file (braces balance); the public reads still read as having no session; the authed reads still read as having one |

### The frontend crawl proof — `frontend/tests/public-crawl-proof.test.tsx` (24 tests)

Six groups, rendered through the **real** server components with the reads mocked.

| Group | Tests | What it pins down |
|---|---|---|
| the first hop — the city landing | 5 | Renders server-side with no cookie jar to open; links to the event the crawl opens next; reads the city's own page and nothing else; never opened the cookie jar; never asked who the visitor is |
| the second hop — the event page | 7 | Renders server-side; shows the description; shows the CTA; shows the status **only when there is one to show**; the CTA points at sign-up as a plain link; never opened the cookie jar; never asked who the visitor is; never read the signed-in surface |
| the JSON-LD, in the crawler's own bytes | 4 | It is in the server-rendered markup; it parses as a Schema.org `Event`; it carries the offer the backend projected; it is the payload's own object |
| the visible page and the structured data agree | 2 | Cancelled: the visible line and the `eventStatus`, asserted together; Scheduled: the visible page says nothing and the structured data agrees |
| the crawl's failure modes | 3 | A real 404 for an unknown slug; "the API could not be reached" rather than pretending it does not exist; a superseded event's reader is sent to the replacement |
| the authed surfaces still branch | 2 | A UUID reads the detail endpoint and not the public one; and reads it **even though the public one would answer** |

**The mock for `next/headers` throws on both `cookies()` and `headers()`.** So the
anonymity is not "the test did not log in" — it is "the door is not there".

---

## Coverage Details

Frontend coverage is not measurable in this repository — `@vitest/coverage-v8` is not a
dependency, and adding it is outside this work item's scope.

Backend coverage was measured over the whole suite:

| Metric | Value |
|---|---|
| Total statements | 10,581 |
| Total coverage | **99.05%** |
| Gate | `pytest --cov` requires 80% overall; `coverage report --include='domain/*' --fail-under=100` requires 100% for `domain/` |
| Result | Both gates met — `domain/` is **100%** (904 statements, 0 missed) |

**The `domain/` gate matters more than usual here.** `domain/revalidation.py` and
`domain/schema_org.py` — the two modules that decide *which paths a change makes
stale* and *what the structured data says* — are pure functions with no I/O, so they
are fully covered by construction, and the gate proves it.

---

## Issues Found

| Issue | Severity | Status |
|---|---|---|
| **The `in_review` URL-feed assertion was vacuous** — it compared a bare slug against a list of *paths*, so it could not have failed whatever the feed did | **Severe** | **Fixed.** `assert f"/events/{unreviewed.slug}" not in [...]`. Found by the mutation probe, which is the only thing that could find it. |
| **The probe harness counted an unusable suite run as a catch** — the exit code alone decided the outcome, so a suite that could not be collected was reported as *"the bug was caught"*. **The harness was applying its own false-green rule to the mutations it planted and exempting itself from it** | **Severe** | **Fixed.** `_is_a_test_failure(code, output)` reads pytest's specific exit codes and vitest's output. Found by the review — and it happened for real, when a concurrent run held the test database. |
| **The comment stripper ate URLs and regex literals** — `re.sub(r"//[^\n]*", "", text)` truncates `"https://…"` to `"https:` and truncates a file at a regex literal holding `//`. **No current assertion was broken, but `app/events/[id]/page.tsx` carries a regex literal** | **Severe** | **Fixed.** A string- and regex-aware scanner, proved on itself by a new 17-test suite. Planting the old regex back turns two of them red. |
| **The FIRE completion path never promoted the intent's own status** — an intent whose every work item was completed still read `in_progress` in `state.yaml`, so the state file did not tell the truth. **The same gap seven intents in this repo had already been patched around by hand, one `chore(fire)` commit at a time** | **Severe** | **Fixed in the tooling.** `syncIntentStatus()` derives the expected status from the work items rather than asserting it, so it cannot drift from them; `syncIntentStatuses()` repairs the intents that predate the fix. Verified against a fixture, and **shown to be non-vacuous** — with the fix stashed, the same fixture comes out `in_progress`. |
| **The CTA assertion was satisfied by the wrong link** — the page carries a second `/signup` link, so a bare substring search measured the closing invitation rather than the CTA | High | **Fixed.** The assertion is scoped to the element carrying `data-public-save-cta`. Found when the plant did not go red. |
| The shared `incoming()` builder **erased the event's venue** on a lifecycle change (the write path updates wholesale), which would have broken the revalidation signal's city path and made the round-trip assertion prove the wrong thing | High | **Fixed.** `incoming_for(event, **overrides)` in the fixtures, built from the event's own columns. |
| The `on_commit` assertion could never fire under `pytest-django`'s `django_db` wrapper, which never commits | High | **Fixed.** `django_capture_on_commit_callbacks(using=CATALOG, execute=True)` — the repository's own established pattern. |
| The contract test raised `KeyError: 'source_modules'` — import-linter's **protected** contracts use `protected_modules` and `allowed_importers` | Medium | **Fixed.** The assertion was rewritten against the real configuration shape. |
| The generated-client check **might have been silently skipping** (a 1.39 s runtime) | Medium | **Fixed by measurement, not by trust.** A planted drift was appended to `schema.ts`; the test failed with *"The generated client has drifted"*; the file was restored. |
| The import contract for the public surface asserted the wrong shape and would have passed for the wrong reason | Medium | **Fixed.** It now asserts the protected modules, the allowed importers, and — the part that matters — that **`apps.catalog` is not on the allowed list**. |
| The crawl event had no fit row, so it was not on the city page the crawl starts from; and the count was off by one | Medium | **Fixed.** The fixtures were restructured around a shared root, so the crawl's event **is one of** the city's six fitted events. |
| `make_fit` could write a fit with a deliberately wrong version — **a shape the write path can never produce** — and the docstring invited its use | Medium | **Fixed.** The override is gone; the stale row is built by moving the event on. |
| `EventFactory` sets no description, so a page-level assertion about the description was asserting something the factory never provided | Low | **Fixed.** `make_event` now sets a description by default. |
| The `in_review` assertions carried a fit row that was irrelevant to what they prove — the *gate* is filtered, not the fit | Low | **Not fixed, and recorded.** The row is harmless; removing it would change three tests without changing what they prove. |

**No issue is open.** No critical, high or medium finding remains.

---

## How to reproduce

```bash
cd frontend
export PATH=$HOME/.nvm/versions/node/v24.22.1/bin:$PATH

npx vitest run tests/public-crawl-proof.test.tsx   # 24 passed
npx vitest run                                      # 1577 passed / 99 files
npx eslint .                                        # clean
npx next typegen && npx tsc --noEmit                # clean
npx prettier --check .                              # clean

cd ../backend
DJANGO_DB_ROLE=owner uv run pytest tests/e2e/test_public_pages_proof.py -q    # 34 passed
DJANGO_DB_ROLE=owner uv run pytest tests/e2e/test_public_pages_contract.py -q # 28 passed
DJANGO_DB_ROLE=owner uv run pytest -q               # 5248 passed
uv run ruff check .                                 # clean
uv run ruff format --check .                        # clean
uv run lint-imports                                 # 19 contracts kept, 0 broken
```

### The mutation probes, on their own

Run from the **repo root** (they touch both trees):

```bash
uv run --directory backend python tests/e2e/mutation_probe_public_pages_e2e.py
# All 9 public-pages probes were caught by the suite.
```

### The two frontend plants, by hand

```bash
cd frontend
export PATH=$HOME/.nvm/versions/node/v24.22.1/bin:$PATH

# Plant 1 — the CTA stops being a link.
#   frontend/components/public-event/public-event-page.tsx
#   <Link href="/signup">Save to Pulse →</Link>  →  <button>Save to Pulse →</button>
npx vitest run tests/public-crawl-proof.test.tsx
#   1 failed, 23 passed

# Plant 2 — the public branch reads the cookie jar.
#   frontend/app/events/[id]/page.tsx
#   const jar = await cookies();
npx vitest run tests/public-crawl-proof.test.tsx
#   17 failed, 7 passed — the mock throws, so the jar is unreachable, not merely empty
```

---

## Ready for Completion

- [x] All tests passing (86 new; 5248 backend; 1577 frontend)
- [x] Coverage target met (99.05% backend, against an 80% gate; `domain/` at 100%)
- [x] All acceptance criteria validated
- [x] **Every assertion shown able to fail** — 9 mutation probes caught, 2 frontend plants red, and 1 vacuous assertion found and fixed by the harness
- [x] No critical issues open
- [x] Code review complete — see the review report

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-024*
