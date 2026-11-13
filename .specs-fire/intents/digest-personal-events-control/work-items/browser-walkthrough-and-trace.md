---
id: browser-walkthrough-and-trace
title: The Walkthrough — Seeing It Work, and Proving the Trace
intent: digest-personal-events-control
complexity: medium
mode: confirm
status: completed
depends_on:
  - digest-composition-proof
  - onboarding-opt-out-decision
created: 2026-11-13
run_id: run-eventpulse24-030
completed_at: 2026-11-13T02:39:46.363Z
---

# Work Item: The Walkthrough — Seeing It Work, and Proving the Trace

## Description

The intent's verification is **automated tests plus a real browser walkthrough** — not
mockups, and not a test suite alone. This item is the walkthrough, and the trace that
proves the intent actually closed what it set out to close.

**The walkthrough** drives the real thing against a running stack: sign in, find the
control, toggle it, and see the digest change. It is the check that the surface is
*reachable* and *understandable* — two things a passing test suite cannot tell you. A
test can prove the toggle calls the right endpoint; only a browser can prove a user
finds it.

**The trace** is the closing accounting. This intent opened because a traceability
matrix reported a gap; it should close by leaving the matrix more truthful than it found
it. Three things are traceable here:

1. **FR-19's opt-out.** The PRD's testable consequence at `prd.md:605` — *"A user can
   opt out of personal events appearing in the Pulse Digest."* — moves from *satisfied by
   machinery, unmet by experience* to *met*.
2. **The intent itself.** `.specs-fire/state.yaml` records this intent and its work
   items, and the run records what was actually built.
3. **The corrections the audit surfaced**, which belong to a **separate** intent and must
   be named rather than quietly fixed here: the matrix mis-flags A-5 and A-7 as uncited
   (both are cited — `EXPERIENCE.md:64,229,1152` and `:1200`), it misses the **A-10 ID
   collision** (PRD `prd.md:751` defines A-10 as FR-22's formula amendment while
   `DESIGN.md:349` and `EXPERIENCE.md:294` define it as the Browse route), and its
   FR-16 remediation points at the wrong row (`EXPERIENCE.md` row 15 claims FR-13).

**The walkthrough reports what it finds.** If something is broken, it is reported, not
smoothed over — the same rule the `browse-surface` intent recorded.

## Acceptance Criteria

- [x] The full backend suite is green, with **no new failures** and no pre-existing failure left unexplained
- [x] The frontend test suite is green
- [x] `make client` produces **no diff** in `frontend/lib/api/` — the AD-19 contract gate, confirming no backend schema changed
- [x] The walkthrough is performed against a **running stack** with real data, and it covers: the control's initial state, the save succeeding, the failure path, the digest changing, and the control being findable from the UI
- [x] The walkthrough records **what actually happened**, including anything broken, in the run's walkthrough document — not a summary written from expectation
- [x] **FR-19's opt-out is traced to a working surface** — the matrix's row for FR-19, and the trace this intent produces, both point at a place a user can reach
- [x] The A-5 / A-7 / A-10 / FR-16 corrections are **recorded as follow-up work**, not fixed inside this intent
- [x] `state.yaml` records this intent's work items as completed, and the run is recorded in `runs.completed`
- [x] Every deviation found during the walkthrough is either fixed and re-verified, or reported as a finding

## Technical Notes

- **The run's walkthrough document.** The FIRE naming convention puts a `walkthrough.md`
  in the run folder — `.specs-fire/runs/{run-id}/walkthrough.md`, created at run
  completion. Read the walkthrough from a recent run (run 029, `browse-surface`) before
  writing this one, so the format matches.
- **What to run.** `make test-backend` and the frontend test command (check the Makefile
  for the frontend target name — the Makefile's `test-e2e` target seeds browse data and
  needs `make up` and a running API). The e2e suite is a separate target and may not be
  part of this intent's proof.
- **Do not skip the `make client` check.** It is the cheapest possible confirmation
  that the "no backend change" constraint held, and it is a CI gate — running it locally
  turns a CI failure into a local one.
- **The walkthrough needs a real preference row.** The control shows the stored value, so
  the walkthrough should visit the screen **twice** — once as a user who has never
  touched the setting (it should read "on") and once after opting out (it should read
  "off"). A single visit proves the toggle renders; two prove it round-trips.
- **Prove the digest actually changed.** The point of the whole intent is that the
  opt-out changes what the user sees. The walkthrough should show the digest **before**
  and **after**, with a personal event inside the 48-hour eligibility window, so the
  change is visible rather than inferred.
- **The corrections are named, not fixed.** The A-10 ID collision in particular is a
  **corpus defect** — two different amendments share one ID, which makes the whole
  amendment ID space unreliable for any tool that reads it. Fixing it means renumbering
  and propagating across the PRD, DESIGN.md, EXPERIENCE.md and the mockups. **That is an
  intent of its own**, and folding it in here would put a corpus-wide renumbering inside
  a feature change — exactly the kind of scope bleed that makes a matrix stop being
  trustworthy.
- **State and matrix updates are the planner's and builder's work, not this item's** —
  this item produces the evidence; the artifacts are updated from it.

## Dependencies

- digest-composition-proof
- onboarding-opt-out-decision
