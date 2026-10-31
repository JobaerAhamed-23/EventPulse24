---
id: e2e-proof-and-contract-tests
title: The end-to-end proof and the AD-10 contract tests
intent: pulse-digest-and-trust
complexity: medium
mode: confirm
status: in_progress
depends_on: [frontend-digest-home, frontend-event-detail, digest-scheduling]
created: 2026-10-30
---

# Design: The end-to-end proof and the AD-10 contract tests

## The shape of this item

This is a **proof item**. It proves the intent works end to end, and it pins the
architectural rules that this intent is the first to be able to break.

The work item says the hard part plainly: *"The substitution test is the hard one to
write honestly."* Asserting that a page does not show an Event Fit by checking rendered
text is weak — **the two indicators look identical on screen, which is the entire
premise of AD-10.** So the assertions here are structural: the import graph, the call
graph, and the absence of any code path from an authenticated surface to the Event Fit
read.

Everything already in the tree that this item would otherwise re-invent is **reused and
extended**, not rewritten:

| What exists | Where | What this item does with it |
|---|---|---|
| the Event Fit wall (AST, prefix-based) | `tests/architecture/test_event_fit_separation.py` | **extends** it with the frontend half and the view-time half |
| the composition separation (AST, call-based) | `tests/architecture/test_digest_composition_separation.py` | **extends** it with the "the read path does not compose" half |
| the schema separation (information_schema) | `tests/architecture/test_personal_events_invariants.py` | **extends** it with the composition path's two-sided read |
| the FR-22 weight lock | `tests/shared/test_constants.py` | **confirms** it and adds the "changing one fails CI" probe |
| the AD-19 contract drift | `tests/api/test_contract.py` | **confirms** it and adds the endpoint-coverage assertion |
| the tick | `tests/worker/test_tick.py` | **confirms** it passes unchanged |
| the redaction allowlist | `adapters/logging/redaction.py` | **extends** it with the PII sweep over the new paths |

**Nothing is written twice.** Where a rule already has a home, this item adds to that
home.

---

## D1 — The scenario is **one test**, and it is a backend test

The previous two intents' proofs are one test each, and they say why: *"the point of a
proof is that the steps compose."* Twelve items of an intent were built and each was
tested in isolation; the failures that matter live in the seams.

So: **one test, one client, one database, one transaction's worth of shared state.**

**Why the frontend is not in the scenario.** The work item's scenario says the user
"opens `/`, sees three cards in three slots with their trust signals, taps one, and
reads a why-this breakdown built from the same persisted row the card rendered."

The *frontend* half of that is already proven, and proven better than a browser could:
the `frontend-digest-home` item's own tests assert the rendered cards, and the
`frontend-event-detail` item's assert the rendered breakdown — and the **equality**
between the two is asserted on the *same persisted row*, because both read the same
`DigestComposition`. The work item's own Technical Notes say a browser dependency is
"a scope decision this item should not make silently."

What the backend scenario adds is the thing a browser cannot see: **the rows.** The
proof walks the whole chain — signup, onboarding, ingestion, composition by the worker,
the read — and asserts that the card the user saw and the breakdown they tapped are
**two projections of one persisted row**. That is the claim FR-21 makes, and it is
about the database, not about the markup.

**What the scenario therefore is:** the backend half, end to end, with the frontend's
identity as a *contract* rather than as a rendering — the scenario asserts the card's
tags, the card's bucket and the breakdown's tags are **the same values, read from the
same row, by two different read paths**.

**The two read paths are the point.** `read_digest` (`apps/personalization/services/digest_read.py`)
and `read_event_detail` (`apps/personalization/services/detail_read.py`) are two
independent services. The scenario drives both and asserts they agree.

---

## D2 — The scenario's steps, and what each one proves

| # | Step | What it proves |
|---|---|---|
| 1 | a user signs up | the session is real |
| 2 | they complete onboarding with interest chips and a city | `DigestPreference` and `Interest` are persisted |
| 3 | events are ingested into their city | the catalog has candidates for them |
| 4 | the worker composes the digest | `PulseDigest` + three `DigestComposition` rows exist |
| 5 | the digest read returns three cards in three slots | the read projects the rows |
| 6 | the detail read returns one card's event | the second read path finds the same event |
| 7 | the detail's `why_this` is **the card's** tags, bucket and badge | **FR-21's consistency consequence, asserted on the rows** |

**Step 4 is the worker's, not the API's.** AD-11: a request handler validates, enqueues
and returns. So the scenario calls `worker.tasks.compose_digest` (or the enqueued
command), not the API — and the architecture test pins that the API module does not
compose.

