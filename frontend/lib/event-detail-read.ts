import type { components } from "@/lib/api/schema";
import { api } from "@/lib/backend-client";
import { sessionHeaders } from "@/lib/session";

/**
 * One event's Detail Screen, read on the server.
 *
 * **The server states the facts; the page renders them.** `GET /api/events/{event_id}`
 * returns the event's public facts and — for a signed-in caller — their own persisted
 * why-this breakdown, their saved state and the k-anonymous neighbor bucket. The page
 * does not score, re-bucket, sort, generate a reason or fill a gap. It renders what it
 * was given (AD-10).
 *
 * **The read carries the visitor's cookies.** A server-side read without them is
 * anonymous, and a signed-in user's own Detail Screen telling them they have no
 * explanation would be the exact failure this surface cannot have — the screen exists
 * to *show* the explanation.
 *
 * **Four answers, not two.** The two that matter are `found` and `anonymous`: the API
 * answers both with a payload, and they differ only in whether `personal` is `null`.
 * The screen *behaves* differently for the two — a signed-in user has a Save button, an
 * anonymous visitor does not — so the read says which one it was.
 *
 * **The two failures are different failures.** `removed` is the 404: the event is not
 * public, or has already started, or has been superseded. That is a fact about the
 * world. `unavailable` is a fact about us: the API could not be reached. Folding them
 * together would either lie about the event or lie about our infrastructure.
 */
export type DetailRead =
  | { kind: "found"; detail: EventDetailOut }
  | { kind: "anonymous"; detail: EventDetailOut }
  | { kind: "removed" }
  | { kind: "unavailable" };

export type EventDetailOut = components["schemas"]["EventDetailOut"];

/**
 * One event's Detail Screen.
 *
 * **The 404 is a 404.** The API says so itself: "An event that is not public — or that
 * has already started — reads as not found, the same set the public catalog shows." A
 * detail page for an event the public catalog does not list would leak that the event
 * exists, so the endpoint refuses it and the screen renders the removed state.
 */
export async function readEventDetail(eventId: string): Promise<DetailRead> {
  try {
    const response = await api.GET("/api/events/{event_id}", {
      params: { path: { event_id: eventId } },
      headers: await sessionHeaders(),
    });

    if (response.response.status === 404) return { kind: "removed" };
    if (!response.data) return { kind: "unavailable" };

    // **`personal === null` is the API's own statement that it looked up nothing.** The
    // screen does not decide this by reading the session: the API is the authority on
    // whether it found a personal payload, and a client that inferred it from its own
    // cookie could render the personal surface to a caller the API refused.
    if (response.data.personal === null || response.data.personal === undefined) {
      return { kind: "anonymous", detail: response.data };
    }
    return { kind: "found", detail: response.data };
  } catch {
    return { kind: "unavailable" };
  }
}
