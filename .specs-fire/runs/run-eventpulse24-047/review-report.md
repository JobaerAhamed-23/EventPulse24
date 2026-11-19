---
run: run-eventpulse24-047
work_item: fr22-published-formula
intent: traceability-gap-closure
generated: 2026-11-19
status: reviewed
---

# Review Report: FR-22 publishes a formula the product does not compute

## Scope of review

Five planning documents, one ADR, one test file. The test file got an ordinary code review;
the documents were judged on structural validity, internal consistency, and whether a later
reader is left with a correct and complete picture.

| File | Change |
|---|---|
| `prd.md` | FR-22 heading, weights table, amendment block re-minted A-10 → A-25, `[ASSUMPTION-11]`, frontmatter |
| `docs/adr/ADR-0025.md` | `Amends:` citation |
| `EXPERIENCE.md` | Two as-built formula notes tagged A-25 |
| `TRACEABILITY.md` | Ledger A-3 / A-10 / A-24 / A-25; closing note; Open-items bullet |
| `work-items/fr22-published-formula.md` | frontmatter → completed |
| `backend/tests/shared/test_constants.py` | +1 test |

## Structural checks

| Check | Result |
|---|---|
| PRD frontmatter parses as YAML | ✅ 5 `amendments` entries |
| EXPERIENCE.md frontmatter parses as YAML | ✅ |
| FR-22 weights table well-formed | ✅ header and all rows 5 pipes after the fix below |
| Ledger table rows well-formed | ✅ |
| A-25 unique before minting | ✅ |
| No ranking reference to `Amendment A-10` remains | ✅ every remaining occurrence is Browse, plus the paragraph in FR-22 that explains the re-mint |
| A-25 propagation | ✅ prd.md 8, TRACEABILITY.md 7, ADR-0025.md 2, EXPERIENCE.md 2 |
| `shared/constants.py` untouched | ✅ no weight moved |
| `ruff check` / `ruff format --check` | ✅ |
| `lint-imports` | ✅ 20 contracts kept, 0 broken |

## Auto-fixed

### 1. The reconciled table dropped the published weights — the thing FR-22 exists to publish

**Found:** the first reconciliation replaced the locked-weights table with a two-column
mapping (component → implemented term → weight) that showed only the **implemented**
values: 0.35 / 0.25 / 0.20 / 0.10 / 0.10. The published weights — `w1` 0.40, `w4` 0.15 —
survived only in the prose beneath it.

**Why it mattered, and why it is the most serious finding in this run:** FR-22's entire
purpose is that the weights are *published and immutable*. A reconciliation that removes the
published values from the published table, in the name of fixing a publication defect, takes
away the very thing the requirement protects — and it would have left `[ASSUMPTION-11]`'s
"`w1=0.40, w2=0.25, w3=0.20, w4=0.15` are locked" pointing at a table that no longer showed
them.

**Fixed:** four columns — published component, **published weight (locked)**, implemented
term, implemented weight. Both weight columns sum to 1.00, with a line naming that as the
check a reader should make: *the published formula and the implemented one distribute the
same unit of weight, differently.*

**Re-verified:** table pipes consistent, `test_constants.py` 38 passed.

### 2. FR-22's heading still named a superseded amendment

**Found:** `#### FR-22: Confidence Pulse (revised by Amendment A-3)` — unchanged, while
A-3 was being recorded as superseded three sections away.

**How it surfaced:** not by inspection. The mutation probe for the new test printed the
FR-22 section's first line in its failure message, and the heading was in it. **A stale
reference the plan's own grep list would have missed**, because the plan looked for
`Amendment A-10` and `A-3` in `[ASSUMPTION-11]`, not in the heading.

**Fixed:** `(revised by Amendment A-3, superseded by Amendment A-25)`.

### 3. `ruff format` wanted one reformat of the new test

Mechanical. Formatted, re-checked, re-run.

## Review of the new test

`test_the_prd_publishes_the_weights_the_product_computes`

| Aspect | Assessment |
|---|---|
| Does it test the right thing? | ✅ The ADR check proves the weights are *authorised*; this proves they are *published*, which is what FR-22 actually promises. |
| Can it fail? | ✅ Proved by mutation — `0.35` → `0.99` in the PRD's FR-22 section fails it; restoring passes. |
| Failure message actionable? | ✅ Names the missing weight and says "Amend FR-22 and record the amendment" rather than reporting a bare missing substring. |
| Brittleness | ⚠️ It hard-codes the PRD path and slices between `#### FR-22` and `#### FR-23`. If the PRD moves or the heading style changes, it breaks. **Mitigated in the test itself**: the `exists()` assertion says "If the PRD has moved, move this test with it — do not delete it, because the publication is the requirement." A reader who hits it is told the right remedy. |
| Scope | ✅ Asserts presence of each weight, not the table's exact shape — so the document can be reformatted without breaking CI, which is the right sensitivity for a doc-reading test. |

## Not changed, and why

| Candidate | Decision |
|---|---|
| The A-25 block's body (per-term rationale, reliability-not-inert argument) | **Left verbatim.** It is well argued and was being re-minted, not rewritten. Only the header and a new ID-change paragraph were added. |
| Browse's A-10 across PRD, DESIGN.md, EXPERIENCE.md and 3 mockups | **Left.** Correct and consistently propagated. The ledger row gained a scope note rather than a rename. |
| `shared/constants.py`, `domain/ranking.py` | **Left.** Their reasoning was ratified, not revised. |
| `TRACEABILITY.md:19` narration of the 2026-11-17 regeneration | **Left.** Accurate as history, for the same reason as in run 046. |
| The `.memlog.md` A-10 references | **Left.** Append-only session logs; all four are Browse anyway. |

## Open after this run

| Item | Note |
|---|---|
| `settings-privacy-ranking-transparency` | FR-22's transparency surface does not exist. Created at Checkpoint 1 with your approval; depends on this work item, which is now complete, so it is unblocked. |
| A-11 – A-20 ledger block | Still the one remaining inconsistent amendment. A **convention** question the ledger has re-flagged at every regeneration since September; it recommends deciding it once. Out of scope here. |
| 3 `test_preferences_api.py` failures | Pre-existing across runs 041, 046 and 047. **Owned by no work item.** |

## Findings Summary

| # | Finding | Severity | Status |
|---|---|---|---|
| 1 | Reconciled table dropped the published weights FR-22 exists to publish | **High** | **Auto-fixed** |
| 2 | FR-22 heading named a superseded amendment | Low | **Auto-fixed** |
| 3 | `ruff format` reformat of the new test | Trivial | **Auto-fixed** |
| 4 | New test hard-codes the PRD path and heading boundaries | Low | **Accepted** — mitigated by an actionable assertion message |

---
*Generated by specs.md - fabriqa.ai FIRE Flow Run run-eventpulse24-047*
