// @vitest-environment node
/**
 * The Browse search's grammar, tested on its own.
 *
 * **The grammar is a pure function, so it is tested without rendering anything.**
 * Tokenisation is the kind of thing that looks trivial and has edge cases, and this
 * file is where they live: an empty query, a whitespace-only query, mixed case, a plain
 * word that is also a tag name, a `tag:` with no token after the colon, and two tags at
 * once.
 *
 * **The design's ten tags are not all the server's tags, and this file is where that
 * is pinned down.** `DESIGN.md` names `music · tech · community · arts · family · food ·
 * sports · outdoor · indoor · rooftop`; the server's why-tag vocabulary is
 * `discovery · nearby · tonight · tomorrow · weekend · saved` plus `matches_<chip>` for
 * ten *other* slugs. Six of the design's ten resolve through the alias table and four
 * do not — and the four that do not **match nothing**, because the grammar's own rule
 * is that an unknown `tag:` token never widens into a plain-word match.
 */
import { describe, expect, it } from "vitest";

import {
  filterCards,
  isEmptyQuery,
  matchesCard,
  querySummary,
  queryTerms,
  survivingTierOneCount,
  tokenize,
  type SearchableCard,
} from "@/lib/browse-search";
import { searchTagKey } from "@/lib/digest-labels";

function card(overrides: Partial<SearchableCard> = {}): SearchableCard {
  return {
    title: "Brooklyn Symphony open rehearsal",
    venue_name: "BAM Howard Gilman Opera House",
    venue_city: "Brooklyn",
    tags: ["nearby", "tonight"],
    ...overrides,
  };
}

describe("tokenising a query", () => {
  it("splits on whitespace, lowercases and trims", () => {
    const query = tokenize("  Jazz   FREE  ");

    expect(query.words).toEqual(["jazz", "free"]);
    expect(query.tags).toEqual([]);
  });

  it("treats an empty query as empty", () => {
    expect(isEmptyQuery(tokenize(""))).toBe(true);
  });

  it("treats a whitespace-only query as empty", () => {
    expect(isEmptyQuery(tokenize("   \t\n  "))).toBe(true);
  });

  it("reads a `tag:` literal as a tag and not as a word", () => {
    const query = tokenize("jazz tag:music");

    expect(query.words).toEqual(["jazz"]);
    expect(query.tags).toEqual(["music"]);
  });

  it("reads a bare `tag:` as no tag at all", () => {
    // The reader meant to type a tag and did not. Narrowing the query to cards with a
    // tag literally named "tag" would be a narrowing nobody asked for.
    const query = tokenize("tag:");

    expect(query.tags).toEqual([]);
    expect(query.words).toEqual([]);
    expect(isEmptyQuery(query)).toBe(true);
  });

  it("reads two tags at once", () => {
    const query = tokenize("tag:tonight tag:tech");

    expect(query.tags).toEqual(["tonight", "tech"]);
    expect(query.words).toEqual([]);
  });

  it("keeps a plain word that is also a tag name as a plain word", () => {
    // `tag:` is the only way to constrain. A bare "music" is a word that matches any
    // card mentioning music anywhere.
    const query = tokenize("music");

    expect(query.words).toEqual(["music"]);
    expect(query.tags).toEqual([]);
  });

  it("lowercases a tag token", () => {
    expect(tokenize("tag:Music").tags).toEqual(["music"]);
  });
});

describe("resolving a tag token", () => {
  it("resolves the friendly names that have a server counterpart", () => {
    expect(searchTagKey("tech")).toBe("matches_tech_meetups");
    expect(searchTagKey("sports")).toBe("matches_sports_fitness");
    expect(searchTagKey("arts")).toBe("matches_arts_culture");
    expect(searchTagKey("family")).toBe("matches_family_kids");
    expect(searchTagKey("community")).toBe("matches_community_volunteering");
    expect(searchTagKey("outdoor")).toBe("matches_outdoors_nature");
  });

  it("resolves the server's own fixed tags to themselves", () => {
    expect(searchTagKey("tonight")).toBe("tonight");
    expect(searchTagKey("tomorrow")).toBe("tomorrow");
    expect(searchTagKey("weekend")).toBe("weekend");
    expect(searchTagKey("nearby")).toBe("nearby");
    expect(searchTagKey("saved")).toBe("saved");
    expect(searchTagKey("discovery")).toBe("discovery");
  });

  it("resolves the four tags the server has no fact for to nothing", () => {
    // The design names these four; the server has no key for any of them, so they
    // cannot be matched against anything.
    for (const token of ["music", "food", "indoor", "rooftop"]) {
      expect(searchTagKey(token), token).toBeNull();
    }
  });

  it("resolves a token nobody has heard of to nothing", () => {
    expect(searchTagKey("quantum")).toBeNull();
  });
});

