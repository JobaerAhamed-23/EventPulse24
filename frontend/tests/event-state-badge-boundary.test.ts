// @vitest-environment node
/**
 * The state badge's structural rules, asserted against the source rather than the DOM.
 *
 * **These are the rules a rendering test cannot catch.** A test that renders the badge
 * can see that it says "Sold out"; it cannot see that the badge contains no literal hex
 * value, or that its colour is on the glyph and nowhere else, or that the three states
 * have three different glyphs rather than three different colours. Those are properties
 * of the source, so they are asserted on the source.
 *
 * **They are the same rules `tests/pulse-card-boundary.test.ts` applies to the card**,
 * because the badge lives on the card and the card's rules are the product's rules.
 */
import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "..");
const BADGE = path.join(ROOT, "components/state/event-state-badge.tsx");

const badgeSource = readFileSync(BADGE, "utf8");

/**
 * The source with its comments removed.
 *
 * **A comment is not code.** The badge's docstring quotes the spec — including the
 * sentences and the glyph names — and a source-text assertion that read them would be
 * asserting on prose.
 */
function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
}

const badgeCode = withoutComments(badgeSource);

/**
 * The class-name strings in a .tsx file.
 *
 * **The `className={[...].join(" ")}` form is matched too.** The card's own boundary
 * test reads `className="..."` and `className={`...`}`, but this badge builds its class
 * list the way the card does — as an array joined at runtime — so a regex that missed
 * that form would find *no* classes in the file and every assertion below would pass
 * vacuously. A guard that cannot fail is not a guard.
 */
function classStrings(source: string): string[] {
  return [
    ...source.matchAll(/className=(?:"([^"]*)"|\{`([^`]*)`\}|\{"([^"]*)"\})/g),
    ...source.matchAll(/className=\{\[([\s\S]*?)\]\.join\(" "\)\}/g),
  ].map((match) => match[1] ?? match[2] ?? match[3] ?? match[0]);
}

