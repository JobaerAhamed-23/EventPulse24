# Test report: `e2e-proof-and-contract-tests`

**Work item**: `e2e-proof-and-contract-tests`
**Intent**: `pulse-digest-and-trust`
**Mode**: confirm
**Date**: 2026-10-31

---

## What was built

| File | Kind | What it is |
|---|---|---|
| `backend/tests/e2e/test_digest_and_detail_proof.py` | new | **the proof** — 12 tests: the end-to-end scenario, the skip path, the empty path, the determinism check |
| `backend/tests/architecture/test_ad10_explanation_persistence.py` | new | 8 tests — AD-10's "no explanation at view time", both halves |
| `backend/tests/architecture/test_ad3_composition_separation.py` | new | 6 tests — AD-3's composition path: no transaction spans both schemas, no query names both aliases |
| `backend/tests/architecture/test_ad13_pii_sweep.py` | new | 6 tests — AD-13's sweep over the new paths, asserted against the logger's allowlist |
| `backend/tests/e2e/mutation_probe_contract_e2e.py` | new | the **backend probe harness** — 10 probes, one per contract rule |
| `frontend/tests/ad10-separation.test.ts` | new | 9 tests — AD-10's frontend wall: the transitive import walk |
| `frontend/tests/personal-separation.test.ts` | new | 7 tests — the brace-aware `personal` data-flow check |
| `frontend/tests/ad19-endpoint-coverage.test.ts` | new | 16 tests — AD-19's endpoint coverage, binding, and call-site rules |
| `frontend/tests/contrast.test.ts` | new | 66 tests — the static WCAG computation, the token-usage rules, and the deviation tripwire |
| `frontend/tests/contrast-mutation.mjs` | new | the **contrast probe harness** — 10 probes |
| `frontend/tests/ad19-client-break.mjs` | new | the **client-break probe harness** — 7 probes |
| `frontend/styles/tokens.css` | modified | the two light ambers darkened to `#8A5A1C` |
| `frontend/components/digest/pulse-card.tsx` | modified | the badge's chromatic colour moved to the glyph; the timezone's ink |
| `frontend/components/detail/detail-header.tsx` | modified | the same, on the Detail Screen |
| `frontend/components/preview/preview-card.tsx` | modified | the same two violations, on the pre-existing preview surface |
| `frontend/components/digest/pulse-card.test.tsx` | modified | two tests updated to the corrected behaviour |
| `DESIGN.md` | modified | the two ambers, and the `component.badge.source` rule |

**130 new tests** (32 backend, 98 frontend) across ten files, plus **27 mutation probes**
across three harnesses.

---

## The proof — `backend/tests/e2e/test_digest_and_detail_proof.py`, 12 tests

### The scenario is one test, and it is a backend test

The work item's scenario says the user "opens `/`, sees three cards in three slots with
their trust signals, taps one, and reads a why-this breakdown built from the same
persisted row the card rendered."

The **rendered** half of that was already proved by the two frontend items — the digest
home's tests assert the rendered cards, the detail screen's assert the rendered
breakdown. What only a backend test can see is the thing the two surfaces agree *about*:
**the persisted `DigestComposition` row.**

So the scenario walks the whole chain and asserts the claim FR-21 makes, which is a claim
about the database rather than about the markup:

| # | Step | What it proves |
|---|---|---|
| 1 | a user signs up | the session is real |
| 2 | they complete onboarding with interest chips and a city | `DigestPreference` and `Interest` are persisted |
| 3 | events are ingested into their city | the catalog has candidates for them |
| 4 | the worker composes the digest | `PulseDigest` + three `DigestComposition` rows exist |
| 5 | the digest read returns three cards in three slots | the read projects the rows |
| 6 | the detail read returns one card's event | the second read path finds the same event |
| 7 | the detail's `why_this` is **the card's** tags, bucket and badge | FR-21's consistency consequence, asserted on the rows |

**Step 4 is the worker's, not the API's.** AD-11: a request handler validates, enqueues
and returns. So the scenario calls `worker.tasks.compose_digest` — and
`test_ad10_explanation_persistence.py` pins the other half of that rule.

**Step 7 is the assertion the whole intent exists for.** The card's `tags` and the
detail's `why_this.tags` are the same list, in the same order, because both read the same
`DigestComposition.tags` column. A future change that gave the detail screen its own
vocabulary fails here.

