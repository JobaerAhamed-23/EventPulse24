// @vitest-environment node
/**
 * AD-10, frontend half: the two explanations never cross.
 *
 * **What AD-10 says.** "Two indicators that look identical must never be silently
 * substituted for one another." The Event Fit (public, per `(event, city)`) and the
 * Relevance Pulse (personal, per user) look **identical on screen** — five dots, a
 * number, a tooltip. That is the whole premise of the rule, and it is why the rule
 * cannot be enforced by reading a rendered string: the two are designed to be
 * indistinguishable.
 *
 * **So the check is on the import graph.** An authenticated surface that reaches the
 * Event Fit's vocabulary could substitute one for the other, and no assertion on the
 * markup could tell.
 *
 * **The check is transitive, and that is what makes it structural.** A name check on
 * the route file would be bypassable by a helper: the route imports a component, the
 * component imports the Event Fit's label, and the route's own source never mentions
 * it. The backend learned this the hard way — the first Event Fit wall named two
 * leaves, and a two-line re-export walked straight through it
 * (`backend/tests/architecture/test_event_fit_separation.py` records the bypass and the
 * fix).
 *
 * So this file walks the frontend's own import graph, **from each authenticated route
 * outward**, and asserts the Event Fit's module is not in it.
 *
 * **The frontend's Event Fit vocabulary has one home.** `lib/event-fit.ts` holds the
 * Event Fit's range and its clamp; `lib/preview-labels.ts` holds its label and its
 * tooltip. Both are **public** vocabulary — the preview's, not the digest's. The
 * check is that the authenticated routes reach neither, and that the **preview** does.
 */
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "..");

/**
 * The **public** Event Fit vocabulary, by module.
 *
 * These are the modules that know what an Event Fit is. The preview's card uses them;
 * the digest's card must not, because the digest's card carries a Relevance Pulse.
 */
const EVENT_FIT_MODULES = ["lib/event-fit.ts", "lib/preview-labels.ts"];

/**
 * The **authenticated** surfaces.
 *
 * `app/page.tsx` is the Pulse Digest home and `app/events/[id]/page.tsx` is the Detail
 * Screen. Both are signed-in surfaces, and both carry a Relevance Pulse when one
 * exists.
 */
const AUTHENTICATED_ROUTES = ["app/page.tsx", "app/events/[id]/page.tsx"];

/** The public preview, which **is** allowed the Event Fit. */
const PUBLIC_ROUTE = "app/preview/page.tsx";

/**
 * The public city page, which **is** allowed the Event Fit.
 *
 * **The city page is a second public surface, and it is allowed the same vocabulary.**
 * The backend's city read projects the *persisted* Event Fit — the score and the tags
 * are carried as stored (`CityPageEventOut`'s own docstring says so, AD-10) — and FR-27's
 * page is where that score is shown. So the wall's direction holds: the Event Fit is
 * public vocabulary, and only public surfaces reach it.
 */
const CITY_ROUTE = "app/events-in/[slug]/page.tsx";

/**
 * The frontend's own modules, by their `@/…` path.
 *
 * The graph is walked over the `@/` alias, which is what every frontend module uses.
 */
const MODULE_BY_ALIAS = new Map<string, string>();

function modulePath(alias: string): string | null {
  const resolved = MODULE_BY_ALIAS.get(alias);
  if (!resolved) return null;
  return resolved;
}

