/**
 * The site's own public origin — the address a share card and a canonical link name.
 *
 * **Why this exists.** Next's metadata resolves a *relative* canonical, OG URL or OG
 * image against `metadataBase`, and without one it falls back to `http://localhost:3000`.
 * That fallback is what a crawler would then be handed: an `og:image` pointing at
 * `localhost`, and an `og:url` that is a bare path with no origin at all. A share card
 * with a `localhost` image is a card that shows nothing, and a relative `og:url` is not
 * a URL a crawler can resolve.
 *
 * **It is the site's public address, not the server's.** In a deployed environment the
 * Next.js server's own address is often an internal one — the same distinction the
 * backend's `FRONTEND_BASE_URL` (the public origin) draws against
 * `FRONTEND_REVALIDATION_URL` (the server-to-server address).
 *
 * **Read per call, never baked in.** The value comes from the environment, so a
 * deployment changes it without a rebuild — the same rule `lib/api-base-url.ts` follows
 * for the API's address.
 */
const DEV_SITE_URL = "http://127.0.0.1:3000";

/**
 * The site's public origin, or `undefined` when it is not configured.
 *
 * **In development it falls back to the local origin**, so a `next dev` on another port
 * still emits absolute URLs against the local address. **In production it returns
 * `undefined`** — and Next then emits its own warning, which is the honest outcome:
 * an unset origin is a deployment mistake, and it says so rather than guessing.
 */
export function siteUrl(): URL | undefined {
  const configured = process.env.PUBLIC_SITE_URL;
  if (configured) return new URL(configured);
  return process.env.NODE_ENV === "production" ? undefined : new URL(DEV_SITE_URL);
}
