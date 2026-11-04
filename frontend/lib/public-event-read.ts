import { unstable_cache } from "next/cache";

import type { components } from "@/lib/api/schema";
import { api } from "@/lib/backend-client";

/**
 * One public event's page, read on the server.
 *
 * **This read carries no cookies, and that is the point of it.** AD-12: "Public event
 * pages render fully without a session and are statically generated or ISR'd." A public
 * read that forwarded the visitor's cookie jar would make the page's content depend on
 * who is asking, and a statically generated page cannot depend on who is asking — the
 * first person to request it would bake their session into the cache for everyone.
 *
 * **So there is no `sessionHeaders()` call here, and there must never be one.** It would
 * opt the whole route out of static generation (a Request-time API), and it would make a
 * public page's content personal. The backend's endpoint does not read a session either
 * — "No session is used and none is set" is in its own description — so the two halves
 * agree.
 *
 * **The server states the facts; the page renders them.** The payload carries the
 * title, the description, both times, the zone, the venue, the canonical URL, the
 * status, the sold-out flag, the version, the source name — and the finished Schema.org
 * object. The page scores nothing, sorts nothing and fills no gap (AD-10, ASSUMPTION-9).
 *
 * **Three answers, and the 404 is a 404.** `found` is the page. `not-found` is the
 * backend's own 404: the slug names no public event. `unavailable` is a failure to
 * answer — a thrown request, a 500, a build machine with no API to talk to. Folding the
 * last two together would either lie about the event or lie about our infrastructure,
 * and the two lie in opposite directions: one says "this does not exist", the other says
 * "we cannot tell you right now".
 */
export type PublicEventRead =
  | { kind: "found"; page: PublicEventPageOut }
  | { kind: "not-found"; code: string | null; supersededBySlug: string | null }
  | { kind: "unavailable" };

export type PublicEventPageOut = components["schemas"]["PublicEventPageOut"];

/**
 * One public event's page facts.
 *
 * **The 404 is checked by status, not by the absence of data.** `response.data` is
 * absent for a 404 *and* for a 500 *and* for a malformed body; the status is the only
 * thing that says which. `lib/event-detail-read.ts` makes the same distinction for the
 * same reason.
 *
 * **The read is cached, and only the "found" answer is.** AD-12: "Public event pages
 * render fully without a session and are statically generated or ISR'd." The segment
 * that serves this page is dynamic (it also serves the personal Detail Screen, and one
 * segment has one rendering mode), so the *page* cannot be in the Full Route Cache —
 * but the *facts* can be in the data cache, and that is where the caching lives.
 *
 * **A not-found is never cached, and that is the important half.** A cached 404 would
 * keep answering 404 for an event that was republished, and a cached "unavailable"
 * would keep answering "we couldn't load this event" for an event that is fine. The
 * backend's own signal is what turns a live event back into a live page — and it does
 * that by invalidating this event's cache entry.
 *
 * **The cache key is the slug, and the cache tag is the event's path.** The tag is
 * `/events/{slug}` — the same string the backend's revalidation signal names
 * (`domain/revalidation.py`, `EVENT_PATH_PREFIX`) — so `revalidatePath("/events/{slug}")`
 * from the `/revalidate` handler drops this entry.
 */
export async function readPublicEvent(slug: string): Promise<PublicEventRead> {
  const cached = unstable_cache(
    async (): Promise<PublicEventPageOut> => {
      const response = await api.GET("/api/catalog/events/by-slug/{slug}", {
        params: { path: { slug } },
      });

      if (response.response.status === 404) {
        // **The backend's own 404, carried out of the cache boundary.** The code and
        // the successor's slug are facts the page needs, and they are facts the
        // backend sent.
        throw new PublicEventNotFound(errorCode(response.error), supersededSlug(response.error));
      }
      if (!isSuccess(response.response.status) || !response.data) {
        // **A 500 is a statement about us, not about the event.** It is not cached
        // either: a cached "we could not answer" would keep answering that way for an
        // event that is perfectly fine.
        //
        // **The status travels with the marker**, because "the API answered 500" and
        // "the API answered 200 with no body" are different faults and the log has to
        // be able to say which. A 200 with no payload is *our* bug — the endpoint
        // declares one — so it is worth naming separately.
        throw new PublicEventUnavailable(
          response.response.status,
          isSuccess(response.response.status) && !response.data,
        );
      }
      return response.data;
    },
    ["public-event", slug],
    { tags: [eventPath(slug)], revalidate: PUBLIC_EVENT_TTL_SECONDS },
  );

  try {
    return { kind: "found", page: await cached() };
  } catch (error) {
    if (error instanceof PublicEventNotFound) {
      // **A 404 is a fact about the world, not an incident.** It is not logged: the
      // backend says this slug names no public event, and that is an answer, not a
      // fault. A crawler walking old links produces these constantly.
      return { kind: "not-found", code: error.code, supersededBySlug: error.supersededBySlug };
    }

    // **Everything else is logged, because it is us failing.** A 500 from the API and
    // a bug in this module both arrive here, and they need different responses — but
    // neither may be silent. The log carries the error's *type* and *message* and
    // nothing else: no session, no cookie, no request body. The slug is not logged
    // either — a public slug is not a secret, but a log line that carries one is a log
    // line that has to be scrubbed, and the incident this answers does not need it.
    console.error("[public-event] the public read could not answer", describeFailure(error));
    return { kind: "unavailable" };
  }
}

