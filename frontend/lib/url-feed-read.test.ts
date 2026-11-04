import { afterAll, beforeEach, describe, expect, it, vi } from "vitest";

import {
  normalizePage,
  readUrlFeed,
  readUrlFeedRange,
  URL_FEED_PAGE_SIZE,
} from "@/lib/url-feed-read";

/**
 * The public URL feed's server-side read.
 *
 * **The property this file exists to defend is the absence of a session.** The feed is
 * the sitemap's source, fetched by crawlers with no account and no cookie, and the facts
 * are cached under one tag for every reader — so the first requester would bake their
 * session into the cache for everyone after them. So the read carries **no cookie
 * header**, and that is asserted here rather than assumed.
 *
 * **The three answers are three answers.** `found` is the feed. `not-found` is the
 * backend's 404 — a fact about the world. `unavailable` is a failure to answer — a fact
 * about us. Folding the last two together would either put a wrong "this site has no
 * pages" into a search index or serve a broken sitemap as if it were the truth.
 *
 * **The slicing is the other half.** The sitemap's children partition the feed, so a
 * range that overlapped wrongly would put a URL on two children or on none — and either
 * is a sitemap that lies about the site.
 */

const GET = vi.fn();
const cookies = vi.fn();
const unstableCache = vi.fn();

/**
 * The failure log.
 *
 * **A 404 is not a failure and must not be logged.** A crawler walking old links produces
 * not-founds constantly, and a log line for each of them is a log nobody reads.
 */
const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

/**
 * **The spy is restored when the file is done.** A mocked `console.error` that outlives its
 * suite silences the runtime's own diagnostics for every test that runs after it.
 */
afterAll(() => {
  consoleError.mockRestore();
});

vi.mock("@/lib/backend-client", () => ({
  api: { GET: (...args: unknown[]) => GET(...args) },
}));

vi.mock("next/headers", () => ({
  cookies: () => cookies(),
}));

/**
 * The mock cache's store — a real one, so the caching claims are real.
 *
 * **A pass-through mock would make every caching test vacuous.** It would "prove" that a
 * 404 is not cached by observing that the mock never caches anything — which is true of
 * any implementation whatsoever, including one that caches the 404.
 *
 * **So the mock behaves like the real thing in the two ways that matter:**
 *
 * - a **resolved** value is stored under its key, and a later call with the same key
 *   returns the stored value **without calling the wrapped function again**;
 * - a **thrown** value stores nothing — which is exactly how `unstable_cache` behaves
 *   (Next's `cacheNewResult` is only reached after the wrapped function resolves), and
 *   it is the behaviour the 404 and 500 paths depend on.
 */
const cacheStore = new Map<string, unknown>();

vi.mock("next/cache", () => ({
  unstable_cache: (fn: (...args: unknown[]) => unknown, key: unknown[], options?: unknown) => {
    unstableCache(key, options);
    const cacheKey = JSON.stringify(key);
    return async (...args: unknown[]) => {
      if (cacheStore.has(cacheKey)) return cacheStore.get(cacheKey);
      // **A throw stores nothing** — and the throw propagates, so the caller sees it.
      const value = await fn(...args);
      cacheStore.set(cacheKey, value);
      return value;
    };
  },
}));

/** One feed entry, in the shape the backend sends it. */
function entry(index: number) {
  return {
    kind: "event" as const,
    last_modified: "2026-08-20T09:14:00Z",
    path: `/events/slug-${index}`,
  };
}

/** A feed page, in the shape the backend sends it. */
function feed(count: number, overrides: Record<string, unknown> = {}): Record<string, unknown> {
  return {
    has_next: false,
    items: Array.from({ length: count }, (_, index) => entry(index)),
    page: 1,
    page_size: URL_FEED_PAGE_SIZE,
    total: count,
    ...overrides,
  };
}

beforeEach(() => {
  GET.mockReset();
  cookies.mockReset();
  unstableCache.mockReset();
  consoleError.mockReset();
  // **The cache is cleared between tests**, so one test's cached entry cannot answer
  // another's read.
  cacheStore.clear();
  cookies.mockResolvedValue(new Map());
});

