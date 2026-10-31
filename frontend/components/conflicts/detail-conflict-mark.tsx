"use client";

/**
 * The Detail Screen's conflict mark: the **same glyph** the Pulse Card draws, as a
 * button that opens the prompt.
 *
 * **It is a client component for one reason**: the button's `onClick`. The mark itself
 * is `ConflictIndicatorButton` — the very component the Pulse Card's non-interactive
 * mark is drawn from — so the two surfaces cannot drift apart in size, colour or shape.
 *
 * **The Detail Screen's header is server-rendered content.** The title, the times and
 * the badges are facts the server decided (AD-10), and the prompt lives in a client
 * island further down the page. So the mark does not hold the prompt's state; it
 * **announces** that the prompt should open, and the island listens.
 *
 * **The event id travels with the signal**, so an island for a different event ignores
 * it. See `lib/conflict-open.ts` for why a DOM event is the channel.
 */
import { ConflictIndicatorButton } from "@/components/conflicts/conflict-indicator";
import { requestConflictOpen } from "@/lib/conflict-open";

export function DetailConflictMark({ eventId }: { eventId: string }) {
  return (
    <ConflictIndicatorButton
      onOpen={() => requestConflictOpen(eventId)}
      label="Schedule conflict. Choose how to handle it."
    />
  );
}
