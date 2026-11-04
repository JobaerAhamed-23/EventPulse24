import { afterAll, beforeEach, describe, expect, it, vi } from "vitest";

import { cityPageHref, cityPath, normalizePage, readCityPage } from "@/lib/city-page-read";

/**
 * The public city page's server-side read.
 *
 * **The property this file exists to defend is the absence of a session.** A public read
 * that forwarded the visitor's cookies would make the page's content depend on who is
 * asking — and the facts are cached under one tag for every reader, so the first
 * requester would bake their session into the cache for everyone after them. So the read
 * carries **no cookie header**, and that is asserted here rather than assumed.
 *
 * **The three answers are three answers.** `found` is the page. `not-found` is the
 * backend's 404 — a fact about the world. `unavailable` is a failure to answer — a fact
 * about us. Folding the last two together would either put a wrong "this city does not
 * exist" into a search index or serve a broken page as if it were the truth.
 *
 * **The caching is the other half.** The load-bearing claim of this module is *"only a
 * found answer is cached"* — a cached 404 would keep answering 404 for a city that was
 * created later, and a cached failure would keep answering "we could not load this" for a
 * city that is perfectly fine.
 */

const GET = vi.fn();
const cookies = vi.fn();
const unstableCache = vi.fn();

/**
 * The failure log.
 *
 * **A 404 is not a failure and must not be logged.** A crawler walking old links produces
 * not-founds constantly, and a log line for each of them is a log nobody reads. A
 * *failure to answer* is us failing, and it has to leave a trace.
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

const SLUG = "brooklyn";

/** The payload the catalog's city read returns. */
function page(overrides: Record<string, unknown> = {}) {
  return {
    country_code: "US",
    event_count: 12,
    has_next: false,
    is_published: true,
    items: [],
    name: "Brooklyn",
    page: 1,
    page_size: 20,
    region: "NY",
    slug: SLUG,
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

describe("readCityPage", () => {
  it("reads the city by its slug", async () => {
    GET.mockResolvedValue({ data: page(), response: { status: 200 } });

    await readCityPage(SLUG, 1);

    expect(GET).toHaveBeenCalledWith("/api/catalog/cities/by-slug/{slug}", {
      params: { path: { slug: SLUG }, query: { page: 1 } },
    });
  });

  it("carries no cookie header — the page must not depend on who is asking", async () => {
    GET.mockResolvedValue({ data: page(), response: { status: 200 } });

    await readCityPage(SLUG, 1);

    // **The whole claim in one assertion.** If the read forwarded a session, the cached
    // page's content would be the first requester's session, and a Request-time API in
    // this module would opt the whole route out of static generation.
    expect(GET.mock.calls[0]?.[1]).not.toHaveProperty("headers");
  });

  it("never reads the request's cookies at all", async () => {
    GET.mockResolvedValue({ data: page(), response: { status: 200 } });

    await readCityPage(SLUG, 1);

    // **Not even to forward them.** A module that called `cookies()` and then chose not
    // to send the header would still have opted the route out of static generation —
    // and the call is the thing that matters, not the header.
    expect(cookies).not.toHaveBeenCalled();
  });

  it("returns the page for a 200", async () => {
    GET.mockResolvedValue({ data: page(), response: { status: 200 } });

    const read = await readCityPage(SLUG, 1);

    expect(read.kind).toBe("found");
    if (read.kind !== "found") throw new Error("expected the found branch");
    expect(read.page.name).toBe("Brooklyn");
    expect(read.page.is_published).toBe(true);
  });

  it("returns a sparse city as a found page, not as a not-found", async () => {
    // **A quiet city is a real city whose page is not published yet.** The backend
    // answers 200 with `is_published: false`, and the page renders "coming soon". If the
    // read folded this into the not-found branch, the city would 404 — and a URL that
    // vanishes after ranking throws away every bit of ranking it earned.
    GET.mockResolvedValue({
      data: page({ is_published: false, event_count: 2 }),
      response: { status: 200 },
    });

    const read = await readCityPage(SLUG, 1);

    expect(read.kind).toBe("found");
    if (read.kind !== "found") throw new Error("expected the found branch");
    expect(read.page.is_published).toBe(false);
    expect(read.page.event_count).toBe(2);
  });

  it("returns not-found for a 404", async () => {
    GET.mockResolvedValue({
      data: undefined,
      error: { code: "not_found", message: "We couldn't find that city.", details: null },
      response: { status: 404 },
    });

    const read = await readCityPage(SLUG, 1);

    expect(read.kind).toBe("not-found");
    if (read.kind !== "not-found") throw new Error("expected the not-found branch");
    // **The backend's own code**, carried through and not invented: the city read
    // raises `CityNotFoundError`, whose code is `"not_found"`.
    expect(read.code).toBe("not_found");
  });

  it("returns unavailable when the request throws", async () => {
    GET.mockRejectedValue(new Error("the network is down"));

    const read = await readCityPage(SLUG, 1);

    expect(read.kind).toBe("unavailable");
  });

  it("returns unavailable for a 500 — a failure to answer is not an answer", async () => {
    GET.mockResolvedValue({ data: undefined, response: { status: 500 } });

    const read = await readCityPage(SLUG, 1);

    expect(read.kind).toBe("unavailable");
  });

  it("returns unavailable when a 200 carries no payload", async () => {
    GET.mockResolvedValue({ data: undefined, response: { status: 200 } });

    const read = await readCityPage(SLUG, 1);

    expect(read.kind).toBe("unavailable");
  });

  /* ── the failure log ──────────────────────────────────────────────────────── */

  it("logs a failure to answer, so a fault is not silent", async () => {
    GET.mockRejectedValue(new Error("the network is down"));

    await readCityPage(SLUG, 1);

    // **The type and the message, and nothing else.** No session, no cookie, no request
    // body — a public slug is not a secret, but a log line that carries one is a log
    // line that has to be scrubbed.
    expect(consoleError).toHaveBeenCalledTimes(1);
    const [message, detail] = consoleError.mock.calls[0] as [
      string,
      { type: string; message: string },
    ];
    expect(message).toContain("city read could not answer");
    expect(detail.type).toBe("Error");
    expect(detail.message).toBe("the network is down");
  });

  it("names the status the API answered with", async () => {
    // **"The API answered 500" and "the request threw" are different faults**, and a
    // log that cannot tell them apart is a log that sends you to the wrong place.
    GET.mockResolvedValue({ data: undefined, response: { status: 500 } });

    await readCityPage(SLUG, 1);

    const [, detail] = consoleError.mock.calls[0] as [string, { message: string; status: number }];
    expect(detail.message).toBe("the API answered 500");
    expect(detail.status).toBe(500);
  });

  it("names a success that arrived with no payload, which is our own bug", async () => {
    // **A 200 with no body should not happen** — the endpoint declares one — so it is
    // worth saying so in the log rather than letting it read as an upstream 500.
    GET.mockResolvedValue({ data: undefined, response: { status: 200 } });

    await readCityPage(SLUG, 1);

    const [, detail] = consoleError.mock.calls[0] as [
      string,
      { message: string; status: number; emptyBody: boolean },
    ];
    expect(detail.message).toBe("the API answered 200 with no payload");
    expect(detail.emptyBody).toBe(true);
  });

  it("logs nothing for a 404 — a fact about the world, not an incident", async () => {
    GET.mockResolvedValue({
      data: undefined,
      error: { code: "not_found", message: "We couldn't find that city.", details: null },
      response: { status: 404 },
    });

    await readCityPage(SLUG, 1);

    expect(consoleError).not.toHaveBeenCalled();
  });

  it("logs nothing for a successful read", async () => {
    GET.mockResolvedValue({ data: page(), response: { status: 200 } });

    await readCityPage(SLUG, 1);

    expect(consoleError).not.toHaveBeenCalled();
  });

  /* ── the cache ────────────────────────────────────────────────────────────── */

  it("caches the read under the city's own path", async () => {
    GET.mockResolvedValue({ data: page(), response: { status: 200 } });

    await readCityPage(SLUG, 1);

    // **The tag is the contract with the backend's revalidation signal.**
    // `domain/revalidation.py` builds `f"{CITY_PATH_PREFIX}{slug}"`, and the
    // `/revalidate` handler invalidates that tag with `revalidateTag(path,
    // { expire: 0 })`. A tag that was not the city's own path would be a cache nothing
    // could ever clear.
    const options = unstableCache.mock.calls[0]?.[1] as { tags?: string[] } | undefined;
    expect(options?.tags).toEqual([`/events-in-${SLUG}`]);
  });

  it("keys the cache on the slug and the page, so two cities do not share an entry", async () => {
    GET.mockResolvedValue({ data: page(), response: { status: 200 } });

    await readCityPage(SLUG, 1);
    await readCityPage("manhattan", 1);

    const first = unstableCache.mock.calls[0]?.[0] as string[] | undefined;
    const second = unstableCache.mock.calls[1]?.[0] as string[] | undefined;

    // **The key carries the slug and the page.** Two cities, or two pages of one city,
    // are different facts and must not share an entry — a shared key would serve one
    // city's events under another city's URL.
    expect(first).toEqual(["city-page", SLUG, "1"]);
    expect(second).toEqual(["city-page", "manhattan", "1"]);
  });

  it("tags every page of a city with the same tag, so one signal clears them all", async () => {
    GET.mockResolvedValue({ data: page(), response: { status: 200 } });

    await readCityPage(SLUG, 1);
    await readCityPage(SLUG, 2);

    const first = unstableCache.mock.calls[0]?.[1] as { tags?: string[] } | undefined;
    const second = unstableCache.mock.calls[1]?.[1] as { tags?: string[] } | undefined;

    // **The key carries the page; the tag does not.** The backend's revalidation signal
    // names the city, not the city-and-page, so a per-page tag would leave page 2
    // serving a stale listing after page 1 was invalidated.
    expect(first?.tags).toEqual([`/events-in-${SLUG}`]);
    expect(second?.tags).toEqual([`/events-in-${SLUG}`]);
  });

  it("caches nothing when the city does not exist", async () => {
    // **A cached 404 is the failure mode this design exists to avoid.** It would keep
    // answering 404 for a city that was created later, and the backend's own signal —
    // which invalidates the tag — would never fire for a city the backend did not know
    // about when the tag was set.
    //
    // **The assertion is against a cache that actually caches.** The mock stores a
    // resolved value and stores nothing for a throw; so if the 404 were returned rather
    // than thrown, it would be stored, and the second read would be served from the
    // cache with **one** request. The test asserts **two** — which is only true because
    // nothing was written.
    GET.mockResolvedValue({
      data: undefined,
      error: { code: "not_found", message: "We couldn't find that city.", details: null },
      response: { status: 404 },
    });

    const first = await readCityPage(SLUG, 1);
    const second = await readCityPage(SLUG, 1);

    expect(first.kind).toBe("not-found");
    expect(second.kind).toBe("not-found");
    // Two reads, two requests — the second one was not served from a cache.
    expect(GET).toHaveBeenCalledTimes(2);
  });

  it("caches nothing when the read could not answer", async () => {
    // **A cached failure is the same failure with a longer life.** "We couldn't load
    // this city" would be served from the cache for a city that is perfectly fine.
    GET.mockResolvedValue({ data: undefined, response: { status: 500 } });

    const first = await readCityPage(SLUG, 1);
    const second = await readCityPage(SLUG, 1);

    expect(first.kind).toBe("unavailable");
    expect(second.kind).toBe("unavailable");
    expect(GET).toHaveBeenCalledTimes(2);
  });

  it("caches the found answer, so a second read costs no request", async () => {
    // **This is the assertion that makes the other two meaningful.** A cache that
    // caches nothing would also pass "a 404 is not cached" — so the cache has to be
    // shown to work *before* its absence can be read as a decision.
    GET.mockResolvedValue({ data: page(), response: { status: 200 } });

    const first = await readCityPage(SLUG, 1);
    const second = await readCityPage(SLUG, 1);

    expect(first.kind).toBe("found");
    expect(second.kind).toBe("found");
    expect(second).toEqual(first);
    // **One request for two reads.** The second was served from the cache.
    expect(GET).toHaveBeenCalledTimes(1);
  });

  it("serves a city created later, because the 404 was never cached", async () => {
    // **The scenario the non-caching exists for.** A slug names no city, a reader
    // arrives and gets a 404 — and then the city is created. The next reader must get
    // the page, not the cached 404.
    GET.mockResolvedValueOnce({
      data: undefined,
      error: { code: "not_found", message: "We couldn't find that city.", details: null },
      response: { status: 404 },
    });
    GET.mockResolvedValue({ data: page(), response: { status: 200 } });

    const first = await readCityPage(SLUG, 1);
    const second = await readCityPage(SLUG, 1);

    expect(first.kind).toBe("not-found");
    expect(second.kind).toBe("found");
  });

  it("caches each page of a city separately", async () => {
    // **Two pages are two facts.** If they shared an entry, page 2 would render page
    // 1's events — and the "next page" link would loop forever on the same listing.
    GET.mockResolvedValue({ data: page({ page: 1 }), response: { status: 200 } });

    await readCityPage(SLUG, 1);
    await readCityPage(SLUG, 2);

    expect(GET).toHaveBeenCalledTimes(2);
  });

  /* ── the page number ──────────────────────────────────────────────────────── */

  it("clamps a page below one to the first page, rather than provoking a 422", async () => {
    // **The backend refuses `page < 1` with a 422** — it treats an out-of-range request
    // as a mistake. A crawler's `?page=0` is not a mistake to be answered with an
    // error; it is a request for the first page.
    GET.mockResolvedValue({ data: page(), response: { status: 200 } });

    await readCityPage(SLUG, 0);

    expect(GET).toHaveBeenCalledWith("/api/catalog/cities/by-slug/{slug}", {
      params: { path: { slug: SLUG }, query: { page: 1 } },
    });
  });

  it("never sends a page size — the endpoint's own default is the right one", async () => {
    GET.mockResolvedValue({ data: page(), response: { status: 200 } });

    await readCityPage(SLUG, 1);

    // **`page_size` is not the frontend's to choose.** The endpoint's default is the
    // listing's own page size; sending a different one would make the backend's
    // `has_next` mean something the page does not.
    const [, options] = GET.mock.calls[0] as [
      string,
      { params: { query: Record<string, unknown> } },
    ];
    expect(options.params.query).not.toHaveProperty("page_size");
  });
});

describe("normalizePage", () => {
  it("keeps a page that is already fine", () => {
    expect(normalizePage(1)).toBe(1);
    expect(normalizePage(7)).toBe(7);
  });

  it("clamps a page below one", () => {
    expect(normalizePage(0)).toBe(1);
    expect(normalizePage(-3)).toBe(1);
  });

  it("treats a page that is not a number as the first page", () => {
    // **`?page=abc` is the same case as `?page=0`.** The reader meant the first page.
    expect(normalizePage(Number.NaN)).toBe(1);
    expect(normalizePage(Number.POSITIVE_INFINITY)).toBe(1);
  });

  it("drops a fractional page, because a page is a whole number of pages", () => {
    expect(normalizePage(2.7)).toBe(2);
  });

  it("treats a page too large to write as the first page", () => {
    // **A float cannot hold every integer past 2^53**, and one it cannot hold is
    // printed in scientific notation — `1e+23` — which is not an integer the backend
    // will accept. It would come back a 422, and a 422 is "unavailable".
    expect(normalizePage(1e23)).toBe(1);
    expect(normalizePage(Number.MAX_VALUE)).toBe(1);
  });

  it("keeps an ordinary large page number", () => {
    // **The guard is not "small numbers only."** A page a person could write is kept,
    // however large — a page past the end is an ordinary answer.
    expect(normalizePage(5000)).toBe(5000);
    expect(normalizePage(Number.MAX_SAFE_INTEGER)).toBe(Number.MAX_SAFE_INTEGER);
  });
});

describe("the city's own URL", () => {
  it("is the hyphenated form, because that is the form the backend names", () => {
    // **`domain/revalidation.py` builds `f"{CITY_PATH_PREFIX}{slug}"`** with
    // `CITY_PATH_PREFIX = "/events-in-"` — and the cache tag, the canonical link, the
    // OG URL and the paging links are all the same string. One definition, one form.
    expect(cityPath(SLUG)).toBe("/events-in-brooklyn");
  });

  it("gives page one no query, because a page must not be two URLs", () => {
    // **`?page=1` would be the same page at two addresses**, and a page that forks
    // after ranking splits the ranking across the two copies.
    expect(cityPageHref(SLUG, 1)).toBe("/events-in-brooklyn");
    expect(cityPageHref(SLUG, 0)).toBe("/events-in-brooklyn");
  });

  it("gives a later page its number", () => {
    expect(cityPageHref(SLUG, 2)).toBe("/events-in-brooklyn?page=2");
    expect(cityPageHref(SLUG, 17)).toBe("/events-in-brooklyn?page=17");
  });
});