describe("readUrlFeed", () => {
  it("reads the feed through the generated client", async () => {
    GET.mockResolvedValue({ data: feed(3), response: { status: 200 } });

    await readUrlFeed(1);

    expect(GET).toHaveBeenCalledWith("/api/catalog/url-feed", {
      params: { query: { page: 1, page_size: URL_FEED_PAGE_SIZE } },
    });
  });

  it("carries no cookie header — the feed must not depend on who is asking", async () => {
    GET.mockResolvedValue({ data: feed(3), response: { status: 200 } });

    await readUrlFeed(1);

    // **The whole claim in one assertion.** If the read forwarded a session, the cached
    // feed's content would be the first requester's session, and a Request-time API in
    // this module would opt the whole route out of static generation.
    expect(GET.mock.calls[0]?.[1]).not.toHaveProperty("headers");
  });

  it("never reads the request's cookies at all", async () => {
    GET.mockResolvedValue({ data: feed(3), response: { status: 200 } });

    await readUrlFeed(1);

    // **Not even to forward them.** A module that called `cookies()` and then chose not
    // to send the header would still have opted the route out of static generation.
    expect(cookies).not.toHaveBeenCalled();
  });

  it("returns the feed for a 200", async () => {
    GET.mockResolvedValue({ data: feed(3), response: { status: 200 } });

    const read = await readUrlFeed(1);

    expect(read.kind).toBe("found");
    if (read.kind !== "found") throw new Error("expected the found branch");
    expect(read.page.items).toHaveLength(3);
    expect(read.page.total).toBe(3);
  });

  it("returns not-found for a 404", async () => {
    GET.mockResolvedValue({
      data: undefined,
      error: { code: "not_found", message: "We couldn't find that feed.", details: null },
      response: { status: 404 },
    });

    const read = await readUrlFeed(1);

    expect(read.kind).toBe("not-found");
    if (read.kind !== "not-found") throw new Error("expected the not-found branch");
    // **The backend's own code**, carried through and not invented.
    expect(read.code).toBe("not_found");
  });

  it("returns unavailable when the request throws", async () => {
    GET.mockRejectedValue(new Error("the network is down"));

    const read = await readUrlFeed(1);

    expect(read.kind).toBe("unavailable");
  });

  it("returns unavailable for a 500 — a failure to answer is not an answer", async () => {
    GET.mockResolvedValue({ data: undefined, response: { status: 500 } });

    const read = await readUrlFeed(1);

    expect(read.kind).toBe("unavailable");
  });

  it("returns unavailable when a 200 carries no payload", async () => {
    GET.mockResolvedValue({ data: undefined, response: { status: 200 } });

    const read = await readUrlFeed(1);

    expect(read.kind).toBe("unavailable");
  });

  it("does not log a 404 — a fact about the world is not a fault", async () => {
    GET.mockResolvedValue({
      data: undefined,
      error: { code: "not_found", message: "We couldn't find that feed.", details: null },
      response: { status: 404 },
    });

    await readUrlFeed(1);

    expect(consoleError).not.toHaveBeenCalled();
  });

  it("logs a failure to answer, so a fault is not silent", async () => {
    GET.mockRejectedValue(new Error("the network is down"));

    await readUrlFeed(1);

    // **The type and the message, and nothing else.** No session, no cookie, no request
    // body — a public path is not a secret, but a log line that carries one is a log
    // line that has to be scrubbed.
    expect(consoleError).toHaveBeenCalledTimes(1);
    const [message, detail] = consoleError.mock.calls[0] as [
      string,
      { type: string; message: string },
    ];
    expect(message).toContain("feed read could not answer");
    expect(detail.type).toBe("Error");
    expect(detail.message).toBe("the network is down");
  });

  it("names the status the API answered with", async () => {
    // **"The API answered 500" and "the request threw" are different faults**, and a
    // log that cannot tell them apart is a log that sends you to the wrong place.
    GET.mockResolvedValue({ data: undefined, response: { status: 500 } });

    await readUrlFeed(1);

    const [, detail] = consoleError.mock.calls[0] as [string, { message: string; status: number }];
    expect(detail.message).toBe("the API answered 500");
    expect(detail.status).toBe(500);
  });

  /* ── the caching ──────────────────────────────────────────────────────────── */

  it("caches a found answer — the second read does not ask again", async () => {
    GET.mockResolvedValue({ data: feed(3), response: { status: 200 } });

    await readUrlFeed(1);
    await readUrlFeed(1);

    expect(GET).toHaveBeenCalledTimes(1);
  });

  it("does not cache a 404 — a feed deployed later would stay a 404", async () => {
    GET.mockResolvedValue({
      data: undefined,
      error: { code: "not_found", message: "We couldn't find that feed.", details: null },
      response: { status: 404 },
    });

    await readUrlFeed(1);
    await readUrlFeed(1);

    // **A cached 404 would keep answering 404 for a feed that was deployed later.**
    expect(GET).toHaveBeenCalledTimes(2);
  });

  it("does not cache a failure — a feed that recovers must not stay broken", async () => {
    GET.mockResolvedValue({ data: undefined, response: { status: 500 } });

    await readUrlFeed(1);
    await readUrlFeed(1);

    expect(GET).toHaveBeenCalledTimes(2);
  });

  it("keys the cache by the page, so two pages do not share an entry", async () => {
    GET.mockResolvedValue({ data: feed(3), response: { status: 200 } });

    await readUrlFeed(1);
    await readUrlFeed(2);

    expect(GET).toHaveBeenCalledTimes(2);
    expect(GET.mock.calls[1]?.[1]).toMatchObject({ params: { query: { page: 2 } } });
  });

  it("tags the cache with the sitemap's own path, so one signal clears every page", async () => {
    GET.mockResolvedValue({ data: feed(3), response: { status: 200 } });

    await readUrlFeed(1);

    expect(unstableCache).toHaveBeenCalledWith(
      ["url-feed", "1"],
      expect.objectContaining({ tags: ["/sitemap.xml"] }),
    );
  });
});

