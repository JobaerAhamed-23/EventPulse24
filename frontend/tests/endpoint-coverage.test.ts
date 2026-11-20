// @vitest-environment node
/**
 * **Every endpoint in the contract is either called from the UI, or declared uncalled.**
 *
 * This file exists because eight gaps accumulated across twelve intents and thirty runs
 * while every test in the repo was green. Four endpoints were built, tested, documented
 * and reachable — and nothing in the frontend called them. A Pro feature could not be
 * used, a promise onboarding made twice could not be kept, and half of FR-24's neighbour
 * rule never fired. None of it failed anything.
 *
 * Two adjacent checks exist and neither covers this:
 *
 * - `backend/tests/.../test_contract.py` asserts the committed schema equals the live API.
 * - `ad19-endpoint-coverage.test.ts` asserts that a hand-maintained list of endpoints is
 *   in the schema and reached through the generated client. It covers the endpoints one
 *   intent added, by name.
 *
 * Both are green while an endpoint has no caller. **This one is not.**
 *
 * **The allow-list is the point.** "Uncalled" is not always a bug: the RFC 8058
 * unsubscribe path is called by a mail provider, the export links from an email, the
 * billing webhook by Stripe, and the public catalog reads are an anonymous API the UI
 * deliberately does not use. Each is a decision, and a decision in a reviewable list is
 * worth more than one in somebody's memory.
 *
 * **What this test cannot see.** A *called* endpoint is not a *reachable* feature. Until
 * this intent, `SavedEventsSection` called `GET /api/personal/saved-events` from a
 * component nothing rendered, and `PersonalEventsPanel`'s list branch was the same shape.
 * This test would have called both covered. Reachability is a different claim and belongs
 * in Section C of the traceability matrix, not here.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "..");
const OPENAPI = path.join(ROOT, "lib/api/openapi.json");

/** An HTTP method as the committed schema spells it. */
const METHODS = ["get", "put", "post", "delete", "patch"] as const;
type Method = (typeof METHODS)[number];

/** One endpoint, as `METHOD /path`. */
type Endpoint = `${Uppercase<Method>} ${string}`;

/**
 * The endpoints with no frontend caller, and why each one is correct.
 *
 * **An entry here is a claim about the world, not a mute button.** If one of these gains
 * a caller, this file fails and the entry must go — a stale exemption is a lie in the
 * same way a missing one is.
 */
const DECLARED_UNCALLED: Record<Endpoint, string> = {
  "GET /api/email/click":
    "Followed from an email client, not from the app. It is a redirect target.",
  "GET /api/email/unsubscribe":
    "RFC 8058 one-click. The mail provider that requests it has no session, and the signed token is the authorisation.",
  "POST /api/email/unsubscribe":
    "The same RFC 8058 path, posted by the provider or by the confirmation page the backend serves.",
  "POST /api/webhooks/billing": "Called by Stripe. There is no browser in this path.",
  "GET /api/exports/{export_id}":
    "The export arrives by email: `download-my-data.tsx` is explicit that the UI requests one and downloads nothing.",
  "GET /api/exports/{export_id}/{fmt}": "The same email link, for one format.",
  "GET /api/catalog/events":
    "The anonymous public list. The signed-in UI uses `/api/personal/browse`, which is personalised and quota-aware.",
  "GET /api/catalog/events/{event_id}":
    "The anonymous public read by id. The UI reads `/api/events/{id}` when signed in and `by-slug` for the public page.",
  "GET /api/auth/profile/avatar/{version}":
    "Fetched by the browser's image loader from an `<img src>`, not by this client. The URL arrives on `me` as `avatar_url` and is put straight into the tag; there is no fetch to typecheck. It is the one endpoint here whose consumer is the markup rather than TypeScript.",
  "POST /api/auth/profile/deletion":
    "**A-16's confirmation modal is not built.** The engine is — the command, the grace period and this endpoint all exist — but the modal that would call it is scoped to a follow-up item, because A-16's third paragraph promises a cancellation surface and an email, and a modal in front of promises the engine does not keep would be worse than no modal. The API a modal needs is already here; the modal is what is missing.",
  "DELETE /api/auth/profile/deletion":
    "The same gap, the other half: cancelling a pending deletion is called by the same modal that does not exist yet.",
};

/** Every `METHOD /path` in the committed contract. */
function contractEndpoints(): Endpoint[] {
  const openapi = JSON.parse(readFileSync(OPENAPI, "utf8")) as {
    paths: Record<string, Record<string, unknown>>;
  };
  const found: Endpoint[] = [];
  for (const [route, operations] of Object.entries(openapi.paths)) {
    for (const method of METHODS) {
      if (operations[method]) found.push(`${method.toUpperCase() as Uppercase<Method>} ${route}`);
    }
  }
  return found.sort();
}

/**
 * Source with its comments removed.
 *
 * **A comment is not a call site.** `ad19-endpoint-coverage.test.ts` found this the hard
 * way: a `toContain(path)` over raw source stayed green after a call site had been
 * rewritten to a hand-written URL, because a docstring still named the path. Several
 * modules in this repo name their endpoint in prose directly above the call.
 */
function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
}

