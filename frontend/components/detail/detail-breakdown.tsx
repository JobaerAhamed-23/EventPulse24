/**
 * The why-this breakdown — "the heart" of the Detail Screen (`EXPERIENCE.md` §12).
 *
 * **One factor per line**, and each line is derived from a **persisted tag key**. This
 * is the one place on the screen where prose is generated, and it is generated from a
 * persisted fact rather than a fresh computation — which is what keeps AD-10 intact.
 *
 * **Nothing is stated that the composition does not support.** There is no reliability
 * score (FR-16 is unbuilt — `Source` has no score field), no distance (no coordinates),
 * no price (no price field) and no attendance (no attendance model). The mockup's
 * "Source reliability 0.91 (Bayesian-smoothed)" and "It's four blocks from your office"
 * are **not reproduced**; the design doc's drift table records why.
 *
 * **The neighbor line is not a factor.** The bucketed neighbor count is its own element
 * at the bottom of the screen, and putting it in here too would give one fact two
 * chances to drift.
 *
 * **The expansion is `motion.fadeIn` (240ms), disabled under reduced motion** — the
 * product's single transition, and the same one the digest's card entrance uses.
 */
import { factorLine } from "@/lib/detail-labels";
import { tagLabel } from "@/lib/digest-labels";

/**
 * The Why-this Tags.
 *
 * **The same three, in the same order, as the card.** FR-21's third consequence is that
 * the tags are "consistent on the Pulse Card and on the Detail Screen", and the
 * strongest form of consistency is *equality*: both surfaces read the same persisted
 * keys and render them through the same `tagLabel`, so the words cannot differ.
 *
 * **The separator is a comma, and it is real text.** A CSS pseudo-element would be
 * visible to a sighted user and invisible to a screen reader, which is the regression
 * `EXPERIENCE.md` §8 forbids.
 */
export function DetailTags({ tags }: { tags: string[] }) {
  if (tags.length === 0) return null;

  return (
    <p className="[font:var(--type-scale-microtag)] text-ink-muted" data-detail-tags>
      {tags.map((tag, index) => (
        <span key={tag}>
          {index > 0 ? ", " : null}
          {tagLabel(tag)}
        </span>
      ))}
    </p>
  );
}

/**
 * The expandable why-this breakdown.
 *
 * **The section is absent, not empty, when there is no composition.** The caller does
 * not render this component at all in that case, so the section element is not in the
 * DOM — which is what the work item's criterion asks for ("not an empty one, not a
 * placeholder").
 */
export function DetailBreakdown({ tags }: { tags: string[] }) {
  const factors = tags.map(factorLine);

  return (
    <section aria-labelledby="detail-why-this" data-detail-breakdown>
      <h2 id="detail-why-this" className="text-ink-primary [font:var(--type-scale-headline-sm)]">
        Why this?
      </h2>

      <p className="mt-3 text-ink-secondary [font:var(--type-scale-body-md)]">Surfaced because:</p>
      {/*
        The list is a `<ul>`: a bulleted list is the honest markup for "one factor per
        line", and the marker is the browser's, not a CSS pseudo-element — a
        `::before` with a `content-` would be visible to a sighted user and invisible
        to a screen reader, which is the regression `EXPERIENCE.md` §8 forbids.
      */}
      <ul className="mt-1 flex list-disc flex-col gap-1 pl-5">
        {factors.map((factor) => (
          <li key={factor} className="text-ink-secondary [font:var(--type-scale-body-sm)]">
            {factor}
          </li>
        ))}
      </ul>
    </section>
  );
}