**The two read paths are independent services.** `read_digest` and `read_event_detail`
are separate modules with separate queries, and the scenario drives both and asserts they
agree — because the claim is that the *row* is the shared truth, not that the two readers
share code.

### The three paths are three tests, not one test with branches

- **The skip-everything path** asserts three things: the composition **completes** (it
  does not raise and does not divide by zero); the persisted `tags` contain **no
  `matches_` tag**, so "no preference" is not "every preference"; and the digest still
  has a card, because the city term still scores.
- **The empty-state path** asserts the status is `empty` and **not** `not_composed` —
  because "there is nothing near you" and "we haven't built it yet" are different
  answers, and the frontend renders them differently.

**Why separate tests.** The skip path is the one nobody clicks manually, because the happy
path is what a developer clicks — so it is the one that rots. A branch would run only on
one path.

### The determinism test composes twice and compares **both** the rows and the page

Two different claims, asserted separately:

1. **The rows are identical.** The digest read before and after the second composition
   returns the same cards, in the same slots, with the same tags, buckets and badges —
   and the row **count** is unchanged, and the rows' `composed_at` is unchanged, because
   the second run did not rewrite them.
2. **The rendered page is identical.** The **HTML** the route returns is byte-identical
   across the two reads.

**Why the HTML is compared and not just the JSON.** Equal JSON does not imply equal
HTML — a page that rendered a timestamp, a "refreshed just now" line or a random id
would have identical data and different HTML. Comparing the bytes is the honest form of
"the identical rendered page". Any excluded region is **named in the test**, so the
comparison is not quietly weaker than it looks.

---

## The contract tests

### AD-10 — the frontend wall is a transitive import walk, not a name check

`frontend/tests/ad10-separation.test.ts`, 9 tests.

The backend half already exists (`test_event_fit_separation.py`): no module under
`apps/personalization` imports `apps.ingestion.event_fit`. This item closes the
**frontend** half.

**Why a name check would be bypassable.** The frontend's Event Fit vocabulary lives in
one place — the preview's read path. If that place is named, the check is a name check,
and a name check is bypassed by a re-export. The lesson `test_event_fit_separation.py`
already learned and recorded.

So the check has two halves:

1. **The structural half**, asserted on the AST — the authenticated routes do not import
   the Event Fit's read module, so an alias or a re-export is seen.
2. **The behavioural half, which is the strong one** — the check walks the frontend's
   *own import graph*, from the route file outward, and asserts the Event Fit read is
   not in it. The transitive walk is what makes it structural rather than nominal: the
   preview's read module is *allowed* to import the Event Fit, and the walk is precisely
   what distinguishes "the route reached it directly" from "the route reached it through
   a helper that reaches it for the preview".

### AD-10 — the `personal` check is a brace-aware data-flow check

`frontend/tests/personal-separation.test.ts`, 7 tests.

The backend half exists: `test_the_event_fit_read_never_reads_the_personal_schema`
checks the PERSONAL alias is absent from the Event Fit read and write.

The frontend half is the one that matters here, because the Detail Screen is new in this
intent and serves **two audiences from one route** — a signed-in reader and an anonymous
visitor.

**The interesting bug is a use of personal data *outside* the guard.** The Detail
Screen's own review found one: the reminder picker rendered for an anonymous visitor,
because the picker sat outside the `personal` check while the breakdown and the neighbour
count sat inside it. So this file does not check "is `personal` read" — it checks
**where** it is read.

**The check is a data-flow check on the source.** Every use of `.personal` in the route
must be **inside a branch guarded by it**. That is stronger than a name check, and it is
the only form that would have caught the picker.

**The walk is a real brace match, not a `lastIndexOf`.** This is the detail that makes the
check correct, and the mutation probe found it: `lastIndexOf("}")` cannot tell a block
that is still **open** from one that has already **closed**. In JSX,
`{personal ? (…) : null}` blocks are **siblings**, not nested — but a backwards
`lastIndexOf("{")` walk treats the *earlier sibling* as an enclosing block, because the
sibling's own `}` is somewhere after the use and the walk never checks it. So a use
placed *after* a guarded sibling looked guarded, and the probe's bug — an unguarded read,
exactly the shape this file exists to catch — sailed through.

**Two delimiters, two walks.** A JSX guard has two layers: the *expression*
`{personal ? ( … ) : null}`, whose brace closes at the very end, and the *branch*
`( … )`, whose parenthesis is what actually encloses the guarded body. Both are walked.

