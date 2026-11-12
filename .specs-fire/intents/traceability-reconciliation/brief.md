---
id: traceability-reconciliation
title: Traceability Reconciliation — Design the Four Undesigned FRs, Re-prove
  the Matrix
status: completed
created: 2026-11-12
completed_at: 2026-11-12T06:13:19.220Z
---

# Intent: Traceability Reconciliation — Design the Four Undesigned FRs, Re-prove the Matrix

## Goal

Make the traceability matrix tell the truth again, and make the four requirements it flags
actually designed rather than inferred.

`TRACEABILITY.md` was generated **2026-09-08**. The first FIRE intent ran **2026-10-27**.
Eleven intents and twenty-seven runs have landed since, and nobody regenerated it. Its own
Epic/Story section still reads *"none found yet — expected pre-epics."* It is a September
snapshot of a November codebase, and it is now wrong in both directions at once:

- **It reports a gap that is closed.** Its stated *"single highest-value finding"* — that
  Architecture never accounted for FR-32/FR-33 after Amendment A-8 lifted them to MVP — is
  false today. `ARCHITECTURE-SPINE.md` has **AD-21**, whose `**Binds:**` line reads
  `FR-32, FR-33, FR-58, FR-53–55; PRD Amendment A-8`, and the Capability → Architecture Map
  carries a row for each (lines 457–458). The matrix says the word "Amendment" appears
  nowhere in the spine; it appears on line 11, line 218 and line 282.
- **It reports gaps that are real, and still are.** FR-20, FR-28, FR-49 and FR-55 have no
  design. That has not changed since September — but the *code* for all four shipped in the
  meantime, so the gap inverted: the software exists and the design describing it does not.

A stale check is worse than no check, because people stop reading it. This intent restores
it to something that can be trusted at a glance, which is the only reason the matrix exists.

## Users

- **Any future agent planning against these docs.** The FIRE planner reads
  `workspace.planning_sources` — PRD, UX, architecture, traceability — to decide what is
  built and what is not. A matrix claiming FR-49 is MISSING when `collections_api.py`,
  `components/collections/` and migration `0014_savedcollection_savedcollectionitem` all
  exist will send a planner to rebuild shipped work.
- **Whoever next touches the four undesigned surfaces.** There is no spec for the share
  affordance, the collections manager, the reminder-default state, or the
  conflict-on-state-change panel. The code is the only description of them, so any change
  is a guess at what was intended versus what was merely implemented.
- **Jobaer, deciding whether the MVP is actually done.** All 45 MVP FRs are claimed by
  shipped intents. Nobody has confirmed the four inferred-design ones satisfy the PRD's own
  testable consequences.

## Problem

Three distinct problems wearing one label.

### 1. Four requirements were built without a design, and still have none

Checked against the `doc-trace` skill's own evidence rules — a self-tagged mockup header
(tier 1) or a named DESIGN.md/EXPERIENCE.md section citing the FR (tier 2):

| FR | What the PRD asks for | Design evidence today |
|---|---|---|
| **FR-20** Personal Event Reminder Defaults | new Personal Event inherits 1d + 1hr; user can remove **all** reminders | none. `reminder-picker-desktop.html` is self-tagged `FR-9` only |
| **FR-28** Share-Card Public Link | sender generates a public share-link with OG-rich metadata | one footnote in EXPERIENCE.md:964. `share-link-desktop.html` is tagged `UJ-5` — the *recipient's* landing page, not the sender's affordance |
| **FR-49** Unlimited Saves + Saved Collections | create, rename, delete **and reorder** named collections | none. EXPERIENCE.md:1236 claims `settings-desktop.html` covers it; that file carries no `FR-` tag at all and no collection content |
| **FR-55** Conflict Resolution on State Change | notify on cancel/postpone, preserve the personal event, per-event mute | nothing tagged anywhere |

The matrix's verdicts (`PARTIAL (inferred only)` ×3, `MISSING` ×1) were re-verified against
every one of the 38 mockup headers on 2026-11-12 and stand.

