"use client";

/**
 * The Detail Screen's "open the conflict prompt" signal.
 *
 * **Two islands, one prompt.** The conflict has two entrances on the Detail Screen:
 *
 *   - the **mark** in the header's trust row — a button that opens the prompt, because
 *     the choice is one tap away;
 *   - the **Save** button, whose 409 opens the same prompt.
 *
 * The header's trust row is server-rendered content — the title, the times, the badges
 * are all facts the server decided (AD-10) — and the action row is a client island that
 * owns the prompt. They are two islands, and the mark has to reach the prompt.
 *
 * **So the mark announces, and the island listens.** A `CustomEvent` on `window` is the
 * one channel that crosses an island boundary without dragging the whole page into the
 * client: the header stays a server component, the action row stays an island, and the
 * signal is a plain DOM event.
 *
 * **This is not global mutable state.** The event carries no data — it says only "open
 * the prompt", and the prompt's subject is the server's, which the island already
 * holds. There is nothing for two listeners to disagree about.
 *
 * **The event name is namespaced**, so it cannot collide with anything else on the
 * page, and the detail is namespaced with it: a second Detail Screen's island on the
 * same document would hear it too, which is why the name carries the event's id and the
 * listener checks it.
 */

/** The event's name, namespaced so it cannot collide with another library's. */
export const CONFLICT_OPEN_EVENT = "eventpulse:detail-conflict-open";

/** The detail of the event — which event's prompt to open. */
export type ConflictOpenDetail = {
  /** The catalog event's id. */
  eventId: string;
};

/**
 * Ask the prompt for one event to open.
 *
 * **The event id travels with the signal** so that an island for a *different* event
 * ignores it. A page that rendered two Detail Screens would otherwise open both.
 */
export function requestConflictOpen(eventId: string): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent<ConflictOpenDetail>(CONFLICT_OPEN_EVENT, { detail: { eventId } }),
  );
}

/**
 * Listen for the prompt to open.
 *
 * **The listener returns its own unsubscribe**, so the island can drop it when it
 * unmounts — a listener left behind would open a prompt for an event that is no longer
 * on screen.
 */
export function onConflictOpen(eventId: string, open: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const handler = (event: Event): void => {
    const detail = (event as CustomEvent<ConflictOpenDetail>).detail;
    if (!detail || detail.eventId !== eventId) return;
    open();
  };
  window.addEventListener(CONFLICT_OPEN_EVENT, handler);
  return () => window.removeEventListener(CONFLICT_OPEN_EVENT, handler);
}
