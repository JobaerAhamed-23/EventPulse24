---
id: reliability-score-domain
title: The arithmetic of trust — FR-16's score as pure functions
intent: trust-loop
complexity: medium
mode: confirm
status: completed
depends_on: []
created: 2026-11-10
run_id: run-eventpulse24-026
completed_at: 2026-11-10T16:34:25.842Z
---

# Work Item: The arithmetic of trust — FR-16's score as pure functions

## Description

FR-16's statistical guardrails are precise enough to be pure functions with no database: a beta-binomial posterior with α = β = 5, a minimum of 30 observations, a floor for new sources, an escalation line, and spike detection. They belong in `domain/`, beside `confidence.py` and `ranking.py`, as Decimal-only functions that the recompute job and its tests call.

## Acceptance Criteria

- [ ] `domain/reliability.py` exposes:
  - `posterior_mean(positives, negatives)`: (α + positives) / (α + β + n), as a two-decimal `Decimal` in [0, 1]. Floats are refused, matching `checked_confidence`.
  - `reliability_score(positives, negatives)`: applies the minimum-N and floor rules below.
  - `should_escalate(score, n)`: true when the score is below 0.3 **and** n ≥ 30.
  - `is_spike(previous, current)`: a drop of 3× or more week over week.
- [ ] **Resolve the PRD's internal tension, and record the resolution.** FR-16 says a source "needs at least 30 dismissal observations before its score moves" and *also* "a new source (under 30 observations) cannot have its score drop below 0.32". If the score doesn't move under 30 observations, it stays at 0.50 and the floor is unreachable. The plan proposes a reading, for example "under 30 the posterior moves but is clamped at 0.32", for confirmation. The tests pin the chosen reading, and the PRD amendment it implies is noted.
- [ ] **Define "3× drop" exactly.** A ratio of 3× on a score that sits in [0, 1] near 0.5 is close to unreachable. The plan states whether it means `previous / current ≥ 3`, a 3× *rate* of negative observations, or something else, and confirms it.
- [ ] All constants (α, β, the minimum N, the floor, the escalation line, the spike multiplier) live in `shared/constants.py`, and `tests/shared/test_constants.py` pins them.
- [ ] Tests cover:
  - a new source at 0.50
  - one negative not cratering the score
  - the floor under 30 observations
  - the boundary at exactly 30
  - escalation at 0.29 and 0.30, with n = 29 and n = 30
  - spike detection at the threshold and just below it
  - float refusal
  - property tests: the score is always in [0, 1], and is monotone in negatives

## Technical Notes

This is pure domain code with no Django import, enforced by the existing import-linter contracts. The dismissal-rate input (FR-25) is unbuilt. The function signature takes positive and negative counts, so dismissals become another source of negatives later, with no signature change. That seam should be documented in the module docstring.

## Dependencies

(none)
