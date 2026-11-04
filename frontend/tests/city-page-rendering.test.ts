// @vitest-environment node
/**
 * The city page's *rendering* properties — the ones a DOM test cannot see.
 *
 * **This file exists because the two hardest properties of this route are not
 * properties of the rendered tree.** They are properties of *where the render sits in
 * Next's machinery*, and of *where the route lives*, and the only way to assert on them
 * is to read the source:
 *
 *   1. **The route must not sit under a Suspense boundary.** Next's rule is exact: "To
 *      return a real `404` status, the resource has to be checked before the response
 *      streams." A Suspense boundary *above* the page streams its fallback first, and
 *      once the response has streamed the status can no longer be set — so the unknown
 *      city's `notFound()` would answer **200**. That is a soft 404, and a soft 404 is
 *      a URL a crawler records as a page that exists.
 *   2. **The public URL must be the hyphenated one.** Next.js has no native prefixed
 *      dynamic segment, so the URL is preserved by a rewrite and the internal segment is
 *      a normal dynamic one — with a permanent redirect back out, or the page would be
 *      served at two URLs and the ranking would split across the copies.
 *
 * **Both were measured against a running production server.** With a segment-level
 * `loading.tsx`, the unknown slug answered 200. With `app/events-in-[slug]/page.tsx`, the
 * public URL answered 404 and the route was registered in `staticRoutes` with the
 * parameter named `nxtPslug` — so `params.slug` never arrived.
 *
 * **So these are asserted on the source** — the same house pattern as
 * `tests/public-event-rendering.test.ts`.
 */
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "..");

/** The route segment's own source, with its comments removed. */
function segmentSource(): string {
  const source = readFileSync(path.join(ROOT, "app/events-in/[slug]/page.tsx"), "utf8");
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
}

/** The read module's own source, with its comments removed. */
function readSource(): string {
  const source = readFileSync(path.join(ROOT, "lib/city-page-read.ts"), "utf8");
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
}

/** The config's own source. */
function configSource(): string {
  return readFileSync(path.join(ROOT, "next.config.ts"), "utf8");
}

describe("the segment has no boundary above the page", () => {
  it("has no loading.tsx", () => {
    // **A `loading.tsx` is a Suspense boundary above the page.** It is the one thing
    // that turns the unknown city's real 404 into a soft 404.
    expect(existsSync(path.join(ROOT, "app/events-in/[slug]/loading.tsx"))).toBe(false);
  });

  it("keeps the notFound() in the render path", () => {
    // **The 404 is raised before anything streams.** `notFound()` is called in the page
    // function itself, which the route awaits.
    const source = segmentSource();

    expect(source).toContain("notFound()");
    expect(source).toContain('read.kind === "not-found"');
  });

  it("wraps the page in no Suspense boundary", () => {
    const source = segmentSource();

    // **There is no `<Suspense>` anywhere in the segment.** One above the page would
    // stream the response before `notFound()` could set the status.
    expect(source).not.toContain("Suspense");
  });
});

describe("the segment's rendering mode", () => {
  it("is dynamic — one segment cannot be both", () => {
    // **The listing is paged** (`?page=N`), and a static segment cannot serve an
    // unbounded number of query-string variants without a `generateStaticParams` per
    // page. So the segment is dynamic and the *facts* are cached in the data cache.
    const source = segmentSource();

    expect(source).toContain('export const dynamic = "force-dynamic"');
  });

  it("registers no static params, so no path is claimed to be prerenderable", () => {
    // **`generateStaticParams` returning `[]` registers the route as prerenderable**,
    // and a prerendered route that bails to dynamic at request time throws "Page
    // changed from static to dynamic at runtime" — a **500 for every URL**. The city
    // slugs are minted at runtime, so a build machine cannot know them anyway.
    const source = segmentSource();

    expect(source).not.toContain("generateStaticParams");
  });

  it("has no segment-level revalidate, which would claim a cache the segment cannot keep", () => {
    const source = segmentSource();

    expect(source).not.toMatch(/export const revalidate\s*=/);
  });
});

