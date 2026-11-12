---
id: matrix-regeneration-and-ledger
title: Regenerate the matrix, retire the findings that are no longer true
intent: traceability-reconciliation
complexity: medium
mode: confirm
status: completed
depends_on:
  - fr-20-reminder-defaults
  - fr-28-share-affordance
  - fr-49-saved-collections
  - fr-55-conflict-on-state-change
created: 2026-11-12
run_id: run-eventpulse24-028
completed_at: 2026-11-12T06:13:19.217Z
---

# Work Item: Regenerate the matrix, retire the findings that are no longer true

## Description

With the four design gaps closed, re-run the project's own `doc-trace` skill
(`.agents/skills/doc-trace/SKILL.md`) and replace `TRACEABILITY.md`, which has been a
September snapshot of a November codebase since the first FIRE intent ran on 2026-10-27.

The regeneration is mechanical. The judgment is in the findings that have **expired**, which
a re-run will drop silently and which deserve to be retired on the record instead:

- The matrix's stated *"single highest-value finding"* — that Architecture never accounted
  for FR-32/FR-33 after Amendment A-8 lifted them to MVP — is **false today**. `AD-21` exists,
  its `**Binds:**` line reads `FR-32, FR-33, FR-58, FR-53–55; PRD Amendment A-8`, and the
  Capability → Architecture Map carries a row for each (lines 457–458). The matrix also claims
  the word "Amendment" appears nowhere in the spine; it appears on lines 11, 218 and 282.
- The Epic/Story section still reads *"none found yet — expected pre-epics."* Eleven intents
  and twenty-seven FIRE runs have landed since.

## Acceptance Criteria

- [ ] `doc-trace` is invoked explicitly (it is `disable-model-invocation: true`) and
      `TRACEABILITY.md` regenerated from its output, not hand-edited into shape.
- [ ] Section A reports **36 FULL · 0 PARTIAL · 0 MISSING · 9 N/A** across the 45 MVP FRs. If
      it does not, the shortfall is reported rather than papered over — a matrix edited to show
      the number we wanted is worse than the stale one, because it looks current.
- [ ] Section B no longer reports an FR-32/FR-33 architecture gap, and names AD-21 as their
      architectural home.
- [ ] The Amendment Ledger's **A-8** row reads consistent across PRD, UX **and** Architecture.
- [ ] The remaining ledger rows marked **No** (A-2, A-3, A-5, A-7, and the A-9–A-21 block the
      PRD never absorbed) are re-checked and either fixed or **recorded as accepted with a
      reason**. A row that has said "No" through twelve intents is either a real debt or a
      convention nobody follows; say which.
- [ ] The Epic/Story section reflects that FIRE work items exist, or states plainly that FIRE
      work items are not the epics/stories the skill looks for and why that is fine.
- [ ] The regenerated matrix carries its new generation date and names the commit or run it
      describes, so the next reader can tell at a glance how stale it has become.
- [ ] The four FRs this intent designed are spot-checked in the new output as FULL, confirming
      the design artifacts actually satisfy `doc-trace`'s evidence rules rather than merely
      existing.

## Technical Notes

`doc-trace` scores **PRD ↔ Design** and **PRD ↔ Architecture**. It does **not** read
application code. Shipping code never moves an FR to FULL — only a self-tagged mockup
(tier 1) or a named doc section citing the FR (tier 2) does. That is precisely why four
shipped features sat at PARTIAL/MISSING for seven weeks, and it is why this item depends on
the four design items rather than running first.

The skill warns that DESIGN.md's and EXPERIENCE.md's own summary tables *"have been found
stale before (they can undercount the real files in the directory)"* and instructs cross-
checking the claimed mockup count against `ls`. That warning just proved itself twice over:
the directory now holds **38** mockups where the matrix scanned 32, and `EXPERIENCE.md:1236`
claimed FR-49 coverage that does not exist. Honour the instruction.

Consider whether this regeneration should become routine — a stale matrix is the failure
mode this intent exists to repair, and nothing currently prevents the next eleven intents
from recreating it. That is a recommendation to surface at the checkpoint, not a change to
make inside this item.