describe("matching a card", () => {
  it("matches everything on an empty query", () => {
    expect(matchesCard(card(), tokenize(""))).toBe(true);
  });

  it("matches a word in the headline", () => {
    expect(matchesCard(card(), tokenize("symphony"))).toBe(true);
    expect(matchesCard(card(), tokenize("rehearsal"))).toBe(true);
  });

  it("matches a word in the where line", () => {
    expect(matchesCard(card(), tokenize("opera"))).toBe(true);
    expect(matchesCard(card(), tokenize("brooklyn"))).toBe(true);
  });

  it("matches a word in a why-tag token", () => {
    expect(matchesCard(card(), tokenize("nearby"))).toBe(true);
    expect(matchesCard(card(), tokenize("tonight"))).toBe(true);
  });

  it("does not match a word that is nowhere on the card", () => {
    expect(matchesCard(card(), tokenize("quantum"))).toBe(false);
  });

  it("matches regardless of case", () => {
    expect(matchesCard(card(), tokenize("SYMPHONY"))).toBe(true);
    expect(matchesCard(card(), tokenize("Symphony"))).toBe(true);
  });

  it("ANDs two plain words", () => {
    expect(matchesCard(card(), tokenize("symphony brooklyn"))).toBe(true);
    // Only one of them is on the card.
    expect(matchesCard(card(), tokenize("symphony quantum"))).toBe(false);
  });

  it("ANDs three plain words", () => {
    expect(matchesCard(card(), tokenize("symphony brooklyn tonight"))).toBe(true);
    expect(matchesCard(card(), tokenize("symphony brooklyn quantum"))).toBe(false);
  });

  it("matches a tag literal against the card's why-tag keys", () => {
    const tagged = card({ tags: ["nearby", "matches_arts_culture"] });

    expect(matchesCard(tagged, tokenize("tag:arts"))).toBe(true);
    expect(matchesCard(tagged, tokenize("tag:nearby"))).toBe(true);
  });

  it("does not match a tag literal against the headline or the venue", () => {
    // A `tag:` constrains to the card's *reason for being here*, not its text.
    const tagged = card({
      title: "Rooftop jazz at Bar Part",
      venue_name: "The Rooftop",
      tags: ["nearby"],
    });

    expect(matchesCard(tagged, tokenize("tag:rooftop"))).toBe(false);
    expect(matchesCard(tagged, tokenize("tag:jazz"))).toBe(false);
  });

  it("does not match a tag literal the card does not carry", () => {
    expect(matchesCard(card({ tags: ["nearby"] }), tokenize("tag:tech"))).toBe(false);
  });

  it("ANDs a tag literal with a plain word", () => {
    const tagged = card({ tags: ["nearby", "matches_arts_culture"] });

    expect(matchesCard(tagged, tokenize("symphony tag:arts"))).toBe(true);
    // The word is on the card; the tag is not.
    expect(matchesCard(tagged, tokenize("symphony tag:tech"))).toBe(false);
    // The tag is on the card; the word is not.
    expect(matchesCard(tagged, tokenize("quantum tag:arts"))).toBe(false);
  });

  it("matches nothing when a tag token is one the server has no fact for", () => {
    // The rule the grammar's trustworthiness rests on: `tag:music` must not quietly
    // become a plain-word search for "music".
    const jazz = card({ title: "Rooftop jazz at Bar Part", tags: ["nearby"] });

    expect(matchesCard(jazz, tokenize("tag:music"))).toBe(false);
    expect(matchesCard(jazz, tokenize("jazz tag:music"))).toBe(false);
  });

  it("matches nothing when a tag token is unknown entirely", () => {
    const jazz = card({ title: "Rooftop jazz at Bar Part", tags: ["nearby"] });

    expect(matchesCard(jazz, tokenize("tag:quantum"))).toBe(false);
  });

  it("ANDs two tag literals", () => {
    const tagged = card({ tags: ["nearby", "matches_arts_culture", "tonight"] });

    expect(matchesCard(tagged, tokenize("tag:tonight tag:arts"))).toBe(true);
    expect(matchesCard(tagged, tokenize("tag:tonight tag:tech"))).toBe(false);
  });
});

