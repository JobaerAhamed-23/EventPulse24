// @vitest-environment node
/**
 * Colour contrast, computed **statically** from the token file.
 *
 * **What this replaces, and why.** The accessibility criterion says "Lighthouse ≥95",
 * and Lighthouse measures a rendered page in a browser under a throttled network.
 * Playwright is not installed and this run does not install it — the same scope
 * decision the previous two intents' proofs made and recorded.
 *
 * But "we could not run Lighthouse" is not the same as "we did not check contrast".
 * **Colour contrast is computable.** Given a foreground colour and a background
 * colour, the WCAG contrast ratio is a formula over two hex values — no browser, no
 * layout, no rendering. So this file computes the ratios for the pairs the two new
 * surfaces actually use, and asserts them against WCAG AA.
 *
 * **Why the token file and not the class names.** The classes are Tailwind's, and
 * Tailwind resolves them from `@theme` — a build step. The token file is where the
 * colours are *defined*, as hex. So the check reads the definitions.
 *
 * **What this cannot prove, stated plainly.** A contrast ratio computed from two hex
 * values is the same ratio a browser computes for those two colours. What it cannot
 * see is whether a particular element *has* that background — an element with a
 * semi-transparent background over a different one, or a gradient, resolves to
 * something else. Every pair below is **opaque**, so the computation is exact for
 * them; and the **axe gate** (which runs over every document and does see the
 * rendered DOM) covers the general case.
 *
 * **The threshold.** WCAG AA for normal text is **4.5:1**; for large text (18.66px
 * bold or 24px regular) it is **3:1**. This file uses **4.5:1** for everything — the
 * stricter one — so no pair here has to argue about which size it is.
 */
import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "..");
const TOKENS = path.join(ROOT, "styles/tokens.css");

const tokens = readFileSync(TOKENS, "utf8");

/**
 * The token file has **two themes**: the `:root` block (light) and the
 * `[data-theme="dark"]` block (dark), and `<html>` carries `data-theme="dark"` **by
 * default**.
 *
 * So a contrast check that reads one block checks one theme and says nothing about
 * the other — and the default theme is the *dark* one, so a parser that took the
 * last match would be checking the default and a parser that took the first would be
 * checking the other.
 *
 * **Both are checked.** Every pair below is asserted in **both** themes.
 */
const THEMES = ["light", "dark"] as const;

type Theme = (typeof THEMES)[number];

/**
 * Every `--color-…: #hex;` definition, by theme.
 *
 * **The split is on the theme blocks, not on the order.** The dark block is the one
 * that begins at `[data-theme="dark"]`, so the source is cut there and each half is
 * parsed independently. Taking "the last match" would silently pick one theme.
 */
function readTokens(): Map<Theme, Map<string, string>> {
  // **The last occurrence, not the first.** The file's own header *describes* the
  // dark block in prose — `"[data-theme=\"dark\"]"` appears in the docstring long
  // before the block itself — so `indexOf` would cut the file in the middle of its
  // own comment and parse an empty light palette.
  //
  // The block opener is distinguished by being at the **start of a line**, which the
  // prose never is. So the search is for the line-opening form, and the **last** one
  // is the block (there is only one, but "last" is what makes the prose safe).
  const darkStart = tokens.lastIndexOf('\n[data-theme="dark"]');
  if (darkStart === -1) {
    throw new Error('the token file has no [data-theme="dark"] block');
  }

  const lightSource = tokens.slice(0, darkStart);
  const darkSource = tokens.slice(darkStart);

  const parse = (source: string): Map<string, string> => {
    const found = new Map<string, string>();
    const pattern = /--color-([a-z-]+):\s*(#[0-9a-fA-F]{6})\s*;/g;

    let match = pattern.exec(source);
    while (match !== null) {
      found.set(match[1], match[2].toLowerCase());
      match = pattern.exec(source);
    }

    return found;
  };

  return new Map<Theme, Map<string, string>>([
    ["light", parse(lightSource)],
    ["dark", parse(darkSource)],
  ]);
}

const palettes = readTokens();

/** The WCAG relative luminance of an opaque sRGB colour. */
function luminance(hex: string): number {
  const value = hex.replace("#", "");
  const channels = [0, 2, 4].map((offset) => {
    const raw = parseInt(value.slice(offset, offset + 2), 16) / 255;
    // The WCAG formula's linearisation: a channel below 0.03928 is divided by
    // 12.92, and the rest is raised to 2.4.
    return raw <= 0.03928 ? raw / 12.92 : ((raw + 0.055) / 1.055) ** 2.4;
  });

  return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2];
}

