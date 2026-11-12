/**
 * The words for the digest's two server-stated facts: the Why-this Tags and the Source
 * Badge.
 *
 * **The server states the fact; the client speaks the user's language.** The API sends
 * tag *keys* (`nearby`, `matches_arts_culture`) and badge *types* (`official_site`), and
 * says so in its own words: "The labels are the frontend's." That split is what lets a
 * label be rewritten without invalidating a stored tag — the tag is a persisted fact, and
 * the label is a translation of it.
 *
 * **This is not `preview-labels.ts`, and it is not a copy of it.** The two indicators have
 * **different tag vocabularies**, and AD-10 forbids substituting one for the other:
 *
 * | Vocabulary | Keys | Belongs to |
 * |---|---|---|
 * | Event Fit | `tonight`, `tomorrow`, `this_weekend`, `in_<city>` | the session-free public preview (AD-12) |
 * | Relevance Pulse | `discovery`, `nearby`, `tonight`, `tomorrow`, `weekend`, `saved`, `matches_<chip>` | the per-user digest (AD-10) |
 *
 * The two overlap on `tonight` and `tomorrow` — where they agree, the labels agree,
 * because they are the same English word. They **disagree on the weekend**: the Event Fit
 * says `this_weekend` and the Relevance Pulse says `weekend`. That is a *backend* naming
 * drift (`shared/constants.EVENT_FIT_TAG_THIS_WEEKEND` against
 * `RANKING_TAG_WEEKEND`), not a frontend one — the two constants are different ideas
 * living in different tables. Each vocabulary is translated on its own terms here, and the
 * drift is recorded rather than papered over by making one key mean two things.
 */

/**
 * The Relevance Pulse's fixed tags.
 *
 * The keys and their order are the server's (`shared.constants.RANKING_TAG_ORDER`), and
 * the card renders them in the order the server sent them — the order is the priority
 * order, and re-sorting it here would be a client-side decision (AD-10).
 */
const TAG_LABELS: Record<string, string> = {
  discovery: "Discovery",
  nearby: "Nearby",
  tonight: "Tonight",
  tomorrow: "Tomorrow",
  weekend: "This weekend",
  saved: "Saved",
};

/**
 * The chip labels, from the server's own chip table (`shared.constants.INTEREST_CHIPS`).
 *
 * A chip-match tag is `matches_<chip_key>` — `matches_arts_culture` for the
 * `arts_culture` chip — and the chip key is a slug that is **stable forever even if the
 * label changes**. So the slug is what is persisted and the label is what is read.
 *
 * **This table is a copy of the server's, and a test checks it.** The frontend cannot
 * import the backend's Python, so the labels are restated here — and
 * `tests/digest-labels.test.ts` reads `backend/shared/constants.py` and fails if the two
 * tables have drifted apart. A chip with no label here is rendered from its slug, so a
 * new chip still appears; the test is what stops the *label* from going stale.
 */
const CHIP_LABELS: Record<string, string> = {
  tech_meetups: "Tech & meetups",
  sports_fitness: "Sports & fitness",
  arts_culture: "Arts & culture",
  family_kids: "Family & kids",
  community_volunteering: "Community & volunteering",
  outdoors_nature: "Outdoors & nature",
  classes_workshops: "Classes & workshops",
  markets_fairs: "Markets & fairs",
  talks_lectures: "Talks & lectures",
  government_civic: "Government & civic",
};

/** The prefix a chip-match tag carries (`RANKING_TAG_CHIP_PREFIX`). */
const CHIP_TAG_PREFIX = "matches_";

/**
 * The Browse search's friendly tag names, and the server's keys they stand for.
 *
 * **The design names ten tags the server does not have.** `DESIGN.md`'s
 * `component.input.search.browse` and `EXPERIENCE.md`'s inline keyword search both
 * specify a vocabulary of ten: `music · tech · community · arts · family · food ·
 * sports · outdoor · indoor · rooftop`. The server's why-tag vocabulary is
 * `RANKING_TAG_ORDER` — `discovery, nearby, tonight, tomorrow, weekend, saved` — plus
 * `matches_<chip_key>` for ten *other* slugs (`tech_meetups`, `sports_fitness`,
 * `arts_culture`, `family_kids`, `community_volunteering`, `outdoors_nature`,
 * `classes_workshops`, `markets_fairs`, `talks_lectures`, `government_civic`).
 *
 * **Six of the design's ten map onto a real chip.** The other four — `music`, `food`,
 * `indoor`, `rooftop` — have **no counterpart at all**: no fixed tag means them and no
 * chip means them. This table therefore maps the six and **deliberately omits the
 * four**, and a `tag:` literal naming an omitted token matches nothing.
 *
 * **Why a missing token matches nothing rather than falling back to a plain word.**
 * The search's own rule is that an unknown `tag:` token matches nothing rather than
 * widening into a plain-word match, because "silently widening a constrained query
 * would make the grammar untrustworthy". Widening is the *worse* failure: a reader who
 * typed `tag:music` would get every card with "music" anywhere in its title and no way
 * to tell that the tag was ignored. Aliasing `music` onto `matches_arts_culture` would
 * be the same lie in a subtler form — it would put "music" on a card the server tagged
 * "Sports & fitness".
 *
 * **This is a translation, and it is the same seam as the labels above.** The server
 * states the fact; the client speaks the user's language. The alias table is the
 * client's vocabulary for a server fact, not a second fact — and
 * `tests/digest-labels.test.ts` reads `backend/shared/constants.py` to prove every alias
 * here still points at a chip the server has.
 */
