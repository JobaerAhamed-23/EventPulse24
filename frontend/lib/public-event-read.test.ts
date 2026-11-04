import { afterAll, beforeEach, describe, expect, it, vi } from "vitest";

import { readPublicEvent } from "@/lib/public-event-read";

/**
 * The public event page's server-side read.
 *
 * **The property this file exists to defend is the absence of a session.** A public read
 * that forwarded the visitor's cookies would make the page's content depend on who is
 * asking — and a statically generated page is served to everyone, so the first requester
 * would bake their session into the cache for every reader after them. So the read
 * carries **no cookie header**, and that is asserted here rather than assumed.
 *
 * **The three answers are three answers.** `found` is the page. `not-found` is the
 * backend's 404 — a fact about the world. `unavailable` is a failure to answer — a fact
 * about us. Folding the last two together would either put a wrong "this does not
 * exist" into a search index or serve a broken page as if it were the truth.
 */

const GET = vi.fn();
const cookies = vi.fn();
const unstableCache = vi.fn();

/**
 * The failure log.
 *
 * **A 404 is not a failure and must not be logged.** A crawler walking old links
 * produces not-founds constantly, and a log line for each of them is a log nobody
 * reads. A *failure to answer* is us failing, and it has to leave a trace — so the
 * distinction is asserted below rather than assumed.
 */
const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

