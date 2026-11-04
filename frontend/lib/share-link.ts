/**
 * The one place a **public event URL** is built (FR-28).
 *
 * **Why a module for one string.** The URL is built on two surfaces — the Pulse Card
 * and the Detail Screen — and they must produce the *same* URL, or a friend who opens
 * one is on a different page from a friend who opens the other. Two copies of a string
 * concatenation are two URLs waiting to drift.
 *
 * **What the URL is.** `{origin}/events/{slug}` — the FR-26 public page's own address.
 * **No query parameter, no fragment, no token, no second shape.** A `?shared_by=…`
 * variant would be a second URL for one document, and the public page's canonical is
 * `/events/{slug}` — so the variant would be a URL the page does not canonicalise to,
 * and a crawler that fetched it would record two documents.
 *
 * **Why the origin is a parameter and not read here.** `PUBLIC_SITE_URL` has no
 * `NEXT_PUBLIC_` prefix, so **a client component cannot read it** — the server resolves
 * it (`lib/site-url.ts`) and passes it down. And `siteUrl()` returns `undefined` in
 * production when the origin is unset, in which case the caller's fallback is the
 * browser's own origin: the origin the user is actually looking at, which is never
 * wrong for the person receiving the link.
 *
 * **This module is pure.** No environment, no `window`, no browser. It takes the origin
 * it is given and returns a string.
 */

/**
 * The public page's URL for an event.
 *
 * **The slug is the event's, and never its id.** `/events/{uuid}` is the *signed-in*
 * Detail Screen — a friend who opened it would meet a sign-in wall instead of the
 * event. That mistake is the one this function exists to make impossible.
 *
 * **The origin falls back to a relative path** when none is given. A relative path is
 * honest — it names the right document — and the caller that has a browser origin
 * resolves it before calling.
 *
 * @param slug The event's minted public slug.
 * @param origin The site's public origin, or `null`/`undefined` when it is not known.
 */
export function publicEventUrl(slug: string, origin?: string | null): string {
  const path = `/events/${slug}`;
  if (!origin) return path;
  return `${origin.replace(/\/+$/, "")}${path}`;
}

/**
 * The origin to share under, from whatever the caller can see.
 *
 * **The configured origin wins; the browser's origin is the fallback.** The configured
 * one is the site's public address — the same origin the canonical link and the
 * Open Graph URL resolve against, so the shared URL and the page's own canonical cannot
 * disagree. The browser's own origin is the address the user is actually at, which is
 * the right answer when the deployment has not set one.
 *
 * @param origin The origin the server resolved, or `null` when it could not.
 */
export function shareOrigin(origin?: string | null): string | null {
  if (origin) return origin.replace(/\/+$/, "");
  if (typeof window === "undefined") return null;
  return window.location.origin;
}
