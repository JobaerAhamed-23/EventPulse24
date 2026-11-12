/**
 * The words for Browse's server-stated facts.
 *
 * **The server states the fact; the client speaks the user's language.** The API sends
 * numbers — a quota's `used` and `cap`, a reset measured in *seconds*, a window's
 * `total` — and it does not send a sentence. This file is the translation from one to
 * the other, and it is deliberately conservative: **every number it renders is a number
 * the payload carried**, and nothing is inferred.
 *
 * **Two rules that the mockup does not follow, because the mockup's numbers are a
 * persona's.**
 *
 * 1. **The reset is a duration, not a clock time.** The API sends
 *    `resets_in_seconds`, so the note says *"resets in 8h"*. The mockup says *"resets
 *    8:00 AM"* — a wall-clock claim the payload does not carry, and one that would be
 *    wrong for every user but the persona it was drawn for. This is the same rule the
 *    city page followed when it worded its count to the payload rather than to the
 *    mockup: **the payload wins.**
 * 2. **A card does not say "Free."** The payload carries no price, so the card says
 *    nothing about one. Inventing a price is a fact the frontend does not have.
 */

/**
 * The save allowance, in words.
 *
 * **A Pro account has `cap: null`** — not a very large number. FR-48's consequence is
 * that a Pro user has no soft wall at all, and a cap of "infinity" is a number a client
 * would eventually render into the hero.
 */
export type QuotaNote = {
  /** The whole line, e.g. "Free plan: 0 of 1 save used today · resets in 8h". */
  text: string;
  /** True when the account has no cap at all. */
  isPro: boolean;
};

/**
 * The quota note, as the hero renders it.
 *
 * **The reading of the quota, not a decision.** The API reports the allowance without
 * spending it — the gate is a different call — so this note is a sign above the gate,
 * not the gate. The client never refuses a save on the strength of this string.
 */
export function quotaNote(quota: {
  used: number;
  /** `null` for a Pro account; the field is optional in the schema. */
  cap?: number | null;
  is_pro: boolean;
  resets_in_seconds: number;
}): QuotaNote {
  if (quota.is_pro || quota.cap === null || quota.cap === undefined) {
    // A Pro account has no wall to report. Saying "unlimited saves" would be a claim the
    // payload does not make, and so would saying "∞ of ∞".
    //
    // **A missing `cap` is the same as a null one.** The schema makes the field optional
    // and Django Ninja omits it when it is null, so "absent" and "explicitly null" are
    // the same answer arriving by two routes.
    return { text: "Pro plan · no save limit", isPro: true };
  }

  const used = Math.max(0, quota.used);
  const cap = Math.max(0, quota.cap);
  const saves = cap === 1 ? "save" : "saves";
  const head = `Free plan: ${used} of ${cap} ${saves} used today`;
  return { text: `${head} · resets in ${resetPhrase(quota.resets_in_seconds)}`, isPro: false };
}

/**
 * The Save button's own label when the allowance is spent.
 *
 * **"1 of 1 used today" — the allowance, in the button's own words.**
 *
 * **The number is the payload's.** The cap is `quota.cap` and the used count is
 * `quota.used`, so if the tier's ceiling ever changed, this would say so. The plural is
 * the same rule `quotaNote()` follows: one save is "save", more are "saves".
 *
 * **The reset time is not in this label.** The button's label is a state, not a status
 * line — it is small, it sits on a card, and the hero already carries the full note
 * ("Free plan: 1 of 1 save used today · resets in 24h"). Saying it twice on one page
 * would be the same fact in two places, and the two could disagree.
 */
export function spentQuotaLabel(quota: {
  used: number;
  /** `null` for a Pro account; the field is optional in the schema. */
  cap?: number | null;
}): string {
  const used = Math.max(0, quota.used);
  const cap = Math.max(0, quota.cap ?? 0);
  const saves = cap === 1 ? "save" : "saves";
  return `${used} of ${cap} ${saves} used today`;
}

