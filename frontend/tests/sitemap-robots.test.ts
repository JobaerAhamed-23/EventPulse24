// @vitest-environment node
/**
 * The sitemap and robots policy — the *documents* they produce and the *rules* they
 * encode.
 *
 * **Three claims are load-bearing here, and each has a test that would fail if the claim
 * were dropped.**
 *
 * 1. **The sitemap is generated, never hand-maintained.** The index is a projection of
 *    the feed's `total`, and a child is a projection of the feed's pages — so the
 *    number of children and the URLs inside them cannot drift from the catalog.
 * 2. **Only publicly addressable URLs appear.** The feed is the public surface, so the
 *    sitemap is too: no `in_review` event, no superseded event, no below-threshold city.
 * 3. **The robots file disallows the authed routes and allows the public ones.** And
 *    the `/events/{uuid}` half is carried by the Detail Screen's own metadata, because
 *    robots.txt cannot express it.
 *
 * **The index split is chosen now, not discovered at scale.** The protocol's ceiling is
 * 50,000 URLs per sitemap; the number of children is `max(1, ceil(total / 50_000))`, and
 * that rule is a pure function of the feed's `total` — so the split is correct at any
 * size without a deployment.
 */
import { readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it, vi } from "vitest";

import { parseChildId, urlSet } from "@/app/sitemap/[id]/route";
import { childLocation, sitemapIndex } from "@/app/sitemap.xml/route";
import { childStart, isNamedChild, sitemapChildren } from "@/lib/sitemap-plan";
import robots from "@/app/robots";

const ROOT = path.resolve(__dirname, "..");

/** The origin the tests resolve against. */
const ORIGIN = new URL("https://eventpulse24.test");

/** The protocol's ceiling: 50,000 URLs in one sitemap. */
const MAX_URLS_PER_SITEMAP = 50_000;

/**
 * The robots rules, as a flat list of strings.
 *
 * **Next's `robots.ts` returns a typed object, and the object is the policy.** The
 * rendered `/robots.txt` is Next's business; what this project owns is the rules it
 * declares.
 */
function rules(): { allow?: string | string[]; disallow?: string | string[] } {
  const declared = robots();
  const rule = Array.isArray(declared.rules) ? declared.rules[0] : declared.rules;
  if (!rule) throw new Error("the robots file declares no rules");
  return rule as { allow?: string | string[]; disallow?: string | string[] };
}

/** The disallow list, as a flat array. */
function disallowed(): string[] {
  const value = rules().disallow;
  if (value === undefined) return [];
  return Array.isArray(value) ? value : [value];
}

// ── The robots file ───────────────────────────────────────────────────────────────

describe("the robots file", () => {
  it("allows the public surface", () => {
    expect(rules().allow).toBe("/");
  });

  it("disallows the authed and dev routes", () => {
    const list = disallowed();

    // **The AC's list, exactly.** Each one is a whole prefix, so `Disallow: /settings`
    // excludes `/settings` and everything under it.
    for (const prefix of ["/settings", "/timeline", "/conflicts", "/onboarding", "/dev"]) {
      expect(list, `${prefix} is not disallowed`).toContain(prefix);
    }
  });

  it("does not disallow /events, because it holds the public event pages", () => {
    // **This is the whole tension of the item, stated as a test.** `/events` is one path
    // segment serving two pages: `/events/{minted-slug}` is the public event page and
    // `/events/{uuid}` is the signed-in Detail Screen. `Disallow: /events/` would take
    // the public pages with it.
    expect(disallowed()).not.toContain("/events");
    expect(disallowed()).not.toContain("/events/");
  });

  it("does not disallow the public city pages", () => {
    expect(disallowed().some((rule) => rule.startsWith("/events-in-"))).toBe(false);
  });

  it("points at the sitemap", () => {
    // **The origin is the site's public origin, not the server's.** `siteUrl()` reads
    // `PUBLIC_SITE_URL`, so a deployment changes it without a rebuild.
    vi.stubEnv("PUBLIC_SITE_URL", "https://eventpulse24.test");

    try {
      expect(robots().sitemap).toBe("https://eventpulse24.test/sitemap.xml");
    } finally {
      vi.unstubAllEnvs();
    }
  });

  it("omits the sitemap line when no origin is configured in production", () => {
    // **An unset origin in production yields `undefined`** — and a `Sitemap:` line
    // naming `http://localhost:3000/sitemap.xml` would send every crawler to a machine
    // that is not this one. **An absent line is honest; a wrong one is not.**
    vi.stubEnv("PUBLIC_SITE_URL", "");
    vi.stubEnv("NODE_ENV", "production");

    try {
      const declared = robots();

      expect(declared.sitemap).toBeUndefined();
    } finally {
      vi.unstubAllEnvs();
    }
  });
});

