---
run: run-eventpulse24-040
work_item: amendment-tag-propagation
intent: traceability-gap-closure
date: 2026-11-17
---

# Report: Propagate the A-2 and A-3 amendment tags into the UX docs

**Partially done, on purpose. A-2 is tagged; A-3 is not, and the reason is a finding.**

## A-2 — done

`DESIGN.md` → `component.card.pulse.digest.category.discovery` now carries
**(Amendment A-2 — serendipity slot.)** with one clause saying what the amendment changed:
Slot 3 is a serendipity category by formula, and its Why-this Tag reads `discovery` or
`new-to-you` rather than a category name.

**The prose was checked before it was tagged**, as the work item required. The entry
already describes the amended behaviour — the slate stripe at 0.85 opacity *plus a
`discovery` micro-tag* is A-2's rule in visual form — so the tag names what is there rather
than decorating something stale.

EXPERIENCE.md has no serendipity section to tag (0 matches for "serendipity" or
"new-to-you"), so DESIGN.md is the whole of A-2's UX surface.

## A-3 — stopped, and raised as `fr22-published-formula`

The work item said: *"If either section still describes the pre-amendment behaviour, that is
a different and larger finding — stop and report it rather than tagging a stale
paragraph."* This is that case, in a sharper form than expected — the UX docs are **not**
stale. The PRD is.

**FR-22 publishes a four-term formula. The product computes five.**

| PRD FR-22 (revised by A-3) | `shared/constants.py` |
|---|---|
| `0.40 × preference_graph_match` | `0.35 × interest_overlap` |
| `0.25 × source_reliability` | `0.25 × source_reliability` |
| `0.20 × recency_fit` | `0.20 × recency` |
| `0.15 × novelty_vs_exploration` | — |
| — | `0.10 × city_match` |
| — | `0.10 × confidence` |

The divergence is deliberate and well-argued in `domain/ranking.py` — the two dropped terms
depend on FR-25's preference graph, which did not exist, and the module refuses to carry
them as inert weights because a formula that stays *"arithmetically checkable and still
produces a different number from the one on the card"* is a worse trust failure than a
reduced one. It is pinned as `RANKING_WEIGHTS_AMENDMENT = "ADR-0025"`, and EXPERIENCE.md
already describes the five-term version as-built.

**What is missing is the PRD.** FR-22's promise is that the weights are *"published in the
PRD and immutable post-launch"*, and EXPERIENCE.md §2 row 9 commits `/settings/privacy` to
showing users "the formula, weights table, bucket boundaries". The one document named as
the source of the published formula does not know the formula changed.

**So tagging A-3 would have been the wrong act.** It would assert that EXPERIENCE.md's
confidence section implements A-3's revision, when it documents a different formula pinned
to a different record — making the Amendment Ledger read clean over a live inconsistency,
which is precisely what `doc-trace` exists to prevent.

## Effect on the Amendment Ledger

| Before | After |
|---|---|
| A-2 inconsistent | **resolved** |
| A-3 inconsistent | **still open — now with a cause and a work item** |
| A-11–A-20 block | unchanged (the convention question) |

Inconsistent amendments go from 3 to 2, and the remaining A-3 row is no longer a
tag-propagation miss; it is a pointer at `fr22-published-formula`.

## Gates

Documentation only — no code, no tests, no build. `DESIGN.md` is the single changed file,
one entry amended in place. No requirement, token, component or mockup was touched.