describe("filtering the loaded set", () => {
  const cards = [
    card({ title: "Brooklyn Symphony open rehearsal", tags: ["nearby", "tonight"] }),
    card({
      title: "Rooftop jazz at Bar Part",
      venue_name: "Bar Part",
      tags: ["nearby", "matches_arts_culture"],
    }),
    card({ title: "Gallery late opening", venue_name: "Pioneer Works", tags: ["saved"] }),
  ];

  it("returns every card on an empty query, in order", () => {
    expect(filterCards(cards, tokenize(""))).toEqual(cards);
  });

  it("keeps the server's order among the survivors", () => {
    // The filter removes cards; it never rearranges them (AD-10).
    const matched = filterCards(cards, tokenize("nearby"));

    expect(matched.map((c) => c.title)).toEqual([
      "Brooklyn Symphony open rehearsal",
      "Rooftop jazz at Bar Part",
    ]);
  });

  it("returns nothing when nothing matches", () => {
    expect(filterCards(cards, tokenize("quantum"))).toEqual([]);
  });

  it("matches a card by its why-tag token", () => {
    const matched = filterCards(cards, tokenize("tag:saved"));

    expect(matched.map((c) => c.title)).toEqual(["Gallery late opening"]);
  });
});

describe("naming the query back to the reader", () => {
  it("names the terms in the order they were typed", () => {
    expect(queryTerms(tokenize("jazz tag:tonight"))).toEqual(["jazz", "tag:tonight"]);
  });

  it("keeps the `tag:` prefix on a tag term", () => {
    // The reader can see it was read as a constraint.
    expect(queryTerms(tokenize("tag:arts"))).toEqual(["tag:arts"]);
  });

  it("says AND between the terms", () => {
    expect(querySummary(tokenize("jazz free"))).toBe("Match: jazz AND free");
  });

  it("says nothing about a single term's operator", () => {
    expect(querySummary(tokenize("jazz"))).toBe("Match: jazz");
  });

  it("says nothing at all about an empty query", () => {
    expect(querySummary(tokenize(""))).toBe("");
  });
});

/**
 * The tier split, counted against the pool.
 *
 * **This is where the filter could quietly re-tier, and the whole file is the defence.**
 * The server's `tier_2_starts_at` is an index into the *pool* it sent. Slicing the
 * *filtered* list at that index would say "the first three survivors are tier one" —
 * and when the filter removed all three of the pool's tier-one cards, the first three
 * survivors would be tier-*two* cards wearing tier one's heading. "3 worth your
 * attention today" would then head cards the server never said were worth the
 * reader's attention, which is the re-tiering AD-10 forbids.
 */
describe("counting the pool's tier-one survivors", () => {
  const pool = [
    { event_id: "a1" },
    { event_id: "a2" },
    { event_id: "a3" },
    { event_id: "b1" },
    { event_id: "b2" },
  ];

  it("counts every tier-one card when nothing was filtered out", () => {
    const matched = new Set(pool.map((c) => c.event_id));

    expect(survivingTierOneCount(pool, matched, 3)).toBe(3);
  });

  it("counts fewer when a tier-one card did not match", () => {
    // The filter removed two of the pool's three tier-one cards. Tier one is now one
    // card — not three.
    const matched = new Set(["a1", "b1", "b2"]);

    expect(survivingTierOneCount(pool, matched, 3)).toBe(1);
  });

  it("counts none when every tier-one card was filtered out", () => {
    // **The defect this exists to prevent.** Only tier-two cards matched. The tier-one
    // section must be empty, and the tier-two cards must stay tier two — promoting
    // them would put them under "3 worth your attention today".
    const matched = new Set(["b1", "b2"]);

    expect(survivingTierOneCount(pool, matched, 3)).toBe(0);
  });

  it("never counts a tier-two card, even when it matched", () => {
    const matched = new Set(["b1", "b2"]);

    expect(survivingTierOneCount(pool, matched, 3)).toBe(0);
    expect(survivingTierOneCount(pool, matched, 0)).toBe(0);
  });

  it("clamps the split to the pool's length", () => {
    // A split larger than the pool is a split past its end. Nothing is tier one.
    const matched = new Set(pool.map((c) => c.event_id));

    expect(survivingTierOneCount(pool, matched, 99)).toBe(5);
  });

  it("treats a negative split as no tier one", () => {
    const matched = new Set(pool.map((c) => c.event_id));

    expect(survivingTierOneCount(pool, matched, -1)).toBe(0);
  });

  it("counts against the pool, not against the matches' own order", () => {
    // The matched set's iteration order is irrelevant — the pool's order decides which
    // of a card's matches are tier one.
    const matched = new Set(["b2", "a2", "b1"]);

    expect(survivingTierOneCount(pool, matched, 3)).toBe(1);
  });
});