### 2. The shipped behaviour has never been checked against those four FRs

The code is substantial and reads as deliberate — `collections_api.py:1` names
*"create, rename, reorder, delete, assign, unassign"*; `detail_read.py:112` distinguishes
FR-55's mute from FR-54's notice as *"two independent facts"*; `personal_events.py:285`
notes FR-20's default is *"a property of creation"*. None of that is a test that the PRD's
consequences hold. The bullets most likely to have been missed are the negative and
ordering ones: FR-20's *"the user can remove all reminders"*, FR-49's *reorder*, FR-49's
*"free user hitting the cap sees a calm in-app upgrade prompt (no modal interruption)"*,
and FR-55's *"the personal event is preserved (no auto-cancel)"*.

### 3. 1,323 untracked duplicate files are sitting in the tree

`backend/` and `frontend/` hold 1,323 files matching `* 2.*` — filesystem conflict copies,
not git history (`git ls-files | grep -c " 2\."` → **0**). They include
`apps/personalization/collections_api 2.py`, `adapters/revalidation/fake 2.py`, and
`apps/personalization/migrations/0013_eventreport 2.py`. A stray duplicate in a Django
`migrations/` directory is the one that matters: the loader walks that directory, and a
filename with a space is not a valid module name. It has not bitten yet. It will.

## Success Criteria

- `doc-trace` regenerated; Section A reports **36 FULL · 0 PARTIAL · 0 MISSING · 9 N/A**
- FR-20, FR-28, FR-49 and FR-55 each have **both** a self-tagged mockup and a named
  DESIGN.md/EXPERIENCE.md component or flow section
- Every `**Consequences (testable):**` bullet under those four FRs has a test that asserts
  it, named so the FR is greppable from the test
- Any consequence the shipped code fails is fixed in code — the PRD wins, not the code
- Section B no longer reports the FR-32/FR-33 architecture gap; the Amendment Ledger row
  for A-8 reads consistent across PRD, UX **and** Architecture
- `find backend frontend -name "* 2.*"` returns nothing, and a `.gitignore` rule prevents
  recurrence
- `EXPERIENCE.md:1236`'s false FR-49 coverage claim is corrected rather than left standing

## Constraints

- **Describe what shipped — this is not a redesign.** The four surfaces exist and work.
  Where code and PRD genuinely disagree, the PRD wins and the code changes; where they
  agree, the design documents what is there.
- **House style is binding** (`ARCHITECTURE-SPINE.md` Consistency Conventions): no
  component kit, CSS-custom-property tokens, `data-theme="dark"` as the default attribute,
  no `prefers-color-scheme` auto-switch, one 240ms `motion.fadeIn`, `<dialog>` for modals.
  UI component names exactly as the UX spine gives them.
- **Every new mockup self-tags its FR in its own header comment.** That is the tier-1
  evidence rule the matrix scores on; an untagged mockup is worth nothing to it.
- **Deleting the duplicates is destructive.** Confirm each is byte-identical to, or
  strictly stale against, its tracked original before removing. None are git-tracked, so
  there is no history to fall back on if this is got wrong.
- `doc-trace` is `disable-model-invocation: true` — it runs only when explicitly invoked.
- The matrix compares PRD ↔ Design and PRD ↔ Architecture. It does **not** read code, so
  shipping code never moves an FR to FULL on its own. Only design artifacts do.

## Notes

Scope decisions taken at capture (2026-11-12):

- **Verify, then update the docs** — both halves, not docs alone.
- **Mockups + doc sections** for design evidence, rather than the cheaper options of
  doc-sections-only or retagging existing mockups.
- **Verification bounded to the PRD's "Consequences (testable)" bullets**, not a full
  implementation audit of each feature.
- **Duplicate-file cleanup folded into this intent** rather than handled separately.

Rejected at capture: launch-readiness work (the `adapters/llm/` port has only a fake and no
real provider — a real gap, but a different intent) and Phase 2 features (FR-31, FR-34–47).
