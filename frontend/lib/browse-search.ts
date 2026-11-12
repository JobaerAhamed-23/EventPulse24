import { searchTagKey } from "@/lib/digest-labels";

/**
 * The Browse search's grammar — the whole of it, in one pure module.
 *
 * **The grammar is small enough to be honest about.** It is:
 *
 * - **plain words** — whitespace-split, lowercased and trimmed, then **AND**-matched
 *   against the card's headline, its where line and its why-tag tokens;
 * - **`tag:<token>` literals** — matched **only** against the why-tag set, and AND-matched
 *   against any plain words beside them.
 *
 * **A card matches only if every term matches something.** That is the whole of it, and
 * it is the whole of it on purpose: a grammar a reader has to learn in five seconds
 * cannot also have rules about precedence.
 *
 * **Nothing here decides what a card *is*.** The search filters the cards the server
 * sent; it does not rank, sort, re-tier or re-bucket them (AD-10). It is a lens over the
 * loaded set, not a second opinion about it.
 *
 * **The search sees only what is loaded.** It matches over the cards the page currently
 * holds — the first page plus whatever the reader has pulled in. A match that sits past
 * the current chunk does not appear until that chunk loads. That is a real limitation of
 * client-side matching, and it is stated in the component that owns it rather than
 * hidden here.
 */

/** A card, in the fields the search reads. */
export type SearchableCard = {
  /** The card's headline. */
  title: string;
  /** The venue name, if the payload carries one. */
  venue_name?: string | null;
  /** The venue city, if the payload carries one. */
  venue_city?: string | null;
  /** The server's why-tag keys, in the server's order. */
  tags: string[];
};

/**
 * A parsed query.
 *
 * **`words` and `tags` are separate lists, and the order between them does not matter.**
 * The query is a conjunction, not a program: every word must match and every tag must
 * match, and there is no ordering to get wrong.
 */
export type SearchQuery = {
  /** The plain words, lowercased and trimmed. */
  words: string[];
  /** The `tag:` tokens, lowercased and trimmed — the *friendly* names, not the server's keys. */
  tags: string[];
  /**
   * The tags that resolve to a server key.
   *
   * **A tag that resolves to nothing is kept, separately.** An unknown `tag:` token is
   * *not* dropped: dropping it would widen the query to whatever the other terms said,
   * which is the failure the grammar exists to prevent. It is kept so the matcher can
   * refuse the whole query.
   */
  resolvedTags: (string | null)[];
};

/** The prefix a tag literal carries. */
const TAG_PREFIX = "tag:";

/**
 * A query, parsed.
 *
 * **The rules, and each one is load-bearing.**
 *
 * - **Whitespace-split, lowercased, trimmed.** `  Jazz   FREE  ` and `jazz free` are
 *   the same query. Lowercasing is what lets `JAZZ` and `jazz` match the same card.
 * - **A `tag:` literal is not a word.** `tag:music` is a constraint, and it is the *only*
 *   way to constrain — a bare `music` is a plain word that matches any card mentioning
 *   music anywhere.
 * - **`tag:` with nothing after the colon is not a tag.** It is dropped entirely: a
 *   reader who typed `tag:` meant to type a tag and did not, and treating the bare
 *   prefix as a term would silently narrow the query to cards with a tag literally
 *   named "tag".
 * - **A tag token that resolves to no server key stays in the query**, as `null` in
 *   `resolvedTags`. The matcher refuses the query rather than dropping the term.
 */
export function tokenize(query: string): SearchQuery {
  const words: string[] = [];
  const tags: string[] = [];

  for (const raw of query.split(/\s+/)) {
    const term = raw.trim().toLowerCase();
    if (!term) continue;

    if (term.startsWith(TAG_PREFIX)) {
      const token = term.slice(TAG_PREFIX.length).trim();
      // **A tag prefix with no token is not a tag.** It is dropped, not narrowed on.
      if (!token) continue;
      tags.push(token);
      continue;
    }

    words.push(term);
  }

  return {
    words,
    tags,
    resolvedTags: tags.map((token) => searchTagKey(token)),
  };
}

/** Whether a query constrains anything at all. */
export function isEmptyQuery(query: SearchQuery): boolean {
  return query.words.length === 0 && query.tags.length === 0;
}

