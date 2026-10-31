/**
 * A scratch harness: plant a real contrast bug, run the contrast test, require a
 * failure, restore. Not part of the suite — a tool for proving the suite bites.
 */
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const ROOT = path.resolve(import.meta.dirname, "..");

const FILES = {
  card: path.join(ROOT, "components/digest/pulse-card.tsx"),
  detail: path.join(ROOT, "components/detail/detail-header.tsx"),
  preview: path.join(ROOT, "components/preview/preview-card.tsx"),
  tokens: path.join(ROOT, "styles/tokens.css"),
};

const PROBES = [
  {
    description: "the card's timezone abbreviation goes back to ink-faint",
    file: "card",
    edits: [
      [
        '{time} <span className="text-ink-muted">({zone})</span>',
        '{time} <span className="text-ink-faint">({zone})</span>',
      ],
    ],
  },
  {
    description: "the card's Source Badge label goes back to terracotta",
    file: "card",
    edits: [
      [
        'const labelColour = badge.italic ? "text-ink-primary italic" : "text-ink-secondary";',
        'const labelColour = badge.official\n    ? "text-accent-terracotta"\n    : badge.italic\n      ? "text-ink-primary italic"\n      : "text-ink-secondary";',
      ],
    ],
  },
  {
    description: "the detail screen's Source Badge label goes back to terracotta",
    file: "detail",
    edits: [
      [
        'const labelColour = badge.italic ? "text-ink-primary italic" : "text-ink-secondary";',
        'const labelColour = badge.official\n    ? "text-accent-terracotta"\n    : badge.italic\n      ? "text-ink-primary italic"\n      : "text-ink-secondary";',
      ],
    ],
  },
  {
    description: "the detail screen's badge glyph loses its aria-hidden",
    file: "detail",
    edits: [
      ['<span aria-hidden="true" className={glyphColour}>', "<span className={glyphColour}>"],
    ],
  },
  {
    description: "the card's warn glyph becomes text on the label",
    file: "card",
    edits: [
      [
        "<BadgeGlyph glyph={badge.glyph} official={badge.official} warn={badge.warn} />",
        '<BadgeGlyph glyph={badge.glyph} official={badge.official} warn={badge.warn} />\n        <span className="text-signal-warn">{badge.label}</span>',
      ],
    ],
  },
  {
    description: "the light signal-warn token goes back to the design's #b8893a",
    file: "tokens",
    edits: [["--color-signal-warn: #8a5a1c;", "--color-signal-warn: #b8893a;"]],
  },
  {
    description: "the light warn-amber token goes back to the design's #b8893d",
    file: "tokens",
    edits: [["--color-warn-amber: #8a5a1c;", "--color-warn-amber: #b8893d;"]],
  },
  {
    description: "the light ink-faint darkens enough to close the recorded deviation",
    file: "tokens",
    edits: [["--color-ink-faint: #c9c2b5;", "--color-ink-faint: #8e8778;"]],
  },
  {
    description: "the dark ink-faint brightens enough to close the recorded deviation",
    file: "tokens",
    edits: [["--color-ink-faint: #3a3a40;", "--color-ink-faint: #686870;"]],
  },
  {
    description: "the preview card's timezone abbreviation goes back to ink-faint",
    file: "preview",
    edits: [
      [
        '{local.date} · {local.time} <span className="text-ink-muted">({zone})</span>',
        '{local.date} · {local.time} <span className="text-ink-faint">({zone})</span>',
      ],
    ],
  },
];

const originals = {};
for (const [key, file] of Object.entries(FILES)) {
  originals[key] = readFileSync(file, "utf8");
}

let failures = 0;

for (const probe of PROBES) {
  const file = FILES[probe.file];
  const original = originals[probe.file];
  let applied = true;

  // **Every pattern is checked before any edit is applied.**
  for (const [pattern] of probe.edits) {
    if (!original.includes(pattern)) {
      console.log(`SKIP  ${probe.description} — pattern not found: ${pattern.slice(0, 60)}`);
      applied = false;
      break;
    }
  }
  if (!applied) {
    failures += 1;
    continue;
  }

  let mutated = original;
  for (const [pattern, replacement] of probe.edits) {
    mutated = mutated.replace(pattern, replacement);
  }
  writeFileSync(file, mutated);

  let caught = false;
  let output = "";
  try {
    execFileSync("npx", ["vitest", "run", "tests/contrast.test.ts"], {
      cwd: ROOT,
      encoding: "utf8",
      stdio: ["ignore", "pipe", "pipe"],
    });
  } catch (error) {
    caught = true;
    output = `${error.stdout ?? ""}${error.stderr ?? ""}`;
  } finally {
    writeFileSync(file, original);
  }

  const names = [...output.matchAll(/FAIL[^\n]*> ([^\n]+)/g)].map((m) => m[1].trim());
  console.log(
    `${caught ? "CAUGHT" : "MISSED"}  ${probe.description}` +
      (caught ? `\n          ${names.slice(0, 3).join("\n          ")}` : ""),
  );
  if (!caught) failures += 1;
}

console.log(`\n${PROBES.length - failures}/${PROBES.length} probes caught`);
process.exit(failures === 0 ? 0 : 1);