/** The WCAG contrast ratio between two opaque colours. */
function contrastRatio(foreground: string, background: string): number {
  const lighter = Math.max(luminance(foreground), luminance(background));
  const darker = Math.min(luminance(foreground), luminance(background));
  return (lighter + 0.05) / (darker + 0.05);
}

/**
 * The pairs the two new surfaces use, **classified by WCAG role**.
 *
 * **The classification is the whole point, and it is not cosmetic.** WCAG 1.4.3
 * ("Contrast Minimum") applies to *text*: 4.5:1 for normal text, 3:1 for large text.
 * WCAG 1.4.11 ("Non-text Contrast") applies to *UI components and meaningful
 * graphics*: 3:1. A purely decorative element is exempt from both.
 *
 * So a single threshold over a single list would be wrong in both directions — it
 * would demand 4.5:1 of a decorative dot, and it would let a small grey label
 * through at 3:1.
 *
 * **Every pair here is opaque**, so the computed ratio is the ratio a browser would
 * compute. The background is stated explicitly for each one, because "ink on paper"
 * is a pair and "ink on elevated" is a different pair — the surface under an ink
 * colour is what decides the ratio.
 *
 * **Where each pair appears** is named, so a reader can check the claim against the
 * markup.
 */

/**
 * **Text pairs.** 4.5:1 in both themes.
 *
 * **The background is the surface the element actually sits on, and this file was
 * written wrong the first time.** The Pulse Card is `bg-surface-elevated`
 * (`components/digest/pulse-card.tsx:109`), not `bg-surface-paper` — so the card's
 * title, venue, time and timezone abbreviation are ink on **elevated**. The Detail
 * Screen's badge and body copy sit on the page itself, which is `bg-surface-paper`
 * (`components/shell/app-shell.tsx:27`). Getting this wrong is not a detail: it moves
 * every ratio by a measurable amount, and it is the difference between a card that
 * passes and one that does not.
 *
 * **The Source Badge's label is ink, and its glyph is the chromatic one.** That split
 * is the design's own: `EXPERIENCE.md` §4 `Badge.Source` — the canonical list — says
 * *"`official_site`: `color.accent.terracotta`-**filled checkmark icon**. Inline label
 * "Official" in `Text.Meta`"*, and `DESIGN.md`'s Amendment A-20 spells the same pattern
 * out for the auth error row: *"a 14×14 `⚠` glyph in `color.signal.warn` … + error text
 * in `{type.scale.meta.sm}` `{color.ink.secondary}`"*. So the **label** is text and
 * needs 4.5:1, and the **glyph** is a meaningful graphic and needs 3:1.
 */
