import type { components } from "@/lib/api/schema";
import { apiBaseUrl } from "@/lib/api-base-url";
import { api } from "@/lib/backend-client";
import { sessionHeaders } from "@/lib/session";

/**
 * The signed-in user's conflict pairs, read on the server.
 *
 * **The server states the fact; the page renders it.** `GET /api/personal/conflicts`
 * returns every pair the system has recorded, already split into `active` (what still
 * needs a decision) and `resolved` (what was decided). The page does not bucket, sort,
 * decide which pairs are active, or compute a count — it renders the two lists as they
 * arrived (AD-10's rule, applied to the review screen).
 *
 * **The read carries the visitor's cookies.** A server-side read without them is
 * anonymous, and an anonymous read of somebody's conflicts would answer with an empty
 * list — which reads exactly like "you have no overlaps". `sessionHeaders()` forwards
 * the whole cookie jar.
 *
 * **Two answers, not one.** `pairs` is the server's answer; `unavailable` is a failure
 * to answer. They are deliberately not folded together: telling a user they have no
 * overlaps because a request failed would be a lie about the world, and a lie the page
 * tells calmly.
 */

/** The pairs the server sent. */
export type ConflictList = components["schemas"]["ConflictListOut"];
/** One pair, with both sides and the choices it offers. */
export type ConflictPair = components["schemas"]["ConflictPairOut"];

/**
 * The user's pairs, or why there aren't any.
 *
 * `pairs` — the server's answer, with both lists.
 * `unavailable` — the request failed, or there was no API to ask.
 */
export type ConflictRead = { kind: "pairs"; pairs: ConflictList } | { kind: "unavailable" };

/**
 * The user's conflict pairs, or `unavailable`.
 *
 * **The base URL may be missing** (a build machine, a misconfigured deploy), and the
 * request may fail (the API is down) or answer with an error (the visitor is not signed
 * in). None of those is a reason to crash the page, and none is a reason to pretend the
 * user has no conflicts — so all three are `unavailable`, and the page says so.
 */
export async function readConflicts(): Promise<ConflictRead> {
  if (!apiBaseUrl()) return { kind: "unavailable" };

  try {
    const response = await api.GET("/api/personal/conflicts", {
      headers: await sessionHeaders(),
    });
    if (!response.data) return { kind: "unavailable" };
    return { kind: "pairs", pairs: response.data };
  } catch {
    return { kind: "unavailable" };
  }
}