**Step 7 is the assertion the whole intent exists for.** The card's `tags` and the
detail's `why_this.tags` are the same list, in the same order, because both read the
same `DigestComposition.tags` column. If a future change gave the detail screen its own
vocabulary, this fails.

---

## D3 — The skip-everything path is a **separate scenario**, not a branch

A user who skips every onboarding step has **no interest chips** and **no city**.

The danger the work item names is specific: *"the ranking must score them without
dividing by zero and without silently treating 'no preference' as 'every preference'."*

So the second scenario asserts three things:

1. the composition **completes** — it does not raise, and it does not divide by zero;
2. the persisted `tags` contain **no `matches_` tag** — "no preference" is not "every
   preference";
3. the digest still has a card — the city term still scores.

**Why a separate scenario and not a branch of the first.** A branch would run only on
one path, and the skip path is the one most likely to rot: it is the path nobody takes
manually, because the happy path is what a developer clicks. A separate test is a
separate thing that can fail on its own.

---

## D4 — The empty-state path is a **third scenario**

A user in a city with **no qualifying events** sees FR-8's card: the empty state with
its copy and its city line — and **not** a "being prepared" state.

The reason this is its own scenario: `composed`/`empty`/`not_composed` are three
different answers that all return 200, and the frontend renders three different
documents. The scenario drives the API and asserts the **status** is `empty` (not
`not_composed`), because the difference between "there is nothing near you" and "we
haven't built it yet" is exactly what the frontend must not confuse.

---

## D5 — The AD-10 contract tests are **structural**, and each is in the right file

### D5a — An authenticated surface never falls back to an Event Fit

**The existing wall** (`test_event_fit_separation.py`) covers the **backend**: no
module under `apps/personalization` imports `apps.ingestion.event_fit`.

**The gap this item closes is the frontend.** The frontend's authenticated surfaces are
`app/page.tsx` (the digest home) and `app/events/[id]/page.tsx` (the detail). Neither
may reach an Event Fit value.

The assertion is on the **source**, not on a rendered string, and it is a *reachability*
assertion rather than a *name* assertion:

- the frontend's Event Fit vocabulary lives in **one place** — the preview's read path.
  If that place is named, the check is a name check, and a name check is bypassable by a
  re-export (the lesson `test_event_fit_separation.py` already learned and recorded).
- so the check is: **the two authenticated routes do not import the module that reads
  the Event Fit**, and *that module* is the preview's own read.

But a name check on a *route* is weak, and the work item says to extend in the same
spirit rather than adding a shallower test. So the check has **two halves**:

1. **The structural half:** the authenticated routes do not import the Event Fit's read
   module — asserted on the AST, so an alias or a re-export is seen.
2. **The behavioural half, which is the strong one:** **the frontend's public Event Fit
   read is the only place `event_fit` appears at all**, and the authenticated routes do
   not import it *transitively* — the check walks the frontend's own import graph, from
   the route file outward, and asserts the Event Fit read is not in it.

The transitive walk is what makes it structural rather than nominal: **the preview's
read module is allowed to import the Event Fit**, and the walk is precisely what
distinguishes "the route reached it directly" from "the route reached it through a
helper that reaches it for the preview".

### D5b — A public surface never reads `personal`

**The backend half exists**: `test_the_event_fit_read_never_reads_the_personal_schema`
checks the PERSONAL alias is absent from the Event Fit read and write.

**The frontend half does not exist, and it is the one that matters here.** The public
Event Fit read is `GET /api/public/preview`. The frontend's public surface is
`app/preview/page.tsx` and the **anonymous branch of the Detail Screen** — and the
Detail Screen's anonymous branch is new in this intent.

So: the frontend's public read path must not carry a `personal` query. The assertion is
on the generated client's usage — the **preview route's** fetch must not include
`personal`-scoped endpoints, and the detail route's `personal` use must be **behind the
`personal !== null` check**.

**How that is asserted structurally.** The detail page's data flow is: one
`readEventDetail` call, whose result is a union. The `personal` half of the payload is
read from `read.detail.personal`, and the personal *surfaces* are gated on it. So the
check is a **data-flow** check on the page's own source: every use of `.personal` in the
page is inside a branch guarded by it.

**That is stronger than it looks**, because the interesting bug — the one this item's
own frontend work found — is exactly a use of personal data *outside* the guard.

### D5c — `personalization` still cannot import the Event Fit

**This already exists** — both the import-linter contract (`event-fit-separation`) and
the AST wall. The AC asks that the existing package-level contract is **unrelaxed**, so
the check is:

