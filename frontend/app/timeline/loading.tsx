import { TimelineSkeleton } from "@/components/timeline/timeline-states";

/**
 * The Timeline's loading state (`EXPERIENCE.md` §5 — Loading Patterns).
 *
 * **Seven columns, each a stack of three to five 40px rectangles.** The columns are
 * the week's shape and the rectangles are the blocks' shape, so what arrives is the
 * shape the user was waiting for.
 *
 * **No day labels.** A skeleton that prints "Mon" and "Tue" is half a rendering, and a
 * half-rendering that then changes is worse than an empty frame — the user reads the
 * label and then watches it move.
 */
export default function Loading() {
  return (
    <div className="fade-in">
      <TimelineSkeleton />
    </div>
  );
}