/**
 * **The spy is restored when the file is done.** A mocked `console.error` that
 * outlives its suite silences the runtime's own diagnostics for every test that runs
 * after it — including failures that would otherwise print a stack.
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
 * **A pass-through mock would make every caching test vacuous.** It would "prove"
 * that a 404 is not cached by observing that the mock never caches anything — which
 * is true of any implementation whatsoever, including one that caches the 404. The
 * load-bearing claim of this work item is *"only a found answer is cached"*, and it
 * has to be tested against a cache that actually caches.
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

const SLUG = "designing-for-calm-2026-08-28-a1b2c3";

/** The payload the catalog's public read returns. */
function page(overrides: Record<string, unknown> = {}) {
  return {
    canonical_url: "https://brooklynartscouncil.org/events/calm",
    description: "A short, opinionated panel on building products that respect attention.",
    end_time_utc: null,
    event_version: 3,
    id: "0196c3a4-5b6d-7e8f-9a0b-1c2d3e4f5061",
    is_sold_out: false,
    schema_org: {
      "@context": "https://schema.org",
      "@type": "Event",
      name: "Designing for Calm",
      startDate: "2026-08-28T18:30:00-04:00",
    },
    slug: SLUG,
    source_name: "Brooklyn Arts Council",
    start_time_tz: "America/New_York",
    start_time_utc: "2026-08-28T22:30:00Z",
    status: "published",
    title: "Designing for Calm",
    tz_review_pending: false,
    venue_address: "27 Clinton Ave",
    venue_city: "Brooklyn",
    venue_country_code: "US",
    venue_name: "Brooklyn Arts Council",
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

describe("readPublicEvent", () => {
  it("reads the event by its slug", async () => {
    GET.mockResolvedValue({ data: page(), response: { status: 200 } });

    await readPublicEvent(SLUG);

    expect(GET).toHaveBeenCalledWith("/api/catalog/events/by-slug/{slug}", {
      params: { path: { slug: SLUG } },
    });
  });

  it("carries no cookie header — the page must not depend on who is asking", async () => {
    GET.mockResolvedValue({ data: page(), response: { status: 200 } });

    await readPublicEvent(SLUG);

    // **The whole claim in one assertion.** If the read forwarded a session, the
    // static page's content would be the first requester's session, and a Request-time
    // API in this module would opt the whole route out of static generation.
    expect(GET.mock.calls[0]?.[1]).not.toHaveProperty("headers");
  });

  it("never reads the request's cookies at all", async () => {
    GET.mockResolvedValue({ data: page(), response: { status: 200 } });

    await readPublicEvent(SLUG);

    // **Not even to forward them.** A module that called `cookies()` and then chose
    // not to send the header would still have opted the route out of static
    // generation — and the call is the thing that matters, not the header.
    expect(cookies).not.toHaveBeenCalled();
  });

  it("returns the page for a 200", async () => {
    GET.mockResolvedValue({ data: page(), response: { status: 200 } });

    const read = await readPublicEvent(SLUG);

    expect(read.kind).toBe("found");
    if (read.kind !== "found") throw new Error("expected the found branch");
    expect(read.page.title).toBe("Designing for Calm");
    expect(read.page.schema_org).toEqual(page().schema_org);
  });

  it("returns not-found for a 404", async () => {
    GET.mockResolvedValue({
      data: undefined,
      error: { code: "not_found", message: "We couldn't find that event.", details: null },
      response: { status: 404 },
    });

    const read = await readPublicEvent(SLUG);

    expect(read.kind).toBe("not-found");
    if (read.kind !== "not-found") throw new Error("expected the not-found branch");
    // **The backend's own code**, carried through and not invented: the public read
    // raises `EventNotFoundError`, whose code is `"not_found"`.
    expect(read.code).toBe("not_found");
    expect(read.supersededBySlug).toBeNull();
  });

  it("names the successor when the event was superseded", async () => {
    // A superseded event's page must stop serving, and the reader who wanted *this*
    // event is served by the one that replaced it — so the backend carries the
    // successor's slug in `details`, and the page shows it.
    GET.mockResolvedValue({
      data: undefined,
      error: {
        // **The backend's code is `"not_found"` for every absent event** — unknown
        // slug, unpublished, superseded alike (`EventNotFoundError.code`, inherited
        // from `NotFoundError`). The *reason* travels in `details`, not in the code.
        code: "not_found",
        message: "We couldn't find that event.",
        details: { slug: SLUG, superseded_by_slug: "designing-for-calm-2026-09-02-d4e5f6" },
      },
      response: { status: 404 },
    });

    const read = await readPublicEvent(SLUG);

    expect(read.kind).toBe("not-found");
    if (read.kind !== "not-found") throw new Error("expected the not-found branch");
    expect(read.supersededBySlug).toBe("designing-for-calm-2026-09-02-d4e5f6");
  });

  it("returns unavailable when the request throws", async () => {
    GET.mockRejectedValue(new Error("the network is down"));

    const read = await readPublicEvent(SLUG);

    expect(read.kind).toBe("unavailable");
  });

  it("returns unavailable for a 500 — a failure to answer is not an answer", async () => {
    GET.mockResolvedValue({ data: undefined, response: { status: 500 } });

    const read = await readPublicEvent(SLUG);

    expect(read.kind).toBe("unavailable");
  });

  it("returns unavailable when a 200 carries no payload", async () => {
    GET.mockResolvedValue({ data: undefined, response: { status: 200 } });

    const read = await readPublicEvent(SLUG);

    expect(read.kind).toBe("unavailable");
  });

  /* ── the failure log ──────────────────────────────────────────────────────── */

  it("logs a failure to answer, so a fault is not silent", async () => {
    // **A failure with no trace is a failure nobody can fix.** The read answers
    // "unavailable" and the page says "not right now" — but without a log line, a
    // broken API and a broken page look identical from the outside.
    GET.mockRejectedValue(new Error("the network is down"));

    await readPublicEvent(SLUG);

    // **The type and the message, and nothing else.** No session, no cookie, no
    // request body — a public slug is not a secret, but a log line that carries one
    // is a log line that has to be scrubbed.
    expect(consoleError).toHaveBeenCalledTimes(1);
    const [message, detail] = consoleError.mock.calls[0] as [
      string,
      { type: string; message: string },
    ];
    expect(message).toContain("public read could not answer");
    expect(detail.type).toBe("Error");
    expect(detail.message).toBe("the network is down");
  });

  it("names the status the API answered with", async () => {
    // **"The API answered 500" and "the request threw" are different faults**, and a
    // log that cannot tell them apart is a log that sends you to the wrong place.
    GET.mockResolvedValue({ data: undefined, response: { status: 500 } });

    await readPublicEvent(SLUG);

    const [, detail] = consoleError.mock.calls[0] as [string, { message: string; status: number }];
    expect(detail.message).toBe("the API answered 500");
    expect(detail.status).toBe(500);
  });

  it("names a success that arrived with no payload, which is our own bug", async () => {
    // **A 200 with no body should not happen** — the endpoint declares one — so it is
    // worth saying so in the log rather than letting it read as an upstream 500.
    GET.mockResolvedValue({ data: undefined, response: { status: 200 } });

    await readPublicEvent(SLUG);

    const [, detail] = consoleError.mock.calls[0] as [
      string,
      { message: string; status: number; emptyBody: boolean },
    ];
    expect(detail.message).toBe("the API answered 200 with no payload");
    expect(detail.emptyBody).toBe(true);
  });

  it("logs nothing for a 404 — a fact about the world, not an incident", async () => {
    // **A crawler walking old links produces not-founds constantly.** Logging each of
    // them would bury the real failures in noise, and a 404 is the backend answering
    // correctly, not something going wrong.
    GET.mockResolvedValue({
      data: undefined,
      error: { code: "not_found", message: "We couldn't find that event.", details: null },
      response: { status: 404 },
    });

    await readPublicEvent(SLUG);

    expect(consoleError).not.toHaveBeenCalled();
  });

  it("logs nothing for a successful read", async () => {
    GET.mockResolvedValue({ data: page(), response: { status: 200 } });

    await readPublicEvent(SLUG);

    expect(consoleError).not.toHaveBeenCalled();
  });

  /* ── the cache ────────────────────────────────────────────────────────────── */

  it("caches the read under the event's own path", async () => {
    GET.mockResolvedValue({ data: page(), response: { status: 200 } });

    await readPublicEvent(SLUG);

    // **The tag is the contract with the backend's revalidation signal.**
    // `domain/revalidation.py` builds `f"{EVENT_PATH_PREFIX}{self.slug}"`, and the
    // `/revalidate` handler invalidates that tag. A tag that was not the event's own
    // path would be a cache nothing could ever clear.
    const options = unstableCache.mock.calls[0]?.[1] as { tags?: string[] } | undefined;
    expect(options?.tags).toEqual([`/events/${SLUG}`]);
  });

  it("keys the cache on the slug, so two events do not share an entry", async () => {
    GET.mockResolvedValue({ data: page(), response: { status: 200 } });

    await readPublicEvent(SLUG);
    await readPublicEvent("another-event-2026-08-28-d4e5f6");

    const first = unstableCache.mock.calls[0]?.[0] as string[] | undefined;
    const second = unstableCache.mock.calls[1]?.[0] as string[] | undefined;

    // **The key carries the slug.** Two slugs, two entries — a shared key would serve
    // one event's facts under another event's URL.
    expect(first).toEqual(["public-event", SLUG]);
    expect(second).toEqual(["public-event", "another-event-2026-08-28-d4e5f6"]);
  });

  it("caches nothing when the event is not public", async () => {
    // **A cached 404 is the failure mode this design exists to avoid.** It would keep
    // answering 404 for an event that was republished, and the backend's signal — which
    // invalidates the tag — would never fire for an event the backend no longer
    // publishes.
    //
    // **The assertion is against a cache that actually caches.** The mock stores a
    // resolved value and stores nothing for a throw; so if the 404 were returned
    // rather than thrown, it would be stored, and the second read would be served from
    // the cache with **one** request. The test asserts **two** — which is only true
    // because nothing was written.
    GET.mockResolvedValue({
      data: undefined,
      error: { code: "not_found", message: "We couldn't find that event.", details: null },
      response: { status: 404 },
    });

    const first = await readPublicEvent(SLUG);
    const second = await readPublicEvent(SLUG);

    expect(first.kind).toBe("not-found");
    expect(second.kind).toBe("not-found");
    // Two reads, two requests — the second one was not served from a cache.
    expect(GET).toHaveBeenCalledTimes(2);
  });

  it("caches nothing when the read could not answer", async () => {
    // **A cached failure is the same failure with a longer life.** "We couldn't load
    // this event" would be served from the cache for an event that is perfectly fine.
    GET.mockResolvedValue({ data: undefined, response: { status: 500 } });

    const first = await readPublicEvent(SLUG);
    const second = await readPublicEvent(SLUG);

    expect(first.kind).toBe("unavailable");
    expect(second.kind).toBe("unavailable");
    expect(GET).toHaveBeenCalledTimes(2);
  });

  it("caches the found answer, so a second read costs no request", async () => {
    // **This is the assertion that makes the other two meaningful.** A cache that
    // caches nothing would also pass "a 404 is not cached" — so the cache has to be
    // shown to work *before* its absence can be read as a decision.
    GET.mockResolvedValue({ data: page(), response: { status: 200 } });

    const first = await readPublicEvent(SLUG);
    const second = await readPublicEvent(SLUG);

    expect(first.kind).toBe("found");
    expect(second.kind).toBe("found");
    expect(second).toEqual(first);
    // **One request for two reads.** The second was served from the cache.
    expect(GET).toHaveBeenCalledTimes(1);
  });

  it("serves a republished event, because the 404 was never cached", async () => {
    // **The scenario the non-caching exists for.** An event is not public, a reader
    // arrives and gets a 404 — and then the event is published. The next reader must
    // get the page, not the cached 404.
    GET.mockResolvedValueOnce({
      data: undefined,
      error: { code: "not_found", message: "We couldn't find that event.", details: null },
      response: { status: 404 },
    });
    GET.mockResolvedValue({ data: page(), response: { status: 200 } });

    const first = await readPublicEvent(SLUG);
    const second = await readPublicEvent(SLUG);

    expect(first.kind).toBe("not-found");
    expect(second.kind).toBe("found");
  });
});