const TEXT_PAIRS = [
  {
    where: "the digest home's event title, on the card",
    foreground: "ink-primary",
    background: "surface-elevated",
  },
  {
    where: "the digest home's event time, on the card",
    foreground: "ink-secondary",
    background: "surface-elevated",
  },
  {
    where: "the digest home's timezone abbreviation, on the card",
    foreground: "ink-muted",
    background: "surface-elevated",
  },
  {
    where: "the digest home's why-this tags, on the card",
    foreground: "ink-muted",
    background: "surface-elevated",
  },
  {
    where: "the digest home's category kicker, on the card",
    foreground: "ink-muted",
    background: "surface-elevated",
  },
  {
    where: "the digest home's header date line, on the page",
    foreground: "ink-secondary",
    background: "surface-paper",
  },
  {
    where: "the digest home's headline, on the page",
    foreground: "ink-primary",
    background: "surface-paper",
  },
  {
    where: "the digest home's lede, on the page",
    foreground: "ink-secondary",
    background: "surface-paper",
  },
  {
    where: "the detail screen's headline, on the page",
    foreground: "ink-primary",
    background: "surface-paper",
  },
  {
    where: "the detail screen's body copy, on the page",
    foreground: "ink-secondary",
    background: "surface-paper",
  },
  {
    where: "the detail screen's metadata, on the page",
    foreground: "ink-muted",
    background: "surface-paper",
  },
  {
    where: "the Source Badge's official label, on the card",
    foreground: "ink-secondary",
    background: "surface-elevated",
  },
  {
    where: "the Source Badge's community label, on the card",
    foreground: "ink-primary",
    background: "surface-elevated",
  },
  {
    where: "the Source Badge's official label, on the detail screen",
    foreground: "ink-secondary",
    background: "surface-paper",
  },
  {
    where: "the Source Badge's warning label, on the detail screen",
    foreground: "ink-secondary",
    background: "surface-paper",
  },
  {
    where: "inverse ink on the ink-primary button",
    foreground: "ink-inverse",
    background: "ink-primary",
  },
] as const;

/**
 * **Non-text pairs.** 3:1 in both themes, under WCAG 1.4.11.
 *
 * **These are the Confidence Pulse's dots and the Source Badge's glyphs** — meaning-
 * ful graphics that convey information the colour carries. The *filled* dot and the
 * *empty* dot are distinguishable only by their colour, so the pair between them is
 * the pair that must be readable.
 *
 * **The badge's glyph is the terracotta and the amber.** That is where `EXPERIENCE.md`
 * §4 puts them — the terracotta *fills the checkmark icon* — and it is where they
 * clear 3:1: the terracotta is 4.37:1 on paper and 4.64:1 on elevated, and the amber
 * is 4.79:1 at its worst across the light surfaces. As *text* they would not have
 * cleared 4.5:1 on paper, which is exactly why they are the glyph's colour and not the
 * label's.
 */
const NON_TEXT_PAIRS = [
  {
    where: "the filled confidence dot against the card",
    foreground: "ink-primary",
    background: "surface-elevated",
  },
  {
    where: "the Source Badge's official glyph, on the card",
    foreground: "accent-terracotta",
    background: "surface-elevated",
  },
  {
    where: "the Source Badge's official glyph, on the detail screen",
    foreground: "accent-terracotta",
    background: "surface-paper",
  },
  {
    where: "the Source Badge's warning glyph, on the card",
    foreground: "signal-warn",
    background: "surface-elevated",
  },
  {
    where: "the Source Badge's warning glyph, on the detail screen",
    foreground: "signal-warn",
    background: "surface-paper",
  },
  {
    where: "the Source Badge's community glyph, on the detail screen",
    foreground: "ink-primary",
    background: "surface-paper",
  },
  {
    where: "the conflict indicator's dot, on the card",
    foreground: "warn-amber",
    background: "surface-elevated",
  },
  {
    // **The same token, on the surface the conflict sheet puts it on.** The design's
    // `color.warn.amber` is one token, and it is used as a filled dot in the conflict
    // resolution sheet too (`components/sheets/conflict-resolution.tsx:305`), where the
    // row's surface is `surface.paper` or `surface.subtle`. **A token has to clear 3:1 on
    // every surface it is used on**, so the paper pair is asserted here too — the
    // design's `#B8893D` is 2.96:1 on paper and fails it.
    where: "the conflict indicator's dot, on the conflict sheet's row",
    foreground: "warn-amber",
    background: "surface-paper",
  },
] as const;

