// @vitest-environment node
/**
 * AD-19: every endpoint this intent added is **in the generated schema**, and the
 * frontend reaches it **through the generated client**.
 *
 * **What AD-19 says.** The frontend talks to the backend only through the generated
 * `api` client; `lib/api/` is generated and never hand-edited. That is a *chain*:
 *
 * ```
 * backend route → live OpenAPI schema → committed openapi.json → schema.ts → the
 * frontend's call site
 * ```
 *
 * A break anywhere in that chain must fail the build. This file checks the **middle**
 * of it — that the new endpoints are actually *there*, in the committed schema and
 * in the generated TypeScript — and the backend's `test_contract.py` checks the
 * first join (that the committed schema still equals the live one).
 *
 * **Why a coverage check and not just a drift check.** `test_contract.py` says the
 * committed schema matches the live API. It does not say the *right* endpoints are
 * there. An endpoint can be missing from the contract and the schema can be perfectly
 * in sync — the drift check would be green, and the frontend would have no way to
 * call it. So the coverage claim is separate, and it is stated here.
 *
 * **The three new endpoints.** This intent added:
 *
 * - `GET /api/events/{event_id}` — the Detail Screen's read;
 * - `POST /api/events/{event_id}/opened` — the detail-open write;
 * - `GET /api/personal/digest` — the Pulse Digest home's read.
 *
 * Each is checked in the committed schema, in the generated TypeScript, and at the
 * frontend's call site.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "..");

const OPENAPI = path.join(ROOT, "lib/api/openapi.json");
const SCHEMA_TS = path.join(ROOT, "lib/api/schema.ts");

/**
 * The one module the frontend reaches the backend through.
 *
 * It is **hand-written** — it is the adapter around the generated schema, not part of
 * the generated folder — so it is not under AD-19's "never hand-edited" rule. But it is
 * the **only door**, and the client-break probe showed that nothing was checking the
 * door was there.
 */
const CLIENT = path.join(ROOT, "lib/backend-client.ts");

/**
 * The endpoints this intent added, with the operation id the generated schema gives
 * them and the frontend modules that call them.
 *
 * **The operation id is the link.** It is the key the generated TypeScript uses, so
 * asserting on it proves two things at once: the endpoint is in the schema, *and* the
 * generated client has a typed binding for it.
 *
 * **`caller` is a list, because an endpoint can have more than one caller.** The
 * resolve endpoint is called from three places — the conflicts page's panel, the Detail
 * Screen's actions, and the personal-events panel — and **all three are checked**. A
 * single-caller field would have let two of them drift out of the contract unnoticed,
 * which is the exact failure the file exists to catch.
 */
const NEW_ENDPOINTS = [
  {
    path: "/api/events/{event_id}",
    method: "get",
    operationId: "apps_personalization_detail_api_get_event_detail",
    /** The frontend's modules that call it. */
    caller: ["lib/event-detail-read.ts"],
  },
  {
    path: "/api/personal/digest",
    method: "get",
    operationId: "apps_personalization_api_read_digest_endpoint",
    caller: ["lib/digest-read.ts"],
  },
  // ── The Unified Timeline and the Conflict Review ───────────────────────────────
  {
    path: "/api/personal/timeline",
    method: "get",
    operationId: "apps_personalization_api_read_timeline",
    caller: ["lib/timeline-read.ts"],
  },
  {
    path: "/api/personal/conflicts",
    method: "get",
    operationId: "apps_personalization_api_list_conflicts",
    caller: ["lib/conflict-list-read.ts"],
  },
  {
    path: "/api/personal/events/conflicts/{pair_id}/resolve",
    method: "post",
    operationId: "apps_personalization_api_resolve_event_conflict",
    // **Three call sites, and all three matter.** The conflicts page answers a pair
    // reviewed later; the Detail Screen answers the prompt it just raised; the
    // personal-events panel answers the prompt its own create raised. Each one posts
    // a `{resolution, side}` body, so each one is a place the contract could be
    // broken.
    caller: [
      "components/conflicts/conflicts-panel.tsx",
      "components/detail/detail-actions.tsx",
      "components/personal-events-panel.tsx",
    ],
  },
  {
    path: "/api/personal/events",
    method: "post",
    operationId: "apps_personalization_api_create_event",
    caller: ["components/personal-events-panel.tsx"],
  },
  {
    path: "/api/personal/saved-events/{catalog_event_id}",
    method: "post",
    operationId: "apps_personalization_api_save_public_event",
    caller: ["components/detail/detail-actions.tsx"],
  },
] as const;