/** Every frontend source file that could hold a call site. */
function sources(): { relative: string; code: string }[] {
  const out: { relative: string; code: string }[] = [];
  const walk = (directory: string): void => {
    for (const entry of readdirSync(directory)) {
      const full = path.join(directory, entry);
      if (statSync(full).isDirectory()) {
        walk(full);
        continue;
      }
      if (!full.endsWith(".ts") && !full.endsWith(".tsx")) continue;
      // A test file names endpoints by the dozen and is not a call site.
      if (full.endsWith(".test.ts") || full.endsWith(".test.tsx")) continue;
      const relative = path.relative(ROOT, full).split(path.sep).join("/");
      // The generated client names every endpoint by definition — it *is* the contract.
      if (relative.startsWith("lib/api/")) continue;
      out.push({ relative, code: withoutComments(readFileSync(full, "utf8")) });
    }
  };
  for (const root of ["app", "components", "lib"]) walk(path.join(ROOT, root));
  return out;
}

/**
 * The endpoints the frontend calls, as `METHOD /path`.
 *
 * **Matched on the call expression itself** — `.POST(` immediately followed by the path
 * literal — not on "the method and the path both appear in this file". A probe proved why
 * the looser rule is worthless: `personal-events-panel.tsx` calls `PATCH` and `DELETE` on
 * the *same* path, so breaking the `DELETE` call site left the file still containing both
 * `.DELETE(` and the path literal, and the loose check reported the endpoint covered. The
 * check could not see the gap it exists to find.
 *
 * **Matched by method and path together.** A path-only match would hide a real gap:
 * `/api/notices/events/{id}/mute` has a `PUT` and a `DELETE`, and the UI uses both — but
 * if it used only one, a path-only check would report the other as covered.
 */
function calledEndpoints(): Map<Endpoint, string[]> {
  const called = new Map<Endpoint, string[]>();
  const files = sources();

  for (const endpoint of contractEndpoints()) {
    const [method, route] = endpoint.split(" ") as [Uppercase<Method>, string];
    // `.POST(` then optional whitespace then the exact path literal. The path is
    // escaped: it contains `{` and `}`, which are regex quantifier syntax.
    const call = new RegExp(`\\.${method}\\s*\\(\\s*"${route.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}"`);
    for (const { relative, code } of files) {
      if (!call.test(code)) continue;
      called.set(endpoint, [...(called.get(endpoint) ?? []), relative]);
    }
  }
  return called;
}

/**
 * Endpoints reached through a path held in a variable, which no call-expression match
 * can see.
 *
 * **This is a loophole, so it is small, named and justified.** `onboarding-flow.tsx`
 * declares `path: "/api/personal/onboarding/step" | "/api/personal/onboarding/step/skip"`
 * and calls `advance(path)`. Both endpoints are genuinely used; a strict matcher reports
 * two false gaps. Each entry names the module, and the module is checked to still contain
 * the path literal — so deleting the call still fails this file.
 */
const CALLED_VIA_VARIABLE: Record<Endpoint, string> = {
  "POST /api/personal/onboarding/step": "components/onboarding/onboarding-flow.tsx",
  "POST /api/personal/onboarding/step/skip": "components/onboarding/onboarding-flow.tsx",
};

/** The endpoints covered either way. */
function coveredEndpoints(): Map<Endpoint, string[]> {
  const covered = calledEndpoints();
  for (const [endpoint, module] of Object.entries(CALLED_VIA_VARIABLE) as [Endpoint, string][]) {
    const [, route] = endpoint.split(" ") as [string, string];
    const file = sources().find((candidate) => candidate.relative === module);
    if (file && file.code.includes(`"${route}"`)) {
      covered.set(endpoint, [...(covered.get(endpoint) ?? []), module]);
    }
  }
  return covered;
}

describe("every endpoint is called or declared uncalled", () => {
  it("has no endpoint that is neither called nor declared", () => {
    const called = coveredEndpoints();
    const orphans = contractEndpoints().filter(
      (endpoint) => !called.has(endpoint) && !(endpoint in DECLARED_UNCALLED),
    );

    expect(
      orphans,
      "These endpoints are in the contract, have no frontend caller, and are not in " +
        "DECLARED_UNCALLED. Either wire one up, or add it to that map with the reason " +
        "it is correct for the UI not to call it:\n  " +
        orphans.join("\n  "),
    ).toEqual([]);
  });

  it("has no declared-uncalled endpoint that is in fact called", () => {
    // **A stale exemption is a lie in the same way a missing one is.** An endpoint that
    // gained a caller must leave this map, or the map stops describing the world.
    const called = coveredEndpoints();
    const stale = Object.keys(DECLARED_UNCALLED).filter((endpoint) =>
      called.has(endpoint as Endpoint),
    );

    expect(
      stale,
      "These endpoints are declared uncalled but now have callers. Remove them from " +
        "DECLARED_UNCALLED:\n  " +
        stale.map((e) => `${e} — ${called.get(e as Endpoint)?.join(", ")}`).join("\n  "),
    ).toEqual([]);
  });

  it("has no declared-uncalled endpoint that has left the contract", () => {
    // An entry for an endpoint that no longer exists is dead weight that reads as a
    // live decision.
    const contract = new Set(contractEndpoints());
    const gone = Object.keys(DECLARED_UNCALLED).filter(
      (endpoint) => !contract.has(endpoint as Endpoint),
    );

    expect(gone, `No longer in the contract: ${gone.join(", ")}`).toEqual([]);
  });

  it("gives every declared-uncalled endpoint a reason, not a shrug", () => {
    const thin = Object.entries(DECLARED_UNCALLED).filter(([, reason]) => reason.length < 30);

    expect(thin.map(([endpoint]) => endpoint)).toEqual([]);
  });
});
