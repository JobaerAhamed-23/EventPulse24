import type { components } from "@/lib/api/schema";
import { api } from "@/lib/backend-client";
import { sessionHeaders } from "@/lib/session";

/**
 * The signed-in user's calendar connections, read on the server (FR-50).
 *
 * **A failure is "unavailable", not "you have none".** The two look identical on screen and
 * mean opposite things — a user with a connected calendar whose read blinked would be shown
 * an empty state that reads as the connection having vanished, on the very screen whose job
 * is to tell them whether it is still there.
 *
 * **The read carries the visitor's cookies.** A server-side read without them is anonymous,
 * and an anonymous read of somebody's calendars is nobody's calendars.
 *
 * **Nothing here is a credential.** `CalendarConnectionOut` carries no address and no
 * fingerprint by design — *"a digest in a response body is one more thing to leak in a
 * screenshot"* — and `last_error_kind` is a slug rather than a message, because an `httpx`
 * exception message contains the full request URL, which **is** the credential (AD-13).
 *
 * **This module is server-only.** It reaches `sessionHeaders()`, and so `next/headers` — a
 * `"use client"` component importing it breaks the production build.
 */
export type CalendarConnection = components["schemas"]["CalendarConnectionOut"];

export type CalendarsRead =
  | { kind: "found"; connections: CalendarConnection[] }
  | { kind: "unavailable" };

export async function readCalendars(): Promise<CalendarsRead> {
  try {
    const response = await api.GET("/api/personal/calendars", {
      headers: await sessionHeaders(),
    });
    // **The endpoint answers an envelope, not a bare list.** `{ items: [...] }` — unlike
    // `/api/personal/collections`, which answers the array itself. The two read helpers
    // therefore differ by one line, and that line is this one.
    if (!response.data) return { kind: "unavailable" };
    return { kind: "found", connections: response.data.items };
  } catch {
    return { kind: "unavailable" };
  }
}
