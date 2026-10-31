/**
 * The neighbor count, as bucketed prose.
 *
 * **FR-24: the count is bucketed, `≥5` is the threshold, below 5 is silently
 * suppressed, and exact counts are never exposed.**
 *
 * **The suppression is silence.** No row, no "0 neighbors", and no field that says the
 * count was suppressed — a field that says "we computed a count and withheld it" is
 * itself a signal about how many people are near this event, which is exactly what the
 * threshold exists to withhold.
 *
 * **The `👥` emoji prefix is gone.** `EXPERIENCE.md` §12's `_RECONCILE_` note revised
 * the bucketed rendering to prose-only under the emoji-as-CTA ban; the PRD's `👥 5–9`
 * is the superseded draft.
 *
 * **No number is rendered, and none is in the DOM.** The API sends a bucket key and no
 * count field at all — `NeighborCount` has no `count` member — so there is nothing here
 * to render even by accident.
 */
import { neighborLine } from "@/lib/detail-labels";

export function DetailNeighbors({ bucket }: { bucket: string | null | undefined }) {
  const line = neighborLine(bucket);

  // **Nothing at all when the count is below the threshold.** Not an empty row, not a
  // muted "no neighbours yet" — silence.
  if (line === null) return null;

  return (
    <p className="text-ink-muted [font:var(--type-scale-meta-md)]" data-detail-neighbors>
      {line}
    </p>
  );
}
