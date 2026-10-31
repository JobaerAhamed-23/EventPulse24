// @vitest-environment node
/** motion.fadeIn is the only motion in the product (DESIGN.md §Token Implementation Contract). */
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const STYLES_DIR = __dirname;
const sheets = readdirSync(STYLES_DIR)
  .filter((file) => file.endsWith(".css"))
  .map((file) => [file, readFileSync(path.join(STYLES_DIR, file), "utf8")] as const);
function css(file: string): string {
  const sheet = sheets.find(([name]) => name === file);
  if (!sheet) throw new Error(`styles/${file} not found`);
  return sheet[1];
}

describe("motion.fadeIn", () => {
  it("is a 240ms opacity transition with ease-out", () => {
    expect(css("tokens.css")).toMatch(/--motion-fade-in:\s*opacity 240ms ease-out;/);
    expect(css("globals.css")).toMatch(/\.fade-in \{\s*transition: var\(--motion-fade-in\);/);
  });

  it("collapses to transition: none under prefers-reduced-motion", () => {
    expect(css("globals.css")).toMatch(
      /@media \(prefers-reduced-motion: reduce\) \{\s*\.fade-in \{\s*transition: none;\s*\}/,
    );
  });

  it("is the only transition in any stylesheet", () => {
    for (const [file, text] of sheets) {
      const transitions = [...text.matchAll(/^\s*transition:\s*([^;]+);/gm)].map((m) => m[1]);
      expect(
        transitions.every((v) => v === "var(--motion-fade-in)" || v === "none"),
        file,
      ).toBe(true);
    }
  });
});

/**
 * The loading skeleton's pulse — the only *animation* in the product.
 *
 * **`EXPERIENCE.md` §5 requires it**: "3 paper rectangles … fading 1px toward
 * `color.ink.faint` at 60% opacity, then back. Pulse period: 1800ms." A repeating
 * 1800ms cycle cannot be expressed as a transition, so the product's single-transition
 * rule gained one companion.
 *
 * **The test's intent survives.** It used to forbid *any* animation, which would have
 * forbidden the one the spine asks for. It now allows **exactly this one** and fails on
 * any other — a second animation is still a build failure.
 */
describe("motion.skeletonPulse", () => {
  it("is an 1800ms opacity cycle between 1 and 0.6", () => {
    expect(css("globals.css")).toMatch(
      /@keyframes skeleton-pulse \{[\s\S]*?opacity: 1;[\s\S]*?opacity: 0\.6;[\s\S]*?\}/,
    );
    expect(css("globals.css")).toMatch(
      /\.skeleton-pulse \{\s*animation: skeleton-pulse 1800ms ease-in-out infinite;/,
    );
  });

  it("collapses to no animation under prefers-reduced-motion", () => {
    expect(css("globals.css")).toMatch(
      /@media \(prefers-reduced-motion: reduce\) \{[\s\S]*?\.skeleton-pulse \{\s*animation: none;\s*\}/,
    );
  });

  it("is the only animation in any stylesheet", () => {
    for (const [file, text] of sheets) {
      const animations = [...text.matchAll(/^\s*animation:\s*([^;]+);/gm)].map((m) => m[1]);
      for (const animation of animations) {
        expect(
          animation === "skeleton-pulse 1800ms ease-in-out infinite" || animation === "none",
          `${file}: ${animation}`,
        ).toBe(true);
      }

      // The keyframes are named, and there is exactly one of them.
      const keyframes = [...text.matchAll(/@keyframes\s+([\w-]+)/g)].map((m) => m[1]);
      for (const name of keyframes) {
        expect(name, file).toBe("skeleton-pulse");
      }
    }
  });

  it("is declared in exactly one stylesheet", () => {
    const declaring = sheets.filter(([, text]) => text.includes("@keyframes skeleton-pulse"));
    expect(declaring.map(([name]) => name)).toEqual(["globals.css"]);
  });
});