describe("the badge's tokens", () => {
  it("uses no literal hex colour", () => {
    // A literal hex would be right in one theme and wrong in the other.
    expect(badgeCode.match(/#[0-9a-fA-F]{3,8}\b/g) ?? []).toEqual([]);
  });

  it("uses no raw rgb() or hsl() colour", () => {
    expect(badgeCode.match(/\b(?:rgb|rgba|hsl|hsla)\(/g) ?? []).toEqual([]);
  });

  it("takes every colour from a token utility", () => {
    const colours = classStrings(badgeCode)
      .flatMap((value) => value.split(/\s+/))
      .filter((token) => /^(?:bg|text|border|ring|outline|fill|stroke)-/.test(token));

    expect(colours.length).toBeGreaterThan(0);
    for (const token of colours) {
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
    const families = classStrings(badgeCode)
      .flatMap((value) => value.split(/\s+/))
      .filter((token) => token.includes("[font:"));

    expect(families.length).toBeGreaterThan(0);
    for (const token of families) {
      expect(token, token).toMatch(/\[font:var\(--type-scale-/);
    }
  });
});

describe("the badge's motion", () => {
  it("declares no transition, duration, delay or animation class", () => {
    const motion = classStrings(badgeCode)
      .flatMap((value) => value.split(/\s+/))
      .filter((token) =>
        /^(?:[\w-]+:)*(?:animate-[\w-]+|transition(?:-[\w-]+)?|duration-[\w-]+|delay-[\w-]+|ease-[\w-]+)$/.test(
          token,
        ),
      );
    expect(motion).toEqual([]);
  });
});

describe("the badge's colour", () => {
  it("puts the signal colour on the glyph and nowhere else", () => {
    // **`DESIGN.md`: "The glyph is aria-hidden; the label carries the meaning. The
    // chromatic colour is the glyph's, and every label is in ink."** So the label's
    // colour is ink, and the only `text-signal-warn` in the file is the glyph's.
    const signalUses = classStrings(badgeCode)
      .flatMap((value) => value.split(/\s+/))
      .filter((token) => token.includes("signal-warn"));

    expect(signalUses.length).toBeGreaterThan(0);
    for (const token of signalUses) {
      expect(token, token).toBe("text-signal-warn");
    }
  });

  it("puts the label in ink, not in the signal colour", () => {
    const label = /className=\{\[([\s\S]*?)\]\.join\(" "\)\}/.exec(badgeCode);
    expect(label?.[1]).toContain("text-ink-secondary");
    expect(label?.[1]).not.toContain("signal-warn");
  });

  it("uses the sold-out badge's anatomy", () => {
    // `DESIGN.md` `component.badge.soldout`: "{color.surface.subtle} fill, 1px
    // {color.border.strong} stroke, {radius.subtle} (6px) … label in
    // {type.scale.meta.sm} {color.ink.secondary}".
    const classes = classStrings(badgeCode).join(" ");
    expect(classes).toContain("bg-surface-subtle");
    expect(classes).toContain("border-border-strong");
    expect(classes).toContain("rounded-subtle");
    expect(classes).toContain("--type-scale-meta-sm");
  });

  it("uses the design's weight and tracking", () => {
    // `DESIGN.md` `component.badge.soldout`: "the state's label in `{type.scale.meta.sm}`
    // `{color.ink.secondary}` **weight 600**, uppercase, **letter-spacing 0.06em**".
    //
    // **`--type-scale-meta-sm` is `500 12px/1.45`**, so the shorthand alone gives
    // weight 500 — the design's 600 has to be asked for explicitly. And the tracking
    // is an arbitrary value, so it is written out rather than inherited.
    //
    // **The mockup's `0.08em` is not the design's**, and the design wins: A-22 settled
    // the typography on `DESIGN.md`'s values.
    const classes = classStrings(badgeCode).join(" ");
    expect(classes).toContain("font-semibold");
    expect(classes).toContain("tracking-[0.06em]");
    expect(classes).toContain("uppercase");
  });

  it("is never red", () => {
    // The conflict indicator is "never red", and so is this — a state change is a fact,
    // not an error.
    //
    // **The check is token-scoped, not a bare substring.** A bare `not.toContain("red")`
    // would trip on any word that happens to contain those three letters — and it says
    // nothing about *which* token would be red. What matters is that no colour utility
    // in the badge names an error or a red.
    expect(badgeCode).not.toContain("signal-error");
    expect(badgeCode).not.toMatch(
      /\b(?:bg|text|border|ring|outline|fill|stroke)-(?:signal-)?(?:error|red|destructive)\b/,
    );
  });
});

describe("the badge's markup", () => {
  it("is a span, not a control", () => {
    // There is nothing to dismiss and nothing to do about a cancelled event, so the
    // badge is never a button and never a focus stop.
    expect(badgeCode).not.toContain("<button");
    expect(badgeCode).not.toContain("role=");
    expect(badgeCode).not.toContain("tabIndex");
  });

  it("renders the shared label, not a literal one", () => {
    // **The badge's label comes from the table, not from a string written into the
    // component.** A literal "Cancelled" here would look entirely reasonable and would
    // quietly fork the vocabulary — which is what `tests/event-state.test.ts` exists to
    // catch on the other side.
    expect(badgeCode).toContain("STATE_LABELS[state]");
  });

  it("is hidden from assistive technology", () => {
    // **The card's link carries the state's name, so the badge must not carry it
    // too.** Two namings of one fact in one card means a browse-mode screen-reader
    // user hears "Cancelled" twice. The badge is `aria-hidden` and the visible label
    // stays — it is what satisfies WCAG 1.4.1.
    expect(badgeCode).toContain('aria-hidden="true"');
  });

  it("hides the glyph from assistive technology", () => {
    expect(badgeCode).toContain('aria-hidden="true"');
  });

  it("gives each state a different glyph", () => {
    // The three states must be told apart by *shape*, because the conflict
    // indicator's amber and the badge's amber are the same hex — so colour cannot do
    // this job, and a badge whose states differ only by colour would be unreadable
    // beside the conflict mark.
    const glyphs = /const GLYPHS[^=]*=\s*\{([\s\S]*?)\n\};/.exec(badgeCode);
    expect(glyphs?.[1]).toBeTruthy();

    const values = [...(glyphs?.[1] ?? "").matchAll(/"([^"]+)"/g)].map((match) => match[1]);
    expect(values).toHaveLength(3);
    expect(new Set(values).size).toBe(3);
  });

  it("gives no state the conflict indicator's shape", () => {
    // The conflict indicator is a 6px *filled* circle — `●`. A glyph that was the same
    // shape would be indistinguishable from it at a glance, and `DESIGN.md` requires
    // the conflict indicator to be "distinct in shape and position from the Source
    // Badge and Confidence Pulse". So no state may use a filled circle.
    const glyphs = /const GLYPHS[^=]*=\s*\{([\s\S]*?)\n\};/.exec(badgeCode);
    const values = [...(glyphs?.[1] ?? "").matchAll(/"([^"]+)"/g)].map((match) => match[1]);
    expect(values.length).toBe(3);
    for (const value of values) {
      expect(value, value).not.toBe("●");
    }
  });

  it("gives the sold-out state a hollow circle, not a solid one", () => {
    // The design's own rule — "a leading `●` glyph" — would put a filled circle in the
    // badge, which is the conflict indicator's shape. The badge's glyph is hollow
    // instead: same hue, different figure, so the two can be told apart side by side.
    const glyphs = /const GLYPHS[^=]*=\s*\{([\s\S]*?)\n\};/.exec(badgeCode);
    expect(glyphs?.[1]).toMatch(/sold_out:\s*"⊘"/);
  });

  it("names its state in the markup, so the card can be tested by state", () => {
    expect(badgeCode).toContain("data-event-state={state}");
  });
});