const SEARCH_TAG_ALIASES: Record<string, string> = {
  tech: "matches_tech_meetups",
  sports: "matches_sports_fitness",
  arts: "matches_arts_culture",
  family: "matches_family_kids",
  community: "matches_community_volunteering",
  outdoor: "matches_outdoors_nature",
};

/**
 * The friendly tag names the search accepts, in the order the hint line lists them.
 *
 * **This is the vocabulary the input's hint line advertises**, and it is deliberately
 * *not* the design's ten: it is the six aliases that resolve plus the six fixed
 * server tags. Listing a token that matches nothing would teach a grammar that lies.
 */
export const SEARCH_TAG_VOCABULARY: string[] = [
  ...Object.keys(SEARCH_TAG_ALIASES),
  "tonight",
  "tomorrow",
  "weekend",
  "nearby",
  "saved",
  "discovery",
];

/**
 * The server's key a friendly tag name stands for, or `null` when it stands for none.
 *
 * **A fixed server tag resolves to itself** — `tag:tonight` is a tag the server sends
 * today, so it needs no alias. The alias table holds only the *friendly* names, and
 * this function is what decides whether a token is one.
 */
export function searchTagKey(token: string): string | null {
  const alias = SEARCH_TAG_ALIASES[token];
  if (alias) return alias;
  // **The fixed tags are their own keys.** `tag:tonight` constrains to the `tonight`
  // why-tag, which the server really does send.
  if (TAG_LABELS[token]) return token;
  return null;
}

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

  if (key.startsWith(CHIP_TAG_PREFIX)) {
    const chip = key.slice(CHIP_TAG_PREFIX.length);
    return CHIP_LABELS[chip] ?? titleCase(chip);
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

/** The Source Badge variants, with `EXPERIENCE.md` §4's labels and tooltips. */
export type SourceBadge = {
  /** The visible inline label. Never icon-only (WCAG 1.1.1, `EXPERIENCE.md` §8). */
  label: string;
  /** The locked tooltip text (`EXPERIENCE.md` §4 `Badge.Source`). */
  tooltip: string;
  /** The glyph that sits before the label. */
  glyph: "check" | "chain" | "inbox" | "warning";
  /** Whether the label is terracotta — the one sanctioned terracotta use on a card body. */
  official: boolean;
  /** Whether the label is italic (`community`). */
  italic: boolean;
  /** Whether the label carries the warning colour (`crawled_html`). */
  warn: boolean;
};

/**
 * The five badge variants, exactly as `EXPERIENCE.md` §4 and `DESIGN.md` list them.
 *
 * ASSUM-9 locks the roster: "No additional source types are accepted without a Trust
 * Review pass; if the source roster grows, the variant list in §4 must be updated and
 * reviewed." So the list is closed, and an unknown type falls back to a plain badge rather
 * than borrowing another type's meaning.
 */
const BADGES: Record<string, SourceBadge> = {
  official_site: {
    label: "Official",
    tooltip: "Verified venue or organizer.",
    glyph: "check",
    official: true,
    italic: false,
    warn: false,
  },
  community: {
    label: "Community",
    tooltip: "Posted by a community member.",
    glyph: "check",
    official: false,
    italic: true,
    warn: false,
  },
  aggregator: {
    label: "Listing site",
    tooltip: "Aggregated from a public listing.",
    glyph: "chain",
    official: false,
    italic: false,
    warn: false,
  },
  user_imported: {
    label: "Forwarded",
    tooltip: "Added by you or from your calendar.",
    glyph: "inbox",
    official: false,
    italic: false,
    warn: false,
  },
  crawled_html: {
    label: "Unverified",
    tooltip: "Read from a public page. We could not confirm it with the organizer.",
    glyph: "warning",
    official: false,
    italic: false,
    warn: true,
  },
};

/**
 * A badge type's label and tooltip, or a plain fallback for a type we do not know yet.
 *
 * **The fallback does not borrow terracotta.** An unknown source is not an official one,
 * and the terracotta label is the one sanctioned accent on a card body — a new source
 * type must not arrive wearing it.
 */
export function sourceBadge(type: string): SourceBadge {
  return (
    BADGES[type] ?? {
      label: "Listed",
      tooltip: "Listed from a public source.",
      glyph: "chain",
      official: false,
      italic: false,
      warn: false,
    }
  );
}
