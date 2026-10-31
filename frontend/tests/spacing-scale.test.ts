// @vitest-environment node
/**
 * Every spacing utility is on the DESIGN.md spacing scale.
 *
 * **An off-scale step fails silently.** `styles/tokens.css` resets Tailwind's spacing
 * multiplier and declares only the DESIGN.md steps, so `px-5` or `py-2.5` generates no CSS
 * at all — no warning, no error, just a button with no padding. Seventy-nine of them had
 * shipped before this test existed. So the scale is checked here, against the steps
 * `tokens.css` actually declares.
 *
 * **An exact size is written as one.** Where DESIGN.md asks for a size the scale does not
 * have — the 6px indicator dot, the 44px tap target — the class says so in brackets
 * (`size-[6px]`, `min-h-[44px]`), and this test leaves it alone.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "..");

/** The steps `tokens.css` declares: `--spacing-4: 16px;` → "4". */
const STEPS = new Set(
  [...readFileSync(path.join(ROOT, "styles/tokens.css"), "utf8").matchAll(/--spacing-(\d+):/g)].map(
    (match) => match[1],
  ),
);

/** The utilities whose numeric value is a spacing step. */
const PROPERTIES = (
  "p px py pt pb pl pr ps pe m mx my mt mb ml mr ms me gap gap-x gap-y space-x space-y " +
  "w h size min-w min-h max-w max-h inset inset-x inset-y top bottom left right start end " +
  "translate-x translate-y scroll-mt scroll-pt indent basis"
)
  .split(" ")
  .join("|");

/** `md:-mt-2.5` → property `mt`, value `2.5`. Brackets, fractions and named sizes don't match. */
const UTILITY = new RegExp(
  `(?<![\\w-])(?:[a-z0-9]+:)*-?(?:${PROPERTIES})-(\\d+(?:\\.\\d+)?)(?![\\w.\\-/\\[])`,
  "g",
);

function sources(directory: string, found: string[] = []): string[] {
  for (const entry of readdirSync(directory)) {
    const full = path.join(directory, entry);
    if (statSync(full).isDirectory()) {
      sources(full, found);
      continue;
    }
    if (!full.endsWith(".tsx") || full.endsWith(".test.tsx")) continue;
    found.push(full);
  }
  return found;
}

/** Every off-scale utility in one file's source, as `file:line utility`. */
function offScale(file: string): string[] {
  const relative = path.relative(ROOT, file);
  return readFileSync(file, "utf8")
    .split("\n")
    .flatMap((line, index) =>
      [...line.matchAll(UTILITY)]
        .filter((match) => !STEPS.has(match[1]))
        .map((match) => `${relative}:${index + 1} ${match[0]}`),
    );
}

describe("the spacing scale", () => {
  it("reads the DESIGN.md steps from tokens.css", () => {
    expect([...STEPS].sort((a, b) => Number(a) - Number(b))).toEqual(
      "0 1 2 3 4 6 8 12 16 20 30".split(" "),
    );
  });

  it("finds an off-scale step, so a pass means something", () => {
    expect([..."px-5 py-2.5 md:gap-5 -mt-7".matchAll(UTILITY)].map((m) => m[1])).toEqual([
      "5",
      "2.5",
      "5",
      "7",
    ]);
    expect(
      [..."px-6 size-[6px] w-full w-3/4 min-h-[44px]".matchAll(UTILITY)].map((m) => m[1]),
    ).toEqual(["6"]);
  });

  it("is the only scale the app and components use", () => {
    const files = [...sources(path.join(ROOT, "app")), ...sources(path.join(ROOT, "components"))];
    expect(files.flatMap(offScale)).toEqual([]);
  });
});