### AD-10 — "no explanation at view time" has two halves, and only one is visible in the AST

`backend/tests/architecture/test_ad10_explanation_persistence.py`, 8 tests.

1. **The read paths do not compute.** `read_digest` and `read_event_detail` must not
   call `domain/ranking.py`'s scoring function and must not call `compose_digest`.
   Asserted by **AST call analysis** — the same technique
   `test_digest_composition_separation.py` uses, and for the same reason: an import is
   not a call, and a re-export cannot hide a call.
2. **The read paths write no composition.** Asserted at the **database**, not on the
   source: the count of `DigestComposition` rows is unchanged across a read.

**The second half is the one that would catch a real bug.** A read that called a service
which wrote would pass every import check and every call check, and still generate an
explanation at view time.

### AD-3 — the composition path reads the two sides separately

`backend/tests/architecture/test_ad3_composition_separation.py`, 6 tests.

**The FK half already exists** (`test_personal_events_invariants.py`, through
`information_schema` — the wall is a database constraint, not a convention). The
**query** half is what this item adds, asserted on the composition path specifically,
because the composition is the one place where both schemas are legitimately touched.

- **No transaction spans both schemas.** The composition's `transaction.atomic` is
  `using=PERSONAL`, and the catalog reads happen **before** the transaction opens. A
  transaction whose window covers a catalog read is a distributed transaction, which
  Postgres cannot do and which the ORM would fake by opening a second connection.
- **No query names both aliases.** Every `objects` chain and every `.using()` in the
  composition names exactly one alias. A chain that mixed them would be a cross-schema
  join, and the ORM would emit it as one statement.

### AD-13 — the PII sweep is against the allowlist, and it sweeps the new paths

`backend/tests/architecture/test_ad13_pii_sweep.py`, 6 tests.

The allowlist exists (`adapters/logging/redaction.py::ALLOWED_FIELDS`) and is
deliberately narrow: ids, counts, durations, slugs — **never free text**. The sweep
runs the **real** paths — the digest composition, the digest read, the detail read, the
detail open, the saved-events write — and captures the real logs.

Three rules are asserted against the captured output: no **email address** survives the
scrubber, no **city** appears, and no **event title** appears. The title is the hardest
one, because free text is unrecognisable by pattern — which is exactly why the
formatter's rule is *"project loggers never interpolate their args at all"*.

**Plus the allowlist check itself:** every **extra** field on a captured record is either
in `ALLOWED_FIELDS` or the literal `[redacted]`. That is the structural form of "asserted
against the logger adapter's allowlist" — it does not depend on knowing which particular
PII to look for.

**The audit sink has its own vocabulary.** Its `details` is a `JSONField` with no schema
and no allowlist — so a title written into it is a title in the database forever. The
sweep asserts against it separately, and probe 8 and 9 are the two probes that prove
those assertions can fail.

### AD-19 — the generated client, and a break **fails the build**

`frontend/tests/ad19-endpoint-coverage.test.ts`, 16 tests.

The chain has five links:

```
backend route → live OpenAPI schema → committed openapi.json → schema.ts → the
frontend's call site
```

`backend/tests/api/test_contract.py` checks the **first** join (the committed schema
still equals the live one). This file checks the **middle** (the new endpoints are in
the schema and bound in the generated TypeScript). `frontend/tests/ad19-client-break.mjs`
checks the **last** join, and it checks it by **breaking** it.

**Why a coverage check and not just a drift check.** `test_contract.py` says the
committed schema matches the live API. It does not say the *right* endpoints are there.
An endpoint can be missing from the contract and the schema can be perfectly in sync —
the drift check would be green, and the frontend would have no way to call it.

**The operation id is the link.** It is the key the generated TypeScript uses, so
asserting on it proves two things at once: the endpoint is in the schema, *and* the
generated client has a typed binding for it. **Both halves are asserted** — the id
appears *twice* in `schema.ts` (as the `operations` key and as the `paths` reference),
and a `toContain` is satisfied by either alone.

**The call site must import the client, and must not define its own.** A call site that
mentions `api.GET(` but imports `api` from somewhere else — or defines its own `api` —
would satisfy the path assertion while bypassing the generated types entirely.

**The client module must export the typed `api`, typed from the generated schema.** An
untyped `api` would satisfy the export and defeat the typing, and the typing is the
whole point of AD-19.

