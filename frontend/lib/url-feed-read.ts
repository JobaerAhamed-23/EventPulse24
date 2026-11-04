import { unstable_cache } from "next/cache";

import type { components } from "@/lib/api/schema";
import { api } from "@/lib/backend-client";

/**
 * The site's public URL feed, read on the server (FR-26, FR-27, AD-12).
 *
 * **This is the sitemap's source, and that is the whole of its job.** It answers one
 * question — *"which URLs does this site serve, and when did each last move?"* — and the
 * sitemap renders the answer. The feed is not a hand-maintained list and the sitemap is
 * not either: both are projections of the public surface, read from the same place the
 * public pages read their facts.
 *
 * **This read carries no cookies, and that is the point of it.** AD-12: "Public event
 * pages render fully without a session and are statically generated or ISR'd." A public
 * read that forwarded the visitor's cookie jar would make the feed's content depend on
 * who is asking, and the first requester would bake their session into the cache for
 * everyone after them. So there is no `sessionHeaders()` call here, and there must never
 * be one — it would also opt the whole route out of static generation.
 *
 * **Three answers, and they are three answers.** `found` is the feed. `not-found` is the
 * backend's own 404 — the feed does not exist, which is a fact about the world.
 * `unavailable` is a failure to answer — a thrown request, a 500, a build machine with no
 * API to talk to. Folding the last two together would either put a wrong "this site has
 * no pages" into a search index or serve a broken sitemap as if it were the truth, and
 * the two lie in opposite directions.
 *
 * **The feed is paged, and the page is a slice of the joined list.** The backend orders
 * the feed by kind then path — a single total order — so a page boundary is exact: two
 * pages cannot overlap, and no URL is served twice or missed. The sitemap's children
 * partition the same list.
 */
export type UrlFeedRead =
  | { kind: "found"; page: UrlFeedOut }
  | { kind: "not-found"; code: string | null }
  | { kind: "unavailable" };

export type UrlFeedOut = components["schemas"]["UrlFeedOut"];
export type UrlFeedEntry = components["schemas"]["UrlFeedEntryOut"];

/**
 * The feed's own defaults, mirrored from the backend's `UrlFeedQuery`.
 *
 * **The page size is the sitemap's child size, and the two must agree.** The feed's page
 * is the unit the sitemap pages in, so a child sitemap is exactly one feed's worth of
 * URLs — and the number of children is decided by the feed's `total`, not by an
 * estimate.
 */
export const URL_FEED_PAGE_SIZE = 1000;

/** How long a cached feed page lives before it is re-read anyway. */
const URL_FEED_TTL_SECONDS = 60 * 60;

/**
 * One page of the public URL feed.
 *
 * **The read is cached, and only the "found" answer is.** The route that serves the
 * sitemap is dynamic — the slugs are minted at runtime, so a build machine cannot
 * enumerate them — so the *document* is never in the Full Route Cache, but the *facts*
 * are in the data cache, and that is where the caching lives.
 *
 * **A not-found and a failure are never cached.** A cached 404 would keep answering 404
 * for a feed that was deployed later, and a cached "we could not answer" would keep
 * answering that way for a feed that is perfectly fine.
 *
 * **The cache key carries the page; the cache tag is the feed's own.** Two pages of the
 * feed are different facts and must not share an entry — so the key is
 * `["url-feed", page]`. The tag is the sitemap's own path, `/sitemap.xml`, so one
 * revalidation signal clears every page of the feed at once, and a per-page tag would
 * leave the second page serving a stale list after the first was invalidated.
 *
 * **`skip` is honoured, and that is the index's escape hatch.** The sitemap *index*
 * reads only the feed's `total`, and the total decides how many children there are. A
 * cached total is a stale total, and a stale total means the index names the wrong
 * number of children — so the index reads the total *uncached*. Everything else — the
 * children's URLs — is still cached, which is where the cost is.
 */
