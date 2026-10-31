// @vitest-environment node
/**
 * The Pulse Card's structural rules, asserted against the source rather than the DOM.
 *
 * **These are the rules a rendering test cannot catch.** A test that renders the card can
 * see that the stripe is the right colour and that the tags are capped; it cannot see
 * that the card contains no literal hex value, or that a hex value has crept into a
 * *second* file, or that the tag separator is a DOM character rather than a CSS
 * pseudo-element. Those are properties of the source, so they are asserted on the source.
 *
 * The rules come from `DESIGN.md` and `EXPERIENCE.md`, and they are the ones whose
 * violation would be silent: a literal hex would look right in one theme and wrong in the
 * other, and a `::after` separator would look right and be silent to a screen reader.
 */
import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "..");
const CARD = path.join(ROOT, "components/digest/pulse-card.tsx");
const LABELS = path.join(ROOT, "lib/digest-labels.ts");

const cardSource = readFileSync(CARD, "utf8");
const labelsSource = readFileSync(LABELS, "utf8");

/**
 * The source with its comments removed.
 *
 * **A comment is not code.** The card's docstrings quote the spec — they mention the
 * middle dot, the pseudo-element rule and the preview's vocabulary — and a source-text
 * assertion that read them would be asserting on prose. So the comments come out first,
 * and what is left is what the compiler sees.
 */
function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
}

const cardCode = withoutComments(cardSource);
const labelsCode = withoutComments(labelsSource);

/** The class-name strings in a .tsx file. */
function classStrings(source: string): string[] {
  return [...source.matchAll(/className=(?:"([^"]*)"|\{`([^`]*)`\}|\{"([^"]*)"\})/g)].map(
    (match) => match[1] ?? match[2] ?? match[3],
  );
}

describe("the card's tokens", () => {
  it("uses no literal hex colour", () => {
    // A literal hex would be right in one theme and wrong in the other, and it would not
    // fail `styles/tokens.test.ts` — that test checks `tokens.css` against `DESIGN.md`.
    const hex = cardCode.match(/#[0-9a-fA-F]{3,8}\b/g) ?? [];
    expect(hex).toEqual([]);
  });

  it("uses no raw rgb() or hsl() colour", () => {
    const raw = cardCode.match(/\b(?:rgb|rgba|hsl|hsla)\(/g) ?? [];
    expect(raw).toEqual([]);
  });

  it("takes every colour from a token utility", () => {
    const colours = classStrings(cardCode)
      .flatMap((value) => value.split(/\s+/))
      .filter((token) => /^(?:bg|text|border|ring|outline|fill|stroke)-/.test(token));

    expect(colours.length).toBeGreaterThan(0);
    for (const token of colours) {
      // The token utilities the card uses, all of which are declared in `tokens.css`.
      // `ring-1` is a *width*, not a colour, so it is not in this set — the ring's
      // colour is the separate `ring-ink-faint` utility.
      if (token === "ring-1") continue;
      expect(
        /^(?:bg|text|border|ring|outline)-(?:surface|ink|accent|warm|warn|signal|border)/.test(
          token,
        ),
        token,
      ).toBe(true);
    }
  });

  it("names no font family outside the type scale", () => {
    const families = classStrings(cardCode)
      .flatMap((value) => value.split(/\s+/))
      .filter((token) => token.includes("[font:"));

    expect(families.length).toBeGreaterThan(0);
    for (const token of families) {
      expect(token, token).toMatch(/\[font:var\(--type-scale-/);
    }
  });

  it("names no font *family* utility outside the type scale", () => {
    // `font-display` / `font-body` / `font-mono` are the three family utilities
    // `tokens.css` declares. A fourth would be a font outside the token layer.
    // `font-medium` and friends are *weight* utilities, not families.
    const weights = new Set([
      "font-thin",
      "font-light",
      "font-normal",
      "font-medium",
      "font-semibold",
      "font-bold",
    ]);
    const familyUtilities = classStrings(cardCode)
      .flatMap((value) => value.split(/\s+/))
      .filter((token) => /^font-[a-z]+$/.test(token) && !weights.has(token));

    for (const token of familyUtilities) {
      expect(["font-display", "font-body", "font-mono"], token).toContain(token);
    }
  });
});

describe("the card's motion", () => {
  it("declares no transition, duration, delay or animation class", () => {
    // `styles/motion.test.ts` proves the *stylesheets* carry one transition. This proves
    // the *markup* adds none — a Tailwind `transition-opacity` would pass that test and
    // would be a second motion in the product.
    const motion = classStrings(cardCode)
      .flatMap((value) => value.split(/\s+/))
      .filter((token) =>
        /^(?:[\w-]+:)*(?:animate-[\w-]+|transition(?:-[\w-]+)?|duration-[\w-]+|delay-[\w-]+|ease-[\w-]+)$/.test(
          token,
        ),
      );
    expect(motion).toEqual([]);
  });

  it("uses the one fade class", () => {
    expect(cardCode).toContain("fade-in");
  });
});

describe("the tag separator", () => {
  it("is a comma in the DOM, not a CSS pseudo-element", () => {
    // `EXPERIENCE.md` §8: visible helper text must be in the DOM. A `::after` would be
    // visible to a sighted user and silent to a screen reader.
    expect(cardCode).not.toContain("::after");
    expect(cardCode).not.toContain("::before");
    expect(cardCode).not.toContain("content-[");
  });

  it("is the comma, not the middle dot the mockup uses", () => {
    // The separator is the string the tag row joins its tags with. The middle dot the
    // mockup uses appears elsewhere on the card — the time row's own separator — so the
    // assertion is about the *separator*, not about the character.
    expect(cardCode).toContain('", "');
    const separator = /index > 0 \? ([^:]+): null/.exec(cardCode);
    expect(separator?.[1]).toContain('", "');
  });
});

describe("the source badge's colours", () => {
  it("keeps terracotta to the official badge and the focus ring", () => {
    // The four sanctioned uses are the today dot, the primary CTA, the verified badge
    // and the focus ring. On this card, two of them are reachable: the badge's label
    // and the link's focus ring. Nothing else may carry it.
    const terracotta = classStrings(cardCode)
      .flatMap((value) => value.split(/\s+/))
      .filter((token) => token.includes("terracotta"));

    expect(terracotta.length).toBeGreaterThan(0);
    for (const token of terracotta) {
      expect(token, token).toMatch(
        /^(?:text-accent-terracotta|focus-visible:outline-accent-terracotta)$/,
      );
    }
  });

  it("gives no interactive element a stripe colour", () => {
    // `color.accent.slate` and `color.accent.amber` are reserved for the category
    // stripe; `color.warm.personal` for the Personal tone. None may appear on a button.
    const stripeColours = classStrings(cardCode)
      .flatMap((value) => value.split(/\s+/))
      .filter((token) => /(?:accent-slate|accent-amber|warm-personal)$/.test(token));

    for (const token of stripeColours) {
      // The only permitted use is the stripe's own `bg-` utility.
      expect(token, token).toMatch(/^bg-/);
    }
  });
});

describe("the label tables", () => {
  it("use no literal hex colour", () => {
    expect(labelsCode.match(/#[0-9a-fA-F]{3,8}\b/g) ?? []).toEqual([]);
  });

  it("do not import the preview's vocabulary", () => {
    // The Relevance Pulse's tags and the Event Fit's tags are different vocabularies
    // (AD-10 forbids substituting one for the other). One translation table each.
    expect(labelsCode).not.toContain("preview-labels");
  });
});
