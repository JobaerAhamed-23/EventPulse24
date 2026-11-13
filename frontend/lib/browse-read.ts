import type { components } from "@/lib/api/schema";
import { apiBaseUrl } from "@/lib/api-base-url";
import { api } from "@/lib/backend-client";
import { sessionHeaders } from "@/lib/session";

/**
 * The signed-in user's Browse surface, read on the server.
 *
 * **The server states the fact; the page renders it.** `GET /api/personal/browse` returns
 * one ranked pool of the user's city across tonight and the next seven days, already
 * ranked by the Relevance Pulse, already split into the two attention tiers by
 * `tier_2_starts_at`, and already carrying each card's save state. The page does not
 * rank, sort, re-tier or re-bucket — it renders the cards in the order they arrived and
 * the tiers where the server said they begin (AD-10).
 *
 * **The read carries the visitor's cookies.** A server-side read without them is
 * anonymous, and a signed-in user's own Browse telling them their city has nothing on is
 * exactly the bug `lib/session.ts` documents. `sessionHeaders()` forwards the whole
 * cookie jar — Django reads `sessionid` and `csrftoken` from it.
 *
 * **Two answers, not one.** `browse` is the payload; `unavailable` is a failure to
 * answer. They are deliberately not folded together: showing a user an empty city
 * because a request failed would be a lie about the world, and the same lie the route
 * decision refuses to tell about their session.
 */

/** The whole Browse payload. */
export type BrowseOut = components["schemas"]["BrowseOut"];
/** One card on the surface. */
export type BrowseCard = components["schemas"]["BrowseCardOut"];
/** The save allowance, as it stands. */
export type BrowseQuota = components["schemas"]["BrowseQuotaOut"];

/**
 * The user's Browse surface, or why there isn't one.
 *
 * `browse` — the server's answer.
 * `unavailable` — the request failed, or there was no API to ask.
 */
export type BrowseRead = { kind: "browse"; browse: BrowseOut } | { kind: "unavailable" };

/**
 * The user's Browse surface, or `unavailable`.
 *
 * **The base URL may be missing** (a build machine, a misconfigured deploy), and the
 * request may fail (the API is down) or answer with an error (the visitor is not signed
 * in). None of those is a reason to crash the page, and none is a reason to pretend the
 * city is empty — so all three are `unavailable`, and the page says so.
 *
 * **`offset` pages within one ranked pool.** The server fetches a single bounded pool
 * and slices it, so paging is sound by construction: one list, one order, sliced. The
 * order and the tier boundary come back on every chunk, so the client never re-ranks.
 */
export async function readBrowse(offset = 0, limit?: number): Promise<BrowseRead> {
  if (!apiBaseUrl()) return { kind: "unavailable" };

  try {
    const response = await api.GET("/api/personal/browse", {
      headers: await sessionHeaders(),
      params: { query: { offset, limit } },
    });
    if (!response.data) return { kind: "unavailable" };
    return { kind: "browse", browse: response.data };
  } catch {
    return { kind: "unavailable" };
  }
}
