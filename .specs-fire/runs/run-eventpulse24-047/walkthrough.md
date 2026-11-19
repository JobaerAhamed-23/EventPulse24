---
run: run-eventpulse24-047
work_item: fr22-published-formula
intent: traceability-gap-closure
generated: 2026-11-19
mode: validate
---

# Walkthrough: FR-22 publishes a formula the product does not compute

## What this run decided

The **five-term as-built formula is canonical**, ratified under new **Amendment A-25**.
FR-22's weights table now maps each published component to the term that evaluates it, so a
reader computing a score by hand from the PRD arrives at the number on the card.

**No weight moved.** `shared/constants.py` is untouched; `RANKING_WEIGHT_SUM == 1.00` still
holds; `domain/ranking.py` is unchanged. One test was added.

## The work item's premise was false

The item, filed 2026-11-17, said:

> the **PRD still publishes the four-term version as immutable**, with no amendment saying
> otherwise … the one document FR-22 names as the source of the published formula is the
> one document that does not know the formula changed.

**It knew.** `prd.md:751` carried the amendment — dated 2026-11-11, publishing the five-term
expression with a per-term rationale, citing `docs/adr/ADR-0025.md` (Accepted, same date).
It landed in commit `59df1a9`, before the doc-trace pass that raised the finding.

So this run's job was not the one on the tin.

## What was actually wrong

### 1. The amendment ID collided — the real defect

| ID | What it is | Where | Date |
|---|---|---|---|
| **A-10** | Browse surface, 6th authed route | PRD, DESIGN.md, EXPERIENCE.md, 3 mockups, ledger | 2026-09-06 |
| **A-10** | The ranking formula amendment | `prd.md:751`, ADR-0025's `Amends:` | 2026-11-11 |

Two amendments, one ID, eight days. The Amendment Ledger scored A-10 `Consistent` on the
strength of the Browse propagation while reading straight over the ranking one.

**For a convention whose premise is that an ID appears in every document a change touches,
a reused ID is worse than a missing tag: a missing tag reads as a gap, a reused one makes
the ledger confidently wrong.**

The ranking amendment moved to **A-25** because it was the newer of the two and cited in
only two places, against Browse's five documents and three mockups. Nothing about its
substance changed — it was **re-minted, not rewritten**.

### 2. FR-22 contradicted itself

The locked table published `w1 preference_graph_match = 0.40`. Two paragraphs below, the
amendment asserted "the MVP weights are unchanged" and then implemented `interest_overlap`
at **0.35**. Both inside one requirement.

A reader computing by hand from the table got a different number from one computing from
the amendment — the precise *"arithmetically checkable while producing a different number
from the one on the card"* failure `domain/ranking.py` refuses to create with inert weights.
The module was right; the PRD's presentation hadn't caught up.

The table is now four columns, and **both weight columns sum to 1.00** — the check a reader
should make:

| Published component | Published weight (locked) | Implemented term (A-25) | Implemented weight |
|---|---|---|---|
| `w1` preference_graph_match | 0.40 | `interest_overlap` | 0.35 |
| `w2` source_reliability | 0.25 | `source_reliability` | 0.25 |
| `w3` recency_fit | 0.20 | `recency` | 0.20 |
| `w4` novelty_vs_exploration | 0.15 | — absent; needs FR-25 | — |
| — | — | `city_match` | 0.10 |
| — | — | `confidence` | 0.10 |
| **Total** | **1.00** | | **1.00** |

`w1` gives up 0.05 and `w4` gives up all 0.15; the freed 0.20 goes to `city_match` and
`confidence`. No term is pinned to a constant — an absent term is absent from the
expression.

### 3. Three stale cross-references

- `[ASSUMPTION-11]` cited **A-3**, never updated. → now cites A-25 as superseding it.
- The PRD frontmatter's amendment list didn't mention the ranking amendment at all. → added.
- FR-22's own **heading** read "(revised by Amendment A-3)". → now names A-25 as superseding.

## What changed