describe("the public URL is the hyphenated one", () => {
  it("rewrites /events-in-:slug into the internal segment", () => {
    // **Next.js has no native prefixed dynamic segment.** `app/events-in-[slug]`
    // registers in `staticRoutes` with the parameter named `nxtPslug`, so the request
    // 404s and no `params.slug` ever arrives. The rewrite is what makes the public URL
    // work at all.
    const source = configSource();

    expect(source).toContain('source: "/events-in-:slug"');
    expect(source).toContain('destination: "/events-in/:slug"');
  });

  it("redirects the internal URL back out, permanently", () => {
    // **The redirect is load-bearing, not cosmetic.** Without it the page is served at
    // two URLs, and a URL that forks after ranking splits the ranking across two
    // copies. A canonical link tag alone does not fix that — a crawler follows links,
    // and the internal URL is a real, reachable, indexable document.
    const source = configSource();

    expect(source).toContain('source: "/events-in/:slug"');
    expect(source).toContain('destination: "/events-in-:slug"');
    expect(source).toContain("permanent: true");
  });

  it("routes through a normal dynamic segment", () => {
    // **The route lives one segment deeper** — `app/events-in/[slug]/page.tsx` — and
    // the prefixed-segment form is *not* used.
    expect(existsSync(path.join(ROOT, "app/events-in/[slug]/page.tsx"))).toBe(true);
    expect(existsSync(path.join(ROOT, "app/events-in-[slug]"))).toBe(false);
  });

  it("reads the page the URL asks for in the metadata too", () => {
    // **The metadata and the document must be about the same page.** If the metadata
    // always read page one, then page two's canonical would name page one — and a
    // crawler that believes its canonical drops page two from its index. A paged
    // listing whose later pages are de-indexed is a listing of one page.
    const source = segmentSource();

    expect(source).toContain("searchParams");
    // **The page number is read once and used twice** — once for the canonical and
    // once for the document.
    expect(source.match(/pageNumber\(query\.page\)/g)?.length).toBe(2);
  });

  it("names the site's public origin as its metadataBase", () => {
    // **Without a `metadataBase`, Next resolves a relative OG image against
    // `http://localhost:3000`** — so a share card points its image at a loopback
    // address and renders nothing. The origin lives in the root layout, because it is
    // a property of the site and not of one page.
    const layout = readFileSync(path.join(ROOT, "app/layout.tsx"), "utf8");

    expect(layout).toContain("metadataBase");
    expect(layout).toContain("siteUrl()");
  });

  it("puts the hyphenated form in every link and every canonical", () => {
    // **The internal segment is a routing detail** and never appears in a link, a
    // canonical or an OG URL. The backend only ever names the hyphenated form.
    //
    // **And there is exactly one definition of it.** The page, the route and the read's
    // cache tag all build the city's address from `cityPath`, so a link and a tag can
    // never disagree about where a city lives — and the string the read tags with is
    // the string the backend's signal names.
    const page = readFileSync(path.join(ROOT, "components/city-page/city-page.tsx"), "utf8");
    const route = segmentSource();
    const read = readSource();

    expect(page).toContain("cityPageHref(");
    expect(page).not.toContain('"/events-in/');
    expect(route).toContain("cityPageHref(");
    expect(read).toContain("return `/events-in-${slug}`");
  });
});

describe("the city page's caching lives in the data cache", () => {
  it("caches the read, tagged with the city's own path", () => {
    // **The tag is the contract with the backend's revalidation signal.**
    // `domain/revalidation.py` builds `f"{CITY_PATH_PREFIX}{slug}"` — and
    // `CITY_PATH_PREFIX` is `"/events-in-"` — and the `/revalidate` handler invalidates
    // that tag with `revalidateTag(path, { expire: 0 })`. A tag that was not the city's
    // own path would be a cache that nothing could ever clear.
    const source = readSource();

    expect(source).toContain("unstable_cache");
    expect(source).toContain("tags: [cityPath(slug)]");
    expect(source).toContain("return `/events-in-${slug}`");
  });

  it("reads no session, so a cached copy can hold nothing personal", () => {
    // **The cached function forwards no cookie header.** A cached public page must be
    // the same for everyone — if the read carried the visitor's cookies, the first
    // requester would bake their session into the cache for every reader after them.
    const source = readSource();

    expect(source).not.toContain("sessionHeaders");
    expect(source).not.toContain("getSession");
    expect(source).not.toContain("cookies(");
  });

  it("caches nothing that is not a payload", () => {
    // **A cached 404 would keep answering 404 for a city that was created later**, and
    // a cached failure would keep answering "we couldn't load this city" for a city
    // that is fine. Both throw out of the cache boundary, so nothing is written.
    const source = readSource();

    expect(source).toContain("throw new CityNotFound(");
    expect(source).toContain("throw new CityUnavailable(");
  });

  it("makes the request inside the cache boundary, so a hit costs no request", () => {
    // **A cache that wraps an already-fetched value caches nothing** — the request has
    // already been paid for. The `api.GET` call has to be inside the cached function.
    const source = readSource();
    const cached = source.slice(source.indexOf("unstable_cache("));

    expect(cached).toContain("api.GET(");
  });

  it("keys the cache on the page, but tags it on the city", () => {
    // **The key carries the page and the tag does not.** The backend's revalidation
    // signal names the city, not the city-and-page, so a per-page tag would leave
    // page 2 serving a stale listing after page 1 was invalidated.
    const source = readSource();

    expect(source).toContain('["city-page", slug, String(requested)]');
    expect(source).toContain("tags: [cityPath(slug)]");
  });
});

describe("the route reads the backend only through the generated client", () => {
  it("never calls fetch()", () => {
    // **AD-19.** The frontend reaches the backend only through `lib/backend-client.ts`.
    const source = readSource();

    expect(source).not.toContain("fetch(");
    expect(source).toContain('api.GET("/api/catalog/cities/by-slug/{slug}"');
  });
});
