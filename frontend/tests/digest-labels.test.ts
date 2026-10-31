// @vitest-environment node
/**
 * The digest's label tables, checked against the backend's.
 *
 * **The server states the fact; the client speaks the user's language.** The tag keys
 * and the chip slugs live in `backend/shared/constants.py`, and the frontend cannot
 * import Python. So the labels are restated in `lib/digest-labels.ts` — and this test is
 * what stops the restatement from going stale.
 *
 * A chip with no label is not an error: it is rendered from its slug, so a new chip still
 * appears on the card. What this test forbids is a chip whose **label** has drifted — a
 * user reading "Arts and culture" on the card and "Arts & culture" in the chip picker is
 * looking at the same fact spelled two ways.
 */
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { sourceBadge, tagLabel } from "@/lib/digest-labels";

const BACKEND_CONSTANTS = path.resolve(__dirname, "../../backend/shared/constants.py");

function constantsSource(): string {
  if (!existsSync(BACKEND_CONSTANTS)) {
    throw new Error(`backend constants not found at ${BACKEND_CONSTANTS}; update the constant.`);
  }
  return readFileSync(BACKEND_CONSTANTS, "utf8");
}

/** The backend's `INTEREST_CHIPS` table: a tuple of `(slug, label)` pairs. */
function backendChips(): [string, string][] {
  const source = constantsSource();
  const block = /INTEREST_CHIPS\s*=\s*\(([\s\S]*?)\n\)/.exec(source);
  if (!block) throw new Error("backend constants have no INTEREST_CHIPS table");
  return [...block[1].matchAll(/\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)/g)].map((match) => [
    match[1],
    match[2],
  ]);
}

/** The backend's fixed Relevance Pulse tag keys (`RANKING_TAG_*`). */
function backendRankingTags(): string[] {
  const source = constantsSource();
  const keys = [...source.matchAll(/^RANKING_TAG_[A-Z_]+\s*=\s*"([^"]+)"$/gm)].map(
    (match) => match[1],
  );
  // The chip prefix is a prefix, not a key.
  return keys.filter((key) => key !== "matches_");
}

describe("the chip labels", () => {
  it("match the backend's chip table exactly", () => {
    const chips = backendChips();
    expect(chips.length).toBeGreaterThan(0);

    for (const [slug, label] of chips) {
      // The chip-match tag key is `matches_<slug>`.
      expect(tagLabel(`matches_${slug}`), slug).toBe(label);
    }
  });

  it("cover every chip the backend can send", () => {
    for (const [slug] of backendChips()) {
      const label = tagLabel(`matches_${slug}`);
      // Not the raw slug: a chip with no label would render as "arts_culture".
      expect(label, slug).not.toBe(slug);
      expect(label, slug).toMatch(/^[A-Z]/);
    }
  });

  it("do not label a chip the backend does not have", () => {
    const known = new Set(backendChips().map(([slug]) => slug));
    // A slug the backend does not have is rendered from itself, so the test cannot see
    // the difference — but the table must not have grown a chip of its own.
    expect(tagLabel("matches_not_a_real_chip")).toBe("Not A Real Chip");
    expect(known.has("not_a_real_chip")).toBe(false);
  });
});

describe("the fixed Why-this Tags", () => {
  it("label every fixed tag the backend can send", () => {
    const tags = backendRankingTags();
    expect(tags.length).toBeGreaterThan(0);

    for (const key of tags) {
      const label = tagLabel(key);
      expect(label, key).not.toBe(key);
      expect(label, key).toMatch(/^[A-Z]/);
    }
  });

  it("label the tags the backend sends under different names", () => {
    // `shared.constants` carries the Event Fit's `this_weekend` and the Relevance
    // Pulse's `weekend` — two keys for one idea, in two tables. The client translates
    // each vocabulary on its own terms and does not merge them.
    expect(tagLabel("this_weekend")).toBe("This Weekend");
    expect(tagLabel("weekend")).toBe("This weekend");
  });

  it("render an unknown tag from its slug rather than dropping it", () => {
    expect(tagLabel("a_brand_new_tag")).toBe("A Brand New Tag");
  });
});

describe("the Source Badge", () => {
  it("has a label and a tooltip for each of the five variants", () => {
    const variants = ["official_site", "community", "aggregator", "user_imported", "crawled_html"];
    for (const variant of variants) {
      const badge = sourceBadge(variant);
      expect(badge.label, variant).toMatch(/^[A-Z]/);
      expect(badge.tooltip, variant).not.toBe("");
    }
  });

  it("keeps the terracotta for the official badge alone", () => {
    expect(sourceBadge("official_site").official).toBe(true);
    for (const variant of ["community", "aggregator", "user_imported", "crawled_html"]) {
      expect(sourceBadge(variant).official, variant).toBe(false);
    }
  });

  it("does not borrow the official treatment for an unknown type", () => {
    const badge = sourceBadge("a_brand_new_source");

    expect(badge.official).toBe(false);
    expect(badge.label).toBe("Listed");
  });

  it("marks only the crawled listing as a warning", () => {
    expect(sourceBadge("crawled_html").warn).toBe(true);
    for (const variant of ["official_site", "community", "aggregator", "user_imported"]) {
      expect(sourceBadge(variant).warn, variant).toBe(false);
    }
  });

  it("italicises only the community label", () => {
    expect(sourceBadge("community").italic).toBe(true);
    for (const variant of ["official_site", "aggregator", "user_imported", "crawled_html"]) {
      expect(sourceBadge(variant).italic, variant).toBe(false);
    }
  });
});