/**
 * The marker a 404 throws out of the cache boundary.
 *
 * **It is a class, so `instanceof` tells it apart from any other failure.** A thrown
 * 404 and a thrown network error are both exceptions; only one of them is the
 * backend's statement that the event is not public.
 */
class PublicEventNotFound extends Error {
  constructor(
    readonly code: string | null,
    readonly supersededBySlug: string | null,
  ) {
    super("the event is not public");
    this.name = "PublicEventNotFound";
  }
}

/**
 * The marker a failed read throws out of the cache boundary.
 *
 * **It exists so a failure is never cached.** A 500, a malformed body or a thrown
 * request are all "we could not answer", and none of them is a fact about the event.
 */
class PublicEventUnavailable extends Error {
  constructor(
    /** The status the API answered with, so the log can name it. */
    readonly status: number,
    /**
     * Whether a **success** came back with no payload — which would be our own bug.
     * A failure carries no payload either, but that is expected rather than a fault.
     */
    readonly emptyBody: boolean,
  ) {
    super("the public read could not answer");
    this.name = "PublicEventUnavailable";
  }
}

/**
 * The event's own path — the cache tag, and the string the backend's revalidation
 * signal names.
 *
 * **It is the same convention, in one place.** `domain/revalidation.py` builds
 * `f"{EVENT_PATH_PREFIX}{self.slug}"`; this builds the same string, and the two must
 * agree or the backend's signal invalidates nothing.
 */
function eventPath(slug: string): string {
  return `/events/${slug}`;
}

/** How long a cached public event's facts live before they are re-read anyway. */
const PUBLIC_EVENT_TTL_SECONDS = 60 * 60 * 24;

/**
 * Whether a status is a success.
 *
 * **Any 2xx, not just 200.** The endpoint declares 200 and 404, so `=== 200` would
 * work today — but a 2xx that arrived with an empty body is a malformed answer, and
 * this branch treats it as one. Reading the range rather than the exact code is the
 * difference between "the API answered" and "the API answered 200".
 */
function isSuccess(status: number): boolean {
  return status >= 200 && status < 300;
}

/**
 * The error's machine-readable code, when the 404 carried one.
 *
 * **`ErrorOut.code` is the backend's own vocabulary.** The public read raises
 * `EventNotFoundError`, whose code is `"not_found"` — one code for *every* way a
 * public event can be absent (unknown slug, unpublished, superseded). The code says
 * the event is not public; it does not say *why*, and the frontend must not read a
 * reason into it that the backend did not send.
 *
 * **The *why* arrives separately, in `details`.** A superseded event's 404 carries
 * `details.superseded_by_slug`, naming the event that replaced it. That is the
 * signal the page acts on, and it is the backend's own, not a code the frontend
 * invented.
 */
function errorCode(error: unknown): string | null {
  if (!error || typeof error !== "object") return null;
  const code = (error as { code?: unknown }).code;
  return typeof code === "string" ? code : null;
}

/**
 * The successor's slug, when this event was superseded by another.
 *
 * **A superseded event's page must stop serving** (FR-26, and the revalidation item's
 * own criteria: "An `in_review` or newly-`superseded` event removes or 404s its page
 * rather than leaving a live page for content that is no longer public"). The backend
 * carries the successor's slug in `details`, so the page can send the reader forward —
 * which is the difference between a dead link and a redirection a reader can follow.
 */
function supersededSlug(error: unknown): string | null {
  if (!error || typeof error !== "object") return null;
  const details = (error as { details?: unknown }).details;
  if (!details || typeof details !== "object") return null;
  const slug = (details as { superseded_by_slug?: unknown }).superseded_by_slug;
  return typeof slug === "string" ? slug : null;
}

/**
 * A failure, in the two fields worth logging.
 *
 * **The type and the message, and nothing else.** The message is what says *what*
 * broke — "fetch failed", "Invalid URL", "Cannot read properties of undefined" — and
 * the type is what says *whose* fault it looks like. A stack would be more, and a
 * stack can carry a request URL, so it is left to the runtime's own error reporting.
 */
function describeFailure(error: unknown): {
  type: string;
  message: string;
  status?: number;
  emptyBody?: boolean;
} {
  if (error instanceof PublicEventUnavailable) {
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
