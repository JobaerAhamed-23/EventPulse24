/**
 * The Pulse Digest's loading state (`EXPERIENCE.md` §5, Loading Patterns).
 *
 * **"3 paper rectangles rendered in `color.surface.paper`, fading 1px toward
 * `color.ink.faint` at 60% opacity, then back. Pulse period: 1800ms. No text inside the
 * skeletons."**
 *
 * **No spinners, anywhere.** A spinner is a visual urgency badge, and the product
 * refuses urgency badges (PRD §13.1). A skeleton says "a card is coming and it is about
 * this big"; a spinner says "wait".
 *
 * **The pulse is `motion.skeletonPulse`** — the product's only animation, declared once
 * in `styles/globals.css` and collapsed to an instant render under
 * `prefers-reduced-motion`. It is a *loading* affordance, so it is not the entrance
 * transition: `.fade-in` would have faded each rectangle in once and then held, which
 * is the preview's behaviour and not this one's.
 *
 * **The rectangles are plain and paper-coloured**, with no internal structure. The
 * preview's skeleton is a card-shaped frame with bars inside it — a different
 * vocabulary, for a different surface. §5's is three paper rectangles, and that is what
 * ships.
 *
 * **They are `aria-hidden`.** The `role="status"` wrapper carries the accessible name,
 * so a screen reader hears "Loading the Pulse Digest" once rather than three
 * indistinguishable rectangles.
 */
export function DigestSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div
      role="status"
      aria-label="Loading the Pulse Digest"
      className="flex max-w-(--layout-container-reading) flex-col gap-4"
    >
      {Array.from({ length: count }, (_, index) => (
        <div
          key={index}
          aria-hidden="true"
          className="skeleton-pulse h-[128px] rounded-card bg-surface-paper"
        />
      ))}
    </div>
  );
}
