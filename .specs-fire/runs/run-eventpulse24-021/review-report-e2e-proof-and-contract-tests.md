# Review report: `e2e-proof-and-contract-tests`

**Work item**: `e2e-proof-and-contract-tests`
**Intent**: `pulse-digest-and-trust`
**Mode**: confirm
**Date**: 2026-10-31

---

## The verdict

**Approved with two recorded deviations and one partially-met criterion.**

The proof is honest: it asserts the thing the intent exists for — that the card and the
breakdown are **two projections of one persisted row** — on the **database**, which is
the only place that claim can be checked. The contract tests are structural rather than
nominal, and **every one of them was verified to fail** when the behaviour it pins was
deliberately broken: **27 of 27 probes caught**.

The review's most important finding is about the probes rather than the product. **Five
probes were rewritten because their first version proved nothing**, and the client-break
probe found **four real holes in the test that had been written to catch it** — including
a false green that read a docstring instead of the code. The lesson is recorded where it
will be read: *a test that asserts a dependency exists proves nothing about whether
anything depends on it.*

**Two product defects were found by the accessibility gate** — both pre-existing, both
real, both now fixed. And **one deviation is recorded rather than silently fixed**: the
empty confidence dot, held open by a tripwire that fires when someone closes it.

---

## What the review checked

| Property | How | Result |
|---|---|---|
| the proof asserts the intent's claim | the card's tags/bucket/badge vs the breakdown's, on the same row | green |
| the composition is the worker's, not the API's | the scenario calls `compose_digest`; the architecture test pins the API side | green |
| the three paths are three tests | happy, skip, empty — not one test with branches | green |
| the skip path does not divide by zero | the composition completes, and no `matches_` tag is persisted | green |
| the empty path says `empty`, not `not_composed` | the status is asserted, and the city line is asserted | green |
| the second composition writes nothing | the row count, the ids, and `composed_at` are unchanged | green |
| the rendered page is byte-identical | the HTML is compared, with the excluded region named | green |
| a read writes no composition row | the count is taken before and after | green |
| an unseen event gets no explanation | `why_this` is `None`, not a recomputed one | green |
| the two read paths agree | **every** card, not just the first | green |
| AD-10's frontend wall is transitive | the import graph is walked from each route outward | green |
| the preview still reaches the Event Fit | the wall is a direction, not an absence | green |
| the `personal` check is data-flow, not line-based | a real brace match, outward through the enclosing blocks | green |
| the read paths call no ranking function | AST **call** analysis, not import analysis | green |
| no transaction spans both schemas | **every** read against **every** transaction | green |
| no query names two aliases | the `using=` argument is checked on every chain | green |
| the PII sweep is against the allowlist | every extra field is core, allowlisted, or `[redacted]` | green |
| the sweep is not vacuous | the sink **proves it works** before the sweep begins | green |
| the client is load-bearing | the client-break probe, 7/7 caught | green |
| the contrast is computable statically | the WCAG formula, self-checked | green |
| the token file matches the design | `styles/tokens.test.ts` asserts it, and DESIGN.md was updated | green |
| the deviation is held open | a tripwire that fails when the deviation closes | green — deviation recorded (D1) |
| Lighthouse ≥95 | a browser | **not verified** — criterion partially met |
| the detail-open endpoint has a caller | the frontend's call sites | **none** — gap recorded (D2) |

---

## The five findings

### Finding 1 — the probes proved more about the tests than about the product

**Five probes had to be rewritten**, and in every case the first version *passed the
suite* — which the harness read as "the suite did not catch the bug", so the probe
correctly reported `FAIL`. That is the mechanism working. But the reasons are worth
recording, because each is a distinct way to write a test that proves nothing:

| The probe | The first version | Why it proved nothing |
|---|---|---|
| the digest read calls the ranking function | planted an **import** | an imported-but-uncalled function computes nothing — and the AST check is a **call** check for exactly that reason |
| the detail read calls `compose_digest` | planted an **import** | the same |
| the composition's transaction spans both schemas | `transaction.atomic(using=PERSONAL, using=CATALOG)` | a **`SyntaxError`** — and the suite "caught" it because a suite that cannot be collected fails. **A false green.** |
| the card's bucket disagrees with the breakdown's | changed the **first** matching pattern | that was the **missing-catalog** card builder, and the scenario's events are all present — so that branch never runs. **A probe that plants a bug in dead code proves nothing.** |
| the detail read goes around the client | replaced the **first** occurrence of the path | that was the **docstring**, not the call site — so the code kept calling the right endpoint |

