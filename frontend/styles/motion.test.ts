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

  it("is the only transition or animation in any stylesheet", () => {
    for (const [file, text] of sheets) {
      const transitions = [...text.matchAll(/^\s*transition:\s*([^;]+);/gm)].map((m) => m[1]);
      expect(
        transitions.every((v) => v === "var(--motion-fade-in)" || v === "none"),
        file,
      ).toBe(true);
      expect(text, file).not.toMatch(/^\s*animation(-name)?:/m);
      expect(text, file).not.toContain("@keyframes");
    }
  });
});
