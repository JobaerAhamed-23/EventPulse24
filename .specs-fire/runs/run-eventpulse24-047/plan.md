---
run: run-eventpulse24-047
work_item: fr22-published-formula
intent: traceability-gap-closure
mode: validate
checkpoint: plan
approved_at: pending
---

# Implementation Plan: FR-22 publishes a formula the product does not compute

## Approach

**Documentation only, plus one optional test.** No weight value moves; no module changes.

The approved design established that the work item's premise is false — the PRD *does*
carry the amendment, at `prd.md:751`, dated 2026-11-11, citing `docs/adr/ADR-0025.md`. What
is actually broken is that **the amendment reuses ID A-10**, which has belonged to the
Browse surface since 2026-09-06; that **FR-22 contradicts itself** about whether the weights
changed; and that **two cross-references are stale**.

This run ratifies the five-term as-built formula, re-mints the ranking amendment as
**A-25**, reconciles FR-22 internally, and corrects the ledger.

## Files to Create

| File | Purpose |
|------|---------|
| (none) | |

## Files to Modify

| File | Changes |
|------|---------|
| `…/prds/prd-EventPulse24-2026-08-19/prd.md` | FR-22: re-mint the `Amendment A-10 (2026-11-11)` block as **A-25**; reconcile the "Initial weights (MVP, locked)" table against it |
| `…/prd.md` `[ASSUMPTION-11]` (line 1308) | Cite A-25 rather than A-3 |
| `…/prd.md` frontmatter `amendments:` | Add the A-25 line |
| `docs/adr/ADR-0025.md` (line 5-6) | `Amends: … via PRD Amendment A-10` → A-25, and the matching block reference |
| `…/ux-designs/…/EXPERIENCE.md` (line 407, and the frontmatter copy at line 6) | Tag the as-built formula note with A-25 beside its existing ADR-0025 pin |
| `…/traceability/TRACEABILITY.md` | Ledger: A-3 superseded by A-25; A-10 row scoped explicitly to Browse; new A-25 row. Open-items bullet for `fr22-published-formula` rewritten as DECIDED |
| `.specs-fire/…/work-items/fr22-published-formula.md` | frontmatter `status: pending` → `completed` |

## Tests

| Test File | Coverage |
|-----------|----------|
| `backend/tests/shared/test_constants.py` *(optional)* | Extend `test_the_ranking_weights_have_an_amendment_that_says_so` so the PRD's FR-22 must carry the same five weights as `shared/constants.py`, not just the ADR |

## Technical Details

### The weights table, reconciled

FR-22 currently publishes this, two paragraphs above an amendment that implements something
different:

```
| Weight | Component              | Value |
| `w1`   | preference_graph_match | 0.40  |
| `w2`   | source_reliability     | 0.25  |
| `w3`   | recency_fit            | 0.20  |
| `w4`   | novelty_vs_exploration | 0.15  |
```

It becomes a mapping, so the published lineage stays visible and the implemented reality is
beside it:

```
| Published component (locked)  | Implemented term (A-25)      | Weight |
| `w1` preference_graph_match   | `interest_overlap`           | 0.35   |
| `w2` source_reliability       | `source_reliability`         | 0.25   |
| `w3` recency_fit              | `recency`                    | 0.20   |
| `w4` novelty_vs_exploration   | — absent, needs FR-25        | —      |
| (the 0.05 + 0.15 freed above) | `city_match`                 | 0.10   |
|                               | `confidence`                 | 0.10   |
|                               | **Total**                    | 1.00   |
```

This is **not a weight change** — `RANKING_WEIGHT_*` in `shared/constants.py` is untouched,
and `RANKING_WEIGHT_SUM == 1.00` still holds. It is the same arithmetic A-10's prose already
states, lifted into the table so a reader computing by hand from the table gets the number
on the card.

The accounting, stated explicitly because it is the part a reader checks: `w1` gives up
0.05 (0.40 → 0.35) and `w4` gives up all 0.15; the 0.20 freed is taken by `city_match` (0.10)
and `confidence` (0.10).

### What the A-25 block must say

Everything A-10's block already says — it is well argued and is being **re-minted, not
rewritten** — plus one new paragraph recording why the ID changed: A-10 was already in use
for the Browse surface (2026-09-06), and an amendment convention whose premise is one ID per
change cannot have two.

### Ledger corrections

| Row | Now | After |
|---|---|---|
| A-3 | "**No — and deliberately left untagged** … See `fr22-published-formula`" | **Superseded by A-25.** A-3 locked the four published weights; A-25 records which term evaluates each. Not "tagged" — tagging A-3 onto the as-built sections would assert a revision they do not implement |
| A-10 | "A-10 (Browse, 6th authed route) … Consistent" | Unchanged in substance, scoped explicitly to Browse, with a note that the ranking amendment formerly sharing this ID is now A-25 |
| A-25 | — | New row: PRD FR-22, ADR-0025, EXPERIENCE.md — Consistent |

The ledger's own closing note ("**Inconsistent amendments: 2**") needs its count and prose
re-checked once A-3 is resolved.

### Verification

1. `grep -rn "Amendment A-10"` across `_bmad-output/` and `docs/` returns **only** Browse
   references — no ranking ones.
2. `grep -rn "A-25"` returns exactly the new, intended occurrences.
3. The five weights in FR-22's reconciled table match `shared/constants.py` exactly.
4. `backend/tests/shared/test_constants.py` passes (it reads ADR-0025 and asserts every
   weight appears there).
5. `git diff --stat` shows no change under `frontend/`, and none under `backend/` beyond the
   optional test.

## Based on Design Doc

Reference: `.specs-fire/intents/traceability-gap-closure/work-items/fr22-published-formula-design.md`

---
*Plan approved at checkpoint. Execution follows.*
