import type { components } from "@/lib/api/schema";
import { api } from "@/lib/backend-client";
import { sessionHeaders } from "@/lib/session";

/**
 * One of the signed-in user's own personal events, read on the server.
 *
 * **It exists for a name.** The reminder plan's payload carries slots and delivery times
 * and no title, so the screen that edits a personal event's plan has to read the event to
 * put its name in the crumb — exactly as the saved-event route reads the Detail Screen's
 * own read for the same reason.
 *
 * **Three outcomes, kept apart.** `missing` is the server's 404 — the event does not
 * exist, or is not this user's, which the API deliberately does not distinguish.
 * `unavailable` is a failure to reach the API at all. A caller that collapsed them would
 * tell a user their event was gone because a request timed out.
 *
 * **This module is server-only.** It reaches `sessionHeaders()`, and so `next/headers`.
 */
export type PersonalEventOut = components["schemas"]["PersonalEventOut"];

export type PersonalEventRead =
  | { kind: "found"; event: PersonalEventOut }
  | { kind: "missing" }
  | { kind: "unavailable" };

export async function readPersonalEvent(eventId: string): Promise<PersonalEventRead> {
  try {
    const response = await api.GET("/api/personal/events/{event_id}", {
      params: { path: { event_id: eventId } },
      headers: await sessionHeaders(),
    });
    if (response.response.status === 404) return { kind: "missing" };
    if (!response.data) return { kind: "unavailable" };
    return { kind: "found", event: response.data };
  } catch {
    return { kind: "unavailable" };
  }
}
