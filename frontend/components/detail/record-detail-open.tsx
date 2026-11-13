"use client";

/**
 * Record that this user opened this event's Detail Screen (FR-24).
 *
 * **Half of the neighbour rule had never been written.** FR-24 counts a neighbour as
 * someone who **saved _or_ opened**, and `neighbor_count.py:157-169` is a set union of
 * `SavedEvent` and `EventDetailOpen` user ids. `POST /api/events/{id}/opened` is the only
 * writer of the second, and nothing in the UI had ever called it — so the union's second
 * half contributed nothing and every neighbour count in the product was the saver count.
 *
 * The deferral was recorded and then lost. `frontend-event-detail.md:48`: *"The `opened`
 * signal is not fired… That belongs to the delivery intent."* The delivery intent never
 * took it, and `tests/ad19-endpoint-coverage.test.ts` recorded the absence honestly rather
 * than papering over it.
 *
 * **It renders nothing.** It exists for its effect, because the screen it reports on is a
 * server component and the write needs a CSRF token and a browser.
 *
 * **It never blocks the render.** The promise is not awaited by anything the user waits
 * for, and a rejection is swallowed: a neighbour signal that failed to record is not worth
 * a word on screen, and there is nothing the reader could do about it.
 *
 * **It is mounted only for a signed-in reader**, by `read.kind === "found"` — the anonymous
 * Detail Screen is `kind: "anonymous"` and the public page is a different branch entirely.
 * The endpoint answers 401 to an anonymous caller, so firing it there would be a guaranteed
 * failed request on every public page view.
 *
 * **It fires once per screen.** The effect has an empty dependency list and a ref guard:
 * React Strict Mode double-invokes effects in development, and while the endpoint is
 * idempotent per `(user, event)` — *"opening the screen again refreshes the timestamp
 * rather than adding a row"* — a doubled request is still a request we did not mean to
 * send.
 */
import { useEffect, useRef } from "react";

import { api } from "@/lib/backend-client";

export function RecordDetailOpen({ eventId }: { eventId: string }) {
  const fired = useRef(false);

  useEffect(() => {
    if (fired.current) return;
    fired.current = true;
    // **One expression, not a fluent chain split across lines.** `ad19-endpoint-coverage`
    // asserts that a caller reaches the generated client, matching `api.POST(` on the
    // comment-stripped source — and a line break between `api` and `.POST` defeats it.
    // The call site is kept contiguous so the coverage check can see it.
    const sent = api.POST("/api/events/{event_id}/opened", {
      params: { path: { event_id: eventId } },
    });
    // Deliberately silent. See the note above: there is nothing to tell the reader.
    void sent.catch(() => {});
  }, [eventId]);

  return null;
}