- the contract is still in `pyproject.toml`, still names the **package** (not a list of
  leaves), and still has the `.*` wildcard;
- `make lint-imports` passes;
- the AST wall's own re-export probe still passes.

**The re-export probe is the important one.** It plants a two-line bypass and asserts
the wall catches it. That is the proof the contract has not been quietly weakened into a
list of names.

### D5d — No explanation is generated at view time

**This is the AD-10 half that has not been testable until now.** Until this intent, the
Relevance Pulse did not exist, so there was nothing for a view-time computation to
substitute *for*. Now there is.

The rule has two halves:

1. **The read paths do not compute.** `read_digest` and `read_event_detail` must not
   call `domain/ranking.py`'s scoring function and must not call `compose_digest`.
   Asserted by **AST call analysis** — the same technique
   `test_digest_composition_separation.py` uses, and for the same reason: an import is
   not a call, and a re-export cannot hide a call.

2. **The read paths write no composition.** Asserted at the **database**, not on the
   source: the count of `DigestComposition` rows is unchanged across a read. This is
   the half a source check cannot do — a read that called a service which wrote would
   pass every import check and still generate an explanation at view time.

**Both halves are asserted, and the second is the one that would catch a real bug.**

---

## D6 — The AD-3 contract test is **about the composition path**

AD-3: no query joins `catalog` and `personal`, and no model in either schema holds a
foreign key into the other.

**The FK half already exists** (`test_personal_events_invariants.py`, through
`information_schema` — the wall is a database constraint, not a convention). The
**query** half is the one this item adds, and it is asserted on the composition path
specifically:

**The composition reads the two sides separately.** `compose_digest` reads the catalog
(candidates) and the personal side (preferences, interests, saves) and writes only to
the personal side. So:

- **No transaction spans both schemas.** The composition's `transaction.atomic` is
  `using=PERSONAL`, and the catalog reads happen **before** the transaction opens. The
  test asserts this structurally — the `transaction.atomic` call names the personal
  alias, and the catalog read calls are **not** inside it.
- **No query names both aliases.** Every `objects` chain and every `.using()` in the
  composition names exactly one alias. A chain that mixed them would be a cross-schema
  join, and the ORM would emit it as one statement.

**How the "no query joins" half is checked.** The check is on the **alias names** in
the composition's own source, using the existing `tests/architecture/checkers.py`
helper that already exists for exactly this rule (AD-3: "every database call names its
alias"). The composition is the one place where both sides are legitimately touched, so
it is the one place where the rule needs a *specific* assertion rather than the general
one.

---

## D7 — The FR-22 weight lock: the constants are pinned, and **a change fails**

FR-22's own consequence: *"a weight change without a PRD amendment is a CI-level test
failure."*

**The pin already exists** (`tests/shared/test_constants.py::test_ranking_weights_are_pinned`).
So the criterion is satisfied by confirming it — and by proving it **can fail**, which
is the AC's deeper demand: *"Each one is verified to fail when the behavior it pins is
deliberately broken."*

**The proof is a mutation probe**, not an assertion. The probe edits one weight in
`shared/constants.py` and runs the test suite; the test must fail. This is the
mechanism the run already has (`tests/e2e/mutation_probe_e2e.py`), and this item
**extends it** rather than inventing a second one.

**Why a probe and not a test.** A test that reads the constants and compares them to
itself proves nothing. The pin is only meaningful if a change to the constant *fails*,
and the only way to show that is to change it.

---

## D8 — The determinism test composes **twice** and compares **both** the rows and the page

*"Composing a user's digest twice produces the identical persisted rows and the
identical rendered page."*

**The re-run is a no-op by design** — `compose_digest` returns the existing digest and
writes nothing. So the test has two halves, and they are different claims:

1. **The rows are identical.** The digest read before and after the second composition
   returns the same cards, in the same slots, with the same tags, buckets and badges —
   and the row **count** is unchanged, and the rows' `composed_at` is unchanged (the
   second run did not rewrite them).

2. **The rendered page is identical.** The **HTML** the route returns is byte-identical
   across the two reads.

**Why the HTML is compared and not just the JSON.** The JSON being equal does not imply
the page being equal — a page that rendered a timestamp, a "refreshed just now" line or
a random id would have identical data and different HTML. Comparing the bytes is the
honest form of "the identical rendered page".

**The comparison has to exclude the parts that legitimately vary** — and it must be
*explicit* about what it excludes, or the test would be weaker than it looks. The
digest's `composed_at` is a timestamp, and the page's footer may carry a build id.
So the comparison is on the **rendered body**, and any excluded region is named in the
test.

