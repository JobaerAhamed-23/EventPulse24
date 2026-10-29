import { api } from "@/lib/backend-client";

import { PersonalEventsPanel } from "@/components/personal-events-panel";

/**
 * The personal-events section: a **server** component that reads the user's own events
 * and hands them to the client island that owns the flow.
 *
 * The stack is "server components + the generated API client" (AD-19), so the *read*
 * happens on the server and the *write* happens in the client island. The list is a
 * server read; the sheets are client components.
 *
 * The read is allowed to fail quietly: a signed-out visitor sees an empty list rather
 * than an error page, because the personal surface is session-based by design (AD-12)
 * and "you have no personal events" is a true statement about that visitor.
 */
export async function PersonalEventsSection() {
  const response = await api.GET("/api/personal/events");
  const events = response.data?.items ?? [];

  return <PersonalEventsPanel events={events} />;
}
