// @vitest-environment node
/**
 * The public event page's *rendering* properties — the ones a DOM test cannot see.
 *
 * **This file exists because the two hardest properties of this route are not
 * properties of the rendered tree.** They are properties of *where the render sits in
 * Next's machinery*, and the only way to assert on them is to read the source:
 *
 *   1. **The public branch must not sit under a Suspense boundary.** Next's rule is
 *      exact: "To return a real `404` status, the resource has to be checked before the
 *      response streams." A Suspense boundary *above* the page streams its fallback
 *      first, and once the response has streamed the status can no longer be set — so
 *      the public branch's `notFound()` would answer **200**. That is a soft 404, and
 *      a soft 404 is a URL a crawler records as a page that exists.
 *   2. **The segment must be dynamic, and the public page's caching must live in the
 *      data cache.** A segment has one rendering mode. The segment also serves the
 *      personal Detail Screen, which reads cookies — so the segment is dynamic, the
 *      page is never in the Full Route Cache, and the public page's caching is the
 *      *facts'* caching.
 *
 * **Both were measured against a running production server, and both failed first.**
 * With a segment-level `loading.tsx`, the unknown slug answered 200. With the segment
 * registered as prerenderable, *both* branches answered 500 — Next's own runtime
 * throws "Page changed from static to dynamic at runtime". A unit test calls the page
 * function directly and sees neither.
 *
 * **So these are asserted on the source** — the same house pattern as
 * `tests/event-detail-boundary.test.ts` and `tests/digest-home-boundary.test.ts`.
 */
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

const ROOT = path.resolve(__dirname, "..");

/** The route segment's own source, with its comments removed. */
function segmentSource(): string {
  const source = readFileSync(path.join(ROOT, "app/events/[id]/page.tsx"), "utf8");
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
}

/** The read module's own source, with its comments removed. */
function readSource(): string {
  const source = readFileSync(path.join(ROOT, "lib/public-event-read.ts"), "utf8");
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/\/\/[^\n]*/g, "");
}

describe("the segment has no boundary above the public branch", () => {
  it("has no loading.tsx", () => {
    // **A `loading.tsx` is a Suspense boundary above the page.** It is the one thing
    // that turns the public branch's real 404 into a soft 404. The Detail Screen's
    // skeleton moved *into* the page for exactly this reason.
    expect(existsSync(path.join(ROOT, "app/events/[id]/loading.tsx"))).toBe(false);
  });

  it("wraps only the detail branch in a Suspense boundary", () => {
    // **The boundary is below the public branch's `notFound()` call site.** The public
    // branch is returned directly, so it is never inside a pending subtree; the detail
    // branch goes inside the boundary, where the skeleton is its fallback.
    const source = segmentSource();

    expect(source).toContain("Suspense");
    // The public branch's return is *not* wrapped.
    expect(source).toContain("return await PublicEventBranch(id);");
    // And the detail branch is.
    expect(source).toContain("<Suspense fallback={<DetailLoading />}>");
  });

  it("keeps the public branch's own notFound() in the render path", () => {
    // **The 404 is raised before anything streams.** `notFound()` is called inside
    // `PublicEventBranch`, which the page awaits — so the throw happens while the
    // page is still rendering, not after.
    const source = segmentSource();

    expect(source).toContain("notFound()");
    expect(source).toContain('read.kind === "not-found"');
  });
});

describe("the segment's rendering mode", () => {
  it("is dynamic — one segment cannot be both", () => {
    // **The segment also serves the personal Detail Screen, which reads cookies.**
    // A prerendered segment cannot run `cookies()`, and Next throws "Page changed from
    // static to dynamic at runtime" when a registered route bails to dynamic — which
    // 500s both branches.
    const source = segmentSource();

    expect(source).toContain('export const dynamic = "force-dynamic"');
  });

  it("registers no static params, so no path is claimed to be prerenderable", () => {
    // **`generateStaticParams` returning `[]` registers the route as prerenderable**,
    // which is what makes the runtime throw. The slugs are minted at runtime and a
    // build machine cannot know them, so there is nothing to register.
    const source = segmentSource();

    expect(source).not.toContain("generateStaticParams");
  });

  it("has no segment-level revalidate, which would claim a cache the segment cannot keep", () => {
    const source = segmentSource();

    expect(source).not.toMatch(/export const revalidate\s*=/);
  });
});

describe("the public page's caching lives in the data cache", () => {
  it("caches the read, tagged with the event's own path", () => {
    // **The tag is the contract with the backend's revalidation signal.**
    // `domain/revalidation.py` builds `f"{EVENT_PATH_PREFIX}{self.slug}"` and the
    // `/revalidate` handler invalidates that tag. A tag that was not the event's own
    // path would be a cache that nothing could ever clear.
    const source = readSource();

    expect(source).toContain("unstable_cache");
    expect(source).toContain("tags: [eventPath(slug)]");
    expect(source).toContain("return `/events/${slug}`");
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
    // **A cached 404 would keep answering 404 for an event that was republished**, and
    // a cached failure would keep answering "we couldn't load this event" for an event
    // that is fine. Both throw out of the cache boundary, so nothing is written.
    const source = readSource();

    expect(source).toContain("throw new PublicEventNotFound(");
    expect(source).toContain("throw new PublicEventUnavailable(");
  });

  it("makes the request inside the cache boundary, so a hit costs no request", () => {
    // **A cache that wraps an already-fetched value caches nothing** — the request has
    // already been paid for. The `api.GET` call has to be inside the cached function.
    //
    // **The assertion is on the cached function's own text**, which is the slice that
    // starts at `unstable_cache(` — so a request made *before* the boundary would not
    // be in it, and the assertion would fail.
    const source = readSource();
    const cached = source.slice(source.indexOf("unstable_cache("));

    expect(cached).toContain("api.GET(");
  });
});

describe("the revalidation handler clears both caches", () => {
  it("invalidates the path and the tag", () => {
    // **Two caches, one signal.** The *page* lives in the Full Route Cache and the
    // *facts* live in the data cache; a signal that cleared only one of them would
    // leave a stale answer on one of them.
    const source = readFileSync(path.join(ROOT, "app/revalidate/route.ts"), "utf8");

    expect(source).toContain("revalidatePath(path)");
    expect(source).toContain("revalidateTag(path");
  });
});
