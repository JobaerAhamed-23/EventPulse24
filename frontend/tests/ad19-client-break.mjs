/**
 * AD-19's client-break probe: **the generated client is load-bearing.**
 *
 * **What AD-19 says.** *"The frontend talks to the backend only through the generated
 * `api` client; `lib/api/` is generated and never hand-edited."* That is a claim about
 * two things: the client is *used*, and the client is *generated*.
 *
 * **The chain has five links.**
 *
 * ```
 * backend route → live OpenAPI schema → committed openapi.json → schema.ts → the
 * frontend's call site
 * ```
 *
 * `backend/tests/api/test_contract.py` checks the **first** join (the committed schema
 * still equals the live one). `frontend/tests/ad19-endpoint-coverage.test.ts` checks the
 * **middle** (the new endpoints are in the schema and bound in the generated
 * TypeScript). This probe checks the **last** join, and it checks it by **breaking** it:
 * each mutation removes or corrupts one link, and the suite must fail.
 *
 * **Why breaking it is the only honest check.** A test that asserts the client *is*
 * present passes just as happily against a client that is present but ignored. The
 * question AD-19 actually raises is *"what happens if the generated client stops
 * working?"* — and the answer has to be "the build breaks", not "nothing, because
 * nothing depended on it". A probe that plants the break and requires a failure is the
 * only way to know the dependency is real.
 *
 * **The four probes.**
 *
 * 1. **The schema loses an operation id.** The generated TypeScript's binding for the
 *    detail endpoint disappears — so the call site has nothing to call.
 * 2. **The schema loses a path.** The route the frontend calls is no longer in the
 *    contract, so `api.GET("/api/events/{event_id}", …)` has no typed path.
 * 3. **The client stops being the client.** `backend-client.ts` stops exporting the
 *    typed `api`, so the call sites have nothing to reach the backend through.
 * 4. **A call site goes around the client.** The frontend hand-writes a `fetch` — which
 *    is exactly what AD-19 forbids, and exactly what the type-checker would catch if
 *    the client's types were the only way in.
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
  openapi: path.join(ROOT, "lib/api/openapi.json"),
  client: path.join(ROOT, "lib/backend-client.ts"),
  detailRead: path.join(ROOT, "lib/event-detail-read.ts"),
};

const PROBES = [
  {
    description: "the generated schema loses the detail endpoint's operation id",
    file: "schema",
    edits: [
      [
        "apps_personalization_detail_api_get_event_detail: {",
        "apps_personalization_detail_api_get_event_detail_BROKEN: {",
      ],
      [
        'get: operations["apps_personalization_detail_api_get_event_detail"];',
        'get: operations["apps_personalization_detail_api_get_event_detail_BROKEN"];',
      ],
    ],
    suite: "tests/ad19-endpoint-coverage.test.ts",
  },
  {
    description: "the committed schema loses the detail endpoint's path",
    file: "openapi",
    edits: [["/api/events/{event_id}", "/api/events/{event_id}_BROKEN"]],
    suite: "tests/ad19-endpoint-coverage.test.ts",
  },
  {
    description: "the generated schema loses the digest endpoint's operation id",
    file: "schema",
    edits: [
      [
        "apps_personalization_api_read_digest_endpoint: {",
        "apps_personalization_api_read_digest_endpoint_BROKEN: {",
      ],
      [
        'get: operations["apps_personalization_api_read_digest_endpoint"];',
        'get: operations["apps_personalization_api_read_digest_endpoint_BROKEN"];',
      ],
    ],
    suite: "tests/ad19-endpoint-coverage.test.ts",
  },
  {
    description: "the generated client stops exporting the typed api",
    file: "client",
    edits: [["export const api = createClient<paths>({", "const api = createClient<paths>({"]],
    suite: "tests/ad19-endpoint-coverage.test.ts",
  },
  {
    description: "the detail read goes around the generated client",
    file: "detailRead",
    // **The call site, not the docstring.** The read's docstring names the path it
    // calls, and that is the *first* occurrence in the file — so a whole-file replace
    // would rewrite the prose and leave the code calling the right endpoint. The
    // mutation has to be the code.
    edits: [['api.GET("/api/events/{event_id}"', 'api.GET("/api/events/hand-written"']],
    suite: "tests/ad19-endpoint-coverage.test.ts",
  },
  {
    description: "the detail read hand-writes a fetch, bypassing the client",
    file: "detailRead",
    edits: [
      [
        'const response = await api.GET("/api/events/{event_id}", {',
        'const response = await fetch("/api/events/{event_id}", {',
      ],
    ],
    suite: "tests/ad19-endpoint-coverage.test.ts",
  },
  {
    description: "the detail read defines its own api, shadowing the import",
    file: "detailRead",
    edits: [
      [
        "export async function readEventDetail(eventId: string): Promise<DetailRead> {",
        "const api = { GET: (p: string) => fetch(p) };\n\nexport async function readEventDetail(eventId: string): Promise<DetailRead> {",
      ],
    ],
    suite: "tests/ad19-endpoint-coverage.test.ts",
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

  // **Every pattern is checked before any edit is applied.**
  let missing = null;
  for (const [pattern] of probe.edits) {
    if (!original.includes(pattern)) {
      missing = pattern;
      break;
    }
  }
  if (missing !== null) {
    console.log(`SKIP  ${probe.description} — pattern not found: ${missing.slice(0, 70)}`);
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
    execFileSync("npx", ["vitest", "run", probe.suite], {
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
      (caught ? `\n          ${names.slice(0, 2).join("\n          ")}` : ""),
  );
  if (!caught) failures += 1;
}

console.log(`\n${PROBES.length - failures}/${PROBES.length} probes caught`);
process.exit(failures === 0 ? 0 : 1);