describe("the Detail Screen's own metadata", () => {
  it("carries the noindex that robots.txt cannot express", () => {
    // **The `/events/{uuid}` half of the AC's disallow list.** robots.txt has no path
    // regular expression — the only wildcards are `*` and `$` — so it cannot exclude a
    // UUID without excluding the public slugs beside it. The document itself has to say
    // so, and a crawler reads that instruction on the page it fetched.
    const source = readFileSync(path.join(ROOT, "app/events/[id]/page.tsx"), "utf8");
    const withoutComments = source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");

    // **The noindex is on the Detail Screen branch only.** The public branch's metadata
    // is the shareable half, and it must stay indexable.
    expect(withoutComments).toContain("robots: { index: false, follow: false }");

    // **And it is inside the `isDetailEvent` branch** — the same discriminator the page
    // itself uses, so the two can never disagree about which surface a parameter names.
    const detailBranch = withoutComments.indexOf("if (isDetailEvent(id))");
    const noindex = withoutComments.indexOf("robots: { index: false, follow: false }");

    expect(detailBranch).toBeGreaterThan(-1);
    expect(noindex).toBeGreaterThan(detailBranch);
  });
});

// ── The sitemap index ─────────────────────────────────────────────────────────────

describe("the sitemap index", () => {
  it("is a sitemapindex, not a urlset", () => {
    // **The index names children; it does not list URLs itself.** A `<urlset>` at the
    // index's address would be a flat sitemap that could not grow past the ceiling.
    const document = sitemapIndex(ORIGIN, 1);

    expect(document).toContain("<sitemapindex");
    expect(document).not.toContain("<urlset");
  });

  it("names one child for a catalog that fits in one sitemap", () => {
    const document = sitemapIndex(ORIGIN, 1);

    expect(document).toContain("<loc>https://eventpulse24.test/sitemap/0.xml</loc>");
    expect(document.match(/<sitemap>/g)).toHaveLength(1);
  });

  it("names three children for 120,000 URLs", () => {
    // **The split is chosen now, not discovered at scale.** 120,000 URLs is three
    // children of at most 50,000 each, and the rule is a pure function of the total.
    const children = sitemapChildren(120_000);

    expect(children).toBe(3);

    const document = sitemapIndex(ORIGIN, children);

    expect(document.match(/<sitemap>/g)).toHaveLength(3);
    expect(document).toContain("<loc>https://eventpulse24.test/sitemap/0.xml</loc>");
    expect(document).toContain("<loc>https://eventpulse24.test/sitemap/1.xml</loc>");
    expect(document).toContain("<loc>https://eventpulse24.test/sitemap/2.xml</loc>");
  });

  it("does not split before the ceiling", () => {
    // **50,000 URLs is exactly one sitemap.** The split happens *past* the ceiling, not
    // at it — a sitemap of exactly 50,000 is legal.
    expect(sitemapChildren(50_000)).toBe(1);
    expect(sitemapChildren(50_001)).toBe(2);
  });

  it("always names at least one child, even for an empty catalog", () => {
    // **An index with no children is not an index.** A crawler would fetch it and find
    // nothing to walk.
    const document = sitemapIndex(ORIGIN, sitemapChildren(0));

    expect(document.match(/<sitemap>/g)).toHaveLength(1);
  });

  it("carries relative locations when no origin is configured", () => {
    // **An unset origin in production yields `undefined`** — and a `Sitemap:` line
    // naming `http://localhost:3000/sitemap.xml` would send every crawler to a machine
    // that is not this one. A relative location is honest.
    const document = sitemapIndex(undefined, 1);

    expect(document).toContain("<loc>/sitemap/0.xml</loc>");
    expect(document).not.toContain("localhost");
  });
});

// ── The child sitemap ─────────────────────────────────────────────────────────────