**One gap is recorded rather than papered over.** The detail-open endpoint
(`POST /api/events/{event_id}/opened`) is in the committed schema and bound in the
generated TypeScript — so the generated-client half of AD-19 holds — but **nothing in the
frontend calls it.** The endpoint's *presence* is asserted; the *caller* is not asserted
to exist, because it does not. A **tripwire** holds the gap open: a test that asserts
the caller list is empty, so the day the frontend gains its caller the test **fails**
and whoever closes it deletes the test and adds the endpoint to `NEW_ENDPOINTS`.

---

## The accessibility gate — `frontend/tests/contrast.test.ts`, 66 tests

**The axe half is the two frontend items' own**, confirmed here: the digest home's gate
runs over four documents, the detail screen's over five. This item does not duplicate
them.

**The Lighthouse half is the honest gap.** Lighthouse measures a rendered page in a
browser under a throttled network. **Playwright is not installed and this run does not
install it** — the same scope decision the previous two intents' proofs made and
recorded.

**The substitute is a static computation of what Lighthouse would measure** that *can*
be measured here: **colour contrast**, computed from the token file and the rendered
pairs against WCAG 2.1's thresholds. This is the one Lighthouse criterion the axe gate
*cannot* cover, because jsdom computes no layout and `color-contrast` is therefore
disabled there. **It is a static computation from the token file, not a Lighthouse run**,
and it is recorded as such.

### The computation

The WCAG relative-luminance formula — `L = 0.2126R + 0.7152G + 0.0722B` with
linearisation `raw <= 0.03928 ? raw/12.92 : ((raw+0.055)/1.055)**2.4` and ratio
`(lighter+0.05)/(darker+0.05)` — computed over the token file's two palettes. The
computation is self-checked: black-on-white is 21:1, white-on-white is 1:1, and the
ratio is symmetric.

**The token file is split on `lastIndexOf('\n[data-theme="dark"]')`**, not `indexOf` —
because the file's own docstring mentions `[data-theme="dark"]` earlier, and `indexOf`
would parse an empty light palette.

### What it found — two real, pre-existing product defects

The check found two genuine defects that nothing had caught, because axe has
`color-contrast` disabled in jsdom:

1. **The light `signal-warn` was 2.96:1 and was used as error text in seven places** —
   the auth field errors, the reset and sign-out alerts, the onboarding errors. The
   design's `#B8893A` **fails** WCAG 1.4.3's 4.5:1 for normal text. The two ambers are
   now `#8A5A1C`, which is **4.79:1 at its worst** across all four light surfaces. The
   dark theme is unchanged: `#D8A86A` is 7.25:1.
2. **The empty confidence dot sat at 1.77:1** — see the recorded deviation below.

### The rule the design settled on