/**
 * Whether a card matches a query.
 *
 * **Every term must match, and an unmatched tag refuses the whole query.**
 *
 * A plain word matches the card's **headline**, its **where line** (the venue name,
 * then the venue city) or one of its **why-tag keys**. A `tag:` literal matches only a
 * why-tag key — never the headline and never the venue, because the tag vocabulary is
 * the card's *reason for being here*, not its text.
 *
 * **The match is against the server's raw keys, not the rendered labels.** A card's tags
 * are `matches_arts_culture` and `tonight`; their labels are "Arts & culture" and
 * "Tonight". Matching on labels would make the grammar depend on copy changes, and
 * `tag:arts` would stop working the day the label became "Arts".
 */
export function matchesCard(card: SearchableCard, query: SearchQuery): boolean {
  // **An unknown tag refuses the query outright.** This is the rule the grammar's
  // trustworthiness rests on: `tag:music` (a name the server has no fact for) must not
  // quietly become a plain-word search for "music".
  if (query.resolvedTags.some((key) => key === null)) return false;

  const title = card.title.toLowerCase();
  const where = [card.venue_name, card.venue_city]
    .filter((part): part is string => Boolean(part))
    .join(" ")
    .toLowerCase();
  // **The tag keys are already lowercase** — the server sends them that way — but the
  // match is on the raw key, so they are compared exactly, not case-folded.
  const tagSet = new Set(card.tags);

  for (const word of query.words) {
    const inTitle = title.includes(word);
    const inWhere = where.includes(word);
    const inTag = card.tags.some((tag) => tag.includes(word));
    if (!inTitle && !inWhere && !inTag) return false;
  }

  for (const key of query.resolvedTags) {
    // `key` is non-null here: the null case returned above.
    if (!key || !tagSet.has(key)) return false;
  }

  return true;
}

/**
 * The cards that match, in the order they were given.
 *
 * **The order is the server's.** The filter removes cards; it does not rearrange them.
 */
export function filterCards<T extends SearchableCard>(cards: T[], query: SearchQuery): T[] {
  if (isEmptyQuery(query)) return cards;
  return cards.filter((card) => matchesCard(card, query));
}

/**
 * How many of a pool's tier-one cards survived a filter.
 *
 * **The tier split belongs to the pool, not to the filtered list.** The server's
 * `tier_2_starts_at` is an index into the *pool* it sent — the first three cards are
 * tier one, and the rest are tier two. A filter that removes a tier-one card does not
 * promote a tier-two card into tier one; it makes tier one *smaller*.
 *
 * **This is why the split cannot be recomputed from the filtered list.** Slicing the
 * filtered list at `tier_2_starts_at` would say "the first three survivors are tier
 * one" — and when the filter removed all three of the pool's tier-one cards, the first
 * three survivors would be tier-*two* cards wearing tier one's heading. The heading
 * "3 worth your attention today" would then head cards the server never said were worth
 * the reader's attention, which is the re-tiering AD-10 forbids.
 *
 * **The count is over the prefix.** The pool's tier one is its first `tierTwoStartsAt`
 * cards; the number of those that matched is the number the grid's first section holds.
 */
export function survivingTierOneCount(
  pool: readonly { event_id: string }[],
  matchedIds: ReadonlySet<string>,
  tierTwoStartsAt: number,
): number {
  const split = Math.max(0, Math.min(tierTwoStartsAt, pool.length));
  let count = 0;
  for (let index = 0; index < split; index += 1) {
    const card = pool[index];
    if (card && matchedIds.has(card.event_id)) count += 1;
  }
  return count;
}

/**
 * The query's terms, as the hint line and the empty state name them.
 *
 * **The reader's own terms, back to them.** The mockup's no-match state says *"No cards
 * in tonight + 7 days satisfy both `quantum` and `poetry`"* — hard-coded, in the
 * mockup, because the mockup had no reader. Here they are the reader's, so the sentence
 * is about their query and not about a persona's.
 *
 * **The terms are named in the order they were typed**, and a `tag:` literal keeps its
 * `tag:` prefix so the reader can see it was read as a constraint.
 */
export function queryTerms(query: SearchQuery): string[] {
  return [...query.words, ...query.tags.map((tag) => `${TAG_PREFIX}${tag}`)];
}

/**
 * The hint line's grammar summary — "Match: `jazz` AND `free`".
 *
 * **"AND" is the whole rule, so it is the word that is said.** A reader who typed two
 * words and got nothing back needs to know that both must match, and "AND" is what the
 * grammar does.
 */
export function querySummary(query: SearchQuery): string {
  const terms = queryTerms(query);
  if (terms.length === 0) return "";
  if (terms.length === 1) return `Match: ${terms[0]}`;
  return `Match: ${terms.join(" AND ")}`;
}