export async function readUrlFeed(
  page = 1,
  options: { skipCache?: boolean } = {},
): Promise<UrlFeedRead> {
  const requested = normalizePage(page);

  const read = async (): Promise<UrlFeedOut> => {
    const response = await api.GET("/api/catalog/url-feed", {
      params: { query: { page: requested, page_size: URL_FEED_PAGE_SIZE } },
    });

    if (response.response.status === 404) {
      // **The backend's own 404, carried out of the cache boundary.** The code is a
      // fact the sitemap can use, and it is a fact the backend sent.
      throw new UrlFeedNotFound(errorCode(response.error));
    }
    if (!isSuccess(response.response.status) || !response.data) {
      // **A 500 is a statement about us, not about the feed.** It is not cached
      // either: a cached "we could not answer" would keep answering that way for a
      // feed that is perfectly fine.
      //
      // **The status travels with the marker**, because "the API answered 500" and
      // "the API answered 200 with no body" are different faults and the log has to
      // be able to say which. A 200 with no payload is *our* bug — the endpoint
      // declares one — so it is worth naming separately.
      throw new UrlFeedUnavailable(
        response.response.status,
        isSuccess(response.response.status) && !response.data,
      );
    }
    return response.data;
  };

  const cached =
    options.skipCache === true
      ? read
      : unstable_cache(read, ["url-feed", String(requested)], {
          tags: [URL_FEED_TAG],
          revalidate: URL_FEED_TTL_SECONDS,
        });

  try {
    return { kind: "found", page: await cached() };
  } catch (error) {
    if (error instanceof UrlFeedNotFound) {
      // **A 404 is a fact about the world, not an incident.** It is not logged: the
      // backend says this feed does not exist, and that is an answer, not a fault.
      return { kind: "not-found", code: error.code };
    }

    // **Everything else is logged, because it is us failing.** A 500 from the API and a
    // bug in this module both arrive here, and neither may be silent. The log carries
    // the error's *type* and *message* and nothing else: no session, no cookie, no
    // request body.
    console.error("[url-feed] the feed read could not answer", describeFailure(error));
    return { kind: "unavailable" };
  }
}

/**
 * One slice of the feed, by **position** rather than by page.
 *
 * **This is the sitemap child's read.** A child sitemap covers a contiguous run of the
 * feed's URLs — the first 50,000, then the next 50,000 — and the feed is paged at 1,000
 * URLs, so a child spans fifty feed pages. This function walks exactly the pages that
 * overlap the requested run and returns the slice.
 *
 * **The slice is computed from the page's own bounds, not from a running count.** The
 * backend's page is a slice of the joined list, so the entries on page `p` occupy
 * positions `[p * page_size, (p + 1) * page_size)` — and the slice is the intersection
 * of that with the requested run. Counting as it went would be the same answer with one
 * more place to be wrong.
 *
 * **A failure part-way through is a failure of the whole read**: a child sitemap with
 * half its URLs is a document that says the site has half the pages it has.
 *
 * **The returned `total` is the feed's size, not the size of the pages walked.** Every
 * page the backend answers carries the feed's total in its `total` field, so the number
 * here is the catalog's size even when the walk stopped on the first page — which is
 * what lets a caller answer "is my slice inside the feed?" from this read alone.
 */
export async function readUrlFeedRange(
  start: number,
  count: number,
  options: { maxPages?: number } = {},
): Promise<UrlFeedRead> {
  const maxPages = options.maxPages ?? MAX_FEED_PAGES;
  const wanted = Math.max(0, count);
  const items: UrlFeedEntry[] = [];
  let total = 0;

  if (wanted === 0) {
    // **An empty run is an empty answer, and it is answered without a request.** The
    // head page carries the feed's `total`, and the total is the only fact an empty
    // run needs — a caller asking for no URLs still needs to know how big the feed is.
    const head = await readUrlFeed(1);
    if (head.kind !== "found") return head;
    return {
      kind: "found",
      page: {
        items: [],
        page: 1,
        page_size: URL_FEED_PAGE_SIZE,
        total: head.page.total,
        has_next: false,
      },
    };
  }

  // The first feed page that overlaps the run. The feed's pages are 1,000 wide, so the
  // run `[start, start + wanted)` begins on page `floor(start / page_size) + 1`.
  const firstPage = Math.floor(start / URL_FEED_PAGE_SIZE) + 1;
  const lastPage = Math.ceil((start + wanted) / URL_FEED_PAGE_SIZE);

  for (let page = firstPage; page <= lastPage && page - firstPage < maxPages; page += 1) {
    const pageStart = (page - 1) * URL_FEED_PAGE_SIZE;

    // **The feed's `total` bounds the walk.** The run was computed from the total, so a
    // page that starts beyond it has nothing in it — and asking for it would be a
    // request to learn what the count already said. The total is known from the first
    // page's answer; before that, `total` is zero and the check does not fire.
    if (total > 0 && pageStart >= total) break;

    const read = await readUrlFeed(page);

    if (read.kind !== "found") return read;

    total = read.page.total;

    // **An empty page ends the walk too**, for the same reason: the catalog is shorter
    // than the run asked for, and there is nothing further to fetch.
    if (read.page.items.length === 0) break;

    const from = Math.max(0, start - pageStart);
    const to = Math.min(read.page.items.length, start + wanted - pageStart);

    for (let index = from; index < to; index += 1) {
      const entry = read.page.items[index];
      if (entry) items.push(entry);
    }
  }

  return {
    kind: "found",
    page: {
      items,
      page: firstPage,
      page_size: URL_FEED_PAGE_SIZE,
      total,
      has_next: false,
    },
  };
}

