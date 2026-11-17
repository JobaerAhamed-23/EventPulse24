---
id: amendment-tag-propagation
title: Propagate the A-2 and A-3 amendment tags into the UX docs
intent: traceability-gap-closure
complexity: low
mode: autopilot
status: pending
depends_on: []
created: 2026-11-17
---

# Work Item: Propagate the A-2 and A-3 amendment tags into the UX docs

## Description

The project's Amendment convention is that **whenever a change gets an Amendment ID, that ID
must appear in every document the change actually touches**. Two amendments never completed
that journey:

- **A-2** revised **FR-5** (Pulse Digest Composition). Cited 5× in the PRD, **0×** in
  DESIGN.md and **0×** in EXPERIENCE.md — re-verified 2026-11-17 — although FR-5 is core UX
  real estate (`Card.PulseDigest`).
- **A-3** revised **FR-22** (Confidence Pulse). Cited 4× in the PRD, **0×** in both UX docs,
  although EXPERIENCE.md references FR-22 eight times and a whole mockup
  (`ranking-algorithm-transparency-desktop.html`) is devoted to it.

These are the last two genuine defects in the Amendment Ledger. They are documentation-only:
no code, no mockup rewrite, no requirement change.

## Acceptance Criteria

- [ ] The DESIGN.md / EXPERIENCE.md section that describes **FR-5**'s digest composition carries an inline `Amendment A-2` tag, in the house style already used by A-8, A-9 and A-19.
- [ ] The section describing **FR-22**'s Confidence Pulse carries an inline `Amendment A-3` tag in the same style.
- [ ] Each tag names what the amendment changed in one short clause — enough that a reader who meets the tag first can tell why it is there, matching how the existing A-N notes read.
- [ ] **No requirement, token, component or mockup is changed.** This item adds citations to text that already describes the amended behaviour correctly.
- [ ] A `doc-trace` regeneration afterwards drops A-2 and A-3 from the inconsistent list, leaving only the A-11–A-20 convention question.

## Technical Notes

**Check before writing that the prose is actually current.** The job is to tag text that
already describes the amended behaviour. If either section still describes the *pre*-amendment
behaviour, that is a different and larger finding — stop and report it rather than tagging a
stale paragraph, which would make the Ledger read clean over a real inconsistency.

**Do not touch A-11 – A-20.** That block (UX-originated amendments the PRD never absorbed) is
a *convention* question — whether such amendments are expected to flow back into the PRD at
all — and the matrix recommends deciding it once, by a human, rather than re-fixing it every
regeneration. It is deliberately outside this intent.

**Do not edit TRACEABILITY.md in this item.** The matrix is the measurement; editing it in the
same pass that changes what it measures is how a matrix stops being trustworthy — the project
has recorded that rule once already (the A-18 as-built note deliberately left it alone). Let
the next `doc-trace` run re-derive the score.

## Dependencies

(none)
