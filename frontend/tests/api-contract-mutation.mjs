/**
 * AD-19's contract probe: **the generated client cannot be hand-edited.**
 *
 * **What this is for.** `tests/api-contract.test.ts` asserts that the committed
 * `frontend/lib/api/schema.ts` is byte-identical to what `openapi-typescript` produces
 * from the committed `openapi.json`. A test that passes proves nothing unless it can
 * fail, so this probe plants a real hand-edit, runs the contract test, and requires a
 * failure.
 *
 * **The two probes.**
 *
 * 1. **A path invented by hand.** A person adds a typed path to `schema.ts` for an
 *    endpoint the backend does not serve — "the backend should have this". The
 *    endpoint-coverage test would stay green, because the operation id would still
 *    *appear* in the file and the sweep only reads the committed schema's ids. The
 *    byte-identity check catches it, and so does the direction check that asks
 *    whether the committed client offers a path the committed schema does not declare.
 * 2. **A path removed by hand.** A person deletes a path from `schema.ts` — perhaps to
 *    "clean it up". Every `toContain` in the endpoint-coverage test still passes,
 *    because the remaining ids are still present. The byte-identity check catches it,
 *    and so does the count check.
 *
 * **The third probe is the one that matters most: a comment.** A person adds an
 * explanatory comment to the generated file. Nothing about the *meaning* changed, so a
 * semantic comparison would stay green — and the file is no longer the generator's
 * output. The byte-identity check is what catches it, and that is the whole reason
 * this contract is stated in bytes rather than in intent.
 *
 * **Every probe restores the file it touched.** The restore is in a `finally`, so a
 * failure cannot leave the tree broken.
 */
import { execFileSync } from "node:child_process";
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const ROOT = path.resolve(import.meta.dirname, "..");

const FILES = {
  schema: path.join(ROOT, "lib/api/schema.ts"),
};

const PROBES = [
  {
    description: "a path is invented in the generated client",
    file: "schema",
    edits: [
      [
        "export interface paths {\n",
        'export interface paths {\n    "/api/personal/browse/invented": {\n        parameters: {\n            query?: never;\n            header?: never;\n            path?: never;\n            cookie?: never;\n        };\n        get: operations["apps_personalization_api_get_browse_invented"];\n        put?: never;\n        post?: never;\n        delete?: never;\n        options?: never;\n        head?: never;\n        patch?: never;\n        trace?: never;\n    };\n',
      ],
    ],
  },
  {
    description: "a path is removed from the generated client",
    file: "schema",
    edits: [['    "/api/auth/csrf": {\n', '    "/api/auth/csrf-removed-by-hand": {\n']],
  },
  {
    description: "a comment is added to the generated client",
    file: "schema",
    edits: [
      [
        "export interface paths {",
        "// A note somebody added by hand, because the file looked like it wanted explaining.\nexport interface paths {",
      ],
    ],
  },
];

let failures = 0;

for (const probe of PROBES) {
  const file = FILES[probe.file];
  const original = readFileSync(file, "utf8");
  let mutated = original;

  for (const [from, to] of probe.edits) {
    if (!mutated.includes(from)) {
      console.error(`✗ ${probe.description}: the probe's anchor text is not in the file.`);
      console.error(`  anchor: ${JSON.stringify(from.slice(0, 80))}`);
      failures += 1;
      break;
    }
    mutated = mutated.replace(from, to);
  }

  if (mutated === original) continue;

  writeFileSync(file, mutated);

  try {
    execFileSync("pnpm", ["exec", "vitest", "run", "tests/api-contract.test.ts"], {
      cwd: ROOT,
      encoding: "utf8",
      stdio: "pipe",
    });
    console.error(`✗ ${probe.description}: the contract test still passed. It does not bite.`);
    failures += 1;
  } catch {
    console.log(`✓ ${probe.description}: the contract test failed, as it must.`);
  } finally {
    writeFileSync(file, original);
  }
}

if (failures > 0) {
  console.error(`\n${failures} probe(s) did not bite.`);
  process.exit(1);
}

console.log("\nEvery probe bit. The contract test is load-bearing.");
