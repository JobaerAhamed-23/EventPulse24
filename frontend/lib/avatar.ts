/**
 * The initials treatment — **the fallback for an account with no picture.**
 *
 * ## Why this is one module
 *
 * **The rule was going to be pasted into three places.** The disc is drawn in the
 * sidenav's account row, in the bottom bar's More sheet and in the account sheet — and
 * each of them needs "what do I show when there is no picture". Three copies of that
 * rule is three places for it to differ from itself in, silently, and the difference
 * would be a *picture* difference: one rail with two letters and another with one.
 *
 * **This module is the one copy.** It sits beside `lib/display-name.ts` and answers the
 * same question the same way: the display name is the input, and the display name is
 * never blank.
 *
 * ## The rule
 *
 * - **One letter per word, at most two.** `"Maya Ahmed"` → `"MA"`. A disc is 32px
 *   across; three letters do not fit legibly, and a rule that grew to fit the widest
 *   name would be a rule nobody could predict.
 * - **The letters come from the *first* word and the *second* word**, not from the first
 *   two characters. `"Mary-Jane Watson"` → `"MW"`, not `"MA"`. A hyphen is part of one
 *   word; splitting it would give `"MJ"` for a person whose name starts with `M` and
 *   `J`.
 * - **The letters are upper-case.** The disc is a small, quiet mark, and a name's own
 *   casing is not what it is there to show.
 * - **It is never empty.** A display name is never empty — `displayName` derives one
 *   from the address when no name is stored — so the initials always have something to
 *   work from. **But the function is written to survive an empty input anyway**, because
 *   a disc with nothing in it is a hole in the rail, and a rule that cannot produce one
 *   is better than a rule that can.
 *
 * ## It is server-safe, and deliberately so
 *
 * **This module imports nothing** — no `next/headers`, no `api`, no client code, no
 * `react`. It can be imported by a server component, a client component or a test, and
 * it must **not** carry a `"use client"` banner.
 *
 * **The store that goes with it is a separate module** — `lib/avatar-store.ts` — for
 * the same reason `lib/session-name.ts` is a module of its own: the rule is a pure
 * function and belongs to anyone, while the store is React plumbing and belongs to the
 * client.
 */

/**
 * The initials for a display name — **at most two letters, never empty.**
 *
 * @param name The display name. Never blank in the product, and blank-safe here.
 */
export function initials(name: string): string {
  // **The words, split on whitespace.** A name is a sequence of words separated by
  // spaces; anything inside a word — a hyphen, an apostrophe, a period — is part of the
  // word and does not start a new one.
  const words = name.trim().split(/\s+/).filter(Boolean);

  // **A blank name yields a blank disc, and a blank disc is a hole in the rail.** The
  // product never asks this of an empty name, but the function answers for one anyway:
  // the absence of letters is stated rather than rendered.
  if (words.length === 0) return "";

  // **One letter per word, at most two words.** `charAt(0)` on a word that has at least
  // one character — the filter above removed the empty ones, so `charAt(0)` is never
  // `""`.
  const letters = words.slice(0, 2).map((word) => word.charAt(0).toUpperCase());
  return letters.join("");
}
