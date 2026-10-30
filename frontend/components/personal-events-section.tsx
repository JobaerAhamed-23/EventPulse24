import type { components } from "@/lib/api/schema";
import { apiBaseUrl } from "@/lib/api-base-url";
import { api } from "@/lib/backend-client";
import { sessionHeaders } from "@/lib/session";

import { PersonalEventsPanel } from "@/components/personal-events-panel";

type PersonalEvent = components["schemas"]["PersonalEventOut"];

/**
 * The personal-events section: a **server** component that reads the user's own events
 * and hands them to the client island that owns the flow.
 *
 * The stack is "server components + the generated API client" (AD-19), so the *read*
 * happens on the server and the *write* happens in the client island. The list is a
 * server read; the sheets are client components.
 *
 * **The read is allowed to fail quietly, and it must never fail the build.** A
 * signed-out visitor sees an empty list rather than an error page, because the personal
 * surface is session-based by design (AD-12) and "you have no personal events" is a true
 * statement about that visitor.
 *
 * That quietness is a *runtime* property, and it has to be arranged so the **build** does
 * not need a live API either. `next build` renders each page to produce its static
 * output; if that render reached for the API, the build would need a running Django — and
 * with no `API_BASE_URL` set, the client has no base URL to reach and `openapi-fetch`
 * rejects the relative path outright (`ERR_INVALID_URL`). So:
 *
 *   - the **page** declares `dynamic = "force-dynamic"`, so the route is rendered per
 *     request and the build never runs this read at all;
 *   - the section returns the empty list when there is no base URL to read from, and
 *   - the section catches a failed read, so a signed-out visitor or a down API is an
 *     empty list rather than an error page.
 */
export async function PersonalEventsSection() {
  const events = await readPersonalEvents();

  return <PersonalEventsPanel events={events} />;
}

/**
 * The user's own events, or an empty list.
 *
 * Every failure mode is the same to the caller: no events. The base URL may be missing
 * (a build machine, a misconfigured deploy), the request may fail (the API is down), and
 * the API may answer with an error (the visitor is not signed in). None of those is a
 * reason to show an error page for a personal list.
 *
 * **The read carries the visitor's cookies, and it has to.** This runs on the Next.js
 * server, which is a different HTTP client from the browser: it has no session of its
 * own, so without `sessionHeaders()` every read here is anonymous, the API answers 401,
 * and the quiet-failure path above turns that into an empty list. The visible symptom was
 * a signed-in user's own home telling them they had no personal events while the same
 * read from the browser listed them — a failure that looks like missing data rather than
 * a missing cookie, which is what made it worth a comment.
 */
async function readPersonalEvents(): Promise<PersonalEvent[]> {
  if (!apiBaseUrl()) return [];

  try {
    const response = await api.GET("/api/personal/events", { headers: await sessionHeaders() });
    return response.data?.items ?? [];
  } catch {
    // A read that cannot be made is a read that found nothing.
    return [];
  }
}
