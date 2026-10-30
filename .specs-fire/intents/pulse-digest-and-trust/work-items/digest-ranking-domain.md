---
id: digest-ranking-domain
title: The ranking domain (slots, Relevance Pulse, buckets, hysteresis)
intent: pulse-digest-and-trust
complexity: high
mode: validate
status: completed
depends_on: []
created: 2026-10-30
run_id: run-eventpulse24-021
completed_at: 2026-10-30T13:02:28.917Z
---

# Work Item: The ranking domain (slots, Relevance Pulse, buckets, hysteresis)

## Description

Builds `backend/domain/ranking.py` — the pure, stdlib-only module AD-2 says ranking belongs in ("the algorithmic core that must be testable without a database — dedup identity derivation, UTC conflict detection, quiet-hours due-time shifting, **ranking**"). `domain/` already holds `conflict.py`, `confidence.py` and `event_fit.py`; this is the fourth of that family and follows their shape exactly: frozen dataclasses, an explicit `now` parameter, no clock read, no randomness, importable with Django uninstalled.

It contains four things: the **slot scoring** (FR-5 / Amendment A-2), the **Relevance Pulse** score (FR-22's formula), the **bucket mapping** with its exact boundaries, and the **hysteresis** rule. It also derives the **Why-this Tags**, because the tags must be the same facts the score was built from — AD-10's whole point is that the explanation and the decision cannot drift apart.

**The formula is reduced, and the reduction is the design.** FR-5 and FR-22 name four inputs this codebase does not have: `source_reliability` (FR-16 unbuilt — `Source` has no score field), `normalized_popularity` (no engagement, save-count or attendance signal exists anywhere), `geographic_distance_factor` (`Venue` has `city` and `country_code` but **no coordinates**, so haversine is not computable), and category tags (`Event` has no category field). The intent decided these are **omitted from the formula and named**, never pinned to constants that would leave a published formula with inert weights. `domain/event_fit.py` set this precedent when it refused to invent a "Free" tag: "they are added to Event Fit's rule set then, not faked now."

## Acceptance Criteria

- [ ] `domain/ranking.py` imports **stdlib only**, plus `shared.constants` and `shared.ids` — the same allowance `domain/event_fit.py` has. The existing `AD-2 domain is pure` import-linter contract covers it with no new entry needed; confirm that it does rather than assuming.
- [ ] **The Relevance Pulse score is a documented formula over inputs that exist**, with every omitted term absent from the expression rather than multiplied by a constant. The module docstring states the formula, names each of the four omitted inputs, says why it is unavailable in this codebase (not merely unimplemented), and names the FR that will supply it. The weights of the terms that remain are **named constants in `shared/constants.py`**, beside the confidence gates.
- [ ] The surviving inputs are: **interest-chip overlap** (the 10 fixed chips the user picked at onboarding), **start-time proximity** in the event's own IANA timezone, **extraction confidence**, and **city match as a band** — not a distance. A reader can compute any event's score by hand from these, which is FR-22's actual promise ("a user reading the PRD can compute the Confidence Pulse for any Event given the inputs").
- [ ] **Bucket mapping is FR-22's, verbatim and exact:** ≥0.85 → 5, ≥0.65 → 4, ≥0.45 → 3, ≥0.25 → 2, else 1. **No interpolation, never a bar.** The score is clamped to [0.0, 1.0] before mapping, and the rendered bucket is always an integer 1–5. Scores are `Decimal`, not float, for the same reason `domain/confidence.py` refuses floats: a float 0.85 is not `Decimal("0.85")` and would land a card in the wrong bucket. A test asserts **0.850 → 4 dots** (the lower bucket wins on an exact boundary) at every one of the five boundaries.
- [ ] **Hysteresis is a pure function of (previous bucket, previous score, new score)**, implementing EXPERIENCE.md §4: once a bucket is assigned for an event on a user's local calendar day, it holds for the rest of that day unless the raw score moves by **≥0.10** within the same day; across days it resets, and no bucket persists between days. The worked example is pinned as a test: 0.83 → 4; a same-day re-score to 0.86 (Δ0.03) stays 4; a re-score to 0.97 (Δ0.14) moves to 5. *(The deprecated `ranking-algorithm-transparency-desktop.html` says "±0.02"; EXPERIENCE.md's ≥0.10 governs under the spines-win rule. Record the deviation.)*
- [ ] **Slot scoring (A-2), as three named functions or one function with a slot parameter:**
  - **Slot 1 (must-know)** — prefers an eligible personal event within 48 hours; the fallback to the highest-scoring public event is the *caller's* composition decision, and this module only scores.
  - **Slot 2 (nearby)** — the standard score.
  - **Slot 3 (serendipity)** — the **preference term is inverted**, so the card is structurally the one the user's own signals would not have picked. This is the published anti-popularity bias expressed over the input that exists; the docstring says so explicitly, because substituting a different input for `(1 - normalized_popularity)` is a deviation from FR-5 and must be legible as one.
- [ ] **Why-this Tags are derived here**, as an ordered tuple of at most **3** keys, from the same inputs the score used — never from raw source text (AD-9). Slot 3's tag is **`discovery`** or **`new-to-you`**, never a category name (Glossary §3 / FR-25; UJ-1's `novel` is stale and does not govern). Tag keys are keys, not display strings: the presentation edge renders them, and `domain/` has no idea a render exists.
- [ ] **Day boundaries are computed in the relevant IANA timezone, never UTC** — the rule `domain/event_fit.py` is built around, and the one easiest to get wrong. The user's local calendar day (for hysteresis) comes from their digest timezone; the event's "tonight"-style proximity comes from the event's own zone. A test pins a DST transition for each.
- [ ] **Determinism:** the same inputs always give the same outputs. No randomness, no clock read, `now` explicit on every function that needs it. `domain/` coverage stays at **100%**, as it is today.
- [ ] Tests cover every bucket boundary at the exact value, hysteresis crossing and not crossing in both directions, each slot's scoring including the inverted term, tag derivation capping at 3, the Slot 3 tag rule, clamping above 1.0 and below 0.0, `Decimal` enforcement, and the two DST cases.

## Technical Notes

**This module is where the honesty of the whole intent lives.** Everything downstream persists what this computes and renders it beside a claim that it means something. If a weight here is inert, a user reading the formula is being misled — which is the trust-collapse failure PRD Risk 11 calls company-ending, arriving by a different road than AD-10's.

Follow `domain/event_fit.py`'s docstring discipline: it explains *why* taking the lower of two bands is the honest rule ("a weighted sum would need weights that nobody can justify without labelled data"). The same standard applies to every choice here, especially the inverted preference term standing in for anti-popularity.

The design doc must decide and record: the exact surviving formula and its weights; how interest-chip overlap is normalized to [0, 1] when the user picked 0, 1, 2 or 3 chips (a user who skipped onboarding has **no** chips, and that path must score sensibly rather than divide by zero); how the cold-start case is expressed, given **ADR-0007 does not exist** and gates all personalized weighting; and whether the score and the bucket are both persisted or the bucket is derived at write time.

FR-22 says a weight change without a PRD amendment is a CI-level test failure. Consider pinning the weights in a test that reads them from `shared/constants.py`, the way `tests/shared/test_constants.py` already pins each confidence threshold to its gate band.

## Dependencies

(none)