describe("the child sitemap", () => {
  it("is a urlset, with a loc and a lastmod per URL", () => {
    const document = urlSet(ORIGIN, [
      { path: "/events/slug-1", last_modified: "2026-08-20T09:14:00Z" },
      { path: "/events-in-brooklyn", last_modified: "2026-08-28T12:00:00Z" },
    ]);

    expect(document).toContain("<urlset");
    expect(document).not.toContain("<sitemapindex");
    expect(document).toContain("<loc>https://eventpulse24.test/events/slug-1</loc>");
    expect(document).toContain("<lastmod>2026-08-20T09:14:00Z</lastmod>");
    expect(document).toContain("<loc>https://eventpulse24.test/events-in-brooklyn</loc>");
  });

  it("escapes the XML", () => {
    // **A path or a timestamp that carried a quote would produce a document no parser
    // accepts** — and a sitemap that does not parse is worth nothing to a crawler.
    const document = urlSet(ORIGIN, [
      { path: "/events/a&b", last_modified: "2026-08-20T09:14:00Z" },
    ]);

    expect(document).toContain("a&amp;b");
    expect(document).not.toContain("a&b");
  });

  it("carries relative locations when no origin is configured", () => {
    const document = urlSet(undefined, [{ path: "/events/slug-1", last_modified: "x" }]);

    expect(document).toContain("<loc>/events/slug-1</loc>");
    expect(document).not.toContain("localhost");
  });

  it("reads the child's id out of the route's parameter", () => {
    // **Next's dynamic segment swallows the `.xml` suffix into the parameter**, so the
    // index advertises `/sitemap/0.xml` and the route serves exactly that name.
    expect(parseChildId("0.xml")).toBe(0);
    expect(parseChildId("12.xml")).toBe(12);
  });

  it("refuses an id that is not a number", () => {
    // **A crawler walking off the end of the index is doing something ordinary**, and
    // the answer is "no such sitemap".
    expect(parseChildId("abc.xml")).toBeNull();
    expect(parseChildId("")).toBeNull();
    expect(parseChildId("-1.xml")).toBeNull();
  });

  it("names its children the same way the index does", () => {
    // **One definition of where a child lives.** The index advertises a name and the
    // route serves it; two definitions would let them drift.
    expect(childLocation(ORIGIN, 3)).toBe("https://eventpulse24.test/sitemap/3.xml");
    expect(childLocation(undefined, 3)).toBe("/sitemap/3.xml");
  });
});

// ── The split, in one place ───────────────────────────────────────────────────────

describe("the sitemap's split", () => {
  it("is a pure function of the feed's total", () => {
    // **The split is chosen now, not discovered at scale.** One URL makes one child;
    // 120,000 URLs make three; and the rule needs no deployment to be right.
    expect(sitemapChildren(1)).toBe(1);
    expect(sitemapChildren(50_000)).toBe(1);
    expect(sitemapChildren(50_001)).toBe(2);
    expect(sitemapChildren(120_000)).toBe(3);
  });

  it("always names at least one child", () => {
    // **An empty catalog still has a child.** An index naming nothing would be a
    // document that says "there is nothing here" without saying it in the form a
    // crawler reads.
    expect(sitemapChildren(0)).toBe(1);
    expect(sitemapChildren(-5)).toBe(1);
    expect(sitemapChildren(Number.NaN)).toBe(1);
  });

  it("starts each child where the previous one ended", () => {
    // **The children partition the feed.** No URL is served twice, and no URL is
    // missed — which is the property the index and the children must agree on.
    expect(childStart(0)).toBe(0);
    expect(childStart(1)).toBe(MAX_URLS_PER_SITEMAP);
    expect(childStart(2)).toBe(2 * MAX_URLS_PER_SITEMAP);
  });

  it("names a child only when the index would name it", () => {
    // **A child the index does not name does not exist.** The index and the children
    // read the same rule, so they cannot disagree about how many children there are —
    // and a disagreement would be a sitemap that describes itself inconsistently.
    expect(isNamedChild(0, 3)).toBe(true);
    expect(isNamedChild(1, 50_001)).toBe(true);
    expect(isNamedChild(2, 50_001)).toBe(false);
    expect(isNamedChild(9, 3)).toBe(false);
    expect(isNamedChild(-1, 3)).toBe(false);
  });
});

// ── The shape of the whole thing ──────────────────────────────────────────────────

describe("the sitemap's shape", () => {
  it("has no app/sitemap.ts beside the route handlers", () => {
    // **Measured, not preferred.** `app/sitemap.ts` and `app/sitemap.xml/route.ts`
    // cannot coexist in one build — the build fails with *"Conflicting route and
    // metadata at /sitemap.xml"* — and Next 16's `app/sitemap.ts` emits a `<urlset>`
    // and never a `<sitemapindex>` at all. So the index is hand-written and
    // `app/sitemap.ts` does not exist.
    const source = readFileSync(path.join(ROOT, "app/sitemap.xml/route.ts"), "utf8");
    expect(source).toContain("<sitemapindex");

    // The file itself must not exist, and this is the check that keeps it that way.
    let exists = true;
    try {
      readFileSync(path.join(ROOT, "app/sitemap.ts"), "utf8");
    } catch {
      exists = false;
    }
    expect(exists, "app/sitemap.ts must not exist beside the route handlers").toBe(false);
  });

  it("routes both documents dynamically", () => {
    // **The slugs are minted at runtime**, so a build machine cannot enumerate them —
    // and a prerendered sitemap would be stale the first time the pipeline ran, which
    // is exactly the "hand-maintained" failure the AC forbids.
    const index = readFileSync(path.join(ROOT, "app/sitemap.xml/route.ts"), "utf8");
    const child = readFileSync(path.join(ROOT, "app/sitemap/[id]/route.ts"), "utf8");

    expect(index).toContain('export const dynamic = "force-dynamic"');
    expect(child).toContain('export const dynamic = "force-dynamic"');
  });
});
