/**
 * The name to address somebody by — **the stored name if there is one, the address
 * otherwise.**
 *
 * ## Why this is one module and not fifteen
 *
 * **The rule was copy-pasted into fifteen files.** Each copy was the same five lines:
 * take the email's local part, split it on `.`, `_` and `-`, capitalise each word, join
 * them with spaces. `maya.ahmed@example.test` became `"Maya Ahmed"`.
 *
 * **Then the account grew a name, and the rule grew a half.** *"The stored name if
 * there is one, otherwise the address"* is a rule with two branches — and a rule with
 * two branches that is pasted fifteen times is a rule that can differ from itself in
 * fifteen places, silently. **This module is the one copy.**
 *
 * ## The two branches
 *
 * - **A stored name wins, verbatim.** Not trimmed, not re-cased, not split on
 *   anything. **A person's name is theirs** — the display rule for the *email* exists
 *   because an address has no capitals, not because names should be capitalised.
 * - **Otherwise the address is derived**, by the rule the copies used, carried over
 *   **byte for byte**. That is the point: **no existing screen changes appearance** for
 *   anyone who has not set a name. Not "close enough" — *the same function*, and a
 *   test pins it.
 *
 * ## Why it takes the whole user
 *
 * `displayName(user)` rather than `displayName(name, email)`. **The rule is "the stored
 * name if there is one, otherwise the address"**, and one object makes it impossible to
 * pass the two in the wrong order — which is the kind of mistake two positional
 * arguments invite.
 *
 * ## It is server-safe, and deliberately so
 *
 * **This module imports nothing** — no `next/headers`, no `api`, no client code. It
 * can be imported by a server component, a client component or a test, and it must
 * **not** carry a `"use client"` banner.
 */
export function displayName(user: { name: string; email: string }): string {
  // **The stored name, exactly as the account holds it.**
  //
  // **The emptiness check is `name === ""`, not a trim.** The backend trims on write,
  // so a stored name is already trimmed. A whitespace-only name is not a name, and
  // trimming here would be the right thing to do — but **trimming must not become
  // re-casing**: a stored name is shown as it is.
  if (user.name !== "") return user.name;

  // **The address's local part, derived by the rule the copies used.**
  //
  // **This is the old function, verbatim.** The empty-local-part case returns the
  // email itself, because there is nothing else to call somebody.
  const local = user.email.split("@")[0] ?? user.email;
  const words = local.split(/[._-]+/).filter(Boolean);
  if (words.length === 0) return user.email;
  return words.map((word) => word.charAt(0).toUpperCase() + word.slice(1)).join(" ");
}