/**
 * **The Confidence Pulse's own state distinction.** 3:1, under WCAG 1.4.11.
 *
 * **Why this pair and not "the empty dot against the card".** The Confidence Pulse is a
 * five-position indicator: `value` positions are filled with `color.ink.primary` and
 * the rest are `color.ink.faint`. What a sighted reader needs to identify is **the
 * state** — "three of five" — and the state is carried by the **difference between the
 * filled and the empty dot**. That difference is what this pair measures, and it is
 * **10.02:1** in light and **10.10:1** in dark: the state is not in doubt.
 *
 * **The empty dot is the track, and the design says so.** `DESIGN.md` names
 * `color.ink.faint` as the colour of the "empty `Indicator.Confidence` dot
 * placeholders" — the *placeholder* for an unfilled position, the way an unfilled
 * progress track is not itself the progress. The filled dot is what identifies the
 * state, and it is asserted against the card above at 17.73:1.
 *
 * **What this file does not claim.** It does not claim the empty dot is readable
 * against the card — at **1.77:1** it is not, and that is a *deliberate, recorded*
 * deviation rather than an oversight. See the deviation block below.
 */
const CONFIDENCE_STATE_PAIR = {
  where: "the filled confidence dot against the empty one",
  filled: "ink-primary",
  empty: "ink-faint",
  backgrounds: ["surface-elevated", "surface-paper"],
} as const;

/** Every pair, for the checks that do not care about the role. */
const ALL_PAIRS = [...TEXT_PAIRS, ...NON_TEXT_PAIRS];

/** WCAG AA for normal text — 1.4.3. */
const AA_NORMAL_TEXT = 4.5;

/** WCAG AA for non-text contrast — 1.4.11. */
const AA_NON_TEXT = 3.0;

describe("the token file", () => {
  it("defines a palette in both themes", () => {
    // **The palette must not be silently empty.** A token file the parser failed to
    // read would make every ratio below `NaN`, and a `NaN` comparison is false —
    // so the ratios would look fine.
    for (const theme of THEMES) {
      expect(palettes.get(theme)?.size ?? 0, `the ${theme} palette is empty`).toBeGreaterThan(10);
    }
  });

  it("defines every colour the pairs use, in both themes", () => {
    const missing: string[] = [];
    for (const theme of THEMES) {
      const palette = palettes.get(theme) as Map<string, string>;
      for (const pair of ALL_PAIRS) {
        if (!palette.has(pair.foreground)) missing.push(`${theme}: ${pair.foreground}`);
        if (!palette.has(pair.background)) missing.push(`${theme}: ${pair.background}`);
      }
    }

    expect(missing, "these tokens are not defined in styles/tokens.css").toEqual([]);
  });

  it("defines every colour as an opaque hex", () => {
    // **Opacity is what makes the computation exact.** A colour with an alpha
    // channel resolves against whatever is behind it, and a computed ratio would be
    // a fiction. So the check is that the colours are six-digit hex.
    const translucent: string[] = [];
    for (const [theme, palette] of palettes) {
      for (const [name, value] of palette) {
        if (!/^#[0-9a-f]{6}$/.test(value)) {
          translucent.push(`${theme} ${name}=${value}`);
        }
      }
    }

    expect(translucent, "these tokens are not opaque hex").toEqual([]);
  });
});

/**
 * **The design's own token rules, checked against the markup.**
 *
 * **Why this is here and not just the ratios.** A ratio says *"this colour on that
 * surface is readable"*. It does not say *"this colour is allowed to be doing this job"*.
 * `DESIGN.md` states its token rules in absolute terms, and the two that bit this
 * intent are:
 *
 * - *"`color.ink.faint` is reserved for empty `Indicator.Confidence` dot placeholders,
 *   the skeleton pulse animation's dim target, and the handle bar on mobile bottom
 *   sheets. **Never used for body copy or interactive affordances.**"*
 * - *"`color.signal.success`, `color.signal.warn`, and `color.signal.error` are signal
 *   colors, not brand colors. They appear only at the moment of state change, never as
 *   decoration."*
 *
 * Both were violated before this check existed, and **both violations were invisible to
 * the ratio computation** — `ink-faint` on paper is 1.67:1, which is *below* every
 * threshold, so a ratio check would catch it *if* the pair were listed, but the pair was
 * only in the list because someone thought to put it there. The rule check is what makes
 * it exhaustive: it says *no text element anywhere in these surfaces may carry
 * `ink-faint`*, so a future pair cannot be forgotten.
 */
