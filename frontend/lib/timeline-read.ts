import type { components } from "@/lib/api/schema";
import { apiBaseUrl } from "@/lib/api-base-url";
import { api } from "@/lib/backend-client";
import { sessionHeaders } from "@/lib/session";

/**
 * The signed-in user's week, read on the server.
 *
 * **The server states the fact; the page renders it.** `GET /api/personal/timeline`
 * returns the week already cut into seven local days, each a time-ordered list of
 * blocks, with the conflict indicator already decided per block. The page does not
 * bucket, sort, re-decide a conflict, or compute a Monday — it renders `days` as they
 * arrived (AD-10's rule, applied to the Timeline).
 *
 * **The read carries the visitor's cookies.** A server-side read without them is
 * anonymous, and a signed-in user's own Timeline telling them they have nothing is
 * exactly the bug `lib/session.ts` documents. `sessionHeaders()` forwards the whole
 * cookie jar — Django reads `sessionid` and `csrftoken` from it.
 *
 * **Two answers, not one.** `week` is a *week*; `unavailable` is a failure to answer.
 * They are deliberately not folded together: telling a user their week is quiet
 * because a request failed would be a lie about the world, and the same lie the route
 * decision refuses to tell about their session.
 */

/** The week the server sent. */
export type TimelineWeek = components["schemas"]["TimelineOut"];
/** One local day, with its blocks. */
export type TimelineDay = components["schemas"]["TimelineDayOut"];
/** One block on one day. */
export type TimelineBlock = components["schemas"]["TimelineBlockOut"];

/**
 * The user's week, or why there isn't one.
 *
 * `week` — the server's answer, with seven days.
 * `unavailable` — the request failed, or there was no API to ask.
 */
export type TimelineRead = { kind: "week"; week: TimelineWeek } | { kind: "unavailable" };

/**
 * The user's week, or `unavailable`.
 *
 * **`week` is any date in the wanted week.** The server names that week's Monday and
 * Sunday, so the client does not have to know which day of the week it asked for. The
 * caller passes the Monday it was given, which keeps the URL canonical — the same week
 * always has the same address.
 *
 * **The base URL may be missing** (a build machine, a misconfigured deploy), and the
 * request may fail (the API is down) or answer with an error (the visitor is not signed
 * in). None of those is a reason to crash the page, and none is a reason to pretend the
 * week is empty — so all three are `unavailable`, and the page says so.
 */
export async function readTimeline(week?: string | null): Promise<TimelineRead> {
  if (!apiBaseUrl()) return { kind: "unavailable" };

  try {
    const response = await api.GET("/api/personal/timeline", {
      headers: await sessionHeaders(),
      params: { query: { week: week ?? undefined } },
    });
    if (!response.data) return { kind: "unavailable" };
    return { kind: "week", week: response.data };
  } catch {
    return { kind: "unavailable" };
  }
}
