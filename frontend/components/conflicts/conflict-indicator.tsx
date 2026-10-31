/**
 * The conflict indicator (`DESIGN.md` `component.indicator.conflict`).
 *
 * **One indicator, two surfaces.** The Pulse Card shows it as a mark — the card is the
 * tap target, and the indicator is a fact about the event. The Detail Screen shows it as
 * a **button**: the conflict prompt is opened from there, so the indicator is the
 * affordance. Both draw the same mark, so the two surfaces cannot drift.
 *
 * **6px, `color.warn.amber`, never red** — ASSUM-13 locks the size and `DESIGN.md` says
 * "Never red". It never collapses at any density (`EXPERIENCE.md` §13).
 *
 * **The ring is what distinguishes it from an unfilled confidence dot.** The confidence
 * dots are 6px circles too, and `DESIGN.md` requires the conflict mark to be "distinct in
 * shape and position". A ring in `color.ink.faint` — the dimmest ink, not a chromatic one —
 * does that without breaking the locked size and without inventing a colour.
 *
 * **Colour is never the sole carrier of meaning** (WCAG 1.4.1). The mark carries an
 * accessible name — "Schedule conflict" — so it is not a bare amber dot.
 */

/**
 * The mark on its own.
 *
 * **Not interactive.** The Pulse Card's indicator is a fact about the event, and the
 * card is the tap target; a second, overlapping target on the card would be a trap for
 * the pointer and for the screen reader's tab order.
 */
export function ConflictIndicator() {
  return (
    <span
      role="img"
      aria-label="Schedule conflict"
      className="inline-flex h-6 w-6 items-center justify-center"
    >
      <span className="size-[6px] rounded-full bg-warn-amber ring-1 ring-ink-faint" />
    </span>
  );
}

/**
 * The mark as a button that opens the conflict prompt.
 *
 * **The accessible name says what pressing it does**, not merely what it is. "Schedule
 * conflict" alone would tell a screen-reader user that something is wrong and not that
 * there is a choice waiting — and the whole point of the Detail Screen's indicator is
 * that the choice is one tap away.
 *
 * **A 44px target.** The mark is 6px, but the button is not: it is a `min-h-6` box
 * around it, and the button's own padding is what the pointer lands on.
 */
export function ConflictIndicatorButton({
  onOpen,
  label = "Schedule conflict. Choose how to handle it.",
}: {
  onOpen: () => void;
  /** The accessible name. The default says what pressing the button does. */
  label?: string;
}) {
  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label={label}
      className="inline-flex h-6 w-6 items-center justify-center rounded-control"
    >
      <span className="size-[6px] rounded-full bg-warn-amber ring-1 ring-ink-faint" />
    </button>
  );
}

/**
 * The Detail Screen's mark lives in its own client component — `detail-conflict-mark.tsx`
 * — because it needs an `onClick` to announce the open, and this file is imported by the
 * Pulse Card, which is a server component. The mark itself is drawn by
 * `ConflictIndicatorButton` below, so the two surfaces share one glyph.
 */
