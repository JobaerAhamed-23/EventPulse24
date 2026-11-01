/**
 * The Reminder Plan's slot vocabulary — the four named tiers and the custom slot's
 * grammar, **read from the server's own rules**.
 *
 * **The client does not own this list; the server does.** `shared/constants.py` names
 * the four tiers, the custom-slot prefix and the custom-slot bounds, and
 * `apps/delivery/services/slots.py` validates against them. This module mirrors those
 * names so the picker can render the four chips — but the **validation is the server's**,
 * and this module deliberately does not clamp an out-of-range custom slot into range.
 * The server's refusal is surfaced inline instead (FR-9: "the server's bound is surfaced
 * as an inline message, not a silent clamp").
 *
 * **Why the names are duplicated at all.** The chips are a fixed set of four, and the
 * picker must render them before the plan has been read. There is no endpoint that
 * returns "the slot vocabulary", so the four names are a constant of the product — the
 * same kind of constant as `EXPERIENCE.md`'s "Remind me:" label.
 *
 * **The chip's visible label is the tier's id, not a sentence.** `5d`, `2d`, `1d`, `1hr`
 * are the labels the work item names, and they are also the ids the API stores. A chip
 * whose label and its stored id could drift apart would be a chip that saves the wrong
 * thing — so the label **is** the id.
 */

/** The four named tiers, in the order the picker shows them. */
export const SLOT_IDS = ["5d", "2d", "1d", "1hr"] as const;

/** One of the four named tiers. */
export type SlotId = (typeof SLOT_IDS)[number];

/**
 * The chip's visible label — **the tier's id**.
 *
 * The work item names the chips "5d / 2d / 1d / 1hr", and the mockup's marker circles
 * carry the same two characters (`5d`, `2d`, `1d`, `1h`). The `1hr` spelling is the
 * server's, so it is the one the chip uses.
 */
export const SLOT_LABELS: Record<SlotId, string> = {
  "5d": "5d",
  "2d": "2d",
  "1d": "1d",
  "1hr": "1hr",
};

/**
 * The accessible name of a chip — what a screen reader reads for it.
 *
 * **The visible label is an abbreviation, and an abbreviation is not a sentence.** "1hr"
 * on its own reads as "one hour" only if the reader already knows what a reminder slot
 * is. The `aria-label` says it plainly — "1 hour before" — so the control is announced
 * as what it does.
 */
export const SLOT_NAMES: Record<SlotId, string> = {
  "5d": "5 days before",
  "2d": "2 days before",
  "1d": "1 day before",
  "1hr": "1 hour before",
};

/**
 * The custom slot's prefix.
 *
 * **The server's prefix, exactly.** `custom:90` is 90 minutes before the event, and the
 * prefix is part of the stored id — so a client that spelled it differently would save
 * a slot the server refuses.
 */
export const CUSTOM_SLOT_PREFIX = "custom:";

/**
 * The custom slot's bounds, in minutes before the event.
 *
 * **The server's bounds, mirrored — and deliberately not enforced here.** 15 minutes is
 * the earliest a custom reminder can be, and 43 200 minutes (30 days) is the latest.
 * The picker *offers* the bound in the input's own hint, and it *shows* the server's
 * refusal when one is given — but it does not clamp the value into the range first.
 *
 * **A silent clamp is a lie about what was saved.** If the user types 5 and the client
 * quietly sends 15, the plan says "15 minutes before" and the user asked for 5. If the
 * client sends 5 and the server refuses, the user is told, and the input still holds
 * what they typed so they can fix it. The refusal is the honest path, and it is the
 * one the work item asks for.
 */
export const CUSTOM_SLOT_MIN_MINUTES = 15;
export const CUSTOM_SLOT_MAX_MINUTES = 43_200;

/** The most slots a plan may carry — the server's bound. */
export const MAX_SLOTS = 4;

/** The most custom slots a plan may carry — the server's bound. */
export const MAX_CUSTOM_SLOTS = 1;

/**
 * The custom slot's id, for a number of minutes.
 *
 * `customMinutes(90)` is `"custom:90"`. The minutes are **not** clamped — see
 * `CUSTOM_SLOT_MIN_MINUTES` — because the id is built from what the user typed and the
 * server decides whether it is acceptable.
 */
export function customMinutes(minutes: number): string {
  return `${CUSTOM_SLOT_PREFIX}${minutes}`;
}

/**
 * Whether a slot id is one of the four named tiers.
 */
export function isNamedSlot(slot: string): slot is SlotId {
  return (SLOT_IDS as readonly string[]).includes(slot);
}

/**
 * Whether a slot id is a custom slot.
 *
 * **The shape, not the validity.** `custom:abc` is a custom slot by shape and an
 * invalid one by value — and the two questions are asked at different times. The picker
 * asks the shape question to decide *how to render* a slot; the server answers the
 * validity question.
 */
export function isCustomSlot(slot: string): boolean {
  return slot.startsWith(CUSTOM_SLOT_PREFIX);
}

/**
 * The minutes of a custom slot id, or `null` when the id is not a custom slot with an
 * integer offset.
 *
 * **A malformed id is `null`, not a guess.** `custom:abc` has no minutes, and
 * rendering "0 minutes before" for it would say something false about a slot the
 * server has stored.
 */
export function customSlotMinutes(slot: string): number | null {
  if (!isCustomSlot(slot)) return null;
  const raw = slot.slice(CUSTOM_SLOT_PREFIX.length);
  if (!/^\d+$/.test(raw)) return null;
  const minutes = Number(raw);
  return Number.isSafeInteger(minutes) ? minutes : null;
}

/**
 * A custom slot's visible label — "30 minutes before".
 *
 * **The label is a sentence, because the chip's own id is not one.** A custom slot has
 * no fixed two-character marker, so the chip says what it is. One hour is spelled "1
 * hour" rather than "60 minutes", because "60 minutes before" reads like a data dump
 * where "1 hour before" reads like a product.
 */
export function customSlotLabel(slot: string): string {
  const minutes = customSlotMinutes(slot);
  if (minutes === null) return "Custom";
  if (minutes === 60) return "1 hour before";
  if (minutes === 120) return "2 hours before";
  if (minutes < 60) return `${minutes} minutes before`;
  if (minutes % 60 === 0) return `${minutes / 60} hours before`;
  if (minutes % 1440 === 0) return `${minutes / 1440} days before`;
  return `${minutes} minutes before`;
}
