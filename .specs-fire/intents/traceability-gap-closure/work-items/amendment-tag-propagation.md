---
id: amendment-tag-propagation
title: Propagate the A-2 and A-3 amendment tags into the UX docs
intent: traceability-gap-closure
complexity: low
mode: autopilot
status: completed
depends_on: []
created: 2026-11-17
run_id: run-eventpulse24-040
completed_at: 2026-11-17T16:07:06.820Z
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

- [x] The DESIGN.md section that describes **FR-5**'s Slot 3 treatment (`component.card.pulse.digest.category.discovery`) carries an inline `Amendment A-2` tag, in the house style already used by A-8, A-9 and A-19.
- [x] ~~The section describing **FR-22**'s Confidence Pulse carries an inline `Amendment A-3` tag~~ — **moved to `fr22-published-formula` on 2026-11-17.** The check this item mandated ("check before writing that the prose is actually current") found that the UX docs are *not* stale: the PRD is. FR-22 publishes four weighted terms, the product computes five, and the divergence is pinned to ADR-0025 rather than to any PRD amendment. Tagging A-3 would assert a revision the section does not implement.
- [ ] Each tag names what the amendment changed in one short clause — enough that a reader who meets the tag first can tell why it is there, matching how the existing A-N notes read.
- [ ] **No requirement, token, component or mockup is changed.** This item adds citations to text that already describes the amended behaviour correctly.
- [x] A `doc-trace` regeneration drops **A-2** from the inconsistent list. **A-3 remains, by design** — it now points at `fr22-published-formula` rather than at a missing tag, which is a more useful thing for the Ledger to say.

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
