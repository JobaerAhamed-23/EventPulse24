import { unstable_cache } from "next/cache";

import type { components } from "@/lib/api/schema";
import { api } from "@/lib/backend-client";

/**
 * One city's public page, read on the server (FR-27, AD-12).
 *
 * **This read carries no cookies, and that is the point of it.** AD-12: "Public event
 * pages render fully without a session and are statically generated or ISR'd." A public
 * read that forwarded the visitor's cookie jar would make the page's content depend on
 * who is asking, and the first requester would bake their session into the cache for
 * everyone after them. So there is no `sessionHeaders()` call here, and there must never
 * be one — it would also opt the whole route out of static generation.
 *
 * **The score and the tags are the fit as stored.** The backend computed them when the
 * Event Fit row was written, and it ordered the listing by `-score, start_time_utc,
 * event_id` — a total order, so two pages cannot overlap and the order cannot shift
 * between them. This read reshapes that payload and re-computes nothing (AD-10).
 *
 * **Three answers, and the 404 is a 404.** `found` is the page. `not-found` is the
 * backend's own 404: the slug names no city. `unavailable` is a failure to answer — a
 * thrown request, a 500, a build machine with no API to talk to. Folding the last two
 * together would either put a wrong "this city does not exist" into a search index or
 * serve a broken page as if it were the truth, and the two lie in opposite directions.
 *
 * **A sparse city is not a not-found.** A city that exists but has too few events comes
 * back as a **200** with `is_published: false` — the backend's own answer, and FR-27's
 * "coming soon" state. The distinction is the whole point of the three answers: an
 * unknown slug is a URL that does not exist, and a quiet city is a real city whose page
 * is not published yet.
 */
export type CityPageRead =
  | { kind: "found"; page: CityPageOut }
  | { kind: "not-found"; code: string | null }
  | { kind: "unavailable" };

export type CityPageOut = components["schemas"]["CityPageOut"];

/**
 * The city's page facts, for one page of the listing.
 *
 * **The read is cached, and only the "found" answer is.** The segment that serves this
 * page is dynamic — a paged listing cannot be enumerated at build time, and the city
 * slugs are minted at runtime — so the *page* is never in the Full Route Cache, but the
 * *facts* are in the data cache, and that is where the caching lives.
 *
 * **A not-found is never cached, and that is the important half.** A cached 404 would
 * keep answering 404 for a city that was created later, and the backend's own signal is
 * what would turn it back into a live page.
 *
 * **The cache key carries the page; the cache tag does not.** Two cities, or two pages
 * of one city, are different facts and must not share an entry — so the key is
 * `["city-page", slug, page]`. But the *tag* is the city's own path, `/events-in/{slug}`:
 * one revalidation signal has to clear **every** page of that city at once, and a
 * per-page tag would leave page 2 serving a stale listing after page 1 was invalidated.
 * The tag is the same string `domain/revalidation.py` builds
 * (`CITY_PATH_PREFIX = "/events-in-"`), so the `/revalidate` handler's existing
 * `revalidateTag(path, { expire: 0 })` drops it.
 */
export async function readCityPage(slug: string, page: number): Promise<CityPageRead> {
  // **The page number is clamped here, before it reaches the API.** The backend's
  // `CityPageQuery` *refuses* a page below one with a 422 — it treats an out-of-range
  // request as a mistake and says so. A crawler's `?page=0` is not a mistake to be
  // answered with an error; it is a request for the first page, and clamping it here
  // keeps the refusal for the callers it was written for.
  const requested = normalizePage(page);

  const cached = unstable_cache(
    async (): Promise<CityPageOut> => {
      const response = await api.GET("/api/catalog/cities/by-slug/{slug}", {
        params: { path: { slug }, query: { page: requested } },
      });

      if (response.response.status === 404) {
        // **The backend's own 404, carried out of the cache boundary.** The code is a
        // fact the page can use, and it is a fact the backend sent.
        throw new CityNotFound(errorCode(response.error));
      }
      if (!isSuccess(response.response.status) || !response.data) {
        // **A 500 is a statement about us, not about the city.** It is not cached
        // either: a cached "we could not answer" would keep answering that way for a
        // city that is perfectly fine.
        //
        // **The status travels with the marker**, because "the API answered 500" and
        // "the API answered 200 with no body" are different faults and the log has to
        // be able to say which. A 200 with no payload is *our* bug — the endpoint
        // declares one — so it is worth naming separately.
        throw new CityUnavailable(
          response.response.status,
          isSuccess(response.response.status) && !response.data,
        );
      }
      return response.data;
    },
    ["city-page", slug, String(requested)],
    { tags: [cityPath(slug)], revalidate: CITY_PAGE_TTL_SECONDS },
  );

  try {
    return { kind: "found", page: await cached() };
  } catch (error) {
    if (error instanceof CityNotFound) {
      // **A 404 is a fact about the world, not an incident.** It is not logged: the
      // backend says this slug names no city, and that is an answer, not a fault. A
      // crawler walking old links produces these constantly.
      return { kind: "not-found", code: error.code };
    }

    // **Everything else is logged, because it is us failing.** A 500 from the API and a
    // bug in this module both arrive here, and neither may be silent. The log carries
    // the error's *type* and *message* and nothing else: no session, no cookie, no
    // request body. The slug is not logged either — a public slug is not a secret, but
    // a log line that carries one is a log line that has to be scrubbed.
    console.error("[city-page] the city read could not answer", describeFailure(error));
    return { kind: "unavailable" };
  }
}