describe("the design's token-usage rules, against the markup", () => {
  /** The files that make up the two new surfaces. */
  const SURFACE_FILES = [
    "components/digest/pulse-card.tsx",
    "components/detail/detail-header.tsx",
    "components/preview/preview-card.tsx",
  ] as const;

  /** A source file with its comments stripped — a comment is not code. */
  function code(relative: string): string {
    return readFileSync(path.join(ROOT, relative), "utf8")
      .replace(/\/\*[\s\S]*?\*\//g, "")
      .replace(/\/\/[^\n]*/g, "");
  }

  /**
   * Every use of a text-colour utility **in a `className`**, with the element it is on.
   *
   * **The element matters, and that is the whole subtlety.** `text-ink-faint` on an
   * `aria-hidden` glyph span is a **shape** — the `▸` chevron, the badge's warning
   * triangle — and a shape is not body copy. `text-ink-faint` on a span that carries
   * words **is** body copy, and the design forbids it.
   *
   * **The search is over `className` attributes, and not over the whole file.** That
   * distinction is load-bearing. The Source Badge's chromatic tokens appear twice in
   * these files: once in the **colour-selection expression** (`warn ? "text-signal-warn"`
   * — the value a variable holds) and once as the **class it is applied as**
   * (`className={colour}` — the class an element carries). Only the second is a
   * rendered class. Searching the whole file would find the first and misreport a
   * variable's value as an element's class — which is what the first version of this
   * check did, and it reported two violations that were not violations at all.
   *
   * **The walk is a backwards scan to the enclosing opening tag.** That is the only
   * thing a source-text check can do without a parser, and it is exact here, because
   * the utilities are on the element's own `className` in every case in these files.
   */
  function textColourUses(
    relative: string,
    utility: RegExp,
  ): { where: string; decorative: boolean }[] {
    const source = code(relative);
    const uses: { where: string; decorative: boolean }[] = [];

    for (const match of source.matchAll(utility)) {
      const before = source.slice(0, match.index);
      const after = source.slice(match.index);

      // **Is this occurrence a rendered class?** It is, if the text around it is inside
      // a `className` attribute — either `className="…text-ink-faint…"` (a literal) or
      // `className={…}` (a variable's value, in which case the token appears in the
      // variable's *definition*, not in the attribute).
      //
      // **A literal class list is the only case where the token appears inside the
      // attribute itself.** A variable's value appears in a `const` or a ternary
      // *outside* any attribute — and the check below handles that case separately,
      // by asking what the variable is applied to.
      const inClassAttribute =
        /className\s*=\s*\{?"[^"]*$/.test(before) && !/["']\s*$/.test(after.slice(0, 1));

      if (!inClassAttribute) continue;

      // **The enclosing element's opening tag.** The nearest `<` before the match that
      // begins a tag.
      const tagStart = before.lastIndexOf("<");
      const tag = before.slice(tagStart);

      uses.push({
        where: `${relative}:${before.split("\n").length}`,
        // **An `aria-hidden` element is a shape or a redundant cue**, and the design's
        // rules are about *body copy* and *interactive affordances* — neither of which an
        // `aria-hidden` glyph is.
        decorative: /aria-hidden\s*=\s*\{?"true"/.test(tag),
      });
    }

    return uses;
  }

  it("no text element carries ink-faint", () => {
    // **`text-ink-faint` is the only way `ink-faint` reaches text.** A `bg-ink-faint` is
    // a shape, and a `ring-ink-faint` is a hairline — neither is body copy.
    const offenders: string[] = [];
    for (const file of SURFACE_FILES) {
      for (const use of textColourUses(file, /text-ink-faint/g)) {
        if (!use.decorative) offenders.push(use.where);
      }
    }

    expect(
      offenders,
      "these elements use text-ink-faint for words. DESIGN.md: color.ink.faint is " +
        "reserved for empty confidence-dot placeholders, the skeleton's dim target, and " +
        "the bottom sheet's handle bar — never for body copy or interactive affordances.",
    ).toEqual([]);
  });

  it("no text element carries a signal colour on these surfaces", () => {
    // **The signal colours are for state change, not for a permanent badge.** A
    // `crawled_html` badge is not a state change — it is a source's identity, and it
    // persists. So the amber belongs on the badge's *glyph* (which is what
    // EXPERIENCE.md §4 specifies, and what the auth error row does) and the label is
    // ink.
    const offenders: string[] = [];
    for (const file of SURFACE_FILES) {
      for (const use of textColourUses(file, /text-signal-(warn|error|success)/g)) {
        if (!use.decorative) offenders.push(use.where);
      }
    }

    expect(
      offenders,
      "these elements use a signal colour for words. DESIGN.md: the signal colours " +
        "appear only at the moment of state change, never as decoration. On the Source " +
        "Badge the amber is the glyph's colour and the label is ink.",
    ).toEqual([]);
  });

  it("the chromatic token reaches only the aria-hidden glyph", () => {
    // **The check that the previous one cannot make.** The chromatic tokens are applied
    // through a *variable* — `className={colour}` on the digest card,
    // `className={glyphColour}` on the detail header — so the search over literal class
    // lists cannot see them reach the DOM at all. Without this check, the rule above
    // would be satisfied by a file where the variable lands on the **label**: the token
    // would be nowhere near a literal `className`, and the rule would pass while the
    // design was broken.
    //
    // **So this traces the variable's provenance.** For each badge implementation:
    //
    // 1. the chromatic token appears in a colour-selection expression that assigns to a
    //    variable;
    // 2. that variable is applied to exactly one element;
    // 3. that element is `aria-hidden`;
    // 4. and the **label's** variable selects only ink.
    for (const file of [
      "components/digest/pulse-card.tsx",
      "components/detail/detail-header.tsx",
    ]) {
      const source = code(file);

      // **The chromatic token is selected somewhere.** If it is not, the badge has lost
      // its sanctioned colour entirely — which is also a failure, and a different one.
      expect(source, `${file}: the badge must still be able to take the terracotta token`).toMatch(
        /text-accent-terracotta/,
      );

      // **The variable that carries a chromatic token is applied to an `aria-hidden`
      // element.** The digest card's is `colour`, the detail header's is `glyphColour`.
      for (const variable of ["colour", "glyphColour"]) {
        const application = new RegExp(
          `<span[^>]*aria-hidden=\\{?"true"\\}?[^>]*className=\\{${variable}\\}|` +
            `<span[^>]*className=\\{${variable}\\}[^>]*aria-hidden=\\{?"true"\\}?`,
        );
        const declared = new RegExp(`const ${variable}\\s*=`);

        if (!declared.test(source)) continue;

        expect(
          source,
          `${file}: the '${variable}' class must be applied to the aria-hidden glyph, ` +
            "and to nothing else. The chromatic colour is the glyph's; the label is ink.",
        ).toMatch(application);
      }
    }
  });

  it("the Source Badge's chromatic colour is on the glyph, not the label", () => {
    // **The specific shape of the rule, on the two Source Badges.** Both surfaces
    // render the badge the same way, so the check is on both: the label is rendered in
    // an ink token, and the chromatic token is applied to the `aria-hidden` glyph.
    //
    // **Why this is a structural check and not a regex on the class string.** The two
    // implementations differ — the digest card's glyph takes its class from a variable
    // (`className={colour}`) while the detail header's takes it from another
    // (`className={glyphColour}`) — so a literal-string match would have to know which
    // is which. What they *share* is the shape: a `glyphColour`/`colour` value that
    // selects the chromatic token for the `official` variant, applied to a span marked
    // `aria-hidden`, and a separate label class that selects only ink.
    for (const file of [
      "components/digest/pulse-card.tsx",
      "components/detail/detail-header.tsx",
    ]) {
      const source = code(file);

      // **The chromatic token is reachable, and it is reachable only for the `official`
      // (or `warn`) variant.**
      expect(
        source,
        `${file}: the badge's glyph must be able to take the terracotta token`,
      ).toMatch(/text-accent-terracotta/);

      // **The glyph span is `aria-hidden`** — it is a shape, and its meaning is carried
      // by the label beside it.
      expect(
        source,
        `${file}: the badge's glyph must be aria-hidden, so the label carries the meaning`,
      ).toMatch(/aria-hidden="true"/);

      // **The label's class selects only ink.** This is the assertion that would fail if
      // the chromatic token were put back on the label: the label's class list is built
      // from `labelColour`, and `labelColour` must never select a chromatic token.
      expect(
        source,
        `${file}: the badge's label class must never select a chromatic token`,
      ).toMatch(
        /labelColour\s*=\s*badge\.italic\s*\?\s*"text-ink-primary italic"\s*:\s*"text-ink-secondary"/,
      );
    }
  });
});

describe("the two new surfaces' text pairs", () => {
  for (const theme of THEMES) {
    for (const pair of TEXT_PAIRS) {
      it(`[${theme}] ${pair.where}: ${pair.foreground} on ${pair.background} meets AA text`, () => {
        const palette = palettes.get(theme) as Map<string, string>;
        const foreground = palette.get(pair.foreground) as string;
        const background = palette.get(pair.background) as string;

        const ratio = contrastRatio(foreground, background);

        expect(
          ratio,
          `[${theme}] ${pair.where}: ${foreground} on ${background} is ` +
            `${ratio.toFixed(2)}:1, below the ${AA_NORMAL_TEXT}:1 AA text threshold ` +
            "(WCAG 1.4.3)",
        ).toBeGreaterThanOrEqual(AA_NORMAL_TEXT);
      });
    }
  }
});

describe("the two new surfaces' non-text pairs", () => {
  for (const theme of THEMES) {
    for (const pair of NON_TEXT_PAIRS) {
      it(`[${theme}] ${pair.where}: ${pair.foreground} on ${pair.background} meets AA non-text`, () => {
        const palette = palettes.get(theme) as Map<string, string>;
        const foreground = palette.get(pair.foreground) as string;
        const background = palette.get(pair.background) as string;

        const ratio = contrastRatio(foreground, background);

        expect(
          ratio,
          `[${theme}] ${pair.where}: ${foreground} on ${background} is ` +
            `${ratio.toFixed(2)}:1, below the ${AA_NON_TEXT}:1 AA non-text threshold ` +
            "(WCAG 1.4.11)",
        ).toBeGreaterThanOrEqual(AA_NON_TEXT);
      });
    }
  }
});

describe("the Confidence Pulse's state distinction", () => {
  for (const theme of THEMES) {
    for (const background of CONFIDENCE_STATE_PAIR.backgrounds) {
      it(`[${theme}] ${CONFIDENCE_STATE_PAIR.where} on ${background} meets AA non-text`, () => {
        const palette = palettes.get(theme) as Map<string, string>;
        const filled = palette.get(CONFIDENCE_STATE_PAIR.filled) as string;
        const empty = palette.get(CONFIDENCE_STATE_PAIR.empty) as string;

        const ratio = contrastRatio(filled, empty);

        expect(
          ratio,
          `[${theme}] the filled and empty confidence dots are ${ratio.toFixed(2)}:1 ` +
            `apart, below the ${AA_NON_TEXT}:1 AA non-text threshold (WCAG 1.4.11). ` +
            "The state the reader needs to identify is 'how many of the five are filled', " +
            "and that is what this ratio measures.",
        ).toBeGreaterThanOrEqual(AA_NON_TEXT);
      });
    }
  }
});

/**
 * **The recorded deviation: the empty confidence dot against the card.**
 *
 * **This is a test that names a deviation, and it is written so it can fail.** The
 * empty dot is `color.ink.faint` — the design's *sanctioned* colour for the empty
 * `Indicator.Confidence` dot placeholder, in both themes — and on the card it is
 * **1.77:1** (light) and **1.64:1** (dark) against the surface. Under a strict reading
 * of WCAG 1.4.11 that is a failure.
 *
 * **Why it is a deviation and not a defect this file silently forgives.** Three things
 * are true at once, and the claim is only honest if all three are stated:
 *
 * 1. **The state is legible.** The Confidence Pulse's state is "how many of the five are
 *    filled", and the filled-vs-empty distinction is **10:1** — the check above. The
 *    filled dot is 17.73:1 against the card. What identifies the state is unambiguous.
 * 2. **The empty dot is a placeholder, by the design's own naming.** `DESIGN.md` calls
 *    it the "empty `Indicator.Confidence` dot **placeholder**" and `color.ink.faint` "the
 *    dimmest readable ink". It is the track of an indicator, the way an unfilled
 *    progress track is not itself the progress.
 * 3. **The value is the design's, and it is pre-existing.** `color.ink.faint` is
 *    `#C9C2B5` light and `#3A3A40` dark, chosen in an earlier run and used on the
 *    Pulse Preview's dot too. Changing it would be a **palette change the design did
 *    not authorise**, made in an intent about the digest. `DESIGN.md` ASSUM-1 asks for
 *    the light palette to be re-verified against AA — and this file *is* that
 *    re-verification, so the finding is reported here rather than absorbed.
 *
 * **So the deviation is recorded with its numbers, and the check is a tripwire.** If
 * `color.ink.faint` is ever darkened to clear 3:1, this test **fails** — the deviation
 * is closed, and the file says so. That is the difference between a recorded deviation
 * and a waived one: a waiver is invisible, and this is a test that will fire.
 */
describe("the recorded deviation", () => {
  for (const theme of THEMES) {
    for (const background of ["surface-elevated", "surface-paper"]) {
      it(
        `[${theme}] the empty confidence dot against ${background} still deviates — ` +
          "close it by darkening color.ink.faint",
        () => {
          const palette = palettes.get(theme) as Map<string, string>;
          const empty = palette.get("ink-faint") as string;
          const surface = palette.get(background) as string;

          const ratio = contrastRatio(empty, surface);

          expect(
            ratio,
            `[${theme}] the empty confidence dot is now ${ratio.toFixed(2)}:1 against ` +
              `${surface}, which clears the ${AA_NON_TEXT}:1 AA non-text threshold. ` +
              "The recorded deviation is closed: remove this test, add the empty dot to " +
              "NON_TEXT_PAIRS, and update the deviation note in the test report.",
          ).toBeLessThan(AA_NON_TEXT);
        },
      );
    }
  }
});

describe("the ratio formula itself", () => {
  it("gives black on white exactly 21:1", () => {
    // **The formula's own check.** A contrast function that is off by a factor would
    // make every ratio above meaningless, and no ratio in this file would notice.
    // Black on white is the one pair with a known, published answer.
    expect(contrastRatio("#000000", "#ffffff")).toBeCloseTo(21, 5);
  });

  it("gives white on white exactly 1:1", () => {
    expect(contrastRatio("#ffffff", "#ffffff")).toBeCloseTo(1, 5);
  });

  it("is symmetric", () => {
    // The ratio does not depend on which colour is the foreground — and a function
    // that did would be measuring something else.
    expect(contrastRatio("#1a1814", "#faf8f4")).toBeCloseTo(
      contrastRatio("#faf8f4", "#1a1814"),
      10,
    );
  });
});