**The `SyntaxError` case is the sharpest.** A probe that breaks the file so badly the
suite cannot collect it will report "caught" — and would have passed while proving
nothing. Every probe in this item plants a bug that **parses, runs, and produces a wrong
answer**, and the harness says so in its own docstring.

**The verdict:** the harness is sound, and the probes are meaningful. But this is a
finding about the *method*, and it is the reason the acceptance criterion says "no test
that passes because a value is absent" — the criterion is not satisfied by writing
assertions, it is satisfied by **watching them fail**.

### Finding 2 — the client-break probe found four real holes in the test written to catch it

This is the sharpest result in the item. The AD-19 test asserted that the frontend
reaches the backend through the generated client. **Four holes would have let a real
break in that chain pass:**

1. **The false green.** `expect(caller).toContain(endpoint.path)` read the detail read's
   **docstring**, which names the path it calls. A call site rewritten to
   `/api/events/hand-written` still passed. **Fixed** by stripping comments before
   reading the source.
2. **The binding was one assertion where it needed two.** The operation id appears
   *twice* in `schema.ts` — as the `operations` key and as the `paths` reference — and
   `toContain` is satisfied by **either** alone. Renaming only the key left the
   reference behind and the check stayed green. **Fixed** by splitting into "is a key in
   `export interface operations {`" **and** "the `paths` entry references it".
3. **Nothing checked the client was exported.** Removing `export` from
   `backend-client.ts` broke every call site, and **every endpoint test stayed green** —
   because the call sites' assertions read their *source*, and a source that says
   `api.GET(…)` still says it when `api` no longer exists. **Fixed** by asserting the
   client module exports `api` and types it from the generated `paths`.
4. **Nothing checked the caller imported it.** A call site that mentions `api.GET(` but
   defines its own `api` satisfies the path assertion while bypassing the generated
   types entirely. **Fixed** by asserting the import from `@/lib/backend-client` and the
   absence of a local definition.

**The verdict:** the test is now honest, and it was not before. This is the clearest
evidence in the item that **the probe technique is worth its cost** — four holes that
review-by-reading had not found.

### Finding 3 — two pre-existing product defects, found by the contrast gate

The accessibility criterion could not be met as written (no browser), and the substitute
— a static WCAG computation from the token file — **found two genuine defects** that
nothing had caught, because axe has `color-contrast` disabled in jsdom.

**The light ambers were failing as text.** `#B8893A` is **2.96:1** on `#FAF8F4`, and it
was used as **error text in seven places** — the auth field errors, the reset and
sign-out alerts, the onboarding errors. The design's own ASSUM-1 asked for exactly this
re-verification. The ambers are now `#8A5A1C`, **4.79:1 at its worst** across all four
light surfaces. The dark theme is unchanged (`#D8A86A` is 7.25:1).

**The empty confidence dot was at 1.77:1** — see D1.

**The fix was made in `DESIGN.md`, not only in the token file.** `styles/tokens.test.ts`
asserts the token file matches DESIGN.md's own bullets, so a token change without a
design change fails that test. The design is the source of truth, and it was updated
with the reasoning — the ASSUM-1 citation, the 2.96:1 failure, the seven call sites, and
the new rule.