describe("normalizePage", () => {
  it("keeps a page the backend will accept", () => {
    expect(normalizePage(3)).toBe(3);
  });

  it("turns a page below one into the first page", () => {
    // **The backend refuses a page below one with a 422**, and this is where that
    // refusal is turned into an answer instead of an error.
    expect(normalizePage(0)).toBe(1);
    expect(normalizePage(-5)).toBe(1);
  });

  it("turns a page that is not a number into the first page", () => {
    expect(normalizePage(Number.NaN)).toBe(1);
    expect(normalizePage(Number.POSITIVE_INFINITY)).toBe(1);
  });

  it("turns a page a float cannot hold into the first page", () => {
    // **One printed in scientific notation** — `1e+23` — which the backend's `page: int`
    // **refuses with a 422**. So a page number has to be an integer a person could
    // write.
    expect(normalizePage(1e23)).toBe(1);
  });
});

describe("readUrlFeedRange", () => {
  it("returns the run of URLs the range names", async () => {
    GET.mockResolvedValue({
      data: feed(5, { items: Array.from({ length: 5 }, (_, index) => entry(index)) }),
      response: { status: 200 },
    });

    const read = await readUrlFeedRange(1, 3);

    expect(read.kind).toBe("found");
    if (read.kind !== "found") throw new Error("expected the found branch");
    expect(read.page.items.map((item) => item.path)).toEqual([
      "/events/slug-1",
      "/events/slug-2",
      "/events/slug-3",
    ]);
  });

  it("reads only the pages that overlap the run", async () => {
    // **A run inside one feed page is one request.** The feed's page is 1,000 URLs, so
    // a 50-URL run inside the first page must not fetch fifty pages.
    GET.mockResolvedValue({ data: feed(3), response: { status: 200 } });

    await readUrlFeedRange(0, 2);

    expect(GET).toHaveBeenCalledTimes(1);
  });

  it("returns an empty run without asking for anything", async () => {
    GET.mockResolvedValue({ data: feed(3), response: { status: 200 } });

    const read = await readUrlFeedRange(0, 0);

    expect(read.kind).toBe("found");
    if (read.kind !== "found") throw new Error("expected the found branch");
    expect(read.page.items).toEqual([]);
  });

  it("hands a failure up rather than returning a partial range", async () => {
    GET.mockResolvedValue({ data: undefined, response: { status: 500 } });

    const read = await readUrlFeedRange(0, 10);

    expect(read.kind).toBe("unavailable");
  });

  it("reports the feed's size, not the size of the pages it walked", async () => {
    // **This is what lets a caller answer "is my slice inside the feed?" from this one
    // read.** The child sitemap asks whether the index names it, and it asks using this
    // number — so the number has to be the catalog's size even when the walk stopped
    // early because the catalog is shorter than the run asked for.
    GET.mockResolvedValue({
      data: feed(3, { total: 3 }),
      response: { status: 200 },
    });

    const read = await readUrlFeedRange(0, 50_000);

    expect(read.kind).toBe("found");
    if (read.kind !== "found") throw new Error("expected the found branch");
    expect(read.page.total).toBe(3);
  });
});
