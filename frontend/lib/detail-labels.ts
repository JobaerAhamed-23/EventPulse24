/**
 * The words for the Detail Screen's two server-stated facts: the why-this breakdown and
 * the neighbor count.
 *
 * **The server states the fact; the client speaks the user's language.** The API sends
 * tag *keys* (`nearby`, `matches_arts_culture`) and a neighbor *bucket key* (`few`), and
 * says so in its own words: "The labels are the frontend's." That split is what lets a
 * label be rewritten without invalidating a stored tag.
 *
 * **This module says nothing that was not persisted.** The breakdown is the one place on
 * this screen where prose is generated, and it is generated from a **persisted fact** —
 * the composition's own tag keys — not from a fresh computation. AD-10 says an
 * explanation is never generated at view time, and a breakdown line that stated a number
 * we never computed would be a lie in the exact place the product is supposed to be
 * honest.
 *
 * **So the factor vocabulary is closed, and it is the tag vocabulary.** There is no
 * reliability score (FR-16 is unbuilt — `Source` has no score field), no distance (no
 * coordinates), no price (no price field), and no attendance (no attendance model). The
 * mockup's "Source reliability 0.91 (Bayesian-smoothed)" and "It's four blocks from
 * your office" are **not reproduced**; see the design doc's drift table, rows 1–4.
 */

import { tagLabel } from "@/lib/digest-labels";

/**
 * The tag keys the backend persists, and the line each one becomes.
 *
 * **The keys are the backend's** (`shared.constants.RANKING_TAG_ORDER` and
 * `RANKING_TAG_CHIP_PREFIX`), and the order here matches it. A tag key the backend adds
 * tomorrow falls through to {@link factorLine}'s fallback, so the breakdown never drops a
 * reason — it renders the tag's own label instead of inventing one.
 */
const FACTOR_LINES: Record<string, string> = {
  nearby: "It's in your city.",
  tonight: "It starts tonight.",
  tomorrow: "It starts tomorrow.",
  weekend: "It starts this weekend.",
  discovery: "It's outside your usual — a little discovery.",
  saved: "You saved a similar event before.",
};

/**
 * The prefix a chip-match tag carries (`RANKING_TAG_CHIP_PREFIX`).
 *
 * The same prefix `lib/digest-labels.ts` reads, so the two tables agree on what a chip
 * tag looks like.
 */
const CHIP_TAG_PREFIX = "matches_";

/**
 * One line of the why-this breakdown, for one persisted tag key.
 *
 * **The line is derived from the key and nothing else.** The chip tag's line names the
 * interest the user picked — which is the fact the tag *is*, not a claim about a model
 * score.
 *
 * **The fallback is the tag's own label.** An unknown key becomes `tagLabel(key)`, which
 * title-cases the slug. So a new server tag appears in the breakdown as a plain,
 * slightly odd line, rather than vanishing or acquiring a fabricated reason. A line
 * that says "Nearby" when we do not know what "nearby" meant is honest; a line that says
 * "It matches something you like" when we do not know is not.
 */
export function factorLine(tag: string): string {
  const known = FACTOR_LINES[tag];
  if (known) return known;

  if (tag.startsWith(CHIP_TAG_PREFIX)) {
    // The chip's own label, from the same table the card uses, so the breakdown and the
    // card name the interest identically.
    return `It matches an interest you picked: ${tagLabel(tag)}.`;
  }

  return tagLabel(tag);
}

/**
 * The neighbor count's prose, per bucket key.
 *
 * **`EXPERIENCE.md` §12's four lines, verbatim.** The keys are the server's
 * (`neighbor_count.NeighborBucket`); the words are the frontend's.
 *
 * **The `👥` emoji prefix is gone.** §12's `_RECONCILE_` note records the revision:
 * "Neighbor-count bucketing … was originally specified with `👥` emoji prefixes per the
 * prior draft. This was revised to prose-only `Text.Meta` labels to honor §3 Voice and
 * Tone ('Emoji as CTAs' ban)". The PRD's `👥 5–9` is the superseded draft.
 *
 * **No line contains a digit.** The bucket is the coarsest thing the API is willing to
 * say, and a number in the prose would be a number the client could have been given.
 */
const NEIGHBOR_LINES: Record<string, string> = {
  few: "A few neighbors saved this.",
  some: "Some neighbors saved this.",
  many: "Many neighbors saved this.",
  a_lot: "A lot of neighbors saved this.",
};

/**
 * The neighbor line for a bucket key, or `null` when the bucket is `null`.
 *
 * **`null` means silence, not a fallback line.** Below the k-anonymity threshold the API
 * sends `neighbor_bucket: null` and the screen shows **nothing** — no row, no "0
 * neighbors", and no "not enough neighbors yet". A line that says the count was
 * suppressed is itself a signal about how many people are near this event, which is
 * exactly what the threshold exists to withhold.
 *
 * An **unknown** bucket key is also `null`. A server that grew a fifth bucket should not
 * have the client invent prose for it — and the fallback would be a guess about how
 * many people that bucket holds.
 */
export function neighborLine(bucket: string | null | undefined): string | null {
  if (!bucket) return null;
  return NEIGHBOR_LINES[bucket] ?? null;
}