/**
 * The city's own path — the cache tag, the public URL, and the string the backend's
 * revalidation signal names.
 *
 * **It is the same convention, in one place.** `domain/revalidation.py` builds
 * `f"{CITY_PATH_PREFIX}{slug}"`; this builds the same string, and the two must agree or
 * the backend's signal invalidates nothing.
 *
 * **It is exported because it is the URL too.** The cache tag and the public address are
 * the same string, so there is exactly one definition of where a city lives — and the
 * canonical link, the OG URL and the paging links are all built from it.
 */
export function cityPath(slug: string): string {
  return `/events-in-${slug}`;
}

/**
 * The link to one page of this city's listing.
 *
 * **Page one carries no query.** `?page=1` would be the same page at two URLs, and a
 * page that forks after ranking splits the ranking across the two copies.
 *
 * **The public URL is the hyphenated form** — `/events-in-{slug}` — because that is the
 * address the backend's revalidation signal names (`domain/revalidation.py`'s
 * `CITY_PATH_PREFIX`) and the one that appears in a search result. The route's internal
 * segment is a routing detail and never appears in a link.
 */
export function cityPageHref(slug: string, page: number): string {
  const base = cityPath(slug);
  return page <= 1 ? base : `${base}?page=${page}`;
}

/** How long a cached city's facts live before they are re-read anyway. */
const CITY_PAGE_TTL_SECONDS = 60 * 60 * 24;

/**
 * The page number, clamped to what the backend will accept.
 *
 * **The backend refuses a page below one with a 422**, and this is where that refusal
 * is turned into an answer instead of an error. A page number that is not a number at
 * all — `?page=abc` — is the same case: the first page is what the reader meant.
 *
 * **A number past `Number.MAX_SAFE_INTEGER` is the same case too.** A float cannot
 * hold every integer past 2^53, and one it cannot hold is printed in scientific
 * notation — `1e+23` — which the backend's `page: int` **refuses with a 422**. So a
 * page number has to be an integer a person could write.
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
 * backend's statement that the city does not exist.
 */
class CityNotFound extends Error {
  constructor(readonly code: string | null) {
    super("the city was not found");
    this.name = "CityNotFound";
  }
}

/**
 * The marker a failed read throws out of the cache boundary.
 *
 * **It exists so a failure is never cached.** A 500, a malformed body or a thrown
 * request are all "we could not answer", and none of them is a fact about the city.
 */
class CityUnavailable extends Error {
  constructor(
    /** The status the API answered with, so the log can name it. */
    readonly status: number,
    /**
     * Whether a **success** came back with no payload — which would be our own bug.
     * A failure carries no payload either, but that is expected rather than a fault.
     */
    readonly emptyBody: boolean,
  ) {
    super("the city read could not answer");
    this.name = "CityUnavailable";
  }
}

/**
 * Whether a status is a success.
 *
 * **Any 2xx, not just 200.** The endpoint declares 200 and 404, so `=== 200` would work
 * today — but a 2xx that arrived with an empty body is a malformed answer, and this
 * branch treats it as one. Reading the range rather than the exact code is the difference
 * between "the API answered" and "the API answered 200".
 */
function isSuccess(status: number): boolean {
  return status >= 200 && status < 300;
}

/**
 * The error's machine-readable code, when the 404 carried one.
 *
 * **`ErrorOut.code` is the backend's own vocabulary.** The city read raises
 * `CityNotFoundError`, whose code is `"not_found"` — inherited from `NotFoundError` — so
 * one code covers every way a city can be absent. The code says the city is not there;
 * it does not say *why*, and the frontend must not read a reason into it that the
 * backend did not send.
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
  if (error instanceof CityUnavailable) {
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
