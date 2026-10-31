/**
 * The preview's loading state: three card-shaped placeholders.
 *
 * `EXPERIENCE.md` is specific — "Card skeletons (3, parallel to digest)" — and equally
 * specific that there are **no spinners anywhere**. A skeleton says "a card is coming and
 * it is about this big"; a spinner says "wait", which is the urgency badge the product
 * refuses.
 *
 * The fade is `.fade-in`, the one transition in the product. The pulsing animation the
 * design doc describes would need a keyframe, and `styles/motion.test.ts` fails the suite
 * on any animation other than that one transition — so the skeletons appear and hold.
 */
export function CardSkeletons({ count = 3 }: { count?: number }) {
  return (
    <div
      role="status"
      aria-label="Loading the preview"
      className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
    >
      {Array.from({ length: count }, (_, index) => (
        <div
          key={index}
          aria-hidden="true"
          className="fade-in flex flex-col gap-3 rounded-card border border-border-subtle bg-surface-elevated px-6 py-4"
        >
          <div className="h-3 w-[96px] rounded-full bg-surface-inset" />
          <div className="h-3 w-[128px] rounded-full bg-surface-inset" />
          <div className="h-[20px] w-full rounded-full bg-surface-inset" />
          <div className="h-[20px] w-3/4 rounded-full bg-surface-inset" />
          <div className="h-3 w-[160px] rounded-full bg-surface-inset" />
          <div className="mt-2 h-[36px] w-[96px] rounded-control bg-surface-inset" />
        </div>
      ))}
    </div>
  );
}
