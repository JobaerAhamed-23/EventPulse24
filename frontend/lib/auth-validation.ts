/**
 * The client-side checks on the auth forms, and the locked words they use.
 *
 * `EXPERIENCE.md` §"Auth-error copy bank" locks these strings: "mockups + engineering
 * must use these verbatim". They are the three checks the browser can make on its own —
 * the shape of an address, the length of a password, and whether two passwords match.
 * Everything else is the API's verdict and the API's wording (`lib/api-errors.ts`).
 *
 * Two strings from that bank are deliberately **absent**: "An account with that email
 * already exists. Sign in →" and "We don't see an account with that email." Both name
 * whether an account exists, which AD-18 and this work item forbid the UI from saying —
 * and the API cannot produce either, because sign-up answers identically for a new and a
 * taken address. A copy bank written before the enumeration rule was settled does not
 * outrank the rule.
 */

/** "Invalid email format" (`/signup`, and the same check on `/signin`). */
export const EMAIL_INVALID = "That doesn't look like a valid email address.";

/** "Password too short (< 8 chars)". */
export const PASSWORD_TOO_SHORT = "Use at least 8 characters.";

/** "Passwords don't match" — the one cross-field check. */
export const PASSWORDS_DONT_MATCH = "Passwords don't match.";

/** The shortest password the backend's `MinimumLengthValidator` accepts. */
export const MIN_PASSWORD_LENGTH = 8;

/**
 * Whether this looks like an address worth sending.
 *
 * The check is deliberately loose: one `@`, something either side, a dot in the domain,
 * no spaces. The browser cannot know whether an address exists, and a stricter pattern
 * rejects valid addresses — the server, which can actually fail the send, has the final
 * say. This only catches the typo before a round trip.
 */
export function isEmailLike(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
}