**The terracotta was deliberately *not* darkened.** `#C4502B` is **4.37:1** on paper — a
graphic's ratio under WCAG 1.4.11 (3:1), not a text's. So it is used as the badge's
`aria-hidden` **glyph** and never as body text. This follows `EXPERIENCE.md §4`, the
canonical list that `DESIGN.md` defers to, and it agrees with every other warn and
terracotta element the design specifies in detail (`component.badge.soldout`, Amendment
A-20's auth error row): **chromatic glyph + ink label**. The glyph/label split is now
asserted against the markup, in both surfaces.

**The verdict:** a real product improvement, correctly scoped, correctly documented at
the source of truth.

### Finding 4 — the design's `ink-faint` rule was being violated by the surfaces themselves

The contrast gate checks the *token pairs*, but the arithmetic cannot see **where** a
colour is used. Three additional checks cover that, and they found two violations:

- The Pulse Card's timezone abbreviation used `text-ink-faint` — a **meta** label, not a
  decorative glyph. The Detail Screen's and the Preview Card's did the same.
- The Preview Card's Source Badge put `text-signal-warn` on the **button**, which is a
  text element — the same violation the two new surfaces had been fixed for.

**Both were fixed**, and the same two violations were fixed on the two new surfaces
(the card's timezone and its badge label). The fixes moved the chromatic colour onto
the `aria-hidden` glyph and lifted the timezone's ink from `faint` to `muted`.

**The verdict:** the token-usage rules are worth having alongside the arithmetic — the
arithmetic says a pair is fine; only the markup check says *where* it is used.

### Finding 5 — one gap was found and **not** silently closed

The `POST /api/events/{event_id}/opened` endpoint is in the committed schema and bound
in the generated TypeScript — so the generated-client half of AD-19 holds — but **nothing
in the frontend calls it.**

**The temptation was to add a caller.** It would have made the coverage claim tidier.
It would also have been a **behaviour change** to the Detail Screen — firing a write on
every screen view is a decision about the surface's semantics and about what a "view"
means; it has to be fire-and-forget, and it must not fire for an anonymous visitor (the
endpoint answers 401). Those are the frontend-event-detail item's decisions to make.

**Instead the gap is held open by a tripwire**: a test that asserts the caller list is
**empty**, with the message *"the detail-open endpoint now has a frontend caller. The gap
is closed: delete this test and add the endpoint to NEW_ENDPOINTS, with its caller's
module."* The day the frontend gains its caller, the test **fails** — which is what
makes it a test rather than a comment.

**The verdict:** correct. The gap is stated, visible, and will fire.

---

## The two deviations

### D1 — the empty confidence dot is below 3:1

`color.ink.faint` is the design's designated value for the empty confidence dot, and the
value is **pre-existing** — this item did not introduce it.

**What was checked.** Light **1.77:1** on `surface-elevated`, dark **1.64:1** on
`surface-paper`. Both below the 3:1 that WCAG 1.4.11 asks of a meaningful graphic.

**Why it was not fixed.** Two reasons, and the second is the one that matters:

1. **The state is legible.** The filled dot is **10:1** against the empty one. So this is
   a *value* deviation, not a state ambiguity — the reader can tell filled from empty.
2. **The value is the design's, and the design's source of truth would have to change.**
   `color.ink.faint` is used for de-emphasised meta text across the app; darkening it to
   clear 3:1 would change every surface that uses it, and that is a **design decision**,
   not a test-suite decision.

**How it is held open.** A tripwire: `describe("the recorded deviation")` asserts the
empty dot is **still** below 3:1, with the message *"the recorded deviation is closed:
remove this test, add the empty dot to NON_TEXT_PAIRS, and update the deviation note in
the test report."* **Closing the deviation makes the test fail** — so the note cannot
drift from the code.

### D2 — the detail-open endpoint has no frontend caller

As recorded in Finding 5. The endpoint exists and is generated; nothing calls it. The
tripwire fires when that changes.

---

## The criterion that is partially met

**The accessibility criterion asks for `axe-core` zero serious/critical **and**
Lighthouse ≥95.**

- ✅ **`axe-core` zero serious/critical on both surfaces**, in CI. The digest home's gate
  runs over four documents, the detail screen's over five — and both were confirmed
  here, not duplicated.
- ⚠️ **Lighthouse ≥95 is unverified.** Lighthouse measures a rendered page in a browser
  under a throttled network. **Playwright is not installed and this run does not install
  it** — the same scope decision the previous two intents' proofs made and recorded.

**The substitute, and its honest limit.** The static WCAG computation covers **colour
contrast**, the one Lighthouse criterion the axe gate *cannot* cover, because jsdom
computes no layout and `color-contrast` is therefore disabled there. And it found two
real defects, so it earned its place.

**But a static computation is not a Lighthouse score.** The run does not claim one. What
remains unmeasured is everything that needs a browser: the rendered contrast in a real
layout, the performance score, the LCP, the touch behaviour, and the screen-reader
experience on a real device.

---

## The proof's own limits, stated

**The scenario is a backend test, and the work item's scenario reads like a browser
test.** The work item says the user "opens `/`, sees three cards in three slots with
their trust signals, taps one, and reads a why-this breakdown built from the same
persisted row the card rendered."

The **rendered** half was proved by the two frontend items — the digest home's tests
assert the rendered cards, the detail screen's assert the rendered breakdown, and both
read the same `DigestComposition`. What this item adds is the half a browser cannot see:
**the rows.** The scenario drives both read services and asserts that the card's tags,
bucket and badge **are** the breakdown's — two independent services, one persisted row.

**That is the claim FR-21 makes, and it is a claim about the database rather than about
the markup.** But it is not a claim that a person saw three cards and tapped one, and
the run does not say it is.

**What is genuinely new here** is that the equality is now asserted **on the rows**, by
two services, in one test — and that the *same* row is what both surfaces render.

---

## The design of the contract tests, reviewed

**The two read paths are named, and a third one would be noticed.**
`test_ad10_explanation_persistence.py` names `digest_read.py` and `detail_read.py`
rather than discovering them, and then pins that **no other module** in
`apps/personalization` queries a `DigestComposition`. A discovery rule would be a list
of holes for every new read path; this way a third read path **cannot appear without
the file noticing**.

**The AD-3 ordering check is on *every* read against *every* transaction.** An earlier
version compared the **earliest** catalog read to the **earliest** `atomic` — and a bug
that moved a catalog read inside a *second* transaction passed it, because the earliest
read was still before the earliest transaction while the later read sat squarely inside
the window. The probe found that; the check is now the strongest form a line-ordering
check can express.

**The PII sweep proves its own instrument before it measures.** The paths under test log
**nothing** — which is the correct behaviour, and also the behaviour that would make
every sweep pass **vacuously**. So the sink emits a calibration record carrying a title
and an email and asserts both came out `[redacted]`, **before** the sweep begins. If the
formatter were broken or the sink miswired, the test fails *before* the silence can be
mistaken for a pass.

**The audit sink has its own vocabulary, stated.** The log sink has an allowlist; the
audit sink's `details` is a `JSONField` with **no** schema and **no** allowlist — so a
title written into it is a title in the database forever. The vocabulary is therefore
stated in the test file, and the check is against it. The key check stops the vocabulary
growing by accident; the three value sweeps cover the values.

**The `personal` data-flow check is the most intricate thing in the item**, and it is
right for a reason worth stating: **a line-based check would not have caught the bug the
Detail Screen's own review found.** The guard `{personal ? (` is on one line and the use
is two lines later. So the check finds each use and walks **outward** through the
enclosing blocks — with a **real brace match**, because `lastIndexOf("}")` cannot tell a
block that is still open from one that has already closed, and in JSX
`{personal ? (…) : null}` blocks are **siblings**, not nested. The probe confirmed that
a use placed *after* a guarded sibling would otherwise have looked guarded.

---

## The gates, re-run

| Gate | Command | Result |
|---|---|---|
| the backend suite | `pytest` | **3920 passed** |
| the frontend suite | `vitest run` | **785 passed**, 58 files |
| the item's backend tests | the four new files | **32 passed** |
| the item's frontend tests | the four new files | **98 passed** |
| the import contracts | `make lint-imports` | **19 kept, 0 broken** |
| the schema check (PERSONAL) | `manage.py check` | no issues (1 silenced) |
| the schema check (CATALOG) | `manage.py check --database catalog` | no issues (0 silenced) |
| the types | `pnpm typecheck` | clean |
| the lint | `pnpm lint` | clean |
| the format | `pnpm format:check` | clean |
| the build | `pnpm build` | 9 routes, success |
| the tick is unchanged | `git diff backend/tests/worker/test_tick.py` | **empty** |
| the contract probes | the three harnesses | **27/27 caught** |

**The tree was confirmed clean after the probes** — the only modified files are the
six intentional ones, and every probe's restore ran in its `finally`.

---

## The closing note

The last work item of an intent is the one that says whether the intent held together.
This one says: **it did, and the proof is honest about what it did and did not check.**

The contract rules are pinned structurally — an import graph, a call graph, a row count,
an allowlist — and **every one of them was watched to fail**. The accessibility criterion
could not be met as written, and the substitute found two real product defects that the
original criterion would have missed, because axe cannot check contrast in jsdom. Two
deviations are recorded with tripwires that fire when they close. And the work item's
own browser scenario is proved at the row level, with the browser half named as the
scope decision it is.
