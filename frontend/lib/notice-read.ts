import type { components } from "@/lib/api/schema";
import { api } from "@/lib/backend-client";
import { sessionHeaders } from "@/lib/session";

/**
 * The signed-in user's open state-change notices, read on the server.
 *
 * **The server states the facts; the strip renders them.** `GET /api/notices` returns the
 * notices the user has not dismissed, newest first, and each one carries the change's
 * *kind* and nothing else about the change. The strip does not decide what a notice
 * means, does not count them, does not work out whether it has seen them, and does not
 * invent a sentence the server did not send (AD-10).
 *
 * **The read carries the visitor's cookies.** A server-side read without them is
 * anonymous, and an anonymous read of somebody's notices would answer with an empty list
 * — which reads exactly like "nothing changed". `sessionHeaders()` forwards the whole
 * cookie jar.
 *
 * **Two answers, not one.** `notices` is the server's answer; `unavailable` is a failure
 * to answer. They are deliberately not folded together: a strip that rendered "you have
 * no notices" because a request failed would be telling the user something untrue about
 * their plans, and the strip's whole job is to tell the truth about plans.
 *
 * **The list is bounded by the server, not by the client.** `NOTICE_STRIP_LIMIT` is the
 * server's product decision — FR-54's "one calm correction", not a page of history — and
 * the endpoint takes no `?limit=` parameter. The client asks for the strip and gets the
 * strip.
 */
export type NoticeRead = { kind: "notices"; notices: NoticeOut[] } | { kind: "unavailable" };

/** One notice, as the server hands it over. */
export type NoticeOut = components["schemas"]["NoticeOut"];

/**
 * The user's open notices, or `unavailable`.
 *
 * **A thrown request, a non-2xx status and a missing body are all `unavailable`.** None
 * of them is a reason to crash the home page, and none is a reason to claim the user has
 * no notices.
 */
export async function readNotices(): Promise<NoticeRead> {
  try {
    const response = await api.GET("/api/notices", { headers: await sessionHeaders() });
    if (!response.data) return { kind: "unavailable" };
    return { kind: "notices", notices: response.data.items ?? [] };
  } catch {
    return { kind: "unavailable" };
  }
}