`EXPERIENCE.md §4` is the canonical list for `Badge.Source`, and `DESIGN.md` defers to
it. It specifies the terracotta as the *filled checkmark icon*, with the label in
`Text.Meta` — and that agrees with every other warn/terracotta element the design
specifies in detail (`component.badge.soldout`, Amendment A-20's auth error row). The
pattern is **chromatic glyph + ink label**.

**The terracotta was not darkened, because it is used as a graphic, not as text.**
`#C4502B` is **4.37:1** on paper — a graphic's ratio under WCAG 1.4.11 (3:1), not a
text's ratio. So it is the badge's `aria-hidden` glyph and never body text, and the
glyph/label split is asserted against the markup.

### The token-usage rules, asserted against the markup

Three checks go beyond the arithmetic, because the arithmetic cannot see *where* a colour
is used:

- no `text-ink-faint` on a non-`aria-hidden` element;
- no signal colour on a non-`aria-hidden` element;
- the chromatic token reaches **only** the `aria-hidden` glyph.

The helper searches only inside literal `className="…"` attributes and reports
`decorative` from the enclosing tag's `aria-hidden` — because the `▸` chevron is a
decorative glyph and the two colour-selection variables are not rendered classes.

### The recorded deviation — the empty confidence dot

`color.ink.faint` is the design's designated value for the empty confidence dot, and the
value is **pre-existing**. The **state** is legible — the filled dot is **10:1** against
the empty one — so this is a value deviation, not a state ambiguity.

**It is held open by a tripwire**, not silently waived and not silently altered: a test
that asserts the empty dot is **still** below 3:1, with the message *"the recorded
deviation is closed: remove this test, add the empty dot to `NON_TEXT_PAIRS`, and update
the deviation note in the test report."* Closing the deviation therefore makes the test
**fail**, which forces the note to be updated at the same time.

---

## Every test can fail — the probe record

The acceptance criterion: *"Every test in this item can fail. No placeholder assertions,
no `or`-fallbacks, no test that passes because a value is absent. Each one is verified to
fail when the behavior it pins is deliberately broken, and the run log records that it was
checked."*

**The mechanism.** Apply one real bug, run the suite that should catch it, and require
that at least one test fails. A probe that leaves the suite green means the tests do not
prove that rule.

**27 of 27 probes caught**, across three harnesses:

| Harness | Probes | Result |
|---|---|---|
| `backend/tests/e2e/mutation_probe_contract_e2e.py` | 10 | **10/10 caught** |
| `frontend/tests/contrast-mutation.mjs` | 10 | **10/10 caught** |
| `frontend/tests/ad19-client-break.mjs` | 7 | **7/7 caught** |

The per-probe table is in the run log (`run.md`, *"The probe record"*). Every probe
restores the file it touched in a `finally` — the restore is unconditional, so a failure
cannot leave the tree broken. The tree was confirmed clean afterwards.

### Five probes were rewritten because the first version proved nothing

This is the part of the record worth reading, because a probe that proves nothing is
worse than no probe — it looks like a pass.

| The probe | The first version | Why it proved nothing | The fix |
|---|---|---|---|
| the digest read calls the ranking function | planted an **import** | an imported-but-uncalled function computes nothing, and the AST check is a **call** check for exactly that reason | plant a **call** that re-buckets the card from the score |
| the detail read calls `compose_digest` | planted an **import** | same reason | plant a **call** |
| the composition's transaction spans both schemas | `transaction.atomic(using=PERSONAL, using=CATALOG)` | a **`SyntaxError`** — and the suite "caught" it because a suite that cannot be collected fails. That is a **false green**. | a catalog read **moved inside** the transaction window: it parses, it runs, it is wrong |
| the card's bucket disagrees with the breakdown's | changed the **first** matching pattern | that was the **missing-catalog** card builder, and the scenario's events are all present — so that branch never runs. **A probe that plants a bug in dead code proves nothing.** | target the **live** builder, identified by the `tz_review_pending=public.…` line only it has |
| the detail read goes around the client | replaced the **first** occurrence of the path | that was the **docstring**, not the call site — so the code kept calling the right endpoint | target `api.GET("/api/events/{event_id}"` |

### The client-break probe found four real holes in the test written to catch it

This is the sharpest result in the item, and it is the reason the probe exists:

1. **The false green.** `expect(caller).toContain(endpoint.path)` read the detail read's
   **docstring**, which names the path it calls — so a call site rewritten to
   `/api/events/hand-written` still passed. Fixed by stripping comments before reading
   the source.
2. **The binding was one assertion where it needed two.** The operation id appears twice
   in `schema.ts`; renaming only the `operations` key left the `paths` reference behind
   and the check stayed green. Split into "is a key in `export interface operations {`"
   **and** "the `paths` entry references it".
3. **Nothing checked the client was exported.** Removing `export` from
   `backend-client.ts` broke every call site and **every endpoint test stayed green**.
4. **Nothing checked the caller imported it.** A call site that defines its own `api`
   satisfies the path assertion while bypassing the generated types entirely.

**The lesson, stated once:** a test that asserts a dependency *exists* proves nothing
about whether anything *depends* on it.

---

## The gates

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

**The tick.** The criterion says `tests/worker/test_tick.py` must pass **unchanged**, so
this item does **not** modify that file. It **runs** it and records that it passed without
a diff — and the diff is the evidence. The Digest intent added a Celery task and a
scheduler; a second tick or a changed period would be an easy and quiet regression,
because the digest would compose on the wrong cadence and nothing else would fail.

---

## The two things that are not proven

Both are named rather than quietly ticked.

1. **Lighthouse ≥95 is unverified.** There is no browser in this stack, and this run does
   not install one. The *substantive* half of the criterion — `axe-core` zero
   serious/critical on both surfaces — is met, and colour contrast, the one Lighthouse
   criterion the axe gate cannot cover, is computed statically. **But a static
   computation is not a Lighthouse score**, and the run does not claim one.
2. **The screen has never been seen in a browser.** jsdom has no layout engine, no
   stacking order and no hit-testing. The rendered contrast, the Lighthouse score, the
   LCP and the touch behaviour are all unmeasured. The **computed** contrast is a
   statement about the token pairs, not about what a user sees.