/**
 * The cache tag — the sitemap's own path.
 *
 * **It is the public address of the thing the feed serves.** One revalidation signal
 * clears every page of the feed at once, which is the point: the sitemap is one
 * document, and its source is one fact.
 */
export const URL_FEED_TAG = "/sitemap.xml";

/**
 * How many feed pages the whole-feed walk will take at most.
 *
 * **The feed's page is 1,000 URLs and the sitemap's ceiling is 50,000, so 50 pages
 * covers one full child.** The cap is a backstop, not the operating range: it exists so
 * that a backend which always answered `has_next: true` would make the walk stop
 * rather than loop.
 */
const MAX_FEED_PAGES = 100;

/**
 * The page number, clamped to what the backend will accept.
 *
 * **The backend refuses a page below one with a 422** — it treats an out-of-range
 * request as a mistake and says so — and this is where that refusal is turned into an
 * answer instead of an error.
 */
export function normalizePage(page: number): number {
  if (!Number.isFinite(page)) return 1;
  const whole = Math.floor(page);
  if (whole < 1) return 1;
  if (!Number.isSafeInteger(whole)) return 1;
  return whole;
}

/**
 * The marker a 404 throws out of the cache boundary.
 *
 * **It is a class, so `instanceof` tells it apart from any other failure.** A thrown
 * 404 and a thrown network error are both exceptions; only one of them is the
 * backend's statement that the feed does not exist.
 */
class UrlFeedNotFound extends Error {
  constructor(readonly code: string | null) {
    super("the url feed was not found");
    this.name = "UrlFeedNotFound";
  }
}

/**
 * The marker a failed read throws out of the cache boundary.
 *
 * **It exists so a failure is never cached.** A 500, a malformed body or a thrown
 * request are all "we could not answer", and none of them is a fact about the feed.
 */
class UrlFeedUnavailable extends Error {
  constructor(
    /** The status the API answered with, so the log can name it. */
    readonly status: number,
    /**
     * Whether a **success** came back with no payload — which would be our own bug.
     * A failure carries no payload either, but that is expected rather than a fault.
     */
    readonly emptyBody: boolean,
  ) {
    super("the url feed read could not answer");
    this.name = "UrlFeedUnavailable";
  }
}

/**
 * Whether a status is a success.
 *
 * **Any 2xx, not just 200.** The endpoint declares 200 and 404, so `=== 200` would work
 * today — but a 2xx that arrived with an empty body is a malformed answer, and this
 * branch treats it as one.
 */
function isSuccess(status: number): boolean {
  return status >= 200 && status < 300;
}

/**
 * The error's machine-readable code, when the 404 carried one.
 *
 * **`ErrorOut.code` is the backend's own vocabulary**, and the frontend must not read a
 * reason into it that the backend did not send.
 */
function errorCode(error: unknown): string | null {
  if (!error || typeof error !== "object") return null;
  const code = (error as { code?: unknown }).code;
  return typeof code === "string" ? code : null;
}

/**
 * A failure, in the two fields worth logging.
 *
 * **The type and the message, and nothing else.** The message is what says *what*
 * broke — "fetch failed", "Invalid URL", "Cannot read properties of undefined" — and the
 * type is what says *whose* fault it looks like. A stack would be more, and a stack can
 * carry a request URL, so it is left to the runtime's own error reporting.
 */
function describeFailure(error: unknown): {
  type: string;
  message: string;
  status?: number;
  emptyBody?: boolean;
} {
  if (error instanceof UrlFeedUnavailable) {
    return {
      type: error.name,
      message: error.emptyBody
        ? `the API answered ${error.status} with no payload`
        : `the API answered ${error.status}`,
      status: error.status,
      emptyBody: error.emptyBody,
    };
  }
  if (error instanceof Error) {
    return { type: error.name, message: error.message };
  }
  return { type: "unknown", message: String(error) };
}
