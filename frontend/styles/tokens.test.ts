// @vitest-environment node
/**
 * tokens.css matches DESIGN.md, read from the design doc itself, so a design change fails here
 * until the CSS follows. The parser must find exactly the expected tokens: a reworded or
 * reformatted DESIGN.md fails loudly instead of passing on an empty set.
 */
import { existsSync, readFileSync, readdirSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

// The one place the dated design-doc path lives.
const DESIGN_MD = path.resolve(
  __dirname,
  "../../_bmad-output/planning-artifacts/ux-designs/ux-EventPulse24-2026-08-23/DESIGN.md",
);
const STYLES_DIR = __dirname;
const TOKENS_CSS = path.join(STYLES_DIR, "tokens.css");

// Path aliases DESIGN.md lists with their own value; they read the primary variable.
const ALIASES: Record<string, string> = {
  "color.cool.public": "color.accent.slate",
  "color.ink.meta": "color.ink.muted",
};

const COLOR_NAMES = [
  "color.surface.paper",
  "color.surface.elevated",
  "color.surface.subtle",
  "color.surface.inset",
  "color.ink.primary",
  "color.ink.secondary",
  "color.ink.muted",
  "color.ink.faint",
  "color.ink.inverse",
  "color.surface.paper.darker",
  "color.warm.personal",
  "color.cool.public",
  "color.warn.amber",
  "color.accent.terracotta",
  "color.accent.slate",
  "color.accent.amber",
  "color.signal.success",
  "color.signal.warn",
  "color.signal.error",
  "color.border.subtle",
  "color.border.strong",
];

function readDesign(): string[] {
  if (!existsSync(DESIGN_MD)) {
    throw new Error(`DESIGN.md not found at DESIGN_MD (${DESIGN_MD}); update the constant.`);
  }
  return readFileSync(DESIGN_MD, "utf8").split("\n");
}

function sectionBullets(lines: string[], heading: string, pattern: RegExp): [string, string][] {
  const start = lines.indexOf(heading);
  if (start === -1) throw new Error(`DESIGN.md has no "${heading}" heading`);
  const found: [string, string][] = [];
  for (const line of lines.slice(start + 1)) {
    if (/^#{2,3} /.test(line)) break;
    const match = pattern.exec(line);
    if (match) found.push([match[1], match[2]]);
  }
  return found;
}

const COLOR_BULLET = /^- `(color\.[a-z.]+)` — `([^`]+)`/;
const lines = readDesign();
const darkBullets = sectionBullets(lines, "### Dark mode (default)", COLOR_BULLET);
const lightBullets = sectionBullets(lines, "### Light mode (alternative)", COLOR_BULLET);

/** A value that must exist; fails with the key instead of an undefined comparison. */
function must<K, V>(map: Map<K, V>, key: K): V {
  const value = map.get(key);
  if (value === undefined) throw new Error(`missing ${String(key)}`);
  return value;
}

const cssVar = (tokenPath: string) => `--${tokenPath.replaceAll(".", "-")}`;
const norm = (value: string) => value.replace(/\s+/g, "").toLowerCase();

function cssBlock(css: string, selector: string): Map<string, string> {
  const start = css.indexOf(`${selector} {`);
  if (start === -1) throw new Error(`tokens.css has no "${selector}" block`);
  const body = css.slice(start + selector.length + 2, css.indexOf("\n}", start));
  const vars = new Map<string, string>();
  for (const [, name, value] of body.matchAll(/(--[\w-]+(?:-\*)?):\s*([^;]+);/g)) {
    vars.set(name, value.trim());
  }
  return vars;
}

const tokensCss = readFileSync(TOKENS_CSS, "utf8");
const light = cssBlock(tokensCss, "@theme static");
const dark = cssBlock(tokensCss, '[data-theme="dark"]');

/** Variables declared under a Tailwind namespace prefix, excluding its `-*: initial` reset. */
const declared = (block: Map<string, string>, prefix: string) =>
  [...block.keys()].filter((name) => name.startsWith(prefix) && !name.endsWith("*")).sort();

describe("DESIGN.md parse", () => {
  it("finds exactly the 21 color bullets in each mode, by name", () => {
    expect(darkBullets.map(([name]) => name)).toEqual(COLOR_NAMES);
    expect(lightBullets.map(([name]) => name)).toEqual(COLOR_NAMES);
  });

  it("gives each alias the same value as its primary token in both modes", () => {
    for (const bullets of [darkBullets, lightBullets]) {
      const values = new Map(bullets);
      expect(norm(must(values, "color.cool.public"))).toBe(
        norm(must(values, "color.accent.slate")),
      );
    }
  });
});

describe("tokens.css colors", () => {
  const primaries = (bullets: [string, string][]) => bullets.filter(([name]) => !(name in ALIASES));

  it("declares 20 variables per mode, after mapping the alias", () => {
    expect(primaries(lightBullets)).toHaveLength(20);
    expect(
      [...light.keys()].filter((name) => name.startsWith("--color-") && !name.endsWith("*")),
    ).toHaveLength(20);
    expect([...dark.keys()].filter((name) => name.startsWith("--color-"))).toHaveLength(20);
  });

  it.each(["light", "dark"] as const)("matches DESIGN.md in %s mode", (mode) => {
    const [bullets, block] = mode === "light" ? [lightBullets, light] : [darkBullets, dark];
    for (const [name, value] of primaries(bullets)) {
      expect(block.get(cssVar(name)), name).toBeDefined();
      expect(norm(must(block, cssVar(name))), name).toBe(norm(value));
    }
  });

  it("never declares an alias as its own variable", () => {
    for (const alias of Object.keys(ALIASES)) {
      expect(tokensCss).not.toContain(`${cssVar(alias)}:`);
    }
  });
});

describe("tokens.css elevation (DESIGN.md §Elevation & Depth, §Color usage rules)", () => {
  it("uses the light shadow on :root and the dark one under data-theme=dark", () => {
    expect(norm(must(light, "--shadow-floating"))).toBe(norm("0 8px 24px rgba(0,0,0,0.08)"));
    expect(norm(must(dark, "--shadow-floating"))).toBe(norm("0 8px 24px rgba(0,0,0,0.4)"));
  });

  it("has no glow in light mode and both glows in dark mode", () => {
    expect(light.get("--glow-today")).toBe("none");
    expect(light.get("--glow-brandmark")).toBe("none");
    expect(norm(must(dark, "--glow-today"))).toBe(norm("0 0 12px rgba(255,106,71,0.55)"));
    expect(norm(must(dark, "--glow-brandmark"))).toBe(norm("0 0 14px rgba(255,106,71,0.55)"));
  });

  it("resets Tailwind's shadows so the floating shadow is the only one", () => {
    expect(light.get("--shadow-*")).toBe("initial");
    expect([...light.keys()].filter((n) => n.startsWith("--shadow-") && !n.endsWith("*"))).toEqual([
      "--shadow-floating",
    ]);
  });
});

describe("tokens.css shapes, spacing and type", () => {
  it("matches every radius in DESIGN.md §Shapes", () => {
    const radii = sectionBullets(lines, "## Shapes", /^- `(radius\.[a-z-]+)` — (\d+(?:px)?)/);
    expect(radii).toHaveLength(7);
    for (const [name, value] of radii) expect(light.get(cssVar(name)), name).toBe(value);
    // Exactly these: an extra radius would become a Tailwind class (rounded-…).
    expect(declared(light, "--radius-")).toEqual(radii.map(([name]) => cssVar(name)).sort());
  });

  it("matches every step in DESIGN.md §Spacing scale and has no Tailwind multiplier", () => {
    const steps = sectionBullets(lines, "### Spacing scale", /^- `(spacing\.\d+)` — (\d+(?:px)?)/);
    expect(steps).toHaveLength(11);
    for (const [name, value] of steps) expect(light.get(cssVar(name)), name).toBe(value);
    expect(declared(light, "--spacing-")).toEqual(steps.map(([name]) => cssVar(name)).sort());
    expect(light.get("--spacing")).toBe("initial");
  });

  it("starts each family with its next/font variable, then DESIGN.md's fallbacks", () => {
    const families = sectionBullets(
      lines,
      "### Type families",
      /^- `(type\.family\.\w+)` — `([^`]+)`/,
    );
    expect(families).toHaveLength(3);
    for (const [name, value] of families) {
      const [, ...fallbacks] = value.split(",").map((part) => part.trim());
      const declared = must(light, cssVar(name))
        .split(",")
        .map((part) => part.trim());
      expect(declared[0], name).toMatch(/^var\(--font-[\w-]+\)$/);
      expect(declared.slice(1), name).toEqual(fallbacks);
    }
  });

  it("keeps only DESIGN.md's tablet and desktop breakpoints", () => {
    expect(light.get("--breakpoint-*")).toBe("initial");
    expect(light.get("--breakpoint-md")).toBe("768px");
    expect(light.get("--breakpoint-lg")).toBe("1024px");
    expect(declared(light, "--breakpoint-")).toEqual(["--breakpoint-lg", "--breakpoint-md"]);
  });
});

describe("theme switching", () => {
  it("has no prefers-color-scheme in any stylesheet: the theme is chosen, never automatic", () => {
    const sheets = readdirSync(STYLES_DIR).filter((file) => file.endsWith(".css"));
    expect(sheets.length).toBeGreaterThan(0);
    for (const sheet of sheets) {
      expect(readFileSync(path.join(STYLES_DIR, sheet), "utf8"), sheet).not.toContain(
        "prefers-color-scheme",
      );
    }
  });
});
