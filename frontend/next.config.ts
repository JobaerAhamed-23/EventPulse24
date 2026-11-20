import type { NextConfig } from "next";

/**
 * The city page's public URL is `/events-in-{slug}`, and Next.js has **no native
 * prefixed dynamic segment**.
 *
 * **What was measured, not inferred.** `app/events-in-[slug]/page.tsx` builds without
 * complaint and is registered in the build's `routes-manifest.json` under
 * **`staticRoutes`** — with the regex `^/([^/]+?)(?:/)?$` and the parameter named
 * `nxtPslug`. The request for `/events-in-brooklyn` answers **404**, and so does a
 * request for `/anything-else`: the route matches any single root segment and none of
 * them resolve.
 *
 * **Why.** Next's own `shared/lib/router/utils/get-segment-param.js` recognises a
 * segment only when it *is* a param (`segment.startsWith("[") && segment.endsWith("]")`),
 * so `events-in-[slug]` returns `null` and the segment is classified **static**. But
 * `route-regex.js`'s `PARAMETER_PATTERN` *does* accept a literal prefix — which is why
 * the regex says `^/([^/]+?)$` while the parameter machinery says "not a param". The
 * matching half and the parameter half of the router disagree, and the parameter half
 * wins: no `params.slug` ever arrives.
 *
 * **So the public URL is preserved by a rewrite, and the internal segment is a normal
 * dynamic one.** The route lives at `app/events-in/[slug]/page.tsx`.
 *
 * **The redirect is load-bearing, not cosmetic.** Without it the page is served at *two*
 * URLs, and a URL that forks after ranking splits the ranking across two copies — the
 * mirror of the failure mode this route exists to avoid ("a URL that vanishes after
 * ranking throws away every bit of ranking it earned"). A canonical link tag alone does
 * not fix it: a crawler follows links, and the internal URL is a real, reachable,
 * indexable document.
 *
 * **Measured against a running production server:**
 *
 * | Request | Result |
 * |---|---|
 * | `/events-in-brooklyn` | **200**, `params.slug === "brooklyn"` |
 * | `/events-in-brooklyn?page=2` | **200**, `searchParams.page === "2"` — the query survives |
 * | `/events-in/brooklyn` | **308 → `/events-in-brooklyn`** — one canonical URL |
 * | `/events-in/brooklyn?page=2` | **308 → `/events-in-brooklyn?page=2`** — the query is preserved |
 * | `/events-in-brooklyn/extra` | **404** — the rewrite's `([^/]+?)` does not span a slash |
 *
 * ## The profile picture needs no `images.remotePatterns`
 *
 * **The avatar is served from the frontend's own origin**, so there is no remote host to
 * allowlist — and `next/image`'s optimizer is not used at all.
 *
 * **What was measured, not inferred.** `me` hands out `/api/auth/profile/avatar/{version}`
 * — an app-owned path on the frontend's origin, which answers **302** to a freshly
 * minted presigned URL. The disc renders a plain `<img src={avatarUrl}>`, not
 * `next/image`, and `components/shell/avatar-disc.tsx` carries the reasoning.
 *
 * **Two things follow, and both are why the optimizer would not help.**
 *
 * 1. **There is no remote host to configure.** `remotePatterns` exists to tell the
 *    optimizer which off-origin hosts it may fetch from; the URL the page carries is
 *    same-origin, so there is nothing to allow.
 * 2. **The optimizer cannot optimize a URL that is a redirect to a signature that
 *    expires.** The URL in the HTML never carries a signature — the browser follows the
 *    302 under it and the signature is minted per request — so there is no stable,
 *    cacheable asset for the optimizer to work on. The 302 *is* the cache-busting
 *    strategy, and the `{version}` segment in the path is the version.
 */
const nextConfig: NextConfig = {
  async rewrites() {
    return [{ source: "/events-in-:slug", destination: "/events-in/:slug" }];
  },
  async redirects() {
    return [{ source: "/events-in/:slug", destination: "/events-in-:slug", permanent: true }];
  },
};

export default nextConfig;
