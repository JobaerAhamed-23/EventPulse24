/**
 * The words for an event's lifecycle, in one table.
 *
 * **The vocabulary is the backend's.** `Event.Status` is `scheduled`, `postponed`,
 * `cancelled` or `superseded` (`backend/apps/ingestion/models.py`, `Event.Status`), and
 * the same four values reach the frontend as `DigestCardOut.status` and
 * `PublicEventPageOut.status`. So the *keys* here are the server's, and this file is a
 * translation of them into the words a reader sees — exactly the split
 * `lib/digest-labels.ts` already makes for the Why-this Tags and the Source Badge.
 *
 * **The public page owned these strings first, and this table is where they moved to.**
 * They lived in `public-event-page.tsx` as a module-level `STATUS_LINES` that nothing
 * could import, which meant a second surface that needed the same fact had to either
 * duplicate the sentence or not say it. The Pulse Card now needs it too, and so does the
 * city card. One table, one sentence, one place to change it.
 *
 * **`scheduled` says nothing, and `superseded` says nothing.** A scheduled event is the
 * ordinary case, and a line reading "Scheduled" tells a reader nothing they did not
 * already assume. A superseded event is one that has been *replaced* by another — the
 * reader is sent to the replacement, and there is nothing to report about the original.
 *
 * **An unrecognised status shows nothing.** A status this system has never heard of is a
 * fact the frontend cannot put into words, and a page that rendered one as "unknown"
 * would be inventing a claim about the world (ASSUMPTION-9). So `statusLineFor` returns
 * `null` for anything not in the table, and the caller renders nothing.
 *
 * **The sold-out line is separate from the status lines, because sold-out is not a
 * status.** It is a fact about the tickets, and the backend states it as its own field
 * (`is_sold_out`). An event can be sold out *and* postponed, and then both facts are
 * true — so they are two fields here too, and a caller shows both rather than choosing.
 */

/**
 * The status lines, keyed by the backend's `Event.Status` values.
 *
 * **These are sentences, not labels.** The public page put them here as full sentences
 * and they stay sentences: "Cancelled — this event is not happening." says what the
 * state means, where a bare "Cancelled" would leave the reader to work out whether the
 * event is off, moved, or merely renamed.
 */
const STATUS_LINES: Record<string, string> = {
  postponed: "Postponed — this event is not happening at the time shown.",
  cancelled: "Cancelled — this event is not happening.",
};

/**
 * A status's line, or `null` when the status has none.
 *
 * **`scheduled` and an unknown status both return `null`, and they are not the same
 * case.** One is "nothing happened" and the other is "we do not know what happened" —
 * and neither is worth a line on a card.
 */
export function statusLineFor(status: string | null | undefined): string | null {
  if (!status) return null;
  return STATUS_LINES[status] ?? null;
}

/**
 * The sold-out line.
 *
 * **The event exists; it is simply gone.** The line says so without calling it a
 * failure, which is why it is a sentence and not a badge label alone.
 */
export const SOLD_OUT_LINE = "Sold out — tickets no longer available.";

/**
 * The sold-out badge's short label.
 *
 * **This is the label, and the badge's colour is its decoration.** The badge pairs the
 * label with a chromatic glyph, so the meaning never rests on the colour alone
 * (WCAG 1.4.1) — and the label is what a screen reader announces.
 */
export const SOLD_OUT_LABEL = "Sold out";

/**
 * The state a card is in, if it is in one.
 *
 * **`status` and `is_sold_out` are two facts, and they are not exclusive.** An event
 * can be sold out *and* postponed — the tickets went and the date went with them — and
 * then both are true. So this function takes both and answers with the one that a
 * badge should show.
 *
 * **The cancellation wins, because a cancelled event is the one that has stopped
 * happening.** The other two states describe an event that still exists: a sold-out
 * one still has a date and a venue, a postponed one still has a date that will be
 * announced. A cancelled one has neither, and a badge saying "Sold out" on a cancelled
 * event would tell the reader to wait for tickets for an event that is not happening.
 *
 * **`scheduled` and `null` are both "no state".** A scheduled event is the ordinary
 * case, and `null` is the server saying it has no lifecycle to report — a personal
 * event, or a card whose catalog event is gone.
 */
export type CardState = "sold_out" | "cancelled" | "postponed";

/**
 * The badge state for a card, or `null` when the card is in no state worth a badge.
 *
 * **An unrecognised status shows nothing**, for the same reason `statusLineFor` returns
 * `null` for one: the frontend cannot put a word to a state it does not know, and
 * guessing would be inventing a fact about the world (ASSUMPTION-9).
 */
export function cardStateFor(
  status: string | null | undefined,
  isSoldOut: boolean | null | undefined,
): CardState | null {
  if (status === "cancelled") return "cancelled";
  if (status === "postponed") return "postponed";
  if (isSoldOut) return "sold_out";
  return null;
}

/**
 * The badge's visible label for each state.
 *
 * **These are the backend's words, shortened.** The full sentences — "Cancelled — this
 * event is not happening." — are above, and they are the *line* a surface renders when
 * it has room for a sentence. A badge is a pill, and a pill holds a label, not a
 * sentence.
 *
 * **They live here, not in the badge component, because two surfaces need them.** The
 * badge renders one, and the card's accessible name renders one, and those two must be
 * the same word — a card whose link says "Sold out" while its badge says "Tickets gone"
 * is describing one fact in two vocabularies.
 */
export const STATE_LABELS: Record<CardState, string> = {
  sold_out: SOLD_OUT_LABEL,
  cancelled: "Cancelled",
  postponed: "Postponed",
};

