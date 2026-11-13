---
id: traceability-implementation-section
title: Section C — PRD ↔ Implementation, the Column the Matrix Never Had
intent: unwired-surfaces
complexity: medium
mode: confirm
status: pending
depends_on:
  - endpoint-coverage-enforcement
created: 2026-11-13
---

# Work Item: Section C — PRD ↔ Implementation

## Description

`TRACEABILITY.md` scores every MVP FR twice:

- **Section A — PRD ↔ Design**: 35 FULL · 1 PARTIAL · 0 MISSING · 9 N/A
- **Section B — PRD ↔ Architecture**: 45 FULL · 0 PARTIAL · 0 MISSING · 0 N/A

Both read as near-perfect coverage. Neither asks **whether a user can reach the thing**.

That is how FR-18 carried `FULL` while its delete control did not exist — scored on
`personal-event-edit-desktop.html`, which draws a danger zone that was never built (fixed
2026-11-13, commit `2ba0073`). The same rule currently scores `FULL` for:

| FR | Scored on | Actually |
|---|---|---|
| FR-20 Personal Event Reminder Defaults | `personal-event-reminders-desktop.html` | no surface; picker hard-coded to `saved_event` |
| FR-24 Neighbour count | design + architecture | half its qualifying rule never fires |
| FR-49 Unlimited Saves + Collections (Pro) | `collections-desktop.html` | collections cannot be filled |
| FR-50 Calendar Read-Only Sync | design + architecture | cannot be disconnected or reconnected |
| FR-25 "Less like this" | `less-like-this-mute-prompt-desktop.html` | built nowhere |

The matrix anticipates the gap without filling it: *"**Whether FIRE work items should be
traced against FRs is an open question**, and would be a third section rather than a
reinterpretation of this one."*

This item writes that third section.

## Acceptance Criteria

- [ ] `TRACEABILITY.md` gains **Section C — PRD ↔ Implementation**, scoring every MVP FR on
      whether a user can reach it, with the same `FULL / PARTIAL / MISSING / N/A` vocabulary
- [ ] Each row cites **running code** — a route, a component, a call site — not a mockup and
      not an architecture row. A mockup is Section A's evidence and must not be reused here
- [ ] The five FRs in the table above are scored honestly against the state of the code at
      the time of writing, whether or not this intent's other items have landed
- [ ] The section states its own limit: a called endpoint is not a reachable feature, and
      `endpoint-coverage-enforcement`'s test cannot see the difference
- [ ] The matrix's "Open items" section carries forward anything Section C finds and this
      intent does not fix
- [ ] **No FR's Section A or Section B score is edited by this item.** Adding a third
      measurement must not quietly restate the first two

## Technical Notes

- **The matrix's own integrity rule applies to this item.** Open item #1: *"editing a
  document to improve the score in the same pass that measures it is how a matrix stops
  being trustworthy."* Score what is there on the day. If this intent's other items land
  afterwards, the scores move in a later regeneration.
- **The repo has a `doc-trace` skill** (`.agents/skills/doc-trace/SKILL.md`) that generated
  the current matrix. Extend it rather than hand-writing a section it will overwrite on the
  next run — a hand-written section is a section the generator deletes.
- **Section C is not the same claim as `endpoint-coverage-enforcement`.** That test asks
  "does any code call this endpoint". Section C asks "can a user get to this requirement".
  The personal-events list is the worked example of the difference: it calls nothing and
  renders nowhere, and only the second question catches it.
- **Depends on `endpoint-coverage-enforcement`** because the exemption list that item
  produces is the raw material for the API half of Section C's evidence.

## Dependencies

- endpoint-coverage-enforcement
