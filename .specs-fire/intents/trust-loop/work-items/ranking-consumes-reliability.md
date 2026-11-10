---
id: ranking-consumes-reliability
title: Paying the ranking debt — source reliability enters the Relevance Pulse
intent: trust-loop
complexity: high
mode: validate
status: pending
depends_on:
  - reliability-recompute-and-escalation
created: 2026-11-10
---

# Work Item: Paying the ranking debt — source reliability enters the Relevance Pulse

## Description

`domain/ranking.py` documents a debt: FR-22's `0.25 × source_reliability` is "absent from the expression", because "FR-16 is unbuilt". The reduced formula already uses all of its weight: `RANKING_WEIGHT_INTEREST = 0.45`, `RECENCY = 0.25`, `CITY = 0.20` and `CONFIDENCE = 0.10` (`shared/constants.py:659-662`), summing to 1. `tests/shared/test_constants.py` pins those weights, and FR-22 calls the weights "immutable post-launch". Adding the term is therefore a **reweighting of every user's digest**, not an addition.

The same module also argues against **inert weights**: "a term pinned to a constant … would" misrepresent the formula. At launch, every source has fewer than 30 observations, so every source sits at or near the 0.50 prior, and the new term would be close to a constant until data accrues.

## Acceptance Criteria

- [ ] The design proposes the new weights and their justification against FR-22's published formula. It also states whether this needs a PRD amendment or is a step *toward* the published weights, which would make the reduced weights a temporary state the PRD already anticipates.
- [ ] **The inert-at-launch problem is answered explicitly.** Options include:
  - enter the term only for sources past the minimum N
  - enter it for everyone, with the prior as a neutral value, and say why that is not "inert" under the module's own definition
  - centre it, so that 0.50 contributes nothing relative to other sources

  The design chooses one, and the module docstring is updated to match.
- [ ] `RankingInputs` gains the source's reliability, read through the published `ingestion` read the recompute item provides. There is no N+1 query, and the bound on query count is tested, as the digest's other reads already are.
- [ ] Slots 2 and 3 (`score_slot_2` and `score_slot_3`, whose FR-5 formulas multiply by `source_reliability`) are updated, or are explicitly left reduced with a reason. Their docstrings currently name FR-16 as the missing input.
- [ ] **Explanations already persisted are not recomputed (AD-10).** The design states what happens to stored `DigestComposition` rows and to hysteresis (`apply_hysteresis`) when the weights change, so that no user sees a card's Confidence Pulse jump with no change in the event.
- [ ] The weight constants are re-pinned in `tests/shared/test_constants.py` with the amendment reference. The pin test must still fail on an unreferenced change.
- [ ] **The proof:** two otherwise-identical events, one from a source scored 0.2 (past the minimum N) and one from a source scored 0.8, rank in that order. A test for each slot that uses the term. A mutation (removing the term) fails them.

## Technical Notes

High complexity, so this item gets a design doc. `relevance_score` is at `domain/ranking.py:263`, `score_slot_2` at :487, `score_slot_3` at :504, and `apply_hysteresis` at :309. Check `tests/e2e/mutation_probe_contract_e2e.py`, which references the ranking weights, before changing them.

## Dependencies

- reliability-recompute-and-escalation
