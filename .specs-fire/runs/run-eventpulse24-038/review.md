---
run: run-eventpulse24-038
work_item: timeline-hover-detail
intent: traceability-gap-closure
date: 2026-11-17
---

# Code Review: Reveal the Timeline block's detail on hover and focus — FR-32 (UI)

## Decisions taken, with reasons recorded in the component

**1. The place is added to the `aria-label`.** Not decoration: an `aria-label` replaces
inner text, so a revealed `<span>` inside the block is never announced. Naming the place in
the label is the only way a screen-reader user gets it at all — and because the label wins,
it cannot be announced twice.

**2. The block grows rather than overlaying its neighbour.** Growth pushes the *later*
blocks in the day down; the hovered block's own top edge does not move, so the pointer
cannot be shaken off the element it is hovering — the flicker loop an overlay or a
self-resizing element would risk. An overlay would also paint over the next block's name,
which is a trust signal, and §13 forbids covering one.

**3. Revealed at every width, not `md:` and up.** §13 describes the hover state as the
desktop one because phones have no hover — but focus exists everywhere, and gating the
reveal behind a breakpoint would deny it to a keyboard user on a narrow viewport. The
reveal is additive, so showing it on focus at any width breaks nothing in §13's mobile
default, which describes the **idle** state.

## Checked and found sound

| Concern | Finding |
|---|---|
| §13's locked anti-pattern | Nothing is removed on hover or focus; a test asserts name, label, conflict indicator and place co-existing |
| Hover/focus parity | Both utilities on one element, asserted |
| `group` placement | On the block root, which is the `<button>` or `<Link>` — a `<span>` is not focusable and would never match |
| Empty state | No element rendered when `place` is null; no reserved gap |
| Overflow | `truncate` on the revealed line, so a long venue cannot widen a 110px column |
| Idle height | Unchanged — the element is `hidden` until hover or focus |

## Verdict

**Approved.** No defects. Three judgement calls, each documented at the point a later
reader would question it.
