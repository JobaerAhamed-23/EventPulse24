---
id: timeline-hover-detail
title: Reveal the Timeline block's detail on hover and focus — FR-32 (UI)
intent: traceability-gap-closure
complexity: medium
mode: confirm
status: pending
depends_on: [timeline-block-detail-contract]
created: 2026-11-17
---

# Work Item: Reveal the Timeline block's detail on hover and focus — FR-32 (UI)

## Description

With the contract item landed, the block reveals its **location** on desktop hover **and**
on keyboard focus. Today it has only the `hover:bg-surface-inset` fill swap.

**The Why-this tag that §13 also names is deliberately not here** — see
`timeline-why-this-tag` for the finding (no persisted tag this surface may read, and an
import contract barring the Event Fit) and the decision.

This is the second half of the only shortfall behind an otherwise-`FULL` FR-32, recorded as
open item **O-2** in the 2026-11-17 matrix.

## Acceptance Criteria

- [ ] On desktop hover, a block reveals its place in `Text.Meta` / `--type-scale-meta-sm` with `text-ink-muted`, consistent with the block's existing meta line.
- [ ] **Focus reveals exactly what hover reveals.** No hover-only affordance — the rule the Pulse Card's `▸` already follows with `group-hover` + `group-focus-within`.
- [ ] Nothing is **removed** on hover or focus. §13's locked anti-pattern is that adaptive density must not hide trust signals; the conflict indicator, the name, the time and the category label all stay exactly as they are.
- [ ] A block with no place (a personal event without one, or a block whose catalog event is gone) reveals nothing extra and does not reserve empty space or shift its neighbours.
- [ ] The reveal does not change the idle block's height, so a hovered block never reflows the day column around it.
- [ ] The mobile/touch view is unaffected — §13's one-day view keeps the idle vocabulary.
- [ ] The accessible name is not duplicated: the existing `aria-label` already carries name + time + kind, and revealed text must not announce the block twice.
- [ ] `tests/timeline-a11y.test.tsx` and the timeline suites pass; `pnpm lint`, `pnpm typecheck` and `pnpm format:check` clean for touched files.

## Technical Notes

**The component was just restructured (2026-11-17).** `timeline-block.tsx` now lays out the
category label on its own right-aligned line, then the name, then the time — after a bug
where an absolutely positioned label overlapped a truncated title. Build the reveal on that
structure; do not reintroduce absolute positioning for the new rows.

**`group-hover` + `group-focus-within`, on the block's own root.** The root is already
`relative` and is a `<button>` for a personal block and a `<Link>` for a public one — both
can carry `group`. Use the same opacity pattern the Pulse Card's `▸` uses rather than a new
mechanism.

**Height stability is the fiddly part.** The desktop grid is seven narrow columns with a
`min-h-[480px]`; a reveal that grows the block will push every later block in that day down.
Decide deliberately between reserving the space and overlaying it, and record which and why
in the component's comment — this file documents its layout reasoning in prose, and a change
that does not is inconsistent with it.

**The place is already resolved.** The server sends one string or null (see
`timeline-block-detail-contract`). The component renders what it is given and never picks
between venue, location and city.

## Dependencies

- timeline-block-detail-contract