/**
 * The detail-open endpoint — **present in the schema, and with no caller.**
 *
 * The backend's own module docstring states the design: *"the signal is a separate
 * request the frontend fires when the screen is actually shown."* The endpoint is in
 * the committed schema and in the generated TypeScript — so the **generated-client**
 * half of AD-19 holds — but **nothing in the frontend calls it.**
 *
 * **So the coverage check is split, and the split is the honest shape of the claim.**
 * The endpoint's *presence* is asserted; the *caller* is not asserted to exist,
 * because it does not. This is recorded as a gap in the work item's report, not
 * papered over with a check that cannot fail.
 *
 * **Why this is not silently fixed here.** Calling the endpoint is a **behaviour
 * change** to the Detail Screen — it would fire a write on every screen view, which
 * is a decision about the surface's semantics and about what a "view" means. It also
 * has to be fire-and-forget (the screen must not wait on it) and it must not fire for
 * an anonymous visitor (the endpoint answers 401). Those are the frontend-event-detail
 * item's decisions to make, not this item's to make in passing.
 */
const DETAIL_OPEN_ENDPOINT = {
  path: "/api/events/{event_id}/opened",
  method: "post",
  operationId: "apps_personalization_detail_api_post_event_opened",
} as const;

const openapi = JSON.parse(readFileSync(OPENAPI, "utf8")) as {
  paths: Record<string, Record<string, { operationId?: string }>>;
};

const schemaTs = readFileSync(SCHEMA_TS, "utf8");

/**
 * The source with its comments removed.
 *
 * **A comment is not code, and an assertion that reads one is asserting on prose.**
 * The detail read's own docstring names the path it calls — *"GET `/api/events/
 * {event_id}` returns the event's public facts"* — so a `toContain(path)` over the raw
 * file would still pass after the call site had been changed to a hand-written URL.
 * **The client-break probe found that**: the probe rewrote the call to
 * `/api/events/hand-written`, and the test stayed green because the docstring still
 * said `{event_id}`.
 */
function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
}

/**
 * Every frontend source file under `app`, `components` and `lib`, handed to `visit`.
 *
 * **The search is over the source tree**, not over a list of files this test knows
 * about — so a caller added in a new module is found, and a caller added anywhere
 * else is not missed.
 *
 * **Test files are skipped.** A test file names endpoints by the dozen — it mocks
 * them, asserts on them — and a test file is not a call site. Including them would
 * report every endpoint as called by every test.
 *
 * **The generated folder is skipped too.** `lib/api/schema.ts` names every endpoint
 * in the contract by definition — it is the contract. So a search that included it
 * would find every endpoint and report them all as called, which is the false green
 * these searches exist to avoid.
 */
function visitSources(visit: (relativePath: string, source: string) => void): void {
  const walk = (directory: string): void => {
    for (const entry of readdirSync(directory)) {
      const full = path.join(directory, entry);
      if (statSync(full).isDirectory()) {
        walk(full);
        continue;
      }
      if (!full.endsWith(".ts") && !full.endsWith(".tsx")) continue;
      if (full.endsWith(".test.ts") || full.endsWith(".test.tsx")) continue;
      const relative = path.relative(ROOT, full).split(path.sep).join("/");
      if (relative.startsWith("lib/api/")) continue;
      visit(relative, readFileSync(full, "utf8"));
    }
  };

  for (const root of ["app", "components", "lib"]) {
    walk(path.join(ROOT, root));
  }
}

/**
 * Every frontend module that names `endpointPath` in a call to the generated client.
 */
function findCallers(endpointPath: string): string[] {
  const callers: string[] = [];

  visitSources((relative, source) => {
    if (source.includes(endpointPath)) {
      callers.push(relative);
    }
  });

  return callers.sort();
}

