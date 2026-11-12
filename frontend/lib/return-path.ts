/**
 * Where a visitor goes after they sign in — the `next` parameter (FR-48).
 *
 * **Why this exists.** The pricing page is public, so a signed-out visitor reads it and
 * can choose a plan. Choosing a plan routes them to sign-in — and if sign-in then drops
 * them at the digest home, the intent they had ("I want to buy Pro") is gone, and the
 * pricing page has to be found again. So the sign-in route carries a return path.
 *
 * **The guard is the whole point of this module.** A `next` parameter taken from the
 * query string and used as a redirect target is the classic open redirect: a crafted
 * link like `/signin?next=https://attacker.example/steal` sends a visitor who has just
 * typed their password to somebody else's site — with the session cookie's referrer
 * trail behind them, and with the site's own domain lending its credibility.
 *
 * So the path is accepted only if it is **a path on this site**:
 *
 *   - it must start with a single `/` — a relative path, not an absolute URL;
 *   - it must not start with `//` — which is a protocol-relative URL (`//evil.example`
 *     is a *host*, not a path, and browsers read it as one);
 *   - it must not contain a backslash — `\` and `/` are interchangeable to some
 *     browsers, so `/\evil.example` is another spelling of the same attack;
 *   - it must not contain a scheme — `javascript:` and `data:` are not paths, and
 *     `javascript:` in a redirect target is a script injection.
 *
 * Everything else falls back to `/`. **A rejected `next` is not an error** — it is a
 * visitor who gets the ordinary sign-in and lands where they would have landed anyway.
 */
const DEFAULT_RETURN_PATH = "/";

/**
 * The path to send the visitor to after they sign in.
 *
 * **Returns `"/"` for anything that is not plainly a path on this site.** The fallback is
 * the ordinary home, so a hostile or malformed `next` changes nothing about where the
 * visitor ends up.
 */
export function returnPath(next: string | null | undefined): string {
  if (typeof next !== "string") return DEFAULT_RETURN_PATH;

  const candidate = next.trim();
  if (candidate === "") return DEFAULT_RETURN_PATH;

  // A relative path only. `//host` and `/path` both start with `/`, so the host form is
  // ruled out first.
  if (!candidate.startsWith("/")) return DEFAULT_RETURN_PATH;
  if (candidate.startsWith("//")) return DEFAULT_RETURN_PATH;

  // `\` and `/` are interchangeable to some browsers, so `/\evil.example` would slip
  // past the check above.
  if (candidate.includes("\\")) return DEFAULT_RETURN_PATH;

  // A scheme is not a path. `javascript:alert(1)` would otherwise be a "relative path"
  // under the checks above.
  if (/^[a-z][a-z0-9+.-]*:/i.test(candidate)) return DEFAULT_RETURN_PATH;

  return candidate;
}

/**
 * The sign-in URL that returns the visitor to `path`.
 *
 * **The path is encoded, so it cannot break out of the query string.** A path carrying a
 * `?` or a `#` — `/pricing?plan=yearly` — survives the round trip intact rather than
 * becoming a second parameter of the sign-in URL.
 */
export function signInUrl(path: string): string {
  return `/signin?next=${encodeURIComponent(path)}`;
}

export { DEFAULT_RETURN_PATH };
