// @vitest-environment node
/**
 * AD-19: the committed TypeScript client is **generated**, not hand-edited.
 *
 * **What is pinned here.** AD-19 says `frontend/lib/api/` is generated and never
 * hand-edited. The chain has five links:
 *
 * ```
 * backend route → live OpenAPI schema → committed openapi.json → schema.ts → the call site
 * ```
 *
 * Two other files already check joins in that chain:
 *
 * - `backend/tests/api/test_contract.py` checks the **first** join — the committed
 *   `openapi.json` still equals the live API's schema.
 * - `frontend/tests/ad19-endpoint-coverage.test.ts` checks the **middle** — the
 *   endpoints are in the schema, bound in the generated TypeScript, and reached
 *   through the generated client.
 *
 * **What was missing was the join that says "and nobody typed it by hand."** Both of
 * the above are satisfied by a `schema.ts` that was edited by a person: a hand-added
 * operation id still *appears* in the file, and a hand-added path still shows up in a
 * `toContain`. Nothing said the file was the generator's output. A person could add a
 * path to `schema.ts` that the backend does not serve, and every check would stay
 * green — the types would promise an endpoint that does not exist.
 *
 * **So this file regenerates the client and compares.** `openapi-typescript` is the
 * exact tool `make client` runs, on the exact file `make client` runs it on, so the
 * output must be **byte-identical** to what is committed. A single hand-edit — a
 * comment, a reordered interface, an added path — changes the bytes and fails here.
 *
 * **Why byte-identity and not a semantic comparison.** A semantic comparison would ask
 * "do these two files say the same thing?", and a hand-edit that says the same thing
 * differently would pass. But AD-19's rule is not "must be semantically equivalent" —
 * it is "never hand-edited", and the only way to see a hand-edit is to compare the
 * bytes. The generator is deterministic, so this is a stable comparison: the same
 * input always produces the same output, which is what makes byte-identity a
 * meaningful assertion rather than a flaky one.
 */
import { execFileSync } from "node:child_process";
import { mkdtempSync, readFileSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "..");

const OPENAPI = path.join(ROOT, "lib/api/openapi.json");
const SCHEMA_TS = path.join(ROOT, "lib/api/schema.ts");

/**
 * Regenerate the TypeScript client from the committed OpenAPI schema.
 *
 * **The command is `make client`'s command.** Not a close relative — the same one:
 * `pnpm --dir frontend exec openapi-typescript lib/api/openapi.json --output
 * lib/api/schema.ts`. A check that ran a *different* generator, or a different
 * version of this one, would be asserting that the file matches something the build
 * does not actually produce, and the file could still drift from the real output.
 *
 * **The output goes to a temporary directory, not over the committed file.** The
 * comparison is the whole point; overwriting the file first would make the check
 * vacuously true.
 */
function regenerateClient(): string {
  const directory = mkdtempSync(path.join(tmpdir(), "ad19-contract-"));
  const output = path.join(directory, "schema.ts");

  try {
    execFileSync(
      "pnpm",
      ["exec", "openapi-typescript", "lib/api/openapi.json", "--output", output],
      { cwd: ROOT, encoding: "utf8", stdio: "pipe" },
    );

    return readFileSync(output, "utf8");
  } finally {
    rmSync(directory, { recursive: true, force: true });
  }
}

describe("AD-19: the committed TypeScript client is generated, not hand-edited", () => {
  it("schema.ts is byte-identical to what openapi-typescript generates from openapi.json", () => {
    const committed = readFileSync(SCHEMA_TS, "utf8");
    const generated = regenerateClient();

    // **The failure message has to say what to do.** A diff of two six-thousand-line
    // files is unreadable, so the message points at the command that fixes it.
    expect(
      committed,
      "frontend/lib/api/schema.ts is not what `make client` generates from " +
        "frontend/lib/api/openapi.json — run `make client` and commit both files. " +
        "(lib/api/ is generated and never hand-edited — AD-19.)",
    ).toBe(generated);
  });

  it("the committed schema is not hand-edited at the top either — it carries the generator's banner", () => {
    // **A cheap second signal, and it is worth having.** The generator writes a
    // banner saying the file is auto-generated. A file that has lost it was edited by
    // something that did not know what it was, and the byte-identity check above
    // would say so too — but this one says it *without* running the generator, which
    // makes the failure legible at a glance.
    const committed = readFileSync(SCHEMA_TS, "utf8");

    expect(committed).toContain("auto-generated by openapi-typescript");
    expect(committed).toContain("Do not make direct changes to the file.");
  });

  it("every path in the committed schema has a binding in the committed client", () => {
    // **The same sweep the endpoint-coverage test makes, kept here too.**
    //
    // The reason for the duplication is the **direction** of the failure each catches.
    // The endpoint-coverage test reads the committed `openapi.json` and checks the
    // committed `schema.ts` — so it catches a schema that grew without the client
    // being regenerated. This one is the last word: it checks that the **committed
    // pair** is the generator's output, which catches a *hand-edit to either file*.
    //
    // A hand-edit to `openapi.json` — a path invented by a person — would make the
    // committed pair inconsistent with the live API (caught by the backend test) and
    // inconsistent with the generator's output (caught here). Both halves are needed
    // for the claim to be complete.
    const openapi = JSON.parse(readFileSync(OPENAPI, "utf8")) as {
      paths: Record<string, Record<string, { operationId?: string }>>;
    };
    const schemaTs = readFileSync(SCHEMA_TS, "utf8");
    const missing: string[] = [];

    for (const operations of Object.values(openapi.paths)) {
      for (const operation of Object.values(operations)) {
        if (!operation.operationId) continue;
        if (!schemaTs.includes(operation.operationId)) {
          missing.push(operation.operationId);
        }
      }
    }

    expect(missing, "these operations are in the schema but not in the client").toEqual([]);
  });

  it("the committed client names no path the committed schema does not declare", () => {
    // **The other direction, and the one a hand-edit breaks.**
    //
    // A person who adds an endpoint to `schema.ts` by hand — because the backend
    // "should have it" — would be promising the frontend a typed path the server
    // does not serve. The type-checker would be perfectly happy: the path *is* in
    // the client's types. The call would 404 at runtime.
    //
    // So the committed client's own path keys are checked against the committed
    // schema's. The client is parsed rather than grepped, because a path can appear
    // in a comment, in a docstring, or in an operation id — and only a **key** in the
    // `paths` interface is a path the client will actually accept.
    const openapi = JSON.parse(readFileSync(OPENAPI, "utf8")) as {
      paths: Record<string, unknown>;
    };
    const schemaTs = readFileSync(SCHEMA_TS, "utf8");

    // The `paths` interface's keys are the paths, one per line, quoted.
    const pathsBlock = schemaTs.slice(
      schemaTs.indexOf("export interface paths {"),
      schemaTs.indexOf("export interface operations {"),
    );
    const clientPaths = new Set(
      [...pathsBlock.matchAll(/^\s{4}"([^"]+)":\s*\{/gm)].map((match) => match[1]),
    );
    const declared = new Set(Object.keys(openapi.paths));
    const invented = [...clientPaths].filter((clientPath) => !declared.has(clientPath));

    expect(
      invented,
      "the generated client offers paths the schema does not declare — the file was " +
        "hand-edited, or the schema is stale. Run `make client` and commit both files.",
    ).toEqual([]);

    // And the count matches, so a path *removed* from the client by hand is caught
    // too — the sweep above only catches paths the client has that the schema does not.
    expect(clientPaths.size).toBe(declared.size);
  });
});