---

## D9 — The `beat_schedule` is **exactly one 60s tick**, and the test passes **unchanged**

The criterion says `tests/worker/test_tick.py` must pass **unchanged**. So this item does
**not** modify that file. It **runs** it, and records that it passed without a diff —
which is the evidence.

**Why the unchanged-ness is the point.** The Digest intent added a Celery task
(`compose_digest`) and a scheduler. A second tick, or a changed period, would be an
easy and quiet regression: the digest would compose on the wrong cadence, and nothing
else would fail. So the criterion is "the *existing* test still passes and the file has
not been edited" — the second half is checked by **git**, not by reading the file.

---

## D10 — The generated client: **every new endpoint** is in the schema, and a break **fails the build**

AD-19. Three sub-claims:

1. **Every new endpoint is in the OpenAPI schema.** This intent added
   `GET /api/events/{event_id}` and `POST /api/events/{event_id}/opened`. The check
   asserts both are present in the **committed** `openapi.json` **and** in the **live**
   schema — the committed one is already checked for *equality* with the live one by
   `test_contract.py`, so what this adds is the **coverage** claim: the endpoint is
   there *at all*, and the TypeScript client has a typed binding for it.

2. **The client is generated rather than hand-written.** The check is that
   `lib/api/schema.ts` **contains the operation id** of the new endpoints, and that the
   frontend's `api` client call sites use the generated `paths` type. The `lib/api/README.md`
   says this folder is *"generated and never edited by hand"*, and the **architecture
   test** already reserves the folder.

3. **A schema change that breaks the client fails the build.** `test_contract.py` already
   fails when the committed schema drifts from the live API, and the frontend's
   `typecheck` fails when a call site no longer typechecks against `schema.ts`. So the
   chain is: **change the API → the committed schema no longer matches → the backend
   suite fails; and if the schema is regenerated but the client is not, the frontend's
   typecheck fails.**

**The probe proves the chain.** A mutation probe changes an API response shape and
asserts the contract test fails. That is what makes the claim "a schema change that
breaks the client fails the build" an *evidence* rather than an *assertion*.

---

## D11 — The PII sweep is against the **allowlist**, and it sweeps **the new paths**

AD-13: *"no email address, no city, no event title, no secret of any kind reaches a log
sink, asserted against the logger adapter's allowlist."*

The allowlist exists (`adapters/logging/redaction.py::ALLOWED_FIELDS`) and it is
deliberately narrow: ids, counts, durations, slugs — **never free text**. And the
formatter is designed so that project loggers never interpolate their args at all.

**The sweep runs the real paths and captures the real logs.** The new paths are:
the digest composition, the digest read, the detail read, the detail open, and the
saved-events write. Each is exercised, and the captured output is asserted against
three rules:

1. **No email address.** The scrubber's email pattern turns one into `[email]`, so the
   sweep asserts no `@`-bearing address survives.
2. **No city.** The user's city is a piece of personal information, and the sweep
   asserts it does not appear.
3. **No event title.** The hardest one, because free text is unrecognisable by
   pattern — which is exactly why the formatter's rule is *"project loggers never
   interpolate their args"*. So the sweep asserts the **title** does not appear.

**Plus the allowlist check itself:** every **extra** field on a captured record is
either in `ALLOWED_FIELDS` or the literal `[redacted]`. That is the structural form of
"asserted against the logger adapter's allowlist" — it does not depend on knowing which
particular PII to look for.

---

## D12 — The accessibility gates hold on **both** new surfaces

`axe-core` zero serious/critical, Lighthouse ≥95.

**The axe half is done** — by the two frontend items' own axe gates: the digest home's
over four documents, the detail screen's over five. **This item confirms both still
pass**, and does not duplicate them.

**The Lighthouse half is the honest gap.** Lighthouse measures a rendered page in a
browser under a throttled network. **Playwright is not installed and this item does not
install it** — the same scope decision the previous two intents' proofs made and
recorded.

So the criterion is met **in part**, and the part that is not met is **named**, not
quietly ticked:

- ✅ `axe-core` zero serious/critical on both surfaces, in CI.
- ⚠️ **Lighthouse ≥95 is unverified.** There is no browser in this stack.

**The substitute is a static check of what Lighthouse would measure** that *can* be
measured here: the accessibility-related things Lighthouse scores that jsdom does not
compute — **colour contrast** (computed from the token file and the rendered pairs) and
**the landmark and heading structure** (already in the axe gate).

