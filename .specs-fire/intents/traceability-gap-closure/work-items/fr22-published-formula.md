---
id: fr22-published-formula
title: FR-22 publishes a formula the product does not compute
intent: traceability-gap-closure
complexity: high
mode: validate
status: pending
depends_on: []
created: 2026-11-17
---

# Work Item: FR-22 publishes a formula the product does not compute

## Description

**Found while trying to tag Amendment A-3, and the reason that tag was not applied.**

FR-22's promise is not the formula — it is the *publication* of the formula. The PRD says
the weights are **"published in the PRD and immutable post-launch** to honor the 'Trust
through transparency' principle", and EXPERIENCE.md §2 row 9 commits
`/settings/privacy` to showing *"the formula, weights table, bucket boundaries, amendment
history, and pledge"* to users.

**The published formula has four terms. The product computes five.**

| PRD FR-22 (revised by A-3) | `shared/constants.py` + `domain/ranking.py` |
|---|---|
| `0.40 × preference_graph_match` | `0.35 × interest_overlap` |
| `0.25 × source_reliability` | `0.25 × source_reliability` |
| `0.20 × recency_fit` | `0.20 × recency` |
| `0.15 × novelty_vs_exploration` | — (no input exists) |
| — | `0.10 × city_match` |
| — | `0.10 × confidence` |

**The divergence is deliberate, documented and well-reasoned — on the code side.**
`domain/ranking.py` explains it at length: `preference_graph_match` and
`novelty_vs_exploration` depend on FR-25's preference graph, which did not exist when
ranking shipped, and the module refuses to carry them as inert weights because *"the
published formula would stay arithmetically checkable and still produce a different number
from the one on the card, which is a worse trust failure than a reduced formula because it
looks verifiable."* That reasoning is sound. It is pinned as `RANKING_WEIGHTS_AMENDMENT =
"ADR-0025"`.

**What is missing is the other half of the trip.** The divergence is pinned to an ADR and
recorded in EXPERIENCE.md's as-built note — and the **PRD still publishes the four-term
version as immutable**, with no amendment saying otherwise. So the one document FR-22 names
as the source of the published formula is the one document that does not know the formula
changed.

**Why this blocks the A-3 tag.** The amendment convention is that an ID appears in every
document a change touches. Tagging EXPERIENCE.md's confidence section "Amendment A-3" would
assert that the section describes A-3's revision. It describes a *different* formula,
pinned to a different record. The tag would make the Amendment Ledger read clean over a
live inconsistency — which is the one outcome `doc-trace` exists to prevent.

## Acceptance Criteria

- [ ] A decision on which formula is canonical, taken by a human: amend FR-22 in the PRD to publish the five-term as-built formula, or change the code to compute what the PRD publishes.
- [ ] **If the PRD is amended:** a new Amendment ID is minted, and it appears in the PRD, DESIGN.md/EXPERIENCE.md and ADR-0025 — the convention applied properly, rather than A-3 being stretched to cover a change it never made.
- [ ] FR-22's bucket boundaries are checked against the new weights: ≥0.85 = 5 dots and so on were set for a four-term formula and may not partition the five-term range the same way.
- [ ] `/settings/privacy`'s ranking-transparency section shows the formula **the product actually runs**, since that surface is FR-22's transparency promise made visible.
- [ ] Only then: the Amendment Ledger entry for A-3 is resolved — either tagged, or recorded as superseded by the new amendment.

## Technical Notes

**Do not "fix" this by editing the UX docs.** They already describe the as-built formula
correctly; the gap is between the PRD and reality, and tagging around it would hide it.

**Check whether a user-facing surface currently shows the wrong formula.** EXPERIENCE.md
commits `/settings/privacy` to a weights table. If that screen exists and renders the PRD's
four weights, a user is being shown a formula they cannot reproduce from their own card —
which is the precise trust failure FR-22 was written to prevent, and it would make this
urgent rather than tidy.

**`domain/ranking.py`'s module docstring is the best statement of the problem** and should
be read before anyone argues for the four-term version; the reasoning for dropping the two
absent terms is already made there and does not need re-deriving.

## Dependencies

(none)
