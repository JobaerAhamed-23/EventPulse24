/**
 * The words for the preview's two server-stated facts: the Why-this tags and the Source
 * Badge.
 *
 * **The server states the fact; the client speaks the user's language.** The API sends
 * tag *keys* (`tonight`, `in_brooklyn`) and badge *types* (`official_site`), and says so
 * in its own comments: "The labels are the frontend's." That split is what lets a label
 * be rewritten without invalidating a stored tag.
 */

import { EVENT_FIT_MAX } from "./event-fit";

/** The time tags, which are a fixed set (`shared/constants.py`: `EVENT_FIT_TAG_ORDER`). */
const TAG_LABELS: Record<string, string> = {
  tonight: "Tonight",
  tomorrow: "Tomorrow",
  this_weekend: "This weekend",
};

/** The place tag is a prefix, not a key: `in_brooklyn`, `in_san_francisco`. */
const CITY_TAG_PREFIX = "in_";

/**
 * A tag key's label.
 *
 * An unknown key is **rendered from its slug**, not dropped. A tag the backend adds
 * tomorrow should appear as soon as it exists, looking slightly plain, rather than vanish
 * from the card with nobody noticing — this file is a translation, not a filter.
 */
export function tagLabel(key: string): string {
  const known = TAG_LABELS[key];
  if (known) return known;

  if (key.startsWith(CITY_TAG_PREFIX)) {
    return `In ${titleCase(key.slice(CITY_TAG_PREFIX.length))}`;
  }
  return titleCase(key);
}

function titleCase(slug: string): string {
  return slug
    .split("_")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}

export type SourceBadge = {
  /** The visible inline label. Never icon-only (WCAG 1.1.1, `EXPERIENCE.md` §8). */
  label: string;
  /** The locked tooltip text (`EXPERIENCE.md` §4 `Badge.Source`). */
  tooltip: string;
  /** Whether this badge is the unverified one, which carries the amber warning glyph. */
  unverified?: boolean;
};

/**
 * The badge types the preview can produce, with `EXPERIENCE.md`'s own labels and
 * tooltips.
 *
 * `user_imported` is the fifth type in the spec and is **not here**: a user-imported event
 * is a personal event, and the preview has no session and never reads `personal` (AD-12),
 * so this surface cannot produce one.
 */
const BADGES: Record<string, SourceBadge> = {
  official_site: { label: "Official", tooltip: "Verified venue or organizer." },
  community: { label: "Community", tooltip: "Posted by a community member." },
  aggregator: { label: "Listing site", tooltip: "Aggregated from a public listing." },
  crawled_html: {
    label: "Unverified",
    tooltip: "Read from a public page. We could not confirm it with the organizer.",
    unverified: true,
  },
};

/** A badge type's label and tooltip, or a plain fallback for a type we do not know yet. */
export function sourceBadge(type: string): SourceBadge {
  return BADGES[type] ?? { label: "Listed", tooltip: "Listed from a public source." };
}

/**
 * What the 1–5 means, in words, for the tooltip and the text alternative.
 *
 * **This is the Event Fit, not the Confidence Pulse.** The mockup's legend describes the
 * Confidence Pulse — "how many sources confirm a listing" — and that is a different
 * number that this page never receives. The Event Fit is
 * `min(how soon it starts, how well its facts were extracted)` (`domain/event_fit.py`),
 * it is the same for every visitor, and AD-10 forbids showing one indicator in the
 * other's clothes. So the card says what it has.
 */
export const EVENT_FIT_TOOLTIP =
  "How soon it is, and how complete our details are. The same for everyone — not a personal recommendation.";

export function eventFitLabel(score: number): string {
  return `Event Fit ${score} of ${EVENT_FIT_MAX}`;
}