**Colour contrast is worth doing properly**, because it is the one Lighthouse criterion
the axe gate *cannot* cover (jsdom computes no layout, so `color-contrast` is disabled
there), and it is a real risk in this codebase: the terracotta accent on the ink-inverse
fill is exactly the kind of pairing that can fail.

So this item computes the contrast of the **token pairs the two surfaces actually use**,
against WCAG 2.1's thresholds (4.5:1 for body text, 3:1 for large text and for
non-text indicators like the confidence dots). **This is a static computation from the
token file, not a Lighthouse run** — and it is recorded as such.

---

## D13 — Every test in this item **can fail**, and the probes are the evidence

*"Every test in this item can fail. No placeholder assertions, no `or`-fallbacks, no
test that passes because a value is absent. Each one is verified to fail when the
behavior it pins is deliberately broken, and the run log records that it was checked."*

**The mechanism is the mutation probe**, which the run already has
(`tests/e2e/mutation_probe_e2e.py`): apply one real bug to the implementation, run the
suite, and require that **at least one test fails**. A probe that passes the suite means
the tests do not prove that rule.

**This item extends the probe file with its own probes**, one per contract rule it
claims to pin:

| Probe | What it breaks | What must fail |
|---|---|---|
| the detail read imports the Event Fit read | AD-10's frontend wall | the frontend structural test |
| the digest read calls the ranking function | "no explanation at view time" | the AST call test |
| the detail read calls `compose_digest` | "no explanation at view time" | the AST call test |
| the read writes a composition row | "no explanation at view time" | the DB row-count test |
| a ranking weight moves | FR-22's lock | the constants test |
| the detail page reads `.personal` outside the guard | "a public surface never reads personal" | the data-flow test |
| the composition's `transaction.atomic` spans both schemas | AD-3 | the composition-separation test |

**The probes are recorded in the run log** — the criterion says so explicitly, and the
probe harness prints a line per probe.

---

## D14 — The `e2e` scenario lives in `tests/e2e/`, and the contract tests in `tests/architecture/`

The two halves of this item go where the run's convention puts them:

- **The scenario** → `backend/tests/e2e/test_digest_and_detail_proof.py`, next to the
  other proofs.
- **The contract tests** → `backend/tests/architecture/`, next to the walls they extend.

**The frontend's half of D5a** goes in `frontend/tests/`, next to the other boundary
tests — because it is a **frontend** import-graph rule and the frontend's test runner
is what can see it.

---

## The drift table

| # | The drift | The resolution |
|---|---|---|
| 1 | The work item's scenario says the user "opens `/`, sees three cards… taps one…". | **The backend half is proved here; the rendered half was proved by the two frontend items.** A browser dependency is a scope decision this item does not make silently (the previous two intents' proofs say the same). The *claim* the scenario makes — the card and the breakdown are two projections of one persisted row — is a claim about the database, and the database is what the scenario walks. |
| 2 | The AC asks for "Lighthouse ≥95". | **Not verified.** There is no browser in this stack and this item does not install one. The *substantive* part of the criterion — `axe-core` zero serious/critical on both surfaces — is met, and **colour contrast** — the one Lighthouse criterion the axe gate cannot cover — is computed statically from the token file. Recorded, not quietly ticked. |
| 3 | The AC asks that `personalization` "still cannot import `apps.ingestion.event_fit`… with the existing package-level contract unrelaxed". | **Already true**, and the check is that it stays true: the contract still names the *package* with the `.*` wildcard, `make lint-imports` passes, and the AST wall's **re-export probe** still catches the two-line bypass. The proof is the probe, not the contract's presence. |
| 4 | The AC asks for the FR-22 weights "read from `shared/constants.py` and pinned". | **Already pinned** by `tests/shared/test_constants.py`. What this item adds is the **probe**: a weight is changed, the suite must fail. A pin nobody has watched fail is a comment. |
| 5 | The AC asks that `tests/worker/test_tick.py` pass "unchanged". | The file is **not edited**. The evidence is that it passes and that git reports no diff to it. |
| 6 | The work item says the empty-state path shows "FR-8's card, with its copy and its city line". | The **backend** proves the `empty` status and its city line. The **copy** is the frontend's, and it was proved by the digest home item. Both halves are asserted; neither is re-implemented. |
| 7 | The work item names "the logger adapter's allowlist" (AD-13). | The allowlist is `adapters/logging/redaction.py::ALLOWED_FIELDS`, and the sweep asserts **every extra field** on a captured record is either allowlisted or `[redacted]` — so the assertion does not depend on guessing which PII to look for. |