| File | Change |
|---|---|
| `prd.md` | FR-22 heading; weights table reconciled; A-10 block re-minted as **A-25** plus a paragraph on why; `[ASSUMPTION-11]`; frontmatter amendment list |
| `docs/adr/ADR-0025.md` | `Amends:` → PRD Amendment A-25, recording it was A-10 until 2026-11-19 |
| `EXPERIENCE.md` | Both as-built formula notes tagged `(PRD **Amendment A-25**)` beside their ADR-0025 pin |
| `TRACEABILITY.md` | A-3 → **superseded by A-25**; A-10 scoped explicitly to Browse; **A-24 and A-25 rows added**; closing note count 2 → 1; Open-items bullet rewritten as DECIDED |
| `backend/tests/shared/test_constants.py` | +1 test |
| `work-items/fr22-published-formula.md` | frontmatter → completed |

### The ledger predicted its own close

The closing note had said the right fix "is probably a *new* amendment ID rather than
stretching A-3 to cover a change it never made." That is exactly what happened, and the note
now says so. **Inconsistent amendments: 2 → 1.** The one remaining is the A-11–A-20 block,
a convention question the ledger has re-flagged since September.

## The test that was added

`test_the_prd_publishes_the_weights_the_product_computes`

The existing `test_the_ranking_weights_have_an_amendment_that_says_so` reads ADR-0025 and
asserts every weight appears there — proving the weights are **authorised**. It never
checked the PRD, and FR-22's promise is that they are **published**:

> The formula and weights are published in the PRD and immutable post-launch … A user
> reading the PRD can compute the Confidence Pulse for any Event given the inputs.

The new test slices `prd.md` between `#### FR-22` and `#### FR-23` and asserts all five
`RANKING_WEIGHT_*` constants appear in it. **Nothing executable would have caught the
contradiction that sat in FR-22 for eight days. Now something does.**

**It was probed rather than trusted:** mutating `0.35` → `0.99` across the FR-22 section
fails it; restoring passes.

## Two things the review caught

**1. The first reconciliation deleted the published weights.** The initial table showed only
the implemented values — 0.40 and 0.15 survived in prose alone. That is the most serious
thing that happened in this run: a reconciliation that removes the published values from the
published table, in the name of fixing a publication defect, takes away the very thing FR-22
protects. It would also have left `[ASSUMPTION-11]`'s "`w1=0.40 …` are locked" pointing at a
table that no longer showed them. **Fixed** — published weight is now its own column.

**2. FR-22's heading named a superseded amendment.** Not found by inspection: the mutation
probe's failure message printed the section's first line, and the stale heading was in it.
The plan's grep list looked for `Amendment A-10` and for A-3 in `[ASSUMPTION-11]` — not in
the heading. **A probe that was run to test a test found a documentation defect.**

## Tests

| Suite | Result |
|---|---|
| Full backend suite | **7477 passed**, 3 pre-existing failures, 7 skipped (5:06) |
| `tests/shared/` + `tests/domain/` + `tests/architecture/`, after review fixes | **1828 passed** |
| `ruff check` / `ruff format --check` | clean |
| `lint-imports` | **20 contracts kept, 0 broken** |
| Tests added | **1**, probed by mutation |

The 3 failures are `tests/delivery/test_preferences_api.py` — `ScheduledSend.DoesNotExist`,
pre-existing across runs 041, 046 and 047, verified against base commit `b8c6b21`. **They
belong to no work item.** Worth filing one before they become scenery.

## What is left

The `traceability-gap-closure` intent now has **one open item**:

| Work item | Status |
|---|---|
| `settings-privacy-ranking-transparency` | pending, medium, `confirm` — **now unblocked** |

FR-22's testable consequence — *"Settings → Privacy → 'Ranking algorithm version' shows the
current weights and the last-amendment date"* — is unbuilt. `frontend/app/settings/` has no
`privacy` route, and nothing in `frontend/` renders a formula. No user is being shown a
wrong formula; the promise is simply unkept. When it is built, the weights must be **served
from `shared.constants`**, never hard-coded in the frontend — a second copy of those numbers
on the one page whose job is that there is only one would drift silently, which is the
failure FR-22 exists to prevent.

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-047*