/**
 * A duration, in the phrase a person would use.
 *
 * **Hours, and a day when it is a day.** A quota window is 24 hours, so the note almost
 * always says "in 24h". Minutes are for a window shorter than an hour and seconds for
 * one shorter than a minute, because "in 0h" is not a thing anyone says.
 */
export function resetPhrase(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  if (total < 60) return `${total}s`;
  const minutes = Math.floor(total / 60);
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  // **A day reads as "24h", not "1d".** The quota window is exactly 24 hours, so "1d"
  // would be the phrase for *every* user and would hide the number the payload carries.
  // Days only take over past a day.
  if (hours <= 24) return `${hours}h`;
  const days = Math.floor(hours / 24);
  return `${days}d`;
}

/**
 * The "N events" count, in words.
 *
 * **The number is the pool's size, and the pool is what the user can page to.** It is
 * not a `COUNT(*)` — the server's staleness bound is applied in Python, so a SQL count
 * would include events the filter then drops, and the count would advertise a number no
 * amount of scrolling arrives at. The word says "events", not "events this week", because
 * the window is *tonight + 7 days* and that is what the eyebrow already says.
 */
export function eventCountLabel(total: number): string {
  return total === 1 ? "1 event" : `${total} events`;
}

/**
 * The section head's meta: "Brooklyn · Thu, Aug 27".
 *
 * **The date is the window's first day, in the user's own zone.** The window opens
 * tonight in the user's zone — the server cut it there — so the date shown is the local
 * date the window starts on. Reading it in UTC would name the previous day for anyone
 * west of Greenwich in the evening, which is the whole reason the window is a local idea.
 */
export function windowDateLabel(windowFrom: string, zone: string): string {
  const instant = new Date(windowFrom);
  if (Number.isNaN(instant.getTime())) return "";

  // **An unusable zone is not a crash.** `Intl` throws a `RangeError` on a malformed
  // `timeZone`, and the payload's `timezone` is a string the server wrote — a typo or a
  // zone the runtime does not know would take the whole page down over a label. The
  // label is decoration on a mono meta line; the honest fallback is the date in UTC.
  let parts: Intl.DateTimeFormatPart[];
  try {
    parts = new Intl.DateTimeFormat("en-US", {
      timeZone: zone || "UTC",
      weekday: "short",
      month: "short",
      day: "numeric",
    }).formatToParts(instant);
  } catch {
    parts = new Intl.DateTimeFormat("en-US", {
      timeZone: "UTC",
      weekday: "short",
      month: "short",
      day: "numeric",
    }).formatToParts(instant);
  }

  const value = (type: Intl.DateTimeFormatPartTypes): string =>
    parts.find((part) => part.type === type)?.value ?? "";
  const weekday = value("weekday");
  const month = value("month");
  const day = value("day");
  if (!weekday || !month || !day) return "";
  return `${weekday}, ${month} ${day}`;
}

/**
 * The stripe's meaning, in words.
 *
 * **Colour is never the only carrier** (WCAG 1.4.1). The server sends a `stripe` of
 * `"public"` or `"must_know"`; the card's kicker says which in letters.
 *
 * **Two stripes, two words — and no third.** Amendment A-12 caps the stripes at two
 * colours and drops the discovery stripe outright, so an unrecognised stripe falls back
 * to the public treatment rather than inventing a third one.
 */
export function stripeLabel(stripe: string): string {
  return stripe === "must_know" ? "Must-know" : "Public";
}

/**
 * The stripe's colour utility.
 *
 * **Slate for public, amber for must-know — and nothing else.** The discovery stripe is
 * dropped by Amendment A-12, so the fallback is slate: a card with an unrecognised
 * stripe is a public card, not a card in a third colour.
 */
export function stripeColour(stripe: string): string {
  return stripe === "must_know" ? "bg-accent-amber" : "bg-accent-slate";
}