describe("AD-19: the new endpoints are in the generated schema", () => {
  for (const endpoint of NEW_ENDPOINTS) {
    it(`${endpoint.method.toUpperCase()} ${endpoint.path} is in the committed schema`, () => {
      const operations = openapi.paths[endpoint.path];

      expect(operations, `${endpoint.path} is not in the committed schema`).toBeDefined();
      expect(
        operations[endpoint.method],
        `${endpoint.method.toUpperCase()} ${endpoint.path} is not in the committed schema`,
      ).toBeDefined();
    });

    it(`${endpoint.method.toUpperCase()} ${endpoint.path} has its operation id`, () => {
      // The operation id is the **link** between the schema and the generated
      // TypeScript. Asserting on it proves the endpoint is not merely present but
      // *reachable* by the client.
      const operation = openapi.paths[endpoint.path]?.[endpoint.method];

      expect(operation?.operationId).toBe(endpoint.operationId);
    });

    it(`${endpoint.operationId} is bound in the generated TypeScript`, () => {
      // **The operation id must be a *key* in the generated `operations` object, and
      // the generated `paths` entry must *reference* that key.**
      //
      // **Why both, and why not `toContain`.** `schema.ts` names an operation id
      // **twice**: once as the key of the `operations` entry that carries the
      // operation's request and response types, and once inside the `paths` entry
      // that points at it (`get: operations["…"]`). A `toContain` over the whole file
      // is satisfied by **either** one alone — so renaming only the `operations` key
      // left the `paths` reference behind and the check stayed green. **The
      // client-break probe found exactly that.** Both halves have to hold, and in the
      // right relationship, or the binding is broken.
      //
      // The `operations` block is the generated interface that carries each
      // operation's request and response types.
      const operationsStart = schemaTs.indexOf("export interface operations {");
      expect(operationsStart, "the generated schema has no operations interface").toBeGreaterThan(
        -1,
      );

      const operationsBlock = schemaTs.slice(operationsStart);

      // **The key.** It is a line that *declares* the operation id, not one that
      // references it — so it is matched at the start of a line, followed by a colon.
      const declared = new RegExp(`^\\s{4}"?${endpoint.operationId}"?:\\s*\\{`, "m");
      expect(
        declared.test(operationsBlock),
        `${endpoint.operationId} is not a key in the generated operations block`,
      ).toBe(true);

      // **The reference.** The `paths` entry points at the operation id.
      expect(schemaTs, `the generated paths do not reference ${endpoint.operationId}`).toContain(
        `operations["${endpoint.operationId}"]`,
      );
    });

    it(`${endpoint.caller.join(", ")} reaches ${endpoint.path} through the generated client`, () => {
      for (const callerPath of endpoint.caller) {
        const caller = withoutComments(readFileSync(path.join(ROOT, callerPath), "utf8"));

        // **Through the generated client, and not around it.** The path appears in the
        // call site's typed path expression — `api.GET("/api/events/{event_id}", …)` —
        // so a call site that spelled the URL out by hand would still be caught.
        //
        // **The comments are stripped first, and that is not a detail.** The detail
        // read's own docstring names the path it calls. A `toContain` over the raw file
        // was satisfied by the *prose*, so a call site rewritten to a hand-written URL
        // still passed. The client-break probe found it.
        expect(caller, `${callerPath} must reach ${endpoint.path}`).toContain(endpoint.path);

        // And the call goes through `api`, the generated client — not through a raw
        // `fetch`, which would bypass the generated types entirely.
        expect(caller, `${callerPath} must call the generated client`).toMatch(/api\.(GET|POST)\(/);
        expect(caller, `${callerPath} must not call fetch`).not.toMatch(/\bfetch\(/);
      }
    });

    it(`${endpoint.caller.join(", ")} imports the generated client, and does not define its own`, () => {
      // **The import is what makes the client load-bearing.** A call site that
      // mentions `api.GET(` but imports `api` from somewhere else — or defines its own
      // `api` — would satisfy the assertion above while bypassing the generated types
      // entirely. The client-break probe found the shape of this hole: removing the
      // export from `backend-client.ts` broke every call site, and nothing said so.
      for (const callerPath of endpoint.caller) {
        const caller = withoutComments(readFileSync(path.join(ROOT, callerPath), "utf8"));

        expect(caller, `${callerPath} must import the generated client`).toMatch(
          /import\s*\{[^}]*\bapi\b[^}]*\}\s*from\s*["']@\/lib\/backend-client["']/,
        );

        // **And it must not define its own `api`.** A local `const api = …` would shadow
        // the import and the call would go somewhere the generated types do not cover.
        expect(caller, `${callerPath} must not define its own 'api'`).not.toMatch(
          /\b(?:const|let|var|function|class)\s+api\b/,
        );
      }
    });
  }
});

describe("AD-19: the detail-open endpoint", () => {
  it("is in the committed schema", () => {
    const operations = openapi.paths[DETAIL_OPEN_ENDPOINT.path];

    expect(operations, `${DETAIL_OPEN_ENDPOINT.path} is not in the committed schema`).toBeDefined();
    expect(operations?.[DETAIL_OPEN_ENDPOINT.method]).toBeDefined();
  });

  it("has its operation id, bound in the generated TypeScript", () => {
    const operation = openapi.paths[DETAIL_OPEN_ENDPOINT.path]?.[DETAIL_OPEN_ENDPOINT.method];

    expect(operation?.operationId).toBe(DETAIL_OPEN_ENDPOINT.operationId);
    expect(schemaTs).toContain(DETAIL_OPEN_ENDPOINT.operationId);
  });

  it("has no frontend caller — a recorded gap, not a silent one", () => {
    // **This test names a gap.** It is a test that **passes** while stating a fact
    // that is *not* what the product wants: the endpoint is generated and reachable,
    // but the Detail Screen never calls it.
    //
    // **Why it is written this way.** The alternative — asserting a caller exists —
    // would fail today, and failing today would mean the run could not close over a
    // gap it did not create. The alternative of *not mentioning it* would be worse:
    // a reader of this file would conclude the endpoint is wired up.
    //
    // So the gap is **stated in a test that can see it change.** When the frontend
    // gains its caller, this test **fails** — because a caller now exists and the
    // gap is closed — and whoever closes it deletes the test and adds the
    // "reaches it through the generated client" assertion alongside the others.
    //
    // That is what makes this a *test* rather than a comment: it is a tripwire on
    // the state of the world, and it will fire.
    const callers = findCallers(DETAIL_OPEN_ENDPOINT.path);

    expect(
      callers,
      "the detail-open endpoint now has a frontend caller. The gap is closed: delete " +
        "this test and add the endpoint to NEW_ENDPOINTS, with its caller's module.",
    ).toEqual([]);
  });
});

describe("AD-19: the generated folder is not hand-edited", () => {
  it("the schema's operation ids are the generated ones, not hand-written ones", () => {
    // **The generated operation ids carry the Django app's dotted path.** That is
    // what `openapi-fetch` generates from a Ninja API, and it is a shape no
    // hand-written id would have. So this is a cheap check that `schema.ts` was
    // generated rather than typed out.
    const generated = openapi.paths["/api/events/{event_id}"]?.get?.operationId ?? "";

    expect(generated).toMatch(/^apps_[a-z_]+_[a-z_]+_[a-z_]+$/);
  });

  it("every operation id in the committed schema appears in the generated TypeScript", () => {
    // **The whole chain, in one assertion.** Every operation the committed schema
    // declares has a binding in the generated client. A schema that grew an
    // endpoint without the client being regenerated would fail here — and that is
    // the "schema regenerated but the client not" half of the chain.
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

  it("every endpoint the frontend calls is in the committed schema", () => {
    // **The other direction of the join, and the one that was missing.**
    //
    // The sweep above goes *from* the schema *into* the client: every operation the
    // committed schema declares has a binding. This goes the other way: every path
    // the frontend **calls** is one the schema declares.
    //
    // **Why it was missing.** `NEW_ENDPOINTS` is a hand-kept list, and a list is only
    // as good as the last time somebody added to it. An endpoint added to the backend
    // and called from the frontend — but not added to `NEW_ENDPOINTS` — would be
    // invisible to every check in this file. The schema would not mention it, so the
    // sweep above would not see it either, and the frontend would be calling a path the
    // contract does not describe. `openapi-fetch` types the call, so `tsc` catches a
    // *typo* — but it cannot catch an endpoint that was added to the backend and
    // **called correctly by hand**: the call is typed, the path is in the schema, and
    // nothing says the schema *should* have it.
    //
    // So this is derived from the source tree rather than from a list. Every
    // `api.GET("…")` / `api.POST("…")` call site is found, and its path is checked
    // against the committed schema.
    const declared = new Set(Object.keys(openapi.paths));
    const uncalled: string[] = [];

    visitSources((relative, source) => {
      const withoutProse = withoutComments(source);
      // The path is the **first argument** of the call — a literal string. A
      // template literal would be a dynamic path, and the contract is keyed by
      // literal paths, so only literals are checked.
      for (const match of withoutProse.matchAll(/api\.(?:GET|POST|PATCH|DELETE)\(\s*"([^"]+)"/g)) {
        if (!declared.has(match[1])) {
          uncalled.push(`${relative} calls ${match[1]}`);
        }
      }
    });

    expect(
      uncalled,
      "the frontend calls endpoints that are not in the committed schema — run `make client`",
    ).toEqual([]);
  });

  it("the client module exports the typed api, and types it from the generated schema", () => {
    // **The client is the one door, and this checks the door exists.**
    //
    // **Why this needed saying.** The client-break probe removed the `export` from
    // `backend-client.ts` — turning the typed client into a module-local const — and
    // **every endpoint test stayed green**. The call sites' own assertions read their
    // *source*, and a source that says `api.GET(…)` still says it when `api` no longer
    // exists. Nothing was checking that the thing the call sites import is actually
    // exported.
    //
    // So two things are asserted: the client is **exported**, and it is **typed from
    // the generated schema** — because an untyped `api` would satisfy the first and
    // defeat the second, and the whole point of AD-19 is the typing.
    const client = withoutComments(readFileSync(CLIENT, "utf8"));

    expect(
      client,
      "the client module must export 'api' — it is the one way the frontend reaches " +
        "the backend (AD-19)",
    ).toMatch(/export\s+const\s+api\b/);

    expect(client, "the client must be typed from the generated schema").toMatch(
      /createClient<\s*paths\s*>/,
    );

    // **And the schema type it uses is the generated one.**
    expect(client).toMatch(/import\s+type\s*\{\s*paths\s*\}\s*from\s*["']@\/lib\/api\/schema["']/);
  });
});
