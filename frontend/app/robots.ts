import type { MetadataRoute } from "next";

import { siteUrl } from "@/lib/site-url";

/**
 * `/robots.txt` — the crawl policy for the site's public surface.
 *
 * **The public surface is allowed, and the authed and dev prefixes are not.** A crawler
 * that follows the site's own rules spends its budget on the pages a reader could
 * reach. The authed prefixes are the ones where a crawl buys nothing: the reader would
 * be sent to a sign-in, and the crawler would record the sign-in as the page's content.
 *
 * **`/events` is deliberately *not* disallowed.** `/events/{minted-slug}` is the public
 * event page and it must be crawled — it is the whole point of a sitemap. The authed
 * branch of the same path (`/events/{uuid}`, the signed-in Detail Screen) is excluded by
 * **its own page's metadata** instead: `app/events/[id]/page.tsx` answers the Detail
 * Screen branch with `robots: { index: false, follow: false }`.
 *
 * **Why robots.txt cannot do that half, and why the half it can do is not enough.**
 * robots.txt has no path regular expression — the only wildcards are `*` (any run of
 * characters) and `$` (the end of a path). So:
 *
 * - `Disallow: /events/` would exclude the **public** event pages along with the authed
 *   branch;
 * - `Allow: /events/` would admit the authed branch, because the two branches share one
 *   path segment — one route, two pages (`lib/event-identifier.ts`).
 *
 * **The two halves together are the policy.** robots.txt keeps the crawler's *budget*
 * off the authed prefixes, and the Detail Screen's own `<meta name="robots">` keeps the
 * *document* out of the index. Either alone leaves a hole: robots.txt alone would let a
 * crawler index a sign-in redirect, and the metadata alone would let the crawler spend
 * its budget fetching pages it may not keep.
 */

/**
 * **`force-dynamic`, and the reason is the origin.**
 *
 * Next prerenders a metadata route that uses no dynamic API, and a prerendered
 * `robots.txt` is a file written **at build time** — so the `Sitemap:` line would be
 * built from whatever `PUBLIC_SITE_URL` happened to be during the build, and a
 * deployment that set it later would serve a file naming the wrong origin. The sitemap's
 * address has to be the one the running site is served from, so the file is rendered per
 * request.
 *
 * **This matches the rest of the site's origin handling.** `app/layout.tsx`'s
 * `metadataBase` is the same `siteUrl()`, and Next reads it at build time too — so the
 * two agree by construction rather than by coincidence.
 */
export const dynamic = "force-dynamic";

export default function robots(): MetadataRoute.Robots {
  const origin = siteUrl();

  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        // **The authed and dev prefixes, as whole prefixes.** A `Disallow: /settings`
        // excludes `/settings` and everything under it, which is what a prefix rule
        // means.
        disallow: ["/settings", "/timeline", "/conflicts", "/onboarding", "/dev"],
      },
    ],
    // **The sitemap is pointed at.** The origin is the site's public origin, not the
    // server's — `siteUrl()` reads `PUBLIC_SITE_URL`, so a deployment changes it
    // without a rebuild.
    //
    // **An unset origin in production omits the line rather than pointing at
    // `localhost`.** `siteUrl()` returns `undefined` there, and a `Sitemap:` line
    // naming `http://localhost:3000/sitemap.xml` would send every crawler to a
    // machine that is not this one. An absent line is honest; a wrong one is not.
    ...(origin ? { sitemap: new URL("/sitemap.xml", origin).toString() } : {}),
  };
}
