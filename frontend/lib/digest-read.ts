import type { components } from "@/lib/api/schema";
import { api } from "@/lib/backend-client";
import { sessionHeaders } from "@/lib/session";

/**
 * The signed-in user's Pulse Digest, read on the server.
 *
 * **The server states the fact; the page renders it.** `GET /api/personal/digest`
 * returns the persisted compositions for the user's local day. The page does not score,
 * sort, re-bucket or compose — it renders the cards in the order they arrived, and the
 * city and the status are the server's too (AD-10).
 *
 * **The read carries the visitor's cookies.** A server-side read without them is
 * anonymous, and a signed-in user's own home page telling them they have no digest is
 * exactly the bug `lib/session.ts` documents. `sessionHeaders()` forwards the whole
 * cookie jar — Django reads `sessionid` and `csrftoken` from it.
 *
 * **The three states are three answers, not two.** `status` is `composed`, `empty` or
 * `not_composed`, and all three answer 200. `empty` means the digest was composed and
 * nothing qualified; `not_composed` means the question has not been asked yet. The
 * difference is a claim about the world, so the page must not collapse them — this
 * module keeps them apart and says which one it got.
 */
export type DigestRead =
  | { kind: "composed"; digest: DigestOut }
  | { kind: "empty"; digest: DigestOut }
  | { kind: "not_composed"; digest: DigestOut }
  | { kind: "unavailable" };

export type DigestOut = components["schemas"]["DigestOut"];
export type DigestCard = components["schemas"]["DigestCardOut"];

/**
 * The user's digest for their local day.
 *
 * **`unavailable` is a failure to answer, not an answer.** It covers a thrown request,
 * a 500 and a non-2xx status. It is deliberately not folded into `empty`: telling a
 * user their day is quiet because a request failed would be a lie about the world, and
 * the same lie the route decision refuses to tell about their session.
 */
export async function readDigest(): Promise<DigestRead> {
  try {
    const response = await api.GET("/api/personal/digest", { headers: await sessionHeaders() });
    if (!response.data) return { kind: "unavailable" };

    const digest = response.data;
    switch (digest.status) {
      case "composed":
        return { kind: "composed", digest };
      case "empty":
        return { kind: "empty", digest };
      case "not_composed":
        return { kind: "not_composed", digest };
      default:
        // A status the client does not know is a status the client cannot render. It is
        // a failure to answer, not a fourth state.
        return { kind: "unavailable" };
    }
  } catch {
    return { kind: "unavailable" };
  }
}
