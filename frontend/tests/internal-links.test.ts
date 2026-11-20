// @vitest-environment node
/**
 * **No internal link in this app may point at a route that does not exist.**
 *
 * The sidenav's own rule, generalised: *"a link to a 404 is a lie about where the label
 * goes."*
 *
 * ## Why this file exists, when the rule already did
 *
 * `tests/digest-home-boundary.test.ts` has resolved internal `href`s against the app
 * directory for some time, and it is a good test with real history — its own comment
 * records that it replaced a deny-list of one string after `/settings/billing` sat in the
 * dev billing panel and three backend config defaults for weeks, returning every
 * completed checkout to a 404 while the suite stayed green.
 *
 * **Its reach was one surface.** It resolves the fifteen files *"the home surface is made
 * of"*. Everything else in `app/` and `components/` was unguarded, and on 2026-11-20 a
 * user reported a 404 from the empty Pulse Digest's "Suggest an event" link. The scan
 * that followed found two more, both outside that file's list and both worse:
 * `/terms` and `/privacy`, linked four times from `signup-form.tsx` and `signin/page.tsx`
 * under the sentence *"By creating an account, you agree to our Terms and Privacy
 * Policy."* The product asked people to accept documents it then 404'd.
 *
 * So the rule is kept and its scope is widened. This file is the general case; the
 * home-surface suite keeps its own copy as a local guard on the surface it describes.
 *
 * ## What counts as a link
 *
 * A literal `href="/..."` in a `.tsx` file under `app/` or `components/`, with comments
 * stripped first — **a comment is not code**, and these files quote withdrawn specs by
 * name. `digest-empty.tsx` discusses `/suggest` at length precisely because it no longer
 * links there.
 *
 * Skipped, with reasons:
 * - **Dynamic segments** (`/events/[id]`) — a template, not a destination; resolving one
 *   needs the params.
 * - **Template literals** (`` href={`/events/${id}`} ``) — same, and they resolve to a
 *   dynamic route by construction.
 * - **Query strings and fragments** — `/browse?offset=20` is `/browse`; the suffix is
 *   trimmed before resolution.
 * - **Test files** — they assert about links, they do not render them in production.
 *
 * ## What it does not catch
 *
 * A route string built at runtime, held in a constant, or returned by a helper. Those are
 * invisible to source matching. `lib/settings-sections.ts` holds exactly such a table and
 * every row in it currently resolves — **if that table grows a dead row, this test will
 * not see it.** The honest scope of this guard is literal hrefs, and saying so here is
 * cheaper than discovering it the way `/settings/billing` was discovered.
 */
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "..");

/** Every `.tsx` under `app/` and `components/` that is not a test. */
function sourceFiles(dir: string, acc: string[] = []): string[] {
  for (const entry of readdirSync(dir)) {
    const full = path.join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry === "node_modules" || entry === ".next") continue;
      sourceFiles(full, acc);
      continue;
    }
    if (!entry.endsWith(".tsx") && !entry.endsWith(".ts")) continue;
    if (entry.includes(".test.") || entry.includes(".spec.")) continue;
    acc.push(full);
  }
  return acc;
}

/**
 * The source with its comments removed.
 *
 * **A comment is not code.** `digest-empty.tsx` names `/suggest` in its header to explain
 * why it no longer links there (Amendment A-26); asserting on that prose would fail the
 * file for documenting itself.
 */
function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
}

/** Resolve a route to the file that would serve it, or null. */
function routeTarget(route: string): string | null {
  const segments = route.split("/").filter(Boolean);
  const candidates = [
    path.join(ROOT, "app", ...segments, "page.tsx"),
    path.join(ROOT, "app", ...segments, "route.ts"),
    path.join(ROOT, "app", ...segments, "route.tsx"),
  ];
  return candidates.find((candidate) => existsSync(candidate)) ?? null;
}

describe("internal links", () => {
  it("every literal internal href resolves to a route", () => {
    const files = [
      ...sourceFiles(path.join(ROOT, "app")),
      ...sourceFiles(path.join(ROOT, "components")),
    ];

    // The sweep is worthless if it silently matches nothing — a refactor to a `Route`
    // helper, or a move of these directories, would leave this suite green and blind.
    expect(files.length).toBeGreaterThan(50);

    // **Two routes are owed and not yet built**, and they are the reason this file
    // exists. `/terms` and `/privacy` are linked four times from the auth surfaces under
    // *"By creating an account, you agree to our Terms and Privacy Policy."*
    // `legal-page-routes` builds them in this same run; until it does, naming them here
    // is how this test lands green without pretending they resolve.
    //
    // **The exception removes itself.** The assertion below fails the moment either
    // route is built, so the fence cannot outlive the gap it covers — the same reverse
    // assertion `digest-home-boundary.test.ts` used to hold `/suggest` honest, which is
    // what made that dead link a known quantity rather than a surprise.
    const UNBUILT = new Set(["/terms", "/privacy"]);
    expect([...UNBUILT].filter((route) => routeTarget(route) !== null)).toEqual([]);

    const missing: string[] = [];
    let checked = 0;

    for (const file of files) {
      const code = withoutComments(readFileSync(file, "utf8"));
      for (const match of code.matchAll(/href="(\/[^"]*)"/g)) {
        const route = match[1].split(/[?#]/)[0];
        if (route.includes("[")) continue;
        checked += 1;
        if (UNBUILT.has(route)) continue;
        if (!routeTarget(route)) {
          missing.push(`${path.relative(ROOT, file)} → ${route}`);
        }
      }
    }

    expect(checked).toBeGreaterThan(10);
    expect(missing).toEqual([]);
  });
});