/** Every module the file imports, as `@/…` aliases. */
function importedAliases(source: string): string[] {
  const aliases: string[] = [];
  const pattern = /(?:from\s+|import\s*\(\s*)["'](@\/[^"']+)["']/g;
  let match = pattern.exec(source);
  while (match !== null) {
    aliases.push(match[1]);
    match = pattern.exec(source);
  }
  return aliases;
}

/**
 * Every module the file imports **relatively**, resolved against its own directory.
 *
 * **The alias alone is not enough.** A sibling module is imported as `./preview-card`,
 * and a file in a subdirectory as `../lib/x` — so a walker that only understood `@/`
 * would see the preview's card as unreachable, and the "the preview still reaches the
 * Event Fit" check would pass vacuously.
 *
 * The resolution tries the exact path, then the three source extensions, then the
 * `index` file of a directory — the same four a bundler tries.
 */
function importedRelatives(source: string, importerAlias: string): string[] {
  const aliases: string[] = [];
  const pattern = /(?:from\s+|import\s*\(\s*)["'](\.[^"']+)["']/g;
  const importerDirectory = importerAlias.slice(0, importerAlias.lastIndexOf("/"));

  let match = pattern.exec(source);
  while (match !== null) {
    const specifier = match[1];
    const resolved = path.posix.normalize(path.posix.join(importerDirectory, specifier));
    const candidates = [
      resolved,
      `${resolved}.ts`,
      `${resolved}.tsx`,
      `${resolved}/index.ts`,
      `${resolved}/index.tsx`,
    ];
    const found = candidates.find((candidate) => MODULE_BY_ALIAS.has(candidate));
    if (found) aliases.push(found);
    match = pattern.exec(source);
  }

  return aliases;
}

/**
 * The source with its comments removed.
 *
 * A comment is not code — and these files' docstrings discuss the Event Fit by name,
 * so a source-text assertion that read them would be asserting on prose.
 */
function withoutComments(source: string): string {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
}

/** Every module under `app/`, `components/` and `lib/`, by its `@/…` alias. */
function discoverModules(): void {
  const roots = ["app", "components", "lib"];
  for (const root of roots) {
    walk(path.join(ROOT, root));
  }
}

function walk(directory: string): void {
  for (const entry of readdirSync(directory)) {
    const full = path.join(directory, entry);
    if (statSync(full).isDirectory()) {
      walk(full);
      continue;
    }
    if (!full.endsWith(".ts") && !full.endsWith(".tsx")) continue;
    if (full.endsWith(".test.ts") || full.endsWith(".test.tsx")) continue;
    const relative = path.relative(ROOT, full).split(path.sep).join("/");
    MODULE_BY_ALIAS.set(`@/${relative.replace(/\.(tsx?|jsx?)$/, "")}`, full);
  }
}

/**
 * Every module reachable from `entry`, by its `@/…` alias.
 *
 * **The walk is transitive and it is the point.** A direct check would be bypassable
 * by a helper; the walk follows every `@/` import to its end.
 */
function reachable(entry: string): Set<string> {
  const seen = new Set<string>();
  const queue = [entry];

  while (queue.length > 0) {
    const alias = queue.shift() as string;
    if (seen.has(alias)) continue;
    seen.add(alias);

    const file = modulePath(alias);
    if (!file) continue;
    const source = withoutComments(readFileSync(file, "utf8"));
    const imported = [...importedAliases(source), ...importedRelatives(source, alias)];
    for (const target of imported) {
      if (!seen.has(target)) queue.push(target);
    }
  }

  return seen;
}

describe("the frontend's module graph", () => {
  it("discovers the frontend's modules", () => {
    // The graph must not be silently empty — a discovery that found nothing would
    // make every reachability assertion vacuously true.
    discoverModules();
    expect(MODULE_BY_ALIAS.size).toBeGreaterThan(20);
    expect(MODULE_BY_ALIAS.has("@/lib/event-fit")).toBe(true);
    expect(MODULE_BY_ALIAS.has("@/lib/preview-labels")).toBe(true);
  });
});

describe("an authenticated surface never reaches the Event Fit", () => {
  for (const route of AUTHENTICATED_ROUTES) {
    it(`${route} does not reach the Event Fit's vocabulary`, () => {
      discoverModules();
      const reached = reachable(`@/${route.replace(/\.tsx$/, "")}`);

      for (const eventFitModule of EVENT_FIT_MODULES) {
        const alias = `@/${eventFitModule.replace(/\.ts$/, "")}`;
        expect(reached.has(alias), `${route} reaches ${alias} transitively`).toBe(false);
      }
    });

    it(`${route} does not name the Event Fit at all`, () => {
      const source = withoutComments(readFileSync(path.join(ROOT, route), "utf8"));
      expect(source).not.toMatch(/event[_-]?fit/i);
      expect(source).not.toMatch(/EventFit/);
    });
  }
});

describe("the public preview still reaches the Event Fit", () => {
  it("the preview reaches the Event Fit's vocabulary", () => {
    // **The wall is a direction, not an absence.**
    //
    // A rule that forbade the Event Fit everywhere would be satisfied by a tree where
    // the preview had no explanation either — and the preview's whole job is to show
    // one. So the check pins that the public surface still has it.
    discoverModules();
    const reached = reachable(`@/${PUBLIC_ROUTE.replace(/\.tsx$/, "")}`);

    expect(reached.has("@/lib/event-fit")).toBe(true);
  });

  it("the Event Fit's vocabulary has exactly two importers, both public", () => {
    // **One home per surface, and both surfaces are public.** The Event Fit's range and
    // clamp are imported by exactly two files — the preview's card and the city page's
    // card. A third importer would be a third surface carrying the public explanation,
    // and the next one could be an authenticated one.
    //
    // **The list is asserted exactly, not as a set.** A new importer has to be *added*
    // here — which is the point: adding one is a decision, and the decision is visible
    // in the diff, and this test fails until it is made.
    //
    // **The Event Fit's own modules are excluded.** `lib/preview-labels.ts` imports
    // `lib/event-fit.ts` because the label and the range are one vocabulary — that is
    // the Event Fit's own home, not a second surface reaching into it.
    discoverModules();
    const eventFitOwnModules = new Set(EVENT_FIT_MODULES.map((m) => `@/${m.replace(/\.ts$/, "")}`));
    const importers: string[] = [];

    for (const [alias, file] of MODULE_BY_ALIAS) {
      if (eventFitOwnModules.has(alias)) continue;
      const source = withoutComments(readFileSync(file, "utf8"));
      const imported = [...importedAliases(source), ...importedRelatives(source, alias)];
      if (imported.includes("@/lib/event-fit")) {
        importers.push(alias);
      }
    }

    expect(importers).toEqual([
      "@/components/city-page/city-event-card",
      "@/components/preview/preview-card",
    ]);
  });

  it("the city page reaches the Event Fit's vocabulary", () => {
    // **The city page shows the persisted fit.** The backend's city read carries the
    // score and the tags *as stored* (AD-10), and FR-27's page is where they are shown
    // — so the wall's direction holds: the Event Fit is public vocabulary, and the
    // public surfaces reach it.
    discoverModules();
    const reached = reachable(`@/${CITY_ROUTE.replace(/\.tsx$/, "")}`);

    expect(reached.has("@/lib/event-fit")).toBe(true);
    expect(reached.has("@/lib/preview-labels")).toBe(true);
  });
});

describe("the digest's own vocabulary is not the Event Fit's", () => {
  it("the digest's labels module does not import the preview's", () => {
    // The card and the detail screen read `lib/digest-labels.ts` — the **Relevance
    // Pulse**'s vocabulary. It must not borrow the Event Fit's.
    discoverModules();
    const reached = reachable("@/lib/digest-labels");

    expect(reached.has("@/lib/event-fit")).toBe(false);
    expect(reached.has("@/lib/preview-labels")).toBe(false);
  });

  it("the detail screen's vocabulary does not import the preview's", () => {
    discoverModules();
    const reached = reachable("@/lib/detail-labels");

    expect(reached.has("@/lib/event-fit")).toBe(false);
    expect(reached.has("@/lib/preview-labels")).toBe(false);
  });
});
